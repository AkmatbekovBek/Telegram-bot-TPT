# handlers/roulette/handlers.py
import asyncio
import random
import re
import logging
from datetime import datetime
from typing import List, Dict, Tuple
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import BadRequest
from sqlalchemy import text, func

from database.crud import UserRepository, RouletteRepository
from database.models import DailyBonusLog
from handlers.modroul.roulette_logs import RouletteLogger
from .game_stats_updater import GameStatsUpdater
from .gif_manager import RouletteGIFManager
from ..donate.config import SUPPORT_USERNAME
from ..record import RecordCore, RecordService

logger = logging.getLogger(__name__)

# Локальные импорты из модульной структуры
from .config import CONFIG
from .state_manager import state_manager
from .models import Bet, UserBetSession, ChatSession, SessionManager
from .validators import BetValidator, BetParser, DatabaseManager
from .game_logic import RouletteGame, RouletteKeyboard, AntiFloodManager
from handlers.game_lock import game_lock
from .utils import (
    get_display_name,
    format_username_with_link,
    get_plain_username,
    delete_bet_messages,
    delete_spin_message,
    format_wait_time,
    get_bet_display_value,
    calculate_bet_result,
    parse_vabank_bet,
)


# =============================================================================
# ОСНОВНОЙ ОБРАБОТЧИК РУЛЕТКИ
# =============================================================================
class RouletteHandler:
    def __init__(self):
        self.game = RouletteGame()
        self.session_manager = SessionManager()
        self.logger = RouletteLogger()
        self.anti_flood = AntiFloodManager()
        self.gif_manager = RouletteGIFManager(base_path="media")
        self._cleanup_task = None
        self._command_handlers = self._setup_command_handlers()
        self.record_core = RecordCore()
        self.record_service = RecordService(self.record_core)
        self.game_stats_updater = GameStatsUpdater()

    async def initialize(self):
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def shutdown(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _periodic_cleanup(self):
        while True:
            await asyncio.sleep(60)
            self.anti_flood.cleanup_old_entries()
            self.session_manager.cleanup_old_sessions()

    def _setup_command_handlers(self) -> Dict[str, callable]:
        return {
            "го": self.spin_roulette,
            "крутить": self.spin_roulette,
            "spin": self.spin_roulette,
            "вертеть": self.spin_roulette,
            "ехало": self.spin_roulette,
            "go": self.spin_roulette,
            "отмена": self.clear_bets_command,
            "очистить": self.clear_bets_command,
            "clear": self.clear_bets_command,
            "ставки": self.show_my_bets,
            "мои ставки": self.show_my_bets,
            "bets": self.show_my_bets,
            "лог": lambda m: self.show_logs_command(m, False),
            "!лог": lambda m: self.show_logs_command(m, True),
            "повторить": lambda m: self._repeat_last_bets(m.from_user.id, m.chat.id, m),
            "repeat": lambda m: self._repeat_last_bets(m.from_user.id, m.chat.id, m),
            "удвоить": lambda m: self._double_bets(m.from_user.id, m.chat.id, m),
            "удвой": lambda m: self._double_bets(m.from_user.id, m.chat.id, m),
            "double": lambda m: self._double_bets(m.from_user.id, m.chat.id, m),
        }

    # =========================================================================
    # ОСНОВНЫЕ КОМАНДЫ РУЛЕТКИ
    # =========================================================================
    async def start_roulette(self, message: types.Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        first_name = message.from_user.first_name or ""
        username = message.from_user.username or ""

        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_or_create_user(db, user_id, username, first_name)
            if not user:
                await message.answer("❌ Ошибка при создании профиля")
                return

        # ТЗ-3: команда "рулетка" запускает меню только если оно не запущено
        if state_manager.is_roulette_session_open(chat_id):
            await message.answer(
                "🎰 Рулетка уже запущена.\n",
                parse_mode="HTML",
            )
            return

        # ТЗ-1: лимит новой группы (1 бесплатный запуск)
        if getattr(message.chat, "type", "private") in ("group", "supergroup"):
            # Если нельзя запускать рулетку (бесплатный запуск использован и лимит не снят)
            if not state_manager.can_launch_roulette(chat_id):
                chat_info = message.chat
                chat_title = getattr(chat_info, 'title', 'Группа')

                await message.answer(
                    f"🔒 <b>Лимит рулетки исчерпан!</b>\n\n"
                    f"Вы уже использовали бесплатный запуск.\n\n"
                    f"<b>ID группы:</b> <code>{chat_id}</code>\n\n"
                    f"<b>Для снятия лимита:</b>\n"
                    f"• Донат 500₽ через /донат\n"
                    f"• Укажите ID группы при оплате\n\n"
                    f"<i>После снятия лимита рулетка будет доступна всем без ограничений.</i>",
                    parse_mode="HTML",
                )
                return

        # Устанавливаем флаг сессии
        state_manager.set_flag(chat_id, "roulette_session_open", True)

        examples = (
            "🎰 Минирулетка\n"
            "Угадайте число из:\n"
            "0💚\n"
            "1🔴 2⚫ 3🔴 4⚫ 5🔴 6⚫\n"
            "7🔴 8⚫ 9🔴10⚫11🔴12⚫\n"
            "Ставки можно текстом:\n"
            "<code>1000000 на красное</code> | <code>5000000 на 12</code>"
        )
        keyboard = RouletteKeyboard.create_roulette_keyboard()
        msg = await message.answer(examples, reply_markup=keyboard)
        session = self.session_manager.get_session(chat_id)
        session.last_menu_message_id = msg.message_id

    async def quick_start_roulette(self, message: types.Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.session_manager.get_session(chat_id)

        # Проверяем, можно ли принимать ставки
        if session.spin_state in ["spinning_no_accept", "finalizing"]:
            await message.answer("🎰 Рулетка уже крутится! Подождите завершения текущей игры.")
            return

        # ТЗ-1: проверка лимита для новых групп
        if getattr(message.chat, "type", "private") in ("group", "supergroup"):
            if not state_manager.can_launch_roulette(chat_id):
                chat_info = message.chat
                chat_title = getattr(chat_info, 'title', 'Группа')

                await message.answer(
                    f"🔒 <b>Лимит рулетки исчерпан!</b>\n\n"
                    f"Вы уже использовали бесплатный запуск.\n\n"
                    f"<b>ID группы:</b> <code>{chat_id}</code>\n\n"
                    f"<b>Для снятия лимита:</b>\n"
                    f"• Донат 500₽ через /донат\n"
                    f"• Укажите ID группы при оплате\n\n"
                    f"<i>После снятия лимита рулетка будет доступна всем без ограничений.</i>",
                    parse_mode="HTML",
                )
                return

        user_session = session.get_user_session(user_id, get_display_name(message.from_user))

        if user_session.has_bets:
            await self.spin_roulette(message)

    async def clear_bets_command(self, message: types.Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.session_manager.get_session(chat_id)

        # Проверяем, можно ли отменять ставки
        if session.spin_state == "spinning_no_accept":
            await message.answer("🎰 Рулетка крутится! Отмена ставок временно недоступна.")
            return
        elif session.spin_state == "finalizing":
            await message.answer("🎰 Рулетка завершает кручение! Отмена ставок недоступна.")
            return

        success, result = await self._clear_bets(user_id, chat_id, message)
        await message.answer(result)

    async def show_my_bets(self, message: types.Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.session_manager.get_session(chat_id)

        if user_id not in session.user_sessions or not session.user_sessions[user_id].has_bets:
            await message.answer(" У вас нет активных ставок")
            return

        user_session = session.user_sessions[user_id]
        await message.answer(
            f"📋 Ваши активные ставки:\n{user_session.get_bets_info()}",
            parse_mode="Markdown"
        )

    async def show_balance(self, message: types.Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        first_name = message.from_user.first_name or ""
        username = message.from_user.username or ""

        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_or_create_user(db, user_id, username, first_name)
            if not user:
                await message.answer(" Ошибка при создании профиля")
                return

            coins = user.coins
            display_name = get_plain_username(get_display_name(message.from_user))
            session = self.session_manager.get_session(chat_id)
            active_bets_amount = 0

            if user_id in session.user_sessions and session.user_sessions[user_id].has_bets:
                active_bets_amount = session.user_sessions[user_id].total_amount

            if active_bets_amount > 0:
                balance_text = f"{display_name}\n{coins} + {active_bets_amount} Монет"
            else:
                balance_text = f"{display_name}\n{coins} Монет"

            if coins == 0 and active_bets_amount == 0:
                bonus_received = await self._check_bonus_received(user_id)
                keyboard = types.InlineKeyboardMarkup(row_width=2)

                keyboard.add(
                    types.InlineKeyboardButton(
                        text="🎁 Бонус",
                        callback_data="zero_balance_bonus"
                    )
                )

                await message.answer(balance_text, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await message.answer(balance_text, parse_mode="Markdown")

    async def show_logs_command(self, message: types.Message, show_all: bool = False):
        chat_id = message.chat.id
        logs_count = self.logger.get_logs_count(chat_id)

        if logs_count == 0:
            await message.answer("📊 Логи рулетки этого чата:\nПока нет записей о играх")
            return

        limit = CONFIG.MAX_GAME_LOGS if show_all else 10
        logs = self.logger.get_recent_logs(chat_id, limit)

        if not logs:
            await message.answer("📊 Логи рулетки этого чата:\nПока нет записей о играх")
            return

        logs_text = "".join(f"{log['color_emoji']}{log['result']}\n" for log in logs)
        await message.answer(logs_text)

    async def unlock_roulette_command(self, message: types.Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Только для групп
        if message.chat.type not in ("group", "supergroup"):
            await message.answer(" Команда доступна только в группах")
            return

        # Проверяем, снят ли уже лимит
        if state_manager.is_roulette_limit_removed(chat_id):
            await message.answer("🎰 В этой группе лимит рулетки уже снят!")
            return

        cost = 100_000_000

        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                 await message.answer(" Ошибка получения профиля")
                 return
                 
            if user.coins < cost:
                cost_fmt = f"{cost:,}".replace(",", " ")
                await message.answer(
                    f" Недостаточно средств!\n"
                    f"Стоимость снятия лимита: {cost_fmt} монет"
                )
                return

            # Снимаем средства
            UserRepository.update_user_balance(db, user_id, user.coins - cost)
            
            # Снимаем лимит
            state_manager.unlock_roulette_with_coins(chat_id, user_id)
            
            chat_title = message.chat.title or "Группа"
            
            await message.answer(
                f"✅ <b>Лимит рулетки снят!</b>\n\n"
                f"👤 Герой: {get_display_name(message.from_user)}\n"
                f"🏷️ Группа: {chat_title}\n"
                f"💰 Потрачено: {cost:,} монет\n"
                f"🎰 Теперь рулетка доступна всем без ограничений!",
                parse_mode="HTML"
            )

    # =========================================================================
    # ОБРАБОТКА СТАВОК
    # =========================================================================
    async def _place_multiple_bets(self, user_id: int, chat_id: int, bets: List[Tuple[int, str, str]],
                                   username: str, reply_target: types.Message) -> Tuple[bool, str, int]:
        async with DatabaseManager.db_session() as db:
            session = self.session_manager.get_session(chat_id)

            # Проверяем, можно ли принимать ставки
            if not session.can_accept_bets() and session.spin_state != "idle":
                return False, "🎰 Рулетка уже крутится! Ставки временно не принимаются.", 0

            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                return False, " Сначала зарегистрируйтесь через /start", 0

            coins = user.coins
            user_session = session.get_user_session(user_id, username)
            successful_bets = []
            total_amount = 0
            errors = []

            for amount, bet_type, bet_value in bets:
                is_valid, error_msg = BetValidator.validate_bet(amount, coins, user_session.total_amount)
                if not is_valid:
                    errors.append(error_msg)
                    continue

                bet = Bet(amount, bet_type, bet_value, username, user_id)
                if user_session.add_bet(bet):
                    coins -= amount
                    total_amount += amount
                    successful_bets.append(bet)
                    UserRepository.update_user_balance(db, user_id, coins)
                    UserRepository.update_max_bet(db, user_id, amount)

            if not successful_bets:
                error_message = "\n".join(errors) if errors else " Не удалось разместить ни одну ставку"
                return False, error_message, 0

            if not getattr(session, 'is_doubling_operation', False) and not getattr(session, 'is_repeat_operation', False):
                session.last_user_bets[user_id] = bets
            session.is_doubling_operation = False

            user_link = format_username_with_link(user_id, username)
            success_text = self._format_success_message(successful_bets, total_amount, user_link, errors)

            try:
                msg = await reply_target.answer(success_text, parse_mode="Markdown")
                user_session.bet_message_ids.append(msg.message_id)
            except Exception as e:
                logger.error(f"Ошибка при создании сообщения: {e}")

            return True, success_text, total_amount

    def _format_success_message(self, successful_bets: List[Bet], total_amount: int,
                                user_link: str, errors: List[str]) -> str:
        def display_value(val):
            """Преобразует внутреннее значение в отображаемое"""
            if val == "зеленое":
                return "зеро"
            return val
        
        if len(successful_bets) == 1:
            bet = successful_bets[0]
            text = f"ставка принята {user_link} {total_amount} на {display_value(bet.value)}"
        else:
            bet_details = [f" ᅠ{bet.amount} на {display_value(bet.value)}" for bet in successful_bets]
            text = f"ставки приняты {user_link}:\n" + "\n".join(bet_details)

        if errors:
            text += f"\nОшибки:\n" + "\n".join(errors)
        return text

    async def _send_roulette_result(self, message: types.Message, full_text: str):
        """Отправляет результат рулетки частями с защитой от перегрузки"""
        max_len = 3500  # Запас под разметку
        max_lines_per_chunk = 50  # Лимит строк в одном сообщении

        # Разбиваем на строки
        lines = full_text.split("\n")

        # Если строк слишком много, обрезаем с уведомлением
        if len(lines) > 200:
            lines = lines[:180]
            lines.append(f"... и ещё {len(lines) - 180} ставок")

        # Группируем в чанки
        chunks = []
        current_chunk = []
        current_length = 0

        for line in lines:
            line_len = len(line)

            if current_length + line_len + 1 > max_len or len(current_chunk) >= max_lines_per_chunk:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0

            current_chunk.append(line)
            current_length += line_len + 1

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        # Отправляем с задержкой между сообщениями
        for i, chunk in enumerate(chunks):
            retry_count = 0
            max_retries = 7  # Увеличено: результат — самое важное сообщение
            sent = False
            
            while retry_count < max_retries:
                try:
                    await message.answer(text=chunk, parse_mode="Markdown")
                    sent = True
                    # Задержка между сообщениями для разгрузки
                    if i % 2 == 0:
                        await asyncio.sleep(0.3)
                    break
                except Exception as e:
                    error_str = str(e)
                    if "Flood control" in error_str or "Retry in" in error_str or "Too Many Requests" in error_str:
                        # Извлекаем реальное время ожидания из ошибки Telegram
                        import re as _re
                        wait_match = _re.search(r'(\d+)\s*seconds?', error_str)
                        if wait_match:
                            wait_time = int(wait_match.group(1)) + 1
                        else:
                            wait_time = min(3 + retry_count * 3, 20)
                        retry_count += 1
                        logger.warning(f"Flood control, ждём {wait_time} сек (попытка {retry_count}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"Ошибка отправки части результата: {e}")
                        # Пробуем отправить без разметки
                        try:
                            await message.answer(text=chunk)
                            sent = True
                        except:
                            pass
                        break
            
            # Гарантированный fallback — результат ОБЯЗАН быть отправлен
            if not sent:
                logger.warning("Все попытки исчерпаны, финальная попытка через 30 сек...")
                await asyncio.sleep(30)
                try:
                    await message.answer(text=chunk, parse_mode="Markdown")
                except:
                    try:
                        await message.answer(text=chunk)
                    except Exception as final_e:
                        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: не удалось отправить результат рулетки: {final_e}")

    async def _send_roulette_menu(self, chat_id: int, bot, session: ChatSession):
        """Отправляет меню рулетки после завершения спина."""
        # Сбрасываем флаг сессии
        state_manager.set_flag(chat_id, "roulette_session_open", False)

        # Убедимся, что атрибут существует
        if not hasattr(session, 'last_menu_message_id'):
            session.last_menu_message_id = None

        examples = (
            "🎰 Минирулетка\n"
            "Угадайте число из:\n"
            "0💚\n"
            "1🔴 2⚫ 3🔴 4⚫ 5🔴 6⚫\n"
            "7🔴 8⚫ 9🔴10⚫11🔴12⚫\n"
            "Ставки можно текстом:\n"
            "<code>1000000 на красное</code> | <code>5000000 на 12</code>"
        )
        keyboard = RouletteKeyboard.create_roulette_keyboard()
        
        # Delete old menu message if exists
        if session.last_menu_message_id:
            try:
                await bot.delete_message(chat_id, session.last_menu_message_id)
            except Exception:
                pass
            session.last_menu_message_id = None
        
        # Retry logic for flood control
        for attempt in range(3):
            try:
                msg = await bot.send_message(chat_id, examples, reply_markup=keyboard)
                session.last_menu_message_id = msg.message_id
                break
            except Exception as e:
                error_str = str(e)
                if "Flood control" in error_str or "Retry in" in error_str:
                    wait_time = min(5 + attempt * 3, 15)
                    logger.warning(f"Flood control меню, ждём {wait_time} сек")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Ошибка отправки меню рулетки: {e}")
                    break

    async def _clear_bets(self, user_id: int, chat_id: int, message: types.Message) -> Tuple[bool, str]:
        session = self.session_manager.get_session(chat_id)

        # Проверяем, можно ли отменять ставки
        if not session.can_accept_bets() and session.spin_state != "idle":
            return False, "🎰 Рулетка крутится! Отмена ставок временно недоступна."

        if user_id not in session.user_sessions or not session.user_sessions[user_id].has_bets:
            return False, " У вас нет активных ставок для очистки"

        user_session = session.user_sessions[user_id]
        total_amount = user_session.clear_bets()

        # Получаем информацию о пользователе для ссылки
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if user:
                UserRepository.update_user_balance(db, user_id, user.coins + total_amount)

        # Получаем username для ссылки
        username = get_display_name(message.from_user)
        user_link = format_username_with_link(user_id, username)

        await delete_bet_messages(chat_id, user_session.bet_message_ids)
        return True, f"Ставки {username} отменены"

    # =========================================================================
    # ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
    # =========================================================================
    async def place_bet(self, message: types.Message):
        text = (message.text or "").strip()
        user_id = message.from_user.id
        chat_id = message.chat.id
        username = get_display_name(message.from_user)
        first_name = message.from_user.first_name or ""

        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_or_create_user(db, user_id, username, first_name)
            if not user:
                await message.answer(" Ошибка при создании профиля")
                return

        if await self._handle_special_commands(text, message, user_id, chat_id, username):
            return

        if text.upper() == "Б" or text.startswith("/"):
            return

        session = self.session_manager.get_session(chat_id)

        # Проверяем, можно ли принимать ставки
        if not session.can_accept_bets() and session.spin_state != "idle":
            await message.answer("🎰 Рулетка уже крутится! Ставки временно не принимаются.")
            return

        if user_id in session.waiting_for_bet:
            await self._handle_waiting_bet(user_id, chat_id, text, username, message, session)
            return

        bets = BetParser.parse_multiple_bets(text)
        if bets:
            ok, result_msg, total = await self._place_multiple_bets(user_id, chat_id, bets, username, message)
            if not ok:
                await message.answer(result_msg)
            return

        amount, bet_type, bet_value = BetParser.parse_single_bet(text)
        if amount and bet_type and bet_value:
            ok, result_msg, total = await self._place_multiple_bets(
                user_id, chat_id, [(amount, bet_type, bet_value)], username, message
            )
            if not ok:
                await message.answer(result_msg)

    async def _handle_special_commands(self, text: str, message: types.Message,
                                       user_id: int, chat_id: int, username: str) -> bool:
        text_lower = text.lower().strip()

        if text_lower in ['лимиты', 'лимит', 'limits']:
            from handlers.transfer_limit import transfer_limit
            limit_info = transfer_limit.get_limit_info(user_id)
            await message.answer(limit_info)
            return True

        if text_lower.startswith(("ва-банк", "вабанк", "ва банк")):
            parts = text_lower.split()
            if len(parts) < 2:
                await message.answer(" Укажите тип ставки для вабанка\nПример: вабанк красное")
                return True
            bet_type = parts[1]
            await self._handle_vabank(user_id, chat_id, bet_type, message)
            return True

        if text_lower in self._command_handlers:
            await self._command_handlers[text_lower](message)
            return True

        return False

    async def _handle_vabank(self, user_id: int, chat_id: int, bet_value: str, message: types.Message):
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_or_create_user(db, user_id,
                                                     message.from_user.username or "",
                                                     message.from_user.first_name or "")
            if not user:
                await message.answer(" Ошибка при создании профиля")
                return

            session = self.session_manager.get_session(chat_id)
            username = get_display_name(message.from_user)
            user_session = session.get_user_session(user_id, username)
            current_balance = user.coins

            if current_balance <= 0:
                await message.answer(" Недостаточно средств для ва-банк")
                return
            if current_balance < CONFIG.MIN_BET:
                await message.answer(f" Минимальная ставка для ва-банка: {CONFIG.MIN_BET}")
                return

            bet_data = parse_vabank_bet(bet_value)
            if not bet_data:
                await message.answer(" Неверный тип ставки для вабанка")
                return

            bet_type, full_bet_value = bet_data

            if bet_type == "группа" and isinstance(full_bet_value, str) and '-' in full_bet_value:
                try:
                    start, end = map(int, full_bet_value.split('-'))
                    if start == end:
                        await message.answer(
                            " Некорректный диапазон ставки. Используйте разные числа (например: 1-3, 4-6)")
                        return
                    if start > end:
                        await message.answer(" Некорректный диапазон ставки. Первое число должно быть меньше второго")
                        return
                except (ValueError, TypeError):
                    pass

            vabank_bet = Bet(current_balance, bet_type, full_bet_value, username, user_id)
            if not user_session.add_bet(vabank_bet):
                await message.answer(" Не удалось разместить ва-банк ставку")
                return

            UserRepository.update_user_balance(db, user_id, 0)
            total_all_bets = user_session.total_amount
            UserRepository.update_max_bet(db, user_id, max(getattr(user, 'max_bet', 0), total_all_bets))

            user_link = format_username_with_link(user_id, username)
            vabank_text = f"ставка принята {user_link} {current_balance} на {full_bet_value}"

            try:
                msg = await message.answer(vabank_text, parse_mode="Markdown")
                user_session.bet_message_ids.append(msg.message_id)
            except Exception as e:
                logger.error(f"Ошибка при создании сообщения: {e}")

    async def _handle_waiting_bet(self, user_id: int, chat_id: int, text: str, username: str,
                                  message: types.Message, session: ChatSession):
        bet_type, bet_value = session.waiting_for_bet[user_id]
        amount = BetParser.parse_amount(text.split()[0])

        if amount is None:
            await message.answer(" Введите корректную сумму (пример: 1000 или 1k)")
            return

        ok, result_msg, total = await self._place_multiple_bets(
            user_id, chat_id, [(amount, bet_type, bet_value)], username, message
        )
        del session.waiting_for_bet[user_id]

        if not ok:
            await message.answer(result_msg)

    # =========================================================================
    # ОБРАБОТКА CALLBACK-ОВ (исправленная для ТЗ-4)
    # =========================================================================
    async def handle_callback(self, call: types.CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        data = call.data

        if not data:
            await call.answer(" Недействительная кнопка!")
            return

        # Обработка основных callback-ов
        if data == "zero_balance_bonus":
            await self._handle_zero_balance_bonus(call)
            return

        if data == "donate_shop":
            await self._open_donate_shop(call)
            return

        if data == "zero_balance_donate":
            await self._open_donate_shop(call)
            return

        if data == "check_subscription":
            await self._check_subscription_callback(call)
            return

        if data == "honest_subscription":
            await self._handle_honest_subscription(call)
            return

        if data == "get_free_bonus":
            await self._handle_free_bonus(call)
            return

        if data == "back_to_chat":
            await self._handle_back_to_chat(call)
            return

        if data == "back_to_shop":
            await self._handle_shop_callback(call, user_id, chat_id)
            return

        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                await call.answer(" Сначала зарегистрируйтесь через /start")
                return

            try:
                if ':' in data:
                    prefix, callback_data = data.split(':', 1)
                    await self._route_callback(prefix, callback_data, call, user_id, chat_id)
                else:
                    await self._handle_legacy_callback(data, call, user_id, chat_id)
            except Exception as e:
                logger.error(f" Ошибка обработки callback: {e}")
                try:
                    await call.answer(" Ошибка обработки кнопки")
                except Exception:
                    pass  # Игнорируем ошибку если callback устарел

    async def _route_callback(self, prefix: str, callback_data: str, call: types.CallbackQuery,
                              user_id: int, chat_id: int):
        handlers = {
            "bet": self._handle_bet_callback,
            "quick": self._handle_quick_bet_callback,
            "action": self._handle_action_callback
        }
        handler = handlers.get(prefix)
        if handler:
            await handler(call, user_id, chat_id, callback_data)
        else:
            await call.answer(" Неизвестный тип кнопки")

    async def _handle_bet_callback(self, call: types.CallbackQuery, user_id: int,
                                   chat_id: int, callback_data: str):
        """Обработка кнопок ставок 1-3, 4-6 и т.д. - ТЗ-4: фиксированная ставка 1,000,000"""
        bet_type_mapping = {
            "1-3": ("группа", "1-3"),
            "4-6": ("группа", "4-6"),
            "7-9": ("группа", "7-9"),
            "10-12": ("группа", "10-12"),
        }

        if callback_data in bet_type_mapping:
            session = self.session_manager.get_session(chat_id)

            # Защита от double-click
            cb_id = f"{user_id}:{callback_data}:{call.message.message_id}"
            if hasattr(session, 'processed_callback_ids') and cb_id in session.processed_callback_ids:
                await call.answer("Ставка уже обрабатывается...", show_alert=False)
                return

            if not hasattr(session, 'processed_callback_ids'):
                session.processed_callback_ids = set()
            session.processed_callback_ids.add(cb_id)

            bet_type, bet_value = bet_type_mapping[callback_data]
            fixed_amount = 5_000  # ТЗ-4: фиксированная сумма
            username = get_display_name(call.from_user)

            # Проверяем баланс
            async with DatabaseManager.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await call.answer("Пользователь не найден", show_alert=True)
                    return

                if user.coins < fixed_amount:
                    await call.answer(f"Недостаточно средств! Нужно {fixed_amount:,} Монет", show_alert=True)
                    return

            # Размещаем ставку
            ok, result_msg, _ = await self._place_multiple_bets(
                user_id, chat_id, [(fixed_amount, bet_type, bet_value)], username, call.message
            )

            if ok:
                display_val = "зеро" if bet_value == "зеленое" else bet_value
                await call.answer(f"Ставка {fixed_amount:,} на {display_val} принята!".replace(',', ' '))
            else:
                await call.answer(f"{result_msg}", show_alert=True)
        else:
            await call.answer(" Неизвестный тип ставки")

    async def _handle_quick_bet_callback(self, call: types.CallbackQuery, user_id: int,
                                         chat_id: int, callback_data: str):
        try:
            amount_str, color_type = callback_data.split("_")
            amount = int(amount_str)
            color_map = {
                "red": ("цвет", "красное"),
                "black": ("цвет", "черное"),
                "green": ("цвет", "зеленое")
            }
            if color_type in color_map:
                bet_type, bet_value = color_map[color_type]
                username = get_display_name(call.from_user)
                ok, result_msg, total = await self._place_multiple_bets(
                    user_id, chat_id, [(amount, bet_type, bet_value)], username, call.message
                )
                if ok:
                    display_val = "зеро" if bet_value == "зеленое" else bet_value
                    await call.answer(f"Ставка {amount:,} на {display_val} принята!".replace(',', ' '))
                else:
                    await call.answer(f" {result_msg}")
            else:
                await call.answer(" Неизвестный тип ставки")
        except Exception as e:
            logger.error(f" Ошибка быстрой ставки: {e}")
            await call.answer(" Ошибка размещения ставки")

    async def _handle_action_callback(self, call: types.CallbackQuery, user_id: int,
                                      chat_id: int, callback_data: str):
        """Обработка callback-действий"""
        if callback_data == "spin":
            try:
                if call.message:
                    class SimpleMessage:
                        def __init__(self, call):
                            self.message_id = call.message.message_id
                            self.date = call.message.date
                            self.chat = call.message.chat
                            self.from_user = call.from_user
                            self.text = "го"
                            self.bot = call.bot

                        async def answer(self, text, **kwargs):
                            return await self.bot.send_message(
                                chat_id=self.chat.id,
                                text=text,
                                **kwargs
                            )

                    await self.spin_roulette(SimpleMessage(call))
                    try:
                        await call.answer("🎰 Крутим рулетку!")
                    except Exception:
                        pass
                else:
                    try:
                        await call.answer(" Не удалось запустить рулетку", show_alert=True)
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f" Ошибка при обработке callback 'spin': {e}")
                try:
                    await call.answer(" Ошибка при запуске рулетки", show_alert=True)
                except Exception:
                    pass

        elif callback_data == "repeat":
            await self._repeat_last_bets(user_id, chat_id, call)
            try:
                await call.answer("🔄 Повторяем последние ставки")
            except Exception:
                pass

        elif callback_data == "double":
            await self._double_bets(user_id, chat_id, call)
            try:
                await call.answer("⚡ Удваиваем ставки")
            except Exception:
                pass

    async def _handle_legacy_callback(self, data: str, call: types.CallbackQuery,
                                      user_id: int, chat_id: int):
        username = get_display_name(call.from_user)
        session = self.session_manager.get_session(chat_id)

        if data.startswith("bet_"):
            # Обработка legacy кнопок - также фиксированная ставка
            bet_value = data.replace("bet_", "")
            fixed_amount = 5_000  # ТЗ-4: фиксированная сумма

            # Защита от double-click
            cb_id = f"{user_id}:{data}:{call.message.message_id}"
            if hasattr(session, 'processed_callback_ids') and cb_id in session.processed_callback_ids:
                await call.answer("Ставка уже обрабатывается...", show_alert=False)
                return

            if not hasattr(session, 'processed_callback_ids'):
                session.processed_callback_ids = set()
            session.processed_callback_ids.add(cb_id)

            # Проверяем баланс
            async with DatabaseManager.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await call.answer("Пользователь не найден", show_alert=True)
                    return

                if user.coins < fixed_amount:
                    await call.answer(f"Недостаточно средств! Нужно {fixed_amount:,} Монет", show_alert=True)
                    return

            ok, result_msg, _ = await self._place_multiple_bets(
                user_id, chat_id, [(fixed_amount, "группа", bet_value)], username, call.message
            )
            if ok:
                await call.answer(f"Ставка {fixed_amount:,} на {bet_value} принята!".replace(',', ' '))
            else:
                await call.answer(f"{result_msg}", show_alert=True)
        elif data.startswith("quick_"):
            quick_data = data.replace("quick_", "")
            await self._handle_quick_bet_callback(call, user_id, chat_id, quick_data)
        elif data in ["repeat", "double", "spin"]:
            await self._handle_action_callback(call, user_id, chat_id, data)

    # =========================================================================
    # ИГРОВАЯ МЕХАНИКА (исправленная)
    # =========================================================================
    async def spin_roulette(self, message: types.Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        session = self.session_manager.get_session(chat_id)

        if not state_manager.is_roulette_enabled(chat_id):
            chat_name = message.chat.title if hasattr(message.chat, 'title') else "этом чате"
            await message.answer(
                f"🚫 <b>Рулетка временно отключена администратором в {chat_name}.</b>\n\n"
                "Для включения используйте команду <code>!ron</code>",
                parse_mode="HTML"
            )
            return

        # Проверяем лимит рулетки для группы
        from database import SessionLocal as DBSessionLocal
        from database.crud import RouletteLimitRepository
        
        db = DBSessionLocal()
        try:
            can_launch = RouletteLimitRepository.use_free_launch(db, chat_id)
        finally:
            db.close()
        
        if not can_launch:
            chat_name = message.chat.title or "этой группе"
            await message.answer(
                f"🔒 <b>Лимит рулетки исчерпан в {chat_name}!</b>\n\n"
                "Вы уже использовали бесплатный запуск.\n\n"
                f"<b>ID группы:</b> <code>{chat_id}</code>\n\n"
                "<b>Для снятия лимита:</b>\n"
                "• Донат 500₽ через /донат\n"
                "• Укажите ID группы при оплате",
                parse_mode="HTML"
            )
            return

        try:
            # Пытаемся взять блокировку с таймаутом
            try:
                await asyncio.wait_for(session.spin_lock.acquire(), timeout=0.5)
            except asyncio.TimeoutError:
                await message.answer("🎰 Рулетка уже крутится! Подождите завершения текущей игры.")
                return

            try:
                if session.is_spinning():
                    await message.answer("🎰 Рулетка уже крутится! Подождите завершения текущей игры.")
                    return

                can_spin, wait_time = self.anti_flood.can_spin(user_id, chat_id)
                if not can_spin:
                    time_text = format_wait_time(wait_time)
                    await message.answer(f"⏳ Слишком часто! Подождите {time_text} перед следующим запуском.")
                    return

                active_users = session.active_users
                if not active_users:
                    await message.answer(" Нет активных ставок для игры!")
                    return

                # Блокировка между разными играми отключена
                # Теперь слоты, рулетка и другие игры могут работать параллельно

                # Генерируем случайное время прокрута: от 5 до 15 секунд
                spin_duration = random.randint(5, 15)
                session.spin_timer = spin_duration

                # Запускаем процесс кручения
                session.spin_state = "spinning_accept"

                # Получаем имя пользователя для отображения
                username = get_display_name(message.from_user)

                # Создаем кликабельную ссылку на пользователя
                user_link = format_username_with_link(user_id, username)

                # Отправляем сообщение о начале кручения в новом формате с кликабельным именем
                spin_msg = await message.answer(
                    f"{user_link} крутит (через {spin_duration} сек.)",
                    parse_mode="Markdown"
                )
                session.spin_message_id = spin_msg.message_id

                # Запускаем асинхронную задачу для процесса кручения
                session.spin_task = asyncio.create_task(
                    self._spin_process(chat_id, spin_duration, session, spin_msg, username, user_id)
                )

                # Ждем завершения спин-процесса
                await session.spin_task

                # ==========================================================
                # ГЕНЕРАЦИЯ И ОТПРАВКА РЕЗУЛЬТАТА
                # ==========================================================
                # Генерируем результат
                result = self.game.spin(chat_id)
                color_emoji = self.game.get_color_emoji(result)
                self.logger.add_game_log(chat_id, result, color_emoji)

                # Обрабатываем результаты
                active_users = session.active_users.copy()
                result_text = await self._process_game_results(active_users, result, color_emoji, chat_id, session)

                # Форматируем результат в старом формате
                result_message = f"Рулетка: {result}{color_emoji}"

                # Добавляем результат только если есть текст
                if result_text.strip():
                    result_message += f"\n{result_text}"

                # Отправляем результат с батчингом
                await self._send_roulette_result(message, result_message)

                # ТЗ-5: после завершения спина снова показываем меню рулетки
                await self._send_roulette_menu(chat_id, message.bot, session)

                logger.info(f"✅ Игра завершена. Результат: {result}{color_emoji}")

            except Exception as e:
                logger.error(f" Ошибка при запуске рулетки: {e}", exc_info=True)
                try:
                    await message.answer(" Произошла ошибка при запуске рулетки")
                except:
                    pass
                session.spin_state = "idle"
            finally:

                # Всегда сбрасываем состояние
                session.spin_state = "idle"
                session.spin_timer = None
                if session.spin_task:
                    session.spin_task = None

                # Разблокируем
                if session.spin_lock.locked():
                    try:
                        session.spin_lock.release()
                    except:
                        pass

        except Exception as e:
            logger.error(f" Общая ошибка в spin_roulette: {e}")
            session.spin_state = "idle"

    async def _spin_process(self, chat_id: int, spin_duration: int, session: ChatSession,
                            spin_msg: types.Message, username: str, user_id: int):
        """Асинхронный процесс кручения рулетки - только анимация и таймер"""
        try:
            accept_bets_time = 5 if spin_duration == 15 else 0

            logger.info(f"🎰 Начинаем кручение: {spin_duration} сек, прием ставок: {accept_bets_time} сек")

            # Создаем кликабельную ссылку на пользователя
            user_link = format_username_with_link(user_id, username)

            # Отсчет времени с обновлением сообщения
            for i in range(spin_duration):
                remaining = spin_duration - i

                # Обновляем сообщение о времени в новом формате с кликабельным именем
                if i % 2 == 0 or remaining <= 3:
                    try:
                        if i < accept_bets_time:
                            await spin_msg.edit_text(
                                f"{user_link} принимает ставки... (осталось {remaining} сек.)",
                                parse_mode="Markdown"
                            )
                        else:
                            await spin_msg.edit_text(
                                f"{user_link} крутит... (осталось {remaining} сек.)",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        logger.debug(f"Не удалось обновить сообщения: {e}")

                if i < accept_bets_time:
                    session.spin_state = "spinning_accept"
                else:
                    session.spin_state = "spinning_no_accept"

                await asyncio.sleep(1)

            # Финальная фаза
            session.spin_state = "finalizing"

            # Удаляем сообщение о прокруте
            try:
                await spin_msg.delete()
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение: {e}")
            session.spin_message_id = None

            # ==========================================================
            # ОТПРАВКА ГИФКИ (по ТЗ)
            # ==========================================================
            try:
                import os
                gif_path = "media/rlt2.gif"

                if os.path.exists(gif_path):
                    logger.info(f"✅ Отправляем GIF: {gif_path}")
                    with open(gif_path, 'rb') as gif_file:
                        gif_message = await spin_msg.bot.send_animation(
                            chat_id=chat_id,
                            animation=gif_file,
                            caption="🎰 Рулетка крутится..."
                        )

                    # Даем GIF проиграться 2 секунды
                    await asyncio.sleep(2)

                    # Удаляем GIF
                    if gif_message:
                        try:
                            await gif_message.delete()
                        except:
                            pass
                else:
                    logger.warning(f" GIF не найден: {gif_path}")
                    # Текстовая анимация как fallback
                    fallback_msg = await spin_msg.bot.send_message(
                        chat_id=chat_id,
                        text="🎰 Рулетка крутится... 🔄"
                    )
                    await asyncio.sleep(1.5)
                    try:
                        await fallback_msg.delete()
                    except:
                        pass

            except Exception as e:
                logger.error(f" Ошибка при отправке GIF: {e}")
                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f" Ошибка в процессе кручения: {e}")

    async def _process_game_results(self, active_users: Dict[int, UserBetSession], result: int,
                                    color_emoji: str, chat_id: int, session: ChatSession) -> str:
        """Обрабатывает результаты игры и возвращает отформатированный текст"""
        # Собираем все данные для вывода
        all_bets_text = []  # Все ставки всех пользователей
        win_bets_text = []  # Все выигрыши
        return_bets_text = []  # Все возвраты

        user_updates = {}
        user_stats_updates = {}

        # Сначала собираем все ставки для повторения
        for user_id, user_session in active_users.items():
            if user_session.bets:
                bets_for_repeat = [(bet.amount, bet.type, bet.value) for bet in user_session.bets]
                session.last_user_bets[user_id] = bets_for_repeat

        # Обрабатываем каждого пользователя
        for user_id, user_session in active_users.items():
            async with DatabaseManager.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    continue

                # Обрабатываем результаты и собираем текст
                user_bets_text, user_win_text, user_return_text = await self._process_user_results(
                    user_id, user_session, result, user, user_updates, user_stats_updates, chat_id
                )

                # Собираем тексты в соответствующие списки
                if user_bets_text:
                    all_bets_text.extend(user_bets_text)
                if user_win_text:
                    win_bets_text.extend(user_win_text)
                if user_return_text:
                    return_bets_text.extend(user_return_text)

                await delete_bet_messages(chat_id, user_session.bet_message_ids)

        # Если есть обновления баланса - применяем их
        if user_updates:
            await self._update_database_batch(user_updates, user_stats_updates)

        # Очищаем ставки у всех пользователей
        for user_id in active_users:
            if user_id in session.user_sessions:
                session.user_sessions[user_id].clear_bets()

        # Формируем итоговый текст в правильном порядке:
        # 1. Все ставки (ограничиваем количество)
        # 2. Возвраты (если есть, ограничиваем)
        # 3. Выигрыши (в самом конце, ограничиваем)

        result_lines = []

        # Все ставки (батчинг/ограничение вывода: ТЗ-4.1)
        if all_bets_text:
            max_lines = 80
            if len(all_bets_text) > max_lines:
                shown = all_bets_text[:max_lines]
                shown.append(f"… и ещё {len(all_bets_text) - max_lines} ставок")
                result_lines.extend(shown)
            else:
                result_lines.extend(all_bets_text)

        # Возвраты
        if return_bets_text:
            max_lines = 40
            if len(return_bets_text) > max_lines:
                shown = return_bets_text[:max_lines]
                shown.append(f"… и ещё {len(return_bets_text) - max_lines} возвратов")
                result_lines.extend(shown)
            else:
                result_lines.extend(return_bets_text)

        # Выигрыши (в самом конце)
        if win_bets_text:
            max_lines = 60
            if len(win_bets_text) > max_lines:
                shown = win_bets_text[:max_lines]
                shown.append(f"… и ещё {len(win_bets_text) - max_lines} выигрышей")
                result_lines.extend(shown)
            else:
                result_lines.extend(win_bets_text)

        # Объединяем все строки - ВАЖНО: без лишних \n в конце
        return "\n".join(result_lines)

    async def _process_user_results(self, user_id: int, user_session: UserBetSession, result: int,
                                    user, user_updates: Dict, user_stats_updates: Dict,
                                    chat_id: int) -> Tuple[List[str], List[str], List[str]]:
        """Обрабатывает результаты для одного пользователя и возвращает три списка:
        - bets_text: список строк со ставками пользователя
        - win_text: список строк с выигрышами
        - return_text: список строк с возвратами
        """
        current_coins = user.coins
        win_coins = user.win_coins or 0
        defeat_coins = user.defeat_coins or 0
        max_win = user.max_win_coins or 0
        min_win = user.min_win_coins or 0
        total_net_profit = 0
        total_payout = 0
        user_bets_text = []
        win_bets_text = []
        return_bets_text = []
        display_name = user_session.username

        transactions_data = []

        # Собираем информацию о всех ставках пользователя
        total_bet_amount = sum(bet.amount for bet in user_session.bets)

        for bet in user_session.bets:
            profit, payout = calculate_bet_result(self.game, bet, result)
            total_net_profit += profit
            total_payout += payout

            # Добавляем информацию о ставке (просто сумма и тип)
            plain_name = get_plain_username(display_name)
            display_val = "зеро" if bet.value == "зеленое" else bet.value
            user_bets_text.append(f"{plain_name} {bet.amount} на {display_val}")

            if profit > 0:
                # Выигрыш - добавляем в отдельный список
                user_link = format_username_with_link(user_id, display_name)
                win_bets_text.append(f"{user_link} выиграл {profit} на {display_val}")
            elif profit < 0 and payout > 0:
                # Возврат 50% - добавляем в отдельный список
                user_link = format_username_with_link(user_id, display_name)
                return_bets_text.append(f"{user_link} возврат {payout}")

            transactions_data.append({
                'user_id': user_id,
                'amount': bet.amount,
                'is_win': profit > 0,
                'bet_type': bet.type,
                'bet_value': str(bet.value),
                'result_number': result,
                'profit': profit
            })

        # Обновляем баланс с учетом ВСЕХ выплат (выигрыши + возвраты)
        user_updates[user_id] = current_coins + total_payout

        # Обновляем статистику рулетки
        if total_bet_amount > 0:
            await self.game_stats_updater.update_roulette_stats(user_id, total_net_profit, total_bet_amount)

        if total_net_profit != 0:
            await self._update_user_records(user_id, total_net_profit, chat_id, display_name)

            if total_net_profit > 0:
                win_coins += total_net_profit
                max_win = max(max_win, total_net_profit)
            else:
                defeat_coins += abs(total_net_profit)

            if min_win is None:
                min_win = 0
            min_win = min(min_win, total_net_profit)

        current_max_bet = max(bet.amount for bet in user_session.bets) if user_session.bets else 0
        new_max_bet = max(getattr(user, 'max_bet_coins', 0), current_max_bet)

        user_stats_updates[user_id] = (win_coins, defeat_coins, max_win, min_win, new_max_bet)
        await self._create_roulette_transactions(transactions_data)

        # Возвращаем три отдельных списка
        return user_bets_text, win_bets_text, return_bets_text

    async def _update_user_records(self, user_id: int, net_profit: int, chat_id: int, username: str):
        try:
            if net_profit > 0:
                success = await self.record_service.add_win_record(
                    user_id=user_id,
                    amount=net_profit,
                    chat_id=chat_id,
                    username=username,
                    first_name=username
                )
                if success:
                    logger.info(f"✅ Рекорд выигрыша обновлен: {user_id} -> {net_profit}")
                else:
                    logger.warning(f"⚠️ Не удалось обновить рекорд для {user_id}")

            elif net_profit < 0:
                loss_amount = abs(net_profit)
                success = await self.record_service.add_loss_record(
                    user_id=user_id,
                    loss_amount=loss_amount,
                    username=username,
                    first_name=username
                )
                if success:
                    logger.info(f"✅ Рекорд проигрыша обновлен: {user_id} -> {loss_amount}")

        except Exception as e:
            logger.error(f" Ошибка обновления рекордов: {e}")

    async def _create_roulette_transactions(self, transactions_data: List[Dict]):
        async with DatabaseManager.db_session() as db:
            for transaction in transactions_data:
                RouletteRepository.create_roulette_transaction(
                    db=db,
                    user_id=transaction['user_id'],
                    amount=transaction['amount'],
                    is_win=transaction['is_win'],
                    bet_type=transaction['bet_type'],
                    bet_value=transaction['bet_value'],
                    result_number=transaction['result_number'],
                    profit=transaction['profit']
                )

    async def _update_database_batch(self, user_updates: Dict, user_stats_updates: Dict):
        try:
            await DatabaseManager.update_users_batch(user_updates, user_stats_updates)
        except Exception as e:
            logger.error(f" Ошибка при пакетном обновлении БД: {e}")

    # =========================================================================
    # ПОВТОРИТЬ/УДВОИТЬ СТАВКИ
    # =========================================================================
    async def _repeat_last_bets(self, user_id: int, chat_id: int, message_or_call):
        session = self.session_manager.get_session(chat_id)
        username = get_display_name(
            message_or_call.from_user if hasattr(message_or_call, 'from_user')
            else message_or_call
        )

        if user_id not in session.last_user_bets or not session.last_user_bets[user_id]:
            if hasattr(message_or_call, 'answer'):
                try:
                    await message_or_call.answer(" Нет последних ставок для повторения", show_alert=True)
                except Exception:
                    pass
            return

        last_bets = session.last_user_bets[user_id]
        try:
            session.is_repeat_operation = True
            if hasattr(message_or_call, 'message'):
                ok, result_msg, total = await self._place_multiple_bets(
                    user_id, chat_id, last_bets, username, message_or_call.message
                )
            else:
                ok, result_msg, total = await self._place_multiple_bets(
                    user_id, chat_id, last_bets, username, message_or_call
                )
            session.is_repeat_operation = False
            if not ok and hasattr(message_or_call, 'answer'):
                try:
                    await message_or_call.answer(result_msg, show_alert=True)
                except Exception:
                    pass
        except Exception as e:
            session.is_repeat_operation = False
            logger.error(f"Ошибка повтора ставок: {e}")
            if hasattr(message_or_call, 'answer'):
                try:
                    await message_or_call.answer(" Ошибка при повторе ставок", show_alert=True)
                except Exception:
                    pass

    async def _double_bets(self, user_id: int, chat_id: int, message_or_call):
        session = self.session_manager.get_session(chat_id)
        username = get_display_name(
            message_or_call.from_user if hasattr(message_or_call, 'from_user')
            else message_or_call
        )

        if user_id not in session.user_sessions or not session.user_sessions[user_id].has_bets:
            reply_method = getattr(message_or_call, 'answer', message_or_call.answer)
            await reply_method(" Нет активных ставок для удвоения")
            return

        user_session = session.user_sessions[user_id]
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                reply_method = getattr(message_or_call, 'answer', message_or_call.answer)
                await reply_method(" Пользователь не найден")
                return

            double_amount = user_session.total_amount

            if double_amount > user.coins:
                reply_method = getattr(message_or_call, 'answer', message_or_call.answer)
                await reply_method(
                    f" Недостаточно средств для удвоения. Нужно: {double_amount}, есть: {user.coins}")
                return

            current_bets = [(bet.amount, bet.type, bet.value) for bet in user_session.bets]
            doubled_bets = [(bet.amount * 2, bet.type, bet.value) for bet in user_session.bets]
            returned_amount = user_session.total_amount
            user_session.clear_bets()

            UserRepository.update_user_balance(db, user_id, user.coins + returned_amount)
            session.is_doubling_operation = True

            if hasattr(message_or_call, 'message'):
                ok, result_msg, total = await self._place_multiple_bets(
                    user_id, chat_id, doubled_bets, username, message_or_call.message
                )
                if not ok:
                    await self._place_multiple_bets_silent(
                        user_id, chat_id, current_bets, username, message_or_call.message
                    )
                    try:
                        await message_or_call.answer(f" {result_msg}", show_alert=True)
                    except Exception:
                        pass
            else:
                ok, result_msg, total = await self._place_multiple_bets(
                    user_id, chat_id, doubled_bets, username, message_or_call
                )
                if not ok:
                    await self._place_multiple_bets_silent(
                        user_id, chat_id, current_bets, username, message_or_call
                    )
                    try:
                        await message_or_call.answer(result_msg)
                    except Exception:
                        pass

    async def _place_multiple_bets_silent(self, user_id: int, chat_id: int, bets: List[Tuple[int, str, str]],
                                          username: str, reply_target: types.Message) -> Tuple[bool, str, int]:
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                return False, " Сначала зарегистрируйтесь через /start", 0

            coins = user.coins
            session = self.session_manager.get_session(chat_id)
            user_session = session.get_user_session(user_id, username)
            successful_bets = []
            total_amount = 0

            for amount, bet_type, bet_value in bets:
                is_valid, error_msg = BetValidator.validate_bet(amount, coins, user_session.total_amount)
                if not is_valid:
                    return False, error_msg, 0

                bet = Bet(amount, bet_type, bet_value, username, user_id)
                if user_session.add_bet(bet):
                    coins -= amount
                    total_amount += amount
                    successful_bets.append(bet)
                    UserRepository.update_user_balance(db, user_id, coins)
                    UserRepository.update_max_bet(db, user_id, amount)

            if not successful_bets:
                return False, " Не удалось разместить ни одну ставку", 0

            if not getattr(session, 'is_doubling_operation', False) and not getattr(session, 'is_repeat_operation', False):
                session.last_user_bets[user_id] = bets
            session.is_doubling_operation = False
            return True, "", total_amount

    async def _check_bonus_received(self, user_id: int) -> bool:
        """Проверяет, получил ли пользователь бонус сегодня"""
        async with DatabaseManager.db_session() as db:
            today = datetime.utcnow().date()
            bonus = db.query(DailyBonusLog).filter(
                DailyBonusLog.user_id == user_id,
                func.date(DailyBonusLog.created_at) == today
            ).first()
            return bonus is not None

    async def _handle_zero_balance_bonus(self, call: types.CallbackQuery):
        """Обработка получения бонуса при нулевом балансе"""
        user_id = call.from_user.id
        
        if await self._check_bonus_received(user_id):
            await call.answer("🎁 Вы уже получили бонус сегодня!", show_alert=True)
            return

        bonus_amount = 5000 
        new_balance = 0
        async with DatabaseManager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if user:
                 new_balance = user.coins + bonus_amount
                 UserRepository.update_user_balance(db, user_id, new_balance)
                 
                 log = DailyBonusLog(
                     user_id=user_id,
                     bonus_amount=bonus_amount,
                     total_bonus_amount=bonus_amount,
                     is_automatic=True
                 )
                 db.add(log)
                 db.commit()

        await call.answer(f"🎁 Получено {bonus_amount} монет!", show_alert=True)
        try:
             # Обновляем баланс в сообщении
             await call.message.edit_text(
                 f"{get_plain_username(get_display_name(call.from_user))} \n💰:{new_balance} Монет",
                 parse_mode="Markdown"
             )
        except Exception:
             pass

    async def _handle_free_bonus(self, call: types.CallbackQuery):
        """Обработка кнопки бесплатного бонуса"""
        await self._handle_zero_balance_bonus(call)

    async def _open_donate_shop(self, call: types.CallbackQuery):
        """Открыть магазин доната"""
        await call.answer("🛒 Магазин доната временно недоступен", show_alert=True)

    async def _check_subscription_callback(self, call: types.CallbackQuery):
        """Проверка подписки"""
        await call.answer("✅ Подписка проверена", show_alert=False)

    async def _handle_honest_subscription(self, call: types.CallbackQuery):
        """Обработка честной подписки"""
        await call.answer("ℹ️ Информация скоро появится", show_alert=True)

    async def _handle_back_to_chat(self, call: types.CallbackQuery):
        """Вернуться в чат"""
        await call.message.delete()

    async def _handle_shop_callback(self, call: types.CallbackQuery, user_id: int, chat_id: int):
        """Вернуться в магазин"""
        await self._open_donate_shop(call)
    
    async def _handle_legacy_callback(self, data: str, call: types.CallbackQuery, user_id: int, chat_id: int):
        """Обработка устаревших колбэков"""
        await call.answer("Неизвестное действие")


# =============================================================================
# РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# =============================================================================
def register_roulette_handlers(dp):
    handler = RouletteHandler()

    # Основные команды
    dp.register_message_handler(
        handler.show_balance,
        lambda m: m.text and m.text.strip().lower() in ["б", "баланс", "balance", "/b", "/б", "/balance"]
    )
    dp.register_message_handler(
        handler.start_roulette,
        commands=["рулетка", "roulette"]
    )
    dp.register_message_handler(
        handler.start_roulette,
        lambda m: m.text and m.text.lower() == "рулетка"
    )
    dp.register_message_handler(
        handler.quick_start_roulette,
        lambda m: m.text and m.text.lower() in ["го", "крутить", "spin", "ехало", "вертеть", "go"]
    )

    # Команды управления ставками
    dp.register_message_handler(
        handler.clear_bets_command,
        lambda m: m.text and m.text.lower() in ["отмена", "очистить", "clear", "отменить"]
    )
    dp.register_message_handler(
        handler.show_my_bets,
        lambda m: m.text and m.text.lower() in ["ставки", "мои ставки", "bets"]
    )

    # Команды повторения и удвоения
    dp.register_message_handler(
        lambda m: handler._repeat_last_bets(m.from_user.id, m.chat.id, m),
        lambda m: m.text and m.text.lower() in ["повторить", "repeat", "репит"]
    )
    dp.register_message_handler(
        lambda m: handler._double_bets(m.from_user.id, m.chat.id, m),
        lambda m: m.text and m.text.lower() in ["удвоить", "удвой", "double", "дабл"]
    )

    # Команды логов
    dp.register_message_handler(
        lambda m: handler.show_logs_command(m, False),
        lambda m: m.text and m.text.lower() == "лог"
    )
    dp.register_message_handler(
        lambda m: handler.show_logs_command(m, True),
        lambda m: m.text and m.text.lower() == "!лог"
    )

    # Текстовые ставки
    BET_PATTERNS = [
        r'^\d+\s*[kк]?\s+',
        r'\d+\s*-\s*\d+',
    ]
    BET_KEYWORDS = ["на", "ставка", "ставку", "ставки", "красн", "черн", "зелен", "кр ", "ч ", "з "]
    VABANK_KEYWORDS = ["ва-банк", "вабанк", "ва банк"]

    dp.register_message_handler(
        handler.place_bet,
        lambda m: m.text and (
                any(word in m.text.lower() for word in BET_KEYWORDS) or
                any(m.text.lower().startswith(keyword) for keyword in VABANK_KEYWORDS) or
                any(re.search(pattern, m.text.lower()) for pattern in BET_PATTERNS)
        ),
        content_types=["text"],
        state="*"
    )

    # Callback обработчики
    dp.register_callback_query_handler(
        handler.handle_callback,
        lambda c: c.data in ["donate_shop", "zero_balance_bonus", "zero_balance_donate",
                             "check_subscription", "get_free_bonus", "go_to_donate",
                             "honest_subscription", "back_to_chat", "back_to_shop"]
    )

    # Обработчики callback рулетки
    dp.register_callback_query_handler(
        handler.handle_callback,
        lambda c: c.data and (
            any(c.data.startswith(prefix) for prefix in ["bet:", "quick:", "action:"])
        )
    )