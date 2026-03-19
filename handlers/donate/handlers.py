import logging
from aiogram import types, Dispatcher

from .texts_simple import donate_texts
from .config import STATUSES, BONUS_COOLDOWN_HOURS, SUPPORT_USERNAME, COIN_PACKAGES
from .utils import format_time_left
from .status_repository import StatusRepository
from .keyboards import (
    create_main_donate_keyboard, create_statuses_keyboard, create_bonus_keyboard,
    create_buy_keyboard, create_status_purchase_keyboard, create_back_keyboard,
    create_my_status_keyboard, create_direct_purchase_keyboard, create_send_check_keyboard
)
from database.crud import UserRepository
from ..admin.admin_helpers import check_admin_async
from .check_states import CheckStates

logger = logging.getLogger(__name__)


class DonateHandler:
    """Класс для обработки операций доната и статусов"""

    def __init__(self):
        self.logger = logger
        self.status_repo = StatusRepository()

    # --- Вспомогательные методы ---
    async def _ensure_private_chat(self, message: types.Message) -> bool:
        """Проверяет, что команда вызвана в личных сообщениях"""
        if message.chat.type != "private":
            bot_username = (await message.bot.get_me()).username
            bot_link = f"https://t.me/{bot_username}"
            await message.reply(
                "💰<b>Магазин доната</b>\n"
                f"Команда доступна только в <a href='{bot_link}'>личном чате с ботом</a>.",

                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return False
        return True

    def _get_main_donate_text(self) -> str:
        """Форматирует главный текст доната"""
        text = donate_texts.get("main")
        # Заменяем {support_username} если есть
        if "{support_username}" in text:
            text = text.format(support_username=SUPPORT_USERNAME)
        return text

    async def _get_user_status_info(self, user_id: int) -> str:
        """Формирует информацию о статусе пользователя"""
        status = self.status_repo.get_user_active_status(user_id)

        if status:
            # Вычисляем оставшееся время
            days_left = 0
            if status.get('expires_at'):
                from datetime import datetime
                now = datetime.now()
                if status['expires_at'] > now:
                    time_left = status['expires_at'] - now
                    days_left = time_left.days
                else:
                    days_left = 0

            # Получаем бонусную сумму
            bonus_amount = self.status_repo.get_user_bonus_amount(user_id)

            text = donate_texts.get("user_status_info").format(
                status_name=status['status_name'].title(),
                status_icon=self._get_status_icon(status['status_id']),
                bonus_amount=bonus_amount,
                days_left=days_left if days_left > 0 else "0 (истек)",
                next_bonus_time="можно получить сейчас" if self.status_repo.can_receive_bonus(
                    user_id) else "через 24 часа",
                support_username=SUPPORT_USERNAME
            )
        else:
            # Базовый статус
            text = donate_texts.get("user_status_info").format(
                status_name="Обычный",
                status_icon="👤",
                bonus_amount=1_000_000,
                days_left="∞",
                next_bonus_time="можно получить сейчас" if self.status_repo.can_receive_bonus(
                    user_id) else "через 24 часа",
                support_username=SUPPORT_USERNAME
            )

        return text

    def _get_status_icon(self, status_id: int) -> str:
        """Получает иконку статуса"""
        status = next((s for s in STATUSES if s["id"] == status_id), None)
        if status:
            return status.get("icon", "")
        return ""

    # --- Основные команды ---
    async def donate_command(self, message: types.Message):
        """Обработчик команды доната - ИНТЕГРИРОВАННЫЙ С /чек"""
        if not await self._ensure_private_chat(message):
            return

        donate_text = donate_texts.get("main")
        # Добавляем кнопку для отправки чека прямо в главное меню
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        keyboard.row(
            types.InlineKeyboardButton(
                text="💸 Купить Монеты",
                callback_data="donate_buy_coins"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                text="👑 Статусы",
                callback_data="donate_statuses"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                text="🎁 Ежедневный бонус",
                callback_data="daily_bonus"
            )
        )

        # ДОБАВЛЯЕМ КНОПКУ ДЛЯ ОТПРАВКИ ЧЕКА
        keyboard.row(
            types.InlineKeyboardButton(
                text="📸 Отправить чек на покупку",
                callback_data="donate_send_check"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                text="📊 Мои чеки",
                callback_data="donate_my_checks"
            )
        )

        await message.answer(donate_text, reply_markup=keyboard, parse_mode="HTML")

    # --- Callback обработчики ---
    async def donate_callback_handler(self, callback: types.CallbackQuery):
        """Обработчик нажатий на кнопки доната"""
        # Используем callback.message.chat вместо callback.chat
        if callback.message.chat.type != "private":
            await callback.answer("💎 Команда работает только в личных сообщениях", show_alert=True)
            return

        action = callback.data
        user_id = callback.from_user.id

        try:
            if action == "back_to_donate":
                await self._handle_back_to_donate(callback)
            elif action == "donate_buy_coins":
                # Открываем меню с опциями покупки монет
                await self._handle_buy_coins_menu(callback)
            elif action == "donate_statuses":
                # Открываем меню с опциями покупки статуса
                await self._handle_statuses_menu(callback, user_id)
            elif action == "daily_bonus":
                await self._handle_daily_bonus(callback, user_id)
            elif action == "donate_my_checks":
                await self._handle_my_checks(callback, user_id)
            elif action == "donate_send_check":
                await self._handle_send_check(callback, user_id)
            elif action == "donate_full_checks_history":
                await self.donate_full_checks_history(callback)
            elif action == "my_statuses_checks":
                await self._handle_my_statuses_checks(callback, user_id)
            elif action == "claim_bonus":
                await self._handle_claim_bonus(callback, user_id)
            elif action.startswith("status_buy_"):
                await self._handle_status_purchase_selection(callback, user_id)
            elif action.startswith("status_active_"):
                await self._handle_active_status_info(callback, user_id)
            elif action.startswith("limit_"):
                # Обработка выбора суммы для снятия лимита
                await self._handle_limit_amount_selection(callback, user_id)
            # Опции из меню покупки монет
            elif action == "buy_coins_with_check":
                await self._handle_buy_coins_with_check(callback, user_id)
            # Опции из меню покупки статуса
            elif action == "buy_status_with_check":
                await self._handle_buy_status_with_check(callback, user_id)
            # Обработка выбора типа покупки
            elif action.startswith("check_type_"):
                await self._handle_check_type_selection(callback)
            # Обработка выбора пакетов и статусов
            elif action.startswith("coins_") or action.startswith("status_"):
                await self._handle_purchase_details_selection(callback)
            elif action == "check_back_to_type":
                # Возврат к выбору типа покупки
                await self._handle_send_check(callback, user_id)
        except Exception as e:
            self.logger.error(f"Error in donate callback handler: {e}")
            await self._handle_error(callback)

    async def _handle_buy_coins_menu(self, callback: types.CallbackQuery):
        """Показывает меню покупки монет"""
        try:
            text = (
                "💰 <b>Покупка монет</b>\n\n"
                "💎 <b>Доступные пакеты монет:</b>\n"
                "▫️ 250.000 — 100₽\n"
                "▫️ 600.000 — 200₽\n"
                "▫️ 1.300.000 — 400₽\n"
                "▫️ 2.800.000 — 700₽\n"
                "▫️ 6.000.000 — 1.200₽\n"
                "▫️ 14.000.000 — 2.000₽\n"
                "▫️ 28.000.000 — 3.500₽\n"
                "▫️ 60.000.000 — 6.000₽\n"
                "▫️ 110.000.000 — 7.500₽\n\n"
                "📌 <b>Для покупки нажмите кнопку ниже:</b>"
            )

            keyboard = types.InlineKeyboardMarkup(row_width=1)

            # Кнопка для покупки с отправкой чека
            keyboard.row(
                types.InlineKeyboardButton(
                    text="📸 Купить с отправкой чека",
                    callback_data="buy_coins_with_check"
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_donate"
                )
            )

            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling buy coins menu: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def _handle_buy_coins_with_check(self, callback: types.CallbackQuery, user_id: int):
        """Покупка монет через отправку чека"""
        try:
            # Проверяем, не забанен ли пользователь
            from .check_repository import CheckRepository
            check_repo = CheckRepository()
            is_banned, reason = check_repo.is_user_banned(user_id)

            if is_banned:
                await callback.answer(
                    f" Вы забанены в системе.\nПричина: {reason}",
                    show_alert=True
                )
                return

            # Показываем меню выбора пакета монет
            keyboard = types.InlineKeyboardMarkup(row_width=1)

            for package in COIN_PACKAGES:
                keyboard.add(
                    types.InlineKeyboardButton(
                        text=f"💰 {package['amount']:,} монет — {package['rub_price']:,}₽",
                        callback_data=f"coins_{package['amount']}"
                    )
                )

            keyboard.add(
                types.InlineKeyboardButton(
                    text="↩️ Назад",
                    callback_data="donate_buy_coins"
                )
            )

            await callback.message.edit_text(
                "💰 <b>Выберите пакет монет для покупки:</b>\n\n"
                "📌 <b>После выбора:</b>\n"
                "1. Вас попросят отправить скриншот оплаты\n"
                "2. Администратор проверит и начислит монеты\n"
                "3. Обычно обработка занимает до 24 часов\n\n"
                "⚠️ <b>Внимание:</b>\n"
                "• Отправляйте только реальные чеки\n"
                "• Фальшивые чеки приведут к бану",
                parse_mode="HTML",
                reply_markup=keyboard
            )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling buy coins with check: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def _handle_statuses_menu(self, callback: types.CallbackQuery, user_id: int):
        """Показывает меню покупки статусов"""
        try:
            text = (
                "👑 <b>Покупка статуса</b>\n\n"
                "🎖️ <b>Доступные статусы:</b>\n"
                "🌑 <b>Бронза</b> — 3.000₽\n"
                "• Ежедневный бонус: 15.000.000 монет\n"
                "• Срок действия: 30 дней\n\n"
                "💰 <b>Платина</b> — 6.000₽\n"
                "• Ежедневный бонус: 40.000.000 монет\n"
                "• Срок действия: 30 дней\n\n"
                "🥇 <b>Золото</b> — 12.000₽\n"
                "• Ежедневный бонус: 100.000.000 монет\n"
                "• Срок действия: 30 дней\n\n"
                "💎 <b>Бриллиант</b> — 27.000₽\n"
                "• Ежедневный бонус: 800.000.000 монет\n"
                "• Срок действия: 30 дней\n\n"
                "📌 <b>Для покупки нажмите кнопку ниже:</b>"
            )

            keyboard = types.InlineKeyboardMarkup(row_width=1)

            # Кнопка для покупки с отправкой чека
            keyboard.row(
                types.InlineKeyboardButton(
                    text="📸 Купить статус с отправкой чека",
                    callback_data="buy_status_with_check"
                )
            )

            keyboard.row(
                types.InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_donate"
                )
            )

            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling statuses menu: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def _handle_buy_status_with_check(self, callback: types.CallbackQuery, user_id: int):
        """Покупка статуса через отправку чека"""
        try:
            # Проверяем, не забанен ли пользователь
            from .check_repository import CheckRepository
            check_repo = CheckRepository()
            is_banned, reason = check_repo.is_user_banned(user_id)

            if is_banned:
                await callback.answer(
                    f" Вы забанены в системе.\nПричина: {reason}",
                    show_alert=True
                )
                return

            # Показываем меню выбора статуса
            keyboard = types.InlineKeyboardMarkup(row_width=1)

            for status in STATUSES[1:]:  # Пропускаем обычный статус
                keyboard.add(
                    types.InlineKeyboardButton(
                        text=f"{status['icon']} {status['name'].title()} — {status['price_rub']:,}₽",
                        callback_data=f"status_{status['id']}"
                    )
                )

            keyboard.add(
                types.InlineKeyboardButton(
                    text="↩️ Назад",
                    callback_data="donate_statuses"
                )
            )

            await callback.message.edit_text(
                "🎖️ <b>Выберите статус для покупки:</b>\n\n"
                "📌 <b>После выбора:</b>\n"
                "1. Вас попросят отправить скриншот оплаты\n"
                "2. Администратор проверит и активирует статус\n"
                "3. Обычно обработка занимает до 24 часов\n\n"
                "⚠️ <b>Внимание:</b>\n"
                "• Отправляйте только реальные чеки\n"
                "• Фальшивые чеки приведут к бану",
                parse_mode="HTML",
                reply_markup=keyboard
            )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling buy status with check: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def _handle_my_statuses_checks(self, callback: types.CallbackQuery, user_id: int):
        """Объединенное меню моих статусов и чеков"""
        try:
            from .status_repository import StatusRepository
            from .check_repository import CheckRepository

            status_repo = StatusRepository()
            check_repo = CheckRepository()

            # Получаем информацию о статусе
            status = status_repo.get_user_active_status(user_id)

            # Получаем историю чеков
            checks = check_repo.get_user_checks(user_id, limit=5)

            text = "📊 <b>Ваша информация</b>\n\n"

            # Информация о статусе
            if status:
                days_left = status.get('days_left', 0)
                text += (
                    f"🎖️ <b>Активный статус:</b> {status['status_name'].title()} {status['status_icon']}\n"
                    f"💰 <b>Ежедневный бонус:</b> {status_repo.get_user_bonus_amount(user_id):,} монет\n"
                    f"⏰ <b>Осталось дней:</b> {days_left if days_left > 0 else '0 (истек)'}\n\n"
                )
            else:
                text += (
                    "🎖️ <b>Активный статус:</b> Обычный 👤\n"
                    "💰 <b>Ежедневный бонус:</b> 1.000.000 монет\n"
                    "⏰ <b>Срок:</b> Бессрочно\n\n"
                )

            # Информация о чеках
            if checks:
                text += "📋 <b>Последние чеки:</b>\n"
                status_icons = {
                    'pending': '⏳',
                    'approved': '✅',
                    'rejected': '',
                    'banned': '🚫',
                    'limit_removed': '🔓'
                }

                for check in checks[:3]:  # Показываем только 3 последних
                    icon = status_icons.get(check['status'], '❓')
                    date_str = check['created_at'].strftime('%d.%m')
                    text += f"{icon} #{check['id']} ({date_str}) - {check['status']}\n"

                text += f"\n📊 Всего чеков: {len(checks)}"
            else:
                text += "📭 У вас еще нет отправленных чеков"

            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton(
                    text="🎁 Получить бонус",
                    callback_data="claim_bonus"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    text="📋 Полная история чеков",
                    callback_data="donate_full_checks_history"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_donate"
                )
            )

            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling my statuses checks: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def donate_full_checks_history(self, callback: types.CallbackQuery):
        """Показывает полную историю чеков"""
        try:
            from .check_repository import CheckRepository
            check_repo = CheckRepository()

            user_id = callback.from_user.id
            checks = check_repo.get_user_checks(user_id, limit=20)

            if not checks:
                response = (
                    "📭 <b>История чеков пуста</b>\n\n"
                    "Вы еще не отправляли чеки на проверку."
                )
            else:
                response = "📋 <b>История ваших чеков</b>\n\n"

                status_icons = {
                    'pending': '⏳',
                    'approved': '✅',
                    'rejected': '',
                    'banned': '🚫',
                    'limit_removed': '🔓'
                }

                for check in checks:
                    icon = status_icons.get(check['status'], '❓')
                    date_str = check['created_at'].strftime('%d.%m.%Y %H:%M')

                    line = f"{icon} <b>#{check['id']}</b> ({date_str}) - {check['status']}"

                    if check['coins_given']:
                        line += f" - {check['coins_given']:,} монет"

                    if check['amount']:
                        line += f" - {check['amount']}₽"

                    response += line + "\n"

                response += f"\n📊 <b>Всего чеков:</b> {len(checks)}"

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    text="📸 Отправить новый чек",
                    callback_data="donate_send_check"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="my_statuses_checks"
                )
            )

            await callback.message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling full checks history: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def handle_check_photo_from_menu(self, message: types.Message):
        """Обрабатывает фото чека из меню доната"""
        try:
            # Получаем диспетчер напрямую из message
            dp = Dispatcher.get_current()
            if dp is None:
                await message.answer(" Ошибка: диспетчер не найден")
                return

            # Получаем данные из state с использованием диспетчера
            state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
            state_data = await state.get_data()

            if not state_data.get('check_type'):
                # Если данные не найдены, показываем меню выбора типа
                keyboard = types.InlineKeyboardMarkup(row_width=1)
                keyboard.add(
                    types.InlineKeyboardButton(
                        text="📸 Отправить чек",
                        callback_data="donate_send_check"
                    )
                )
                return

            # Используем тот же метод, что и в check_handler.py
            from .check_handler import CheckHandler
            check_handler = CheckHandler()

            # Передаем управление в check_handler с нашими данными
            # Важно: используем state, созданный через диспетчер
            await check_handler.handle_check_photo(message, state)

        except Exception as e:
            self.logger.error(f"Error handling check photo from menu: {e}")
            await message.answer(" Произошла ошибка при обработке чека.")

    async def _handle_send_check(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает отправку чека из меню доната"""
        try:
            # Проверяем, не забанен ли пользователь
            from .check_repository import CheckRepository
            check_repo = CheckRepository()
            is_banned, reason = check_repo.is_user_banned(user_id)

            if is_banned:
                await callback.answer(
                    f" Вы забанены в системе.\nПричина: {reason}",
                    show_alert=True
                )
                return

            # Показываем меню выбора типа покупки
            keyboard = types.InlineKeyboardMarkup(row_width=1)

            keyboard.add(
                types.InlineKeyboardButton(
                    text="💰 Покупка монет",
                    callback_data="check_type_coins"
                )
            )

            keyboard.add(
                types.InlineKeyboardButton(
                    text="👑 Покупка статуса",
                    callback_data="check_type_status"
                )
            )

            keyboard.add(
                types.InlineKeyboardButton(
                    text="🔓 Снятие лимита",
                    callback_data="check_type_limit"
                )
            )

            keyboard.add(
                types.InlineKeyboardButton(
                    text="🎰 Лимит рулетки",
                    callback_data="check_type_roulette_limit"
                )
            )

            keyboard.add(
                types.InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_donate"
                )
            )

            await callback.message.edit_text(
                "📝 <b>Выберите тип покупки:</b>\n\n"
                "💰 <b>Покупка монет</b> - если вы покупаете монеты\n"
                "👑 <b>Покупка статуса</b> - если вы покупаете статус\n"
                "🔓 <b>Снятие лимита</b> - если хотите снять лимит\n\n"
                "📌 <b>После выбора:</b>\n"
                "1. Отправьте скриншот оплаты\n"
                "2. Укажите детали покупки",
                parse_mode="HTML",
                reply_markup=keyboard
            )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling send check: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def _handle_my_checks(self, callback: types.CallbackQuery, user_id: int):
        """Показывает историю чеков пользователя"""
        try:
            from .check_repository import CheckRepository
            check_repo = CheckRepository()

            checks = check_repo.get_user_checks(user_id, limit=10)

            if not checks:
                response = (
                    "📭 <b>История чеков пуста</b>\n\n"
                    "Вы еще не отправляли чеки на проверку.\n"
                    "Чтобы отправить чек, нажмите '📸 Отправить чек на покупку'"
                )
            else:
                response = "📋 <b>История ваших чеков</b>\n\n"

                status_icons = {
                    'pending': '⏳',
                    'approved': '✅',
                    'rejected': '',
                    'banned': '🚫',
                    'limit_removed': '🔓'
                }

                for check in checks:
                    icon = status_icons.get(check['status'], '❓')
                    date_str = check['created_at'].strftime('%d.%m')

                    line = f"{icon} <b>#{check['id']}</b> ({date_str})"

                    if check['coins_given']:
                        line += f" - {check['coins_given']:,} монет"

                    response += line + "\n"

                response += f"\n📊 <b>Всего чеков:</b> {len(checks)}"

            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    text="📸 Отправить новый чек",
                    callback_data="donate_send_check"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_donate"
                )
            )

            await callback.message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling my checks: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def _handle_check_type_selection(self, callback: types.CallbackQuery):
        """Обрабатывает выбор типа покупки"""
        try:
            check_type = callback.data

            if check_type == "check_type_coins":
                # Показываем пакеты монет для выбора
                keyboard = types.InlineKeyboardMarkup(row_width=1)

                for package in COIN_PACKAGES:
                    keyboard.add(
                        types.InlineKeyboardButton(
                            text=f"💰 {package['amount']:,} монет — {package['rub_price']:,}₽",
                            callback_data=f"coins_{package['amount']}"
                        )
                    )

                keyboard.add(
                    types.InlineKeyboardButton(
                        text="↩️ Назад",
                        callback_data="donate_send_check"
                    )
                )

                await callback.message.edit_text(
                    "💰 <b>Выберите пакет монет:</b>\n\n"
                    "▫️ 250.000 — 100₽\n"
                    "▫️ 600.000 — 200₽\n"
                    "▫️ 1.300.000 — 400₽\n"
                    "▫️ 2.800.000 — 700₽\n"
                    "▫️ 6.000.000 — 1.200₽\n"
                    "▫️ 14.000.000 — 2.000₽\n"
                    "▫️ 28.000.000 — 3.500₽\n"
                    "▫️ 60.000.000 — 6.000₽\n"
                    "▫️ 110.000.000 — 7.500₽\n\n"
                    f"🔓 <b>Автоматическое снятие лимита:</b>\n"
                    f"• При покупке от 250₽ лимит снимается автоматически\n"
                    f"• При покупке от 100₽ можно купить отдельно снятие лимита\n\n"
                    "📌 <b>Или укажите свою сумму вручную в комментарии к чеку</b>",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

            elif check_type == "check_type_status":
                # Показываем статусы для выбора
                keyboard = types.InlineKeyboardMarkup(row_width=1)

                for status in STATUSES[1:]:  # Пропускаем обычный статус
                    keyboard.add(
                        types.InlineKeyboardButton(
                            text=f"{status['icon']} {status['name'].title()} — {status['price_rub']:,}₽",
                            callback_data=f"status_{status['id']}"
                        )
                    )

                keyboard.add(
                    types.InlineKeyboardButton(
                        text="↩️ Назад",
                        callback_data="donate_send_check"
                    )
                )

                await callback.message.edit_text(
                    "🎖️ <b>Выберите статус:</b>\n\n"
                    "🌑 <b>Бронза</b> — 3.000₽\n"
                    "• Бонус: 15.000.000 монет/день\n"
                    "• Срок: 30 дней\n\n"
                    "💰 <b>Платина</b> — 6.000₽\n"
                    "• Бонус: 40.000.000 монет/день\n"
                    "• Срок: 30 дней\n\n"
                    "🥇 <b>Золото</b> — 12.000₽\n"
                    "• Бонус: 100.000.000 монет/день\n"
                    "• Срок: 30 дней\n\n"
                    "💎 <b>Бриллиант</b> — 27.000₽\n"
                    "• Бонус: 800.000.000 монет/день\n"
                    "• Срок: 30 дней\n\n"
                    f"🔓 <b>Автоматическое снятие лимита:</b>\n"
                    f"• При покупке статуса лимит снимается автоматически\n\n"
                    "📌 <b>Или укажите статус вручную в комментарии к чеку</b>",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

            elif check_type == "check_type_limit":
                # Для снятия лимита - фиксированная сумма 100₽
                text = (
                    "🔓 <b>Снятие лимита на передачу монет</b>\n\n"
                    "💎 <b>Сумма:</b> 100₽\n\n"
                    "📌 <b>После оплаты:</b>\n"
                    "• Лимит на передачу монет будет снят\n"
                    "• Вы сможете переводить неограниченные суммы\n\n"
                    "💡 <b>Альтернатива:</b>\n"
                    "• Покупка монет от 250₽ также снимает лимит\n"
                    "• Покупка любого статуса снимает лимит"
                )

                keyboard = types.InlineKeyboardMarkup(row_width=1)

                keyboard.add(
                    types.InlineKeyboardButton(
                        text="✅ Купить снятие лимита за 100₽",
                        callback_data="limit_100"
                    )
                )

                keyboard.add(
                    types.InlineKeyboardButton(
                        text="↩️ Назад",
                        callback_data="donate_send_check"
                    )
                )

                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

            elif check_type == "check_type_roulette_limit":
                # НОВАЯ ОПЦИЯ: Снятие лимита рулетки
                # Сохраняем данные
                dp = Dispatcher.get_current()
                state = dp.current_state(chat=callback.message.chat.id, user=callback.from_user.id)
                
                await state.update_data(
                    check_type="check_type_roulette_limit",
                    purchase_details="Снятие лимита рулетки в группе",
                    purchase_amount=500,
                    purchase_type="roulette_limit"
                )

                text = (
                    "🎰 <b>Снятие лимита рулетки в группе</b>\n\n"
                    "💎 <b>Сумма:</b> 500₽\n\n"
                    "📝 <b>Инструкция:</b>\n"
                    "1. Нажмите кнопку ниже для начала процесса\n"
                    "2. Введите ID группы (например: -100123456789)\n"
                    "3. Отправьте фото чека об оплате 500₽\n"
                    "4. Админ проверит и активирует\n\n"
                    "⚠️ <b>Внимание:</b>\n"
                    "• Лимит снимается навсегда для всей группы\n"
                    "• После снятия рулетка доступна всем без ограничений\n"
                    "• Отправляйте только реальные чеки"
                )

                # Добавляем кнопку назад
                keyboard = types.InlineKeyboardMarkup(row_width=1)
                keyboard.add(
                    types.InlineKeyboardButton(
                        text="↩️ Назад",
                        callback_data="donate_send_check"
                    )
                )

                await callback.message.edit_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

                # Переходим к запросу ID группы
                await CheckStates.waiting_for_group_id.set()

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling check type selection: {e}")
            await callback.message.edit_text(" Произошла ошибка. Попробуйте снова.")
            await callback.answer()

    async def _handle_limit_amount_selection(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает выбор снятия лимита за 100₽"""
        try:
            # Фиксированная сумма 100₽ для снятия лимита
            amount = 100

            # Сохраняем данные для обработки фото
            from aiogram.dispatcher import FSMContext
            from aiogram import Dispatcher

            dp = Dispatcher.get_current()
            if dp is None:
                await callback.answer(" Ошибка: диспетчер не найден", show_alert=True)
                return

            state = dp.current_state(chat=callback.from_user.id, user=callback.from_user.id)

            # Сохраняем данные для снятия лимита
            await state.set_data({
                'check_type': 'check_type_limit',
                'purchase_details': f'Снятие лимита на передачу монет',
                'purchase_amount': amount,
                'user_id': user_id
            })

            # Просим отправить фото
            await callback.message.edit_text(
                f"🔓 <b>Снятие лимита на передачу монет</b>\n\n"
                f"💎 <b>Сумма:</b> 100₽\n\n"
                f"📸 <b>Теперь отправьте скриншот оплаты:</b>\n"
                f"1. Сделайте скриншот успешной оплаты\n"
                f"2. Отправьте фото или скриншот в этот чат\n"
                f"3. Убедитесь, что чек читаемый\n\n"
                f"⚠️ <b>Внимание:</b>\n"
                f"• Отправляйте только реальные чеки\n"
                f"• Фальшивые чеки приведут к бану",
                parse_mode="HTML"
            )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling limit amount selection: {e}")
            await callback.message.edit_text(" Произошла ошибка. Попробуйте снова.")
            await callback.answer()

    async def _handle_purchase_details_selection(self, callback: types.CallbackQuery):
        """Обрабатывает выбор деталей покупки"""
        try:
            data = callback.data

            if data == "check_back_to_type":
                # Возвращаемся к выбору типа
                await self._handle_send_check(callback, callback.from_user.id)
                await callback.answer()
                return

            purchase_details = ""
            purchase_amount = 0
            purchase_coins = None
            purchase_status_id = None
            purchase_status_name = None
            check_type = None

            if data.startswith("coins_"):
                amount = int(data.split("_")[1])

                # Находим пакет
                package = next((p for p in COIN_PACKAGES if p['amount'] == amount), None)
                if package:
                    purchase_details = f"Покупка {amount:,} монет"
                    purchase_amount = package['rub_price']
                    purchase_coins = amount
                    check_type = "check_type_coins"

            elif data.startswith("status_"):
                status_id = int(data.split("_")[1])

                # Находим статус
                status = next((s for s in STATUSES if s['id'] == status_id), None)
                if status:
                    purchase_details = f"Покупка статуса {status['name'].title()}"
                    purchase_amount = status['price_rub']
                    purchase_status_id = status_id
                    purchase_status_name = status['name']
                    check_type = "check_type_status"

            if not check_type:
                await callback.answer(" Неизвестный тип покупки", show_alert=True)
                return

            # Сохраняем данные для обработки фото
            dp = Dispatcher.get_current()
            if dp is None:
                await callback.answer(" Ошибка: диспетчер не найден", show_alert=True)
                return

            # Используем правильный chat и user ID
            state = dp.current_state(chat=callback.message.chat.id, user=callback.from_user.id)

            await state.set_data({
                'check_type': check_type,
                'purchase_details': purchase_details,
                'purchase_amount': purchase_amount,
                'purchase_coins': purchase_coins,
                'purchase_status_id': purchase_status_id,
                'purchase_status_name': purchase_status_name,
                'user_id': callback.from_user.id
            })

            # Просим отправить фото
            await callback.message.edit_text(
                f"📸 <b>Теперь отправьте скриншот оплаты:</b>\n\n"
                f"ℹ️ <b>Инструкция:</b>\n"
                f"1. Сделайте скриншот успешной оплаты\n"
                f"2. Отправьте фото или скриншот в этот чат\n"
                f"3. Убедитесь, что чек читаемый\n\n"
                f"📝 <b>Ваша покупка:</b> {purchase_details} — {purchase_amount}₽\n\n"
                f"⏳ <b>Время обработки:</b> до 24 часов\n"
                f"👨‍💼 <b>Проверяет:</b> администратор\n\n"
                f"⚠️ <b>Внимание:</b>\n"
                f"• Отправляйте только реальные чеки\n"
                f"• Фальшивые чеки приведут к бану\n"
                f"• Чек должен быть читаемым",
                parse_mode="HTML"
            )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling purchase details: {e}")
            await callback.message.edit_text(" Произошла ошибка. Попробуйте снова.")
            await callback.answer()

    async def _handle_back_to_donate(self, callback: types.CallbackQuery):
        """Возвращает в главное меню доната"""
        donate_text = self._get_main_donate_text()

        # Создаем клавиатуру как в donate_command
        keyboard = types.InlineKeyboardMarkup(row_width=1)

        keyboard.row(
            types.InlineKeyboardButton(
                text="💸 Купить Монеты",
                callback_data="donate_buy_coins"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                text="👑 Статусы",
                callback_data="donate_statuses"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                text="🎁 Ежедневный бонус",
                callback_data="daily_bonus"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                text="📸 Отправить чек на покупку",
                callback_data="donate_send_check"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                text="📊 Мои чеки",
                callback_data="donate_my_checks"
            )
        )

        try:
            await callback.message.edit_text(donate_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            if "Message is not modified" not in str(e):
                self.logger.error(f"Error editing message when going back to donate: {e}")

        await callback.answer()

    async def _handle_daily_bonus(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает показ ежедневных бонусов"""
        has_active_status = bool(self.status_repo.get_user_active_status(user_id))

        if has_active_status:
            bonus_text = donate_texts.get("bonus")
            can_receive = self.status_repo.can_receive_bonus(user_id)

            if can_receive:
                bonus_text += "\n\n🎉 <b>Статус:</b> бонус доступен!"
            else:
                bonus_text += "\n\n⏳ <b>Статус:</b> бонус будет доступен через 24 часа"
        else:
            # Пользователь с базовым статусом
            bonus_text = (
                "🎁 <b>Ежедневные бонусы</b>\n\n"
                "👤 <b>Ваш статус:</b> Обычный\n"
                "💰 <b>Ежедневный бонус:</b> 1.000.000 Монет\n\n"
                "💡 <b>Хотите больше?</b>\n"
                "Приобретите статус для увеличения бонусов!\n\n"
            )

            can_receive = self.status_repo.can_receive_bonus(user_id)
            if can_receive:
                bonus_text += "🎉 <b>Статус:</b> бонус доступен!"
            else:
                bonus_text += "⏳ <b>Статус:</b> бонус будет доступен через 24 часа"

        keyboard = types.InlineKeyboardMarkup(row_width=1)

        if can_receive:
            keyboard.add(
                types.InlineKeyboardButton(
                    text="🎁 Получить бонус",
                    callback_data="claim_bonus"
                )
            )

        keyboard.add(
            types.InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="back_to_donate"
            )
        )

        try:
            await callback.message.edit_text(bonus_text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            if "Message is not modified" not in str(e):
                self.logger.error(f"Error editing message for daily bonus: {e}")

        await callback.answer()

    async def _handle_claim_bonus(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает получение бонуса (ручной запрос)"""
        try:
            # Проверяем, может ли пользователь получить бонус
            can_receive, time_left = self.status_repo.can_receive_bonus(user_id)

            if not can_receive:
                await callback.answer(f"⏳ Бонус будет доступен через {time_left}", show_alert=True)
                return

            # Начисляем бонус
            success, message, bonus_amount = self.status_repo.award_manual_bonus(user_id)

            if not success:
                await callback.answer(f" {message}", show_alert=True)
                return

            # Получаем информацию о статусе
            status = self.status_repo.get_user_active_status(user_id)
            status_name = status.get('status_name').title() if status else "Обычный"

            # Получаем текущий баланс пользователя
            from database import get_db
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await callback.answer(" Ошибка: пользователь не найден", show_alert=True)
                return

            # Формируем сообщение об успехе
            text = donate_texts.get("bonus_claimed").format(
                bonus_amount=bonus_amount,
                status_name=status_name,
                new_balance=user.coins
            )

            # Показываем статус пользователя
            status_info = await self._get_user_status_info(user_id)
            full_text = text + "\n\n" + status_info

            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="daily_bonus"
                )
            )

            try:
                await callback.message.edit_text(full_text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                if "Message is not modified" not in str(e):
                    self.logger.error(f"Error editing message after claiming bonus: {e}")

            await callback.answer("✅ Бонус успешно получен!")

        except Exception as e:
            self.logger.error(f"Error claiming bonus: {e}")
            await callback.answer(" Ошибка при получении бонуса", show_alert=True)

    async def _handle_status_purchase_selection(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает выбор статуса для покупки"""
        status_id = int(callback.data.split("_")[2])
        status = next((s for s in STATUSES if s["id"] == status_id), None)

        if status:
            # Формируем информацию о статусе
            text = donate_texts.get("status_info").format(
                status_name=status['name'].title(),
                status_icon=status['icon'],
                price_rub=f"{status['price_rub']:,}",
                price_tenge=f"{status['price_tenge']:,}" if status['price_tenge'] > 0 else "не доступно",
                bonus_amount=status['bonus_amount'],
                duration=status['duration_days'],
                support_username=SUPPORT_USERNAME,
                user_id=user_id
            )

            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton(
                    text="📸 Отправить чек на покупку",
                    callback_data=f"status_{status_id}"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    text="↩️ Назад",
                    callback_data="check_type_status"
                )
            )

            try:
                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                if "Message is not modified" not in str(e):
                    self.logger.error(f"Error editing message for status purchase: {e}")

            await callback.answer(f"🎖️ {status['name'].title()}")
        else:
            await callback.answer(" Статус не найден")

    async def _handle_active_status_info(self, callback: types.CallbackQuery, user_id: int):
        """Обрабатывает нажатие на уже активный статус"""
        status_id = int(callback.data.split("_")[2])
        status = next((s for s in STATUSES if s["id"] == status_id), None)

        if status:
            # Получаем информацию о статусе пользователя
            user_status = self.status_repo.get_user_active_status(user_id)

            if user_status and user_status['status_id'] == status_id:
                # Формируем информацию об активном статусе
                from datetime import datetime

                days_left = 0
                if user_status.get('expires_at'):
                    now = datetime.now()
                    if user_status['expires_at'] > now:
                        time_left = user_status['expires_at'] - now
                        days_left = time_left.days
                    else:
                        days_left = 0

                text = (
                    f"✅ <b>Ваш активный статус</b>\n\n"
                    f"🎖️ <b>Название:</b> {status['name'].title()} {status['icon']}\n"
                    f"💰 <b>Ежедневный бонус:</b> {status['bonus_amount']:,} Монет\n"
                    f"⏳ <b>Осталось дней:</b> {days_left}\n\n"
                    f"💡 <b>Для продления:</b>\n"
                    f"Напишите @{SUPPORT_USERNAME}"
                )

                keyboard = types.InlineKeyboardMarkup(row_width=1)
                keyboard.add(
                    types.InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="donate_statuses"
                    )
                )

                try:
                    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        self.logger.error(f"Error editing message for active status info: {e}")

                await callback.answer("✅ Активный статус")
            else:
                await callback.answer(" Этот статус не активен")
        else:
            await callback.answer(" Статус не найден")

    async def _handle_error(self, callback: types.CallbackQuery):
        """Обрабатывает общие ошибки"""
        try:
            await callback.message.edit_text(
                " Произошла ошибка. Попробуйте снова.",
                parse_mode="HTML"
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                self.logger.error(f"Error editing message in _handle_error: {e}")

        await callback.answer("⚠️ Произошла ошибка")

    async def check_expired_statuses(self, message: types.Message):
        """Команда для проверки истекших статусов (только для админов)"""
        if not await check_admin_async(message.from_user.id):
            return

        try:
            # Получаем истекшие статусы
            expired_statuses = self.status_repo.get_expired_statuses()

            if not expired_statuses:
                await message.reply("✅ Нет истекших статусов")
                return

            expired_count = 0
            report_lines = []

            for status_info in expired_statuses:
                # Деактивируем статус
                if self.status_repo.remove_user_status(status_info['user_id'], status_info['status_id']):
                    expired_count += 1
                    report_lines.append(f"• ID {status_info['user_id']} - {status_info['status_name']}")

            if expired_count > 0:
                report = f"✅ Деактивировано {expired_count} истекших статусов:\n" + "\n".join(report_lines[:20])
                if len(report_lines) > 20:
                    report += f"\n...и еще {len(report_lines) - 20}"
                await message.reply(report)
            else:
                await message.reply("ℹ️ Все истекшие статусы уже обработаны")

        except Exception as e:
            await message.reply(f" Ошибка: {str(e)}")


def register_donate_handlers(dp: Dispatcher):
    """Регистрация обработчиков доната"""
    handler = DonateHandler()

    # Регистрация команд доната
    dp.register_message_handler(handler.donate_command, commands=["донат", "donate"], state="*")
    dp.register_message_handler(handler.donate_command,
                                lambda m: m.text and m.text.lower() in ["донат", "donate"],
                                state="*")

    # Регистрация обработки фото чеков из меню доната
    dp.register_message_handler(
        handler.handle_check_photo_from_menu,
        content_types=["photo"],
        state="*"
    )

    # Регистрация callback обработчиков
    donate_callbacks = [
        "status_buy_", "status_active_", "daily_bonus", "donate_my_checks",
        "back_to_donate", "claim_bonus", "donate_buy_coins",
        "donate_statuses", "donate_send_check", "donate_full_checks_history",
        "buy_coins_with_check", "buy_status_with_check", "my_statuses_checks",
        "check_type_", "coins_", "status_", "check_back_to_type", "limit_"
    ]
    dp.register_callback_query_handler(handler.donate_callback_handler,
                                       lambda c: any(c.data.startswith(prefix) for prefix in donate_callbacks),
                                       state="*")

    logging.info("✅ Донат обработчики зарегистрированы")