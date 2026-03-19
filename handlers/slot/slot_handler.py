import logging
import asyncio
import random
import re
from datetime import datetime, timedelta
from aiogram import types, Dispatcher
from aiogram.utils.exceptions import RetryAfter

from .slot_game import SlotGame, SlotDatabase
from database.models import Chat
# game_lock removed — slots and roulette now work independently

logger = logging.getLogger(__name__)


class SlotHandler:
    """Обработчик команд игры в слот"""

    def __init__(self):
        self.game = SlotGame()
        self.db = SlotDatabase()
        self.active_chats = set()  # Чаты где игра включена
        self.user_cooldowns = {}  # Кулдауны пользователей
        self.active_spins = {}  # Активные вращения по пользователям

    async def slot_command(self, message: types.Message):
        """Обработка команды слот/!слот"""
        # Проверяем сообщение
        text = message.text or ''
        text_lower = text.lower().strip()

        # Проверяем, что сообщение точно команда "слот" или "!слот"
        # Без аргументов или с аргументами
        if text_lower not in ['слот', '!слот'] and not (
                text_lower.startswith('слот ') or
                text_lower.startswith('!слот ')
        ):
            return

        # Если просто "слот" или "!слот" без аргументов - показываем справку
        if text_lower in ['слот', '!слот']:
            await self._show_help(message)
            return

        # Проверяем, не активен ли уже спин у пользователя (ГЛОБАЛЬНАЯ БЛОКИРОВКА)
        user_id = message.from_user.id
        if user_id in self.active_spins:
            await message.reply("⏳ У вас уже запущена игра! Дождитесь результата.")
            return

        # Устанавливаем флаг активного спина (для совместимости можно оставить, но lock уже есть)
        self.active_spins[user_id] = True

        try:
            # Проверяем, что игра включена в чате
            chat_id = message.chat.id
            if not await self._is_game_enabled(chat_id):
                await message.reply("🎰 Игра 'Слот' отключена в этом чате\n"
                                    "Для включения используйте !slon")
                self.active_spins.pop(user_id, None)
                return

            # Парсим ставку
            try:
                # Извлекаем аргумент после "слот" или "!слот"
                parts = text_lower.split()
                if len(parts) < 2:
                    await self._show_help(message)
                    self.active_spins.pop(user_id, None)
                    return

                bet_str = parts[1]

                # Парсим ставку (поддержка K/M)
                bet = self.game.parse_bet(bet_str)

                # Проверяем ставку
                if not self.game.is_valid_bet(bet):
                    min_bet = self.game.config.MIN_BET
                    max_bet = self.game.config.MAX_BET
                    await message.reply(
                        f" Недопустимая ставка!\n"
                        f"Минимальная: {min_bet:,}\n"
                        f"Максимальная: {max_bet:,}\n"
                        f"Пример: слот 1000 или слот 1k или слот 2.5m"
                    )
                    self.active_spins.pop(user_id, None)
                    return

            except ValueError as e:
                logger.error(f"Error parsing bet: {e}")
                await self._show_help(message)
                self.active_spins.pop(user_id, None)
                return

            # Проверяем баланс
            balance = self.db.get_user_balance(user_id)

            if balance < bet:
                await message.reply(
                    f" Недостаточно средств!\n"
                    f"💰 Ваш баланс: {balance:,}\n"
                    f"🎰 Ставка: {bet:,}"
                )
                self.active_spins.pop(user_id, None)
                return

            # Снимаем ставку с описанием для истории
            if not self.db.update_user_balance(user_id, -bet, "Ставка"):
                await message.reply(" Ошибка при списании средств")
                self.active_spins.pop(user_id, None)
                return

            # Отправляем начальное сообщение
            loading_text = (
                f"🎰 <b>Игрок:</b> {message.from_user.first_name}\n"
                f"💰 <b>Ставка:</b> {bet:,} Монет\n\n"
                f"🔄 <i>Начинаем вращение...</i>"
            )

            try:
                loading_msg = await message.reply(loading_text, parse_mode="HTML")
            except RetryAfter as e:
                # Ждем если flood control
                await asyncio.sleep(e.timeout)
                loading_msg = await message.reply(loading_text, parse_mode="HTML")

            # === АНИМАЦИЯ ПООЧЕРЕДНОГО ЗАМЕДЛЕНИЯ ===

            # 1. Быстрое вращение всех барабанов (5 шагов вместо 8 — меньше давления на API)
            for step in range(5):
                animated_reels = []
                for _ in range(3):
                    drum = random.choices(
                        self.game.config.SYMBOLS,
                        k=3
                    )
                    animated_reels.append(drum)

                # Создаем анимированное отображение
                animated_display = self._get_reels_display(animated_reels)
                animation_text = (
                    f"🎰 <b>Игрок:</b> {message.from_user.first_name}\n"
                    f"💰 <b>Ставка:</b> {bet:,} Монет\n\n"
                    f"🔄 <b>Барабаны крутятся:</b>\n"
                    f"{animated_display}\n\n"
                    f"<i>Ускоряемся...</i>"
                )

                try:
                    await loading_msg.edit_text(animation_text, parse_mode="HTML")
                except:
                    pass

                # Быстрая смена в начале
                if step < 3:
                    await asyncio.sleep(0.2)
                else:
                    await asyncio.sleep(0.4)  # Начинаем замедляться

            # 2. Замедление первого барабана
            for step in range(3):
                animated_reels = self._generate_partial_result(step=step)
                animated_display = self._get_reels_display(animated_reels)

                status = "🔄 <b>Замедляем 1й барабан...</b>" if step == 0 else \
                    "🔄 <b>Замедляем 2й барабан...</b>" if step == 1 else \
                        "🔄 <b>Замедляем 3й барабан...</b>"

                animation_text = (
                    f"🎰 <b>Игрок:</b> {message.from_user.first_name}\n"
                    f"💰 <b>Ставка:</b> {bet:,} Монет\n\n"
                    f"{status}\n"
                    f"{animated_display}"
                )

                try:
                    await loading_msg.edit_text(animation_text, parse_mode="HTML")
                except:
                    pass

                # Постепенно увеличиваем задержку
                await asyncio.sleep(0.5 + step * 0.3)

            # Генерируем финальный результат
            result = self.game.spin(bet, user_id)

            # 3. Показываем финальный результат с паузами
            final_display = result.get_reels_display()
            animation_text = (
                f"🎰 <b>Игрок:</b> {message.from_user.first_name}\n"
                f"💰 <b>Ставка:</b> {bet:,} Монет\n\n"
                f"🎰 <b>РЕЗУЛЬТАТ:</b>\n"
                f"{final_display}"
            )

            try:
                await loading_msg.edit_text(animation_text, parse_mode="HTML")
            except:
                pass

            await asyncio.sleep(0.8)

            # Начисляем выигрыш если есть с описанием для истории
            if result.win_amount > 0:
                # Определяем тип выигрыша для истории
                win_type_for_history = self._get_win_type_for_history(result)
                self.db.update_user_balance(user_id, result.win_amount, win_type_for_history)

            # Получаем новый баланс
            new_balance = self.db.get_user_balance(user_id)

            # Формируем финальный результат
            result_text = (
                f"🎰 <b>СЛОТ</b>\n\n"
                f"<b>Игрок:</b> {message.from_user.first_name}\n"
                f"<b>Ставка:</b> {bet:,} Монет\n\n"
                f"<b>Результат:</b>\n"
                f"{result.get_reels_display()}\n\n"
                f"<b>{result.get_win_message()}</b>\n"
            )

            if result.win_amount > 0:
                result_text += (
                    f"\n🎉 <b>Выигрыш:</b> {result.win_amount:,} Монет"
                )
            else:
                result_text += (
                    f"\n😢 <b>Выигрыш:</b> 0 Монет"
                )

            # Обновляем сообщение с результатом
            try:
                await loading_msg.edit_text(result_text, parse_mode="HTML")
            except RetryAfter as e:
                await asyncio.sleep(e.timeout)
                await loading_msg.edit_text(result_text, parse_mode="HTML")
            except Exception:
                # Если не удалось отредактировать, отправляем новое
                await message.answer(result_text, parse_mode="HTML")

            # Если выигрыш, добавляем эффект мигания ячеек
            if result.win_amount > 0:
                await self._send_win_effect_with_highlight(loading_msg, result, message)

        except Exception as e:
            logger.error(f"Error in slot command: {e}", exc_info=True)
            try:
                await message.answer(" Произошла ошибка при запуске игры")
            except:
                pass
        finally:
            self.active_spins.pop(user_id, None)

    def _get_win_type_for_history(self, result) -> str:
        """Возвращает описание выигрыша для истории"""
        if result.win_type == "three_sevens":
            return "Джекпот 777"
        elif result.win_type == "three_drums":
            return "3 барабана"
        elif result.win_type == "two_drums":
            return "2 барабана"
        elif result.win_type == "single_drum":
            return "1 барабан"
        else:
            return "Выигрыш"

    def _generate_partial_result(self, step: int = 0):
        """Генерирует частичный результат для анимации"""
        # Генерируем случайные символы
        reels = []
        for _ in range(3):
            drum = random.choices(
                self.game.config.SYMBOLS,
                k=3
            )
            reels.append(drum)

        # Если это последний шаг, делаем более "реальные" комбинации
        if step == 2:
            # Увеличиваем шанс на выигрышные комбинации для демонстрации
            symbols = self.game.config.SYMBOLS
            # Создаем барабан с одинаковыми символами
            same_symbol = random.choice(symbols[:8])  # Без семерок
            reels[0] = [same_symbol] * 3
            reels[1] = [same_symbol] * 3
            reels[2] = [same_symbol] * 3

        return reels

    def _get_reels_display(self, reels):
        """Форматирует барабаны для отображения"""
        lines = []
        for i in range(3):  # 3 строки (ячейки)
            row = []
            for drum in reels:
                row.append(drum[i].value)
            lines.append(f"|{'|'.join(row)}|")
        return "\n".join(lines)

    async def _send_win_effect_with_highlight(self, message_obj: types.Message, result,
                                              original_message: types.Message):
        """Эффект мигания с подсветкой выигрышных ячеек"""
        if result.win_amount == 0:
            return

        # Получаем символы для подсветки
        reels_display = result.get_reels_display()
        lines = reels_display.split('\n')

        # Определяем какие ячейки подсвечивать
        highlight_cells = self._get_highlight_cells(result)

        # Цикл мигания (2 раза — меньше API вызовов для совместимости с другими играми)
        for flash_count in range(2):
            # Мигаем подсветкой
            for state in [True, False]:
                if state:
                    # Подсвеченное состояние
                    modified_lines = []
                    for line_idx, line in enumerate(lines):
                        cells = line.split('|')
                        new_cells = []
                        for cell_idx, cell in enumerate(cells):
                            if cell.strip():
                                if (line_idx, cell_idx) in highlight_cells:
                                    # Подсвечиваем ячейку
                                    new_cells.append(f"✨{cell}✨")
                                else:
                                    new_cells.append(cell)
                        modified_lines.append(f"|{'|'.join(new_cells)}|")
                    highlighted_display = "\n".join(modified_lines)
                else:
                    # Обычное состояние
                    highlighted_display = reels_display

                # Обновляем сообщение с подсветкой
                try:
                    # Создаем текст с эффектом
                    effect_text = (
                        f"🎰 <b>СЛОТ</b>\n\n"
                        f"<b>Игрок:</b> {original_message.from_user.first_name}\n"
                        f"<b>Ставка:</b> {result.bet:,} Монет\n\n"
                        f"<b>Результат:</b>\n"
                        f"{highlighted_display}\n\n"
                        f"<b>{result.get_win_message()}</b>\n"
                        f"\n✨ <b>ВЫИГРЫШ!</b> ✨"
                    )

                    await message_obj.edit_text(effect_text, parse_mode="HTML")
                except:
                    pass

                await asyncio.sleep(0.3)

        # Возвращаем к обычному виду
        final_text = (
            f"🎰 <b>СЛОТ</b>\n\n"
            f"<b>Игрок:</b> {original_message.from_user.first_name}\n"
            f"<b>Ставка:</b> {result.bet:,} Монет\n\n"
            f"<b>Результат:</b>\n"
            f"{reels_display}\n\n"
            f"<b>{result.get_win_message()}</b>\n"
            f"\n🎉 <b>Выигрыш:</b> {result.win_amount:,} Монет"
        )

        try:
            await message_obj.edit_text(final_text, parse_mode="HTML")
        except:
            pass

    def _get_highlight_cells(self, result):
        """Определяет какие ячейки нужно подсветить"""
        highlight_cells = set()

        if result.win_type == "single_drum":
            # Находим барабан с одинаковыми символами
            for drum_idx, drum in enumerate(result.reels):
                if len(set(drum)) == 1:
                    # Подсвечиваем все ячейки этого барабана
                    for row in range(3):
                        highlight_cells.add((row, drum_idx))
                    break

        elif result.win_type == "two_drums":
            # Находим два одинаковых барабана подряд
            for i in range(len(result.reels) - 1):
                if result.reels[i] == result.reels[i + 1]:
                    # Подсвечиваем оба барабана
                    for drum_idx in [i, i + 1]:
                        for row in range(3):
                            highlight_cells.add((row, drum_idx))
                    break

        elif result.win_type == "three_drums" or result.win_type == "three_sevens":
            # Подсвечиваем все три барабана
            for drum_idx in range(3):
                for row in range(3):
                    highlight_cells.add((row, drum_idx))

        return highlight_cells

    async def _show_help(self, message: types.Message):
        """Показывает справку по игре"""
        min_bet = self.game.config.MIN_BET
        max_bet = self.game.config.MAX_BET

        help_text = (
            f"🎰 <b>Игра 'Слот'</b>\n\n"
            f"<b>Команда:</b> <code>слот [ставка]</code> или <code>!слот [ставка]</code>\n"
            f"<b>Примеры:</b>\n"
            f"<code>слот 1000</code>\n"
            f"<code>слот 1k</code> (1,000 Монет)\n"
            f"<code>слот 2.5k</code> (2,500 Монет)\n"
            f"<code>слот 1m</code> (1,000,000 Монет)\n"
            f"<code>!слот 5000000</code>\n\n"
            f"<b>Допустимые ставки:</b> от {min_bet:,} до {max_bet:,} Монет\n\n"
            f"<b>Правила:</b>\n"
            f"• 3 одинаковых на 1 барабане → ×2\n"
            f"• 2 барабана подряд одинаковые → ×6\n"
            f"• 3 барабана одинаковые → ×9\n"
            f"• 777 на всех барабанах → ×12\n\n"
            f"<b>Управление игрой (админы):</b>\n"
            f"<code>!slon</code> - включить игру в чате\n"
            f"<code>!sloff</code> - выключить игру в чате\n\n"
            f"<b>История:</b> Все ставки и выигрыши сохраняются в истории операций"
        )

        await message.reply(help_text, parse_mode="HTML")

    async def _is_game_enabled(self, chat_id: int) -> bool:
        """Проверяет, включена ли игра в чате"""
        # Проверяем в БД
        from database import SessionLocal
        db = SessionLocal()
        try:
            chat = db.query(Chat).filter(Chat.chat_id == chat_id).first()
            return chat.slots_enabled if chat else True  # По умолчанию включено
        except:
            return True
        finally:
            db.close()

    async def slot_on_command(self, message: types.Message):
        """Команда !slon - включить игру в чате"""
        if not await self._check_admin(message):
            await message.reply(" Только администраторы могут управлять игрой")
            return

        chat_id = message.chat.id
        from database import SessionLocal
        db = SessionLocal()
        try:
            chat = db.query(Chat).filter(Chat.chat_id == chat_id).first()
            if chat:
                chat.slots_enabled = True
            else:
                # Создаем запись о чате
                chat = Chat(
                    chat_id=chat_id,
                    title=message.chat.title,
                    chat_type=message.chat.type,
                    is_active=True,
                    slots_enabled=True,
                    basketball_enabled=True
                )
                db.add(chat)

            db.commit()
            self.active_chats.add(chat_id)
            await message.reply("✅ Игра 'Слот' включена в этом чате!")
        except Exception as e:
            logger.error(f"Error enabling slot game: {e}")
            await message.reply(" Ошибка при включении игры")
        finally:
            db.close()

    async def slot_off_command(self, message: types.Message):
        """Команда !sloff - выключить игру в чате"""
        if not await self._check_admin(message):
            await message.reply(" Только администраторы могут управлять игрой")
            return

        chat_id = message.chat.id
        from database import SessionLocal
        db = SessionLocal()
        try:
            chat = db.query(Chat).filter(Chat.chat_id == chat_id).first()
            if chat:
                chat.slots_enabled = False
                db.commit()
                self.active_chats.discard(chat_id)
                await message.reply(" Игра 'Слот' выключена в этом чате")
            else:
                await message.reply("ℹ️ Игра еще не была активирована в этом чате")
        except Exception as e:
            logger.error(f"Error disabling slot game: {e}")
            await message.reply(" Ошибка при выключении игры")
        finally:
            db.close()

    async def _check_admin(self, message: types.Message) -> bool:
        """Проверяет, является ли пользователь администратором"""
        try:
            chat_member = await message.bot.get_chat_member(
                message.chat.id,
                message.from_user.id
            )
            return chat_member.is_chat_admin()
        except:
            return False


def register_slot_handlers(dp: Dispatcher):
    """Регистрация обработчиков игры в слот"""
    handler = SlotHandler()

    # Регистрируем обработчик для команд "слот" и "!слот" (с пробелом или без)
    dp.register_message_handler(
        handler.slot_command,
        lambda m: m.text and m.text.strip().lower() in ['слот', '!слот'] or
                  m.text and (m.text.lower().startswith('слот ') or
                              m.text.lower().startswith('!слот ')),
        state="*"
    )

    # Команды управления
    dp.register_message_handler(
        handler.slot_on_command,
        lambda m: m.text and m.text.lower().startswith('!slon'),
        state="*"
    )
    dp.register_message_handler(
        handler.slot_off_command,
        lambda m: m.text and m.text.lower().startswith('!sloff'),
        state="*"
    )

    logger.info("✅ Обработчики игры 'Слот' зарегистрированы")