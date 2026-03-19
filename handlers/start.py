# start.py
from typing import List, Dict
from dataclasses import dataclass

from aiogram import types, Dispatcher

from config import bot
from database.crud import UserRepository
from handlers.link_texts_simple import link_texts
import logging


logger = logging.getLogger(__name__)





# =============================================================================
# УТИЛИТЫ ДЛЯ ФОРМАТИРОВАНИЯ
# =============================================================================

class UserFormatter:
    """Утилиты для форматирования имен пользователей с ссылками"""

    __slots__ = ()

    @staticmethod
    def get_display_name(user: types.User) -> str:
        """Получает отображаемое имя пользователя"""
        if user.first_name:
            return user.first_name
        elif user.username:
            return f"@{user.username}"
        return "Аноним"

    @staticmethod
    def get_user_link_html(user_id: int, display_name: str) -> str:
        """Создает HTML-ссылку на профиль пользователя"""
        safe_name = display_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return f'<a href="tg://user?id={user_id}">{safe_name}</a>'

    @staticmethod
    def format_user_html(user: types.User) -> str:
        """Форматирует объект пользователя с HTML-ссылкой"""
        display_name = UserFormatter.get_display_name(user)
        return UserFormatter.get_user_link_html(user.id, display_name)

    @staticmethod
    def format_user_by_data_html(user_id: int, username: str, first_name: str) -> str:
        """Форматирует пользователя по данным с HTML-ссылкой"""
        display_name = first_name if first_name else (username if username else "Аноним")
        return UserFormatter.get_user_link_html(user_id, display_name)


# =============================================================================
# СЕРВИС ПРОФИЛЯ
# =============================================================================

class ProfileService:
    """Сервис для работы с профилями пользователей"""

    __slots__ = ('_user_formatter',)

    def __init__(self, user_formatter: UserFormatter):
        self._user_formatter = user_formatter

    def format_profile_text(self, user, telegram_user_id: int) -> str:
        """Форматирует текст профиля игрока"""

        # 1. Имя пользователя (ник) с кликабельной ссылкой
        display_name = user.first_name or "Anonymous"
        user_link = f'<a href="tg://user?id={telegram_user_id}">{display_name}</a>'

        # 2. Status: Донат-статус с иконками из ТЗ
        from handlers.donate.status_repository import StatusRepository
        status_repo = StatusRepository()
        active_status = status_repo.get_user_active_status(telegram_user_id)

        # Маппинг иконок из ТЗ
        status_icons = {
            1: "🐾",  # Обычный
            2: "🌑",  # Бронза
            3: "💷",  # Платина
            4: "🥇",  # Золото
            5: "💎",  # Бриллиант
        }

        if active_status and active_status['status_id'] != 1:
            status_id = active_status['status_id']
            status_icon = status_icons.get(status_id, "🐾")
            status_name = active_status['status_name'].title()

            # Если есть ссылка в статусе (выдан через /status с ссылкой)
            if active_status.get('link_url'):
                status_line = f'Status: <a href="{active_status["link_url"]}">{status_name}{status_icon}</a>\n'
            else:
                status_line = f"Status: {status_name}{status_icon}\n"
        else:
            # Обычный статус или отсутствие статуса скрываем
            status_line = ""

        # 3. Клан: информация о клане пользователя
        clan_info = self._get_clan_info(telegram_user_id)

        # 4. Монеты (фактический баланс)
        coins_amount = int(user.coins) if user.coins else 0

        # 5. Выиграно
        win_amount = int(user.win_coins) if user.win_coins else 0

        # 6. Проиграно
        defeat_amount = int(user.defeat_coins) if user.defeat_coins else 0

        # 7. Макс. ставка
        max_bet = int(getattr(user, 'max_bet', 0))

        # 8. Макс. выигрыш
        max_win = int(user.max_win_coins) if user.max_win_coins else 0


        max_defeat = int(user.roulette_max_loss) if user.roulette_max_loss else 0

        # Формируем профиль (без лицензий, без информации о супруге)
        marriage_info = self._get_marriage_info(telegram_user_id)

        profile_text = (
            f"{display_name}\n"
            f"{status_line}"
            f"Клан: {clan_info}\n"
            f"{marriage_info}"
            f"Монет: {coins_amount}\n"
            f"Выиграно: {win_amount}\n"
            f"Проиграно: {defeat_amount}\n"
            f"Макс. ставка: {max_bet}\n"
            f"Макс. выигрыш: {max_win}\n"
            f"Макс. проигрыш: {max_defeat}"

        )

        return profile_text


    def _get_marriage_info(self, user_id: int) -> str:
        """Возвращает строку про супруга/супругу для профиля."""
        from database import SessionLocal
        from database import models

        db = SessionLocal()
        try:
            m = db.query(models.Marriage).filter(
                (models.Marriage.groom_id == user_id) | (models.Marriage.bride_id == user_id)
            ).order_by(models.Marriage.created_at.desc()).first()

            if not m:
                return ""

            if m.groom_id == user_id:
                spouse_id = m.bride_id
                label = "💍 Жена"
            else:
                spouse_id = m.groom_id
                label = "💍 Муж"

            spouse = db.query(models.TelegramUser).filter(models.TelegramUser.telegram_id == spouse_id).first()
            if spouse:
                spouse_name = spouse.first_name or (spouse.username or "Аноним")
            else:
                spouse_name = "Аноним"

            spouse_link = self._user_formatter.get_user_link_html(int(spouse_id), spouse_name)
            return f"{label}: {spouse_link}\n"

        except Exception as e:
            logging.error(f" Ошибка получения брака: {e}")
            return ""
        finally:
            db.close()

    def _get_clan_info(self, user_id: int) -> str:
        """Получает информацию о клане пользователя"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            from database.clan_models import ClanMember, Clan

            # Проверяем, состоит ли пользователь в клане
            member = db.query(ClanMember).filter(
                ClanMember.user_id == user_id
            ).first()

            if not member:
                return "Не состоит в клане"

            # Получаем информацию о клане
            clan = db.query(Clan).filter(Clan.id == member.clan_id).first()

            if clan:
                return f"{clan.name} [{clan.tag}]"
            else:
                return "Неизвестный клан"

        except Exception as e:
            logging.error(f" Ошибка получения информации о клане: {e}")
            return "Ошибка загрузки"
        finally:
            db.close()

    def _get_license_count(self, user_id: int) -> Dict[str, int]:
        """Получает количество лицензий пользователя"""
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Подсчитываем обычные лицензии (item_id = 3)
            standard_result = db.execute(
                text("""
                     SELECT COUNT(*) as count
                     FROM user_purchases
                     WHERE user_id = :user_id
                       AND item_id = 3
                       AND
                         (expires_at IS NULL
                        OR expires_at
                         > NOW())
                     """),
                {"user_id": user_id}
            ).fetchone()

            # Подсчитываем VIP-лицензии (item_id = 4)
            vip_result = db.execute(
                text("""
                     SELECT COUNT(*) as count
                     FROM user_purchases
                     WHERE user_id = :user_id
                       AND item_id = 4
                       AND
                         (expires_at IS NULL
                        OR expires_at
                         > NOW())
                     """),
                {"user_id": user_id}
            ).fetchone()

            standard_count = standard_result[0] if standard_result else 0
            vip_count = vip_result[0] if vip_result else 0

            return {
                'standard': standard_count,
                'vip': vip_count
            }

        except Exception as e:
            logging.error(f" Ошибка подсчета лицензий: {e}")
            return {'standard': 0, 'vip': 0}
        finally:
            db.close()


# =============================================================================
# ОСНОВНЫЕ ОБРАБОТЧИКИ
# =============================================================================

class StartHandlers:
    """Обработчики стартовых команд и меню"""

    __slots__ = ('_user_formatter', '_privilege_service', '_profile_service')

    def __init__(self):
        self._user_formatter = UserFormatter()
        self._profile_service = ProfileService(self._user_formatter)


    async def start_button(self, message: types.Message) -> None:
        """Обработчик команды /start"""
        command = message.get_full_command()
        payload = command[1] if len(command) > 1 else None

        # Обрабатываем реферальную ссылку (если есть)
        if payload:
            # Импортируем реферальный сервис из reference.py
            from handlers.reference import referral_service
            await referral_service.process_referral(message, payload)

        await self._send_main_menu(message)

    async def _send_main_menu(self, message: types.Message) -> None:
        """Отправляет главное меню"""
        try:
            # Используем просто имя пользователя без ссылки
            username = message.from_user.username
            if username:
                greeting = f"Привет, @{username}!"
            else:
                greeting = f"Привет, {message.from_user.first_name}!"

            start_text = (
                f"{greeting}\n"
                f"Добро пожаловать в @TopTashPlusBot\n\n"
                f"Начав использование бота Вы подтверждаете свое согласие с\n"
                f"<a href='https://t.me/+n2uMkFplNpQwNDY6'>Пользовательским соглашением</a>"
            )

            # Импортируем клавиатуру
            from keyboards.main_menu_kb import start_menu_keyboard

            await bot.send_message(
                chat_id=message.chat.id,
                text=start_text,
                parse_mode=types.ParseMode.HTML,
                reply_markup=start_menu_keyboard()
            )
        except Exception as e:
            logging.error(f" Ошибка в _send_main_menu: {e}")
            await message.answer(" Ошибка загрузки меню")

    # ---------- ТЕКСТОВЫЕ КОМАНДЫ ----------

    async def profile_command(self, message: types.Message):
        """Обработчик текстовой команды 'профиль'"""
        try:
            from database import get_db
            db = next(get_db())
            try:
                user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)

                if not user:
                    await message.reply(" Профиль не найден")
                    return

                profile_text = self._profile_service.format_profile_text(
                    user, message.from_user.id
                )

                # Используем HTML для кликабельных статусов
                await message.reply(profile_text, parse_mode=types.ParseMode.HTML)

            finally:
                db.close()
        except Exception as e:
            logging.error(f" Ошибка в profile_command: {e}")
            await message.reply(" Ошибка загрузки профиля")

    async def links_command(self, message: types.Message):
        """Обработчик текстовой команды 'ссылки'"""
        try:
            links_text = link_texts.get()
            # Используем HTML парсинг вместо Markdown
            await message.reply(links_text, parse_mode=types.ParseMode.HTML)
        except Exception as e:
            logging.error(f" Ошибка в links_command: {e}")
            await message.reply(" Ошибка загрузки ссылок")

    async def id_command(self, message: types.Message):
        """Обработчик команды /id - показывает ID пользователя"""
        try:
            # Определяем, чей ID показывать
            if message.reply_to_message:
                # Если это ответ на сообщение - показываем ID того пользователя
                target_user = message.reply_to_message.from_user
                user_type = "Пользователь"
            else:
                # Иначе показываем ID отправителя команды
                target_user = message.from_user
                user_type = "Ваш ID" if message.chat.type == 'private' else "Пользователь"

            user_id = target_user.id
            user_name = self._user_formatter.get_display_name(target_user)

            # Форматируем ответ
            if message.reply_to_message:
                response = (
                    f"{user_type}: {user_name}\n"
                    f"ID: <code>{user_id}</code>"
                )
            else:
                if message.chat.type == 'private':
                    response = (
                        f"Ваш профиль: {user_name}\n"
                        f"Ваш ID: <code>{user_id}</code>"
                    )
                else:
                    response = (
                        f"{user_type}: {user_name}\n"
                        f"ID: <code>{user_id}</code>\n\n"
                    )

            await message.reply(response, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            logging.error(f" Ошибка в id_command: {e}")
            await message.reply(" Ошибка выполнения команды")

    # ---------- INLINE КНОПКИ ----------

    async def profile_button(self, callback: types.CallbackQuery) -> None:
        """Показ профиля через inline кнопку"""
        try:
            from database import get_db
            db = next(get_db())
            try:
                user = UserRepository.get_user_by_telegram_id(db, callback.from_user.id)

                if not user:
                    await callback.answer(" Профиль не найден", show_alert=True)
                    return

                profile_text = self._profile_service.format_profile_text(
                    user, callback.from_user.id
                )
                await callback.message.edit_text(profile_text, parse_mode=types.ParseMode.HTML)
                await callback.answer()

            finally:
                db.close()
        except Exception as e:
            logging.error(f" Ошибка в profile_button: {e}")
            await callback.answer(" Ошибка загрузки профиля", show_alert=True)

    async def reference_button(self, callback: types.CallbackQuery) -> None:
        """Показ реферального меню"""
        try:
            from handlers.reference import reference_menu_call
            await reference_menu_call(callback)
        except Exception as e:
            logging.error(f" Ошибка в reference_button: {e}")
            await callback.answer(" Ошибка загрузки реферального меню", show_alert=True)

    async def links_button(self, callback: types.CallbackQuery) -> None:
        """Показ ссылок через inline кнопку"""
        try:
            links_text = link_texts.get()
            await callback.message.edit_text(links_text, parse_mode=types.ParseMode.HTML)
            await callback.answer()
        except Exception as e:
            logging.error(f" Ошибка в links_button: {e}")
            await callback.answer(" Ошибка загрузки ссылок", show_alert=True)

    async def shop_button(self, callback: types.CallbackQuery) -> None:
        from handlers.modroul.shop import ShopHandler
        """Переход в магазин"""
        try:
            shop_handler = ShopHandler()
            await shop_handler.shop_command(callback.message)
            await callback.answer()
        except Exception as e:
            logging.error(f" Ошибка в shop_button: {e}")
            await callback.answer(" Ошибка загрузки магазина", show_alert=True)

    async def roulette_button(self, callback: types.CallbackQuery) -> None:
        from handlers.roulette import RouletteHandler
        """Переход в рулетку"""
        try:
            roulette_handler = RouletteHandler()
            await roulette_handler.start_roulette(callback.message)
            await callback.answer()
        except Exception as e:
            logging.error(f" Ошибка в roulette_button: {e}")
            await callback.answer(" Ошибка загрузки рулетки", show_alert=True)



    async def donate_button(self, callback: types.CallbackQuery) -> None:
        from handlers.donate import DonateHandler

        """Переход к донату"""
        try:
            donate_handler = DonateHandler()
            await donate_handler.donate_command(callback.message)
            await callback.answer()
        except Exception as e:
            logging.error(f" Ошибка в donate_button: {e}")
            await callback.answer(" Ошибка загрузки доната", show_alert=True)



    async def language_button(self, callback: types.CallbackQuery) -> None:
        """Обработчик кнопки выбора языка"""
        try:
            await callback.message.edit_text(
                "🌐 Выбор языка\n\n"
                "Доступные языки:\n"
                "• Русский\n"
                "• English\n"
                "• O'zbek\n\n"
                "Выберите язык:",
                parse_mode=types.ParseMode.HTML,
                reply_markup=self._get_language_keyboard()
            )
            await callback.answer()
        except Exception as e:
            logging.error(f" Ошибка в language_button: {e}")
            await callback.answer(" Ошибка загрузки выбора языка", show_alert=True)

    async def clans_button(self, callback: types.CallbackQuery) -> None:
        """Обработчик кнопки кланов - запускает систему кланов"""
        try:
            # Импортируем клавиатуры из системы кланов
            from handlers.clan.clan_keyboards import get_main_clan_keyboard

            # Создаем текст приветствия для системы кланов
            clans_text = (
                "🏰 <b>Система кланов</b>\n\n"
                "Здесь вы можете создавать кланы, приглашать друзей "
                "и соревноваться с другими игроками!\n\n"
                "<b>Доступные действия:</b>\n"
                "• Создать свой клан\n"
                "• Присоединиться к существующему\n"
                "• Управлять своим кланом\n"
                "• Смотреть топ кланов\n"
                "• И многое другое!"
            )

            # Редактируем текущее сообщение, показывая меню кланов
            await callback.message.edit_text(
                clans_text,
                parse_mode="HTML",
                reply_markup=get_main_clan_keyboard()
            )
            await callback.answer()

        except Exception as e:
            logging.error(f" Ошибка в clans_button: {e}", exc_info=True)
            await callback.answer(" Ошибка загрузки системы кланов", show_alert=True)

    def _get_language_keyboard(self):
        """Клавиатура для выбора языка"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        keyboard = InlineKeyboardMarkup(row_width=2)

        languages = [
            ("🇷🇺 Русский", "ru"),
            ("🇺🇸 English", "en"),
            ("🇺🇿 O'zbek", "uz"),
        ]

        for name, code in languages:
            keyboard.add(InlineKeyboardButton(name, callback_data=f"set_lang_{code}"))

        keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="back_to_main"))

        return keyboard

    async def _send_main_menu_callback(self, callback: types.CallbackQuery) -> None:
        """Возврат к главному меню из callback"""
        from keyboards.main_menu_kb import start_menu_keyboard

        try:
            username = callback.from_user.username
            if username:
                greeting = f"Привет, @{username}!"
            else:
                greeting = f"Привет, {callback.from_user.first_name}!"

            start_text = (
                f"{greeting}\n"
                f"Добро пожаловать в @TopTashPlusBot\n\n"
                f"Начав использование бота Вы подтверждаете свое согласие с\n"
                f"<a href='https://t.me/+n2uMkFplNpQwNDY6'>Пользовательским соглашением</a>"
            )

            await callback.message.edit_text(
                text=start_text,
                parse_mode=types.ParseMode.HTML,
                reply_markup=start_menu_keyboard()
            )
            await callback.answer()
        except Exception as e:
            logging.error(f" Ошибка при возврате в главное меню: {e}")
            await callback.answer(" Ошибка", show_alert=True)


# =============================================================================
# РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# =============================================================================

def register_start_handler(dp: Dispatcher) -> None:
    """Регистрация обработчиков стартовых команд"""
    handlers = StartHandlers()

    # Команды
    dp.register_message_handler(handlers.start_button, commands=['start'])
    dp.register_message_handler(handlers.id_command, commands=['id'])

    # Текстовые команды
    dp.register_message_handler(
        handlers.profile_command,
        lambda message: message.text and message.text.strip().lower() == 'профиль'
    )
    dp.register_message_handler(
        handlers.links_command,
        lambda message: message.text and message.text.strip().lower() == 'ссылки'
    )


    # inline-кнопки (только нужные)
    callback_handlers = {
        "profile": handlers.profile_button,
        "links": handlers.links_button,
        "reference": handlers.reference_button,
        "shop": handlers.shop_button,
        "donate": handlers.donate_button,
        "language": handlers.language_button,
        "clans": handlers.clans_button,
        "back_to_main": handlers._send_main_menu_callback,
    }

    for callback_data, handler in callback_handlers.items():
        dp.register_callback_query_handler(
            handler,
            lambda c, data=callback_data: c.data == data
        )

    logging.info("✅ Стартовые обработчики зарегистрированы")