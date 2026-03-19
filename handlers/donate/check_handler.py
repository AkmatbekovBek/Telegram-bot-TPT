"""
Обработчик системы проверки чеков - ИСПРАВЛЕННЫЙ
"""
import logging
from datetime import datetime
from typing import Dict, Any
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.callback_data import CallbackData

from .check_model import Check
from .check_repository import CheckRepository
from .check_config import ADMIN_GROUP_ID, CHECK_BUTTONS, CHECK_MESSAGES
from .check_states import CheckStates
from .status_repository import StatusRepository
from .config import STATUSES, COIN_PACKAGES, SUPPORT_USERNAME
from database.crud import UserRepository

logger = logging.getLogger(__name__)

# Callback data для кнопок
check_callback = CallbackData("check", "action", "check_id")


class CheckHandler:
    """Обработчик системы проверки чеков"""

    def __init__(self):
        self.logger = logger
        self.check_repo = CheckRepository()
        self.status_repo = StatusRepository()

    async def start_check_upload(self, message: types.Message, state: FSMContext):
        """Начинает процесс загрузки чека с выбором типа покупки"""
        try:
            # Проверяем, не забанен ли пользователь
            is_banned, reason = self.check_repo.is_user_banned(message.from_user.id)
            if is_banned:
                await message.reply(
                    f" Вы забанены в системе.\n"
                    f"Причина: {reason}\n\n"
                    f"Для разбана обратитесь к администратору."
                )
                return

            # Создаем клавиатуру для выбора типа покупки
            keyboard = InlineKeyboardMarkup(row_width=1)

            keyboard.add(
                InlineKeyboardButton(
                    text="💰 Покупка монет",
                    callback_data="check_type_coins"
                )
            )

            keyboard.add(
                InlineKeyboardButton(
                    text="🎖️ Покупка статуса",
                    callback_data="check_type_status"
                )
            )

            keyboard.add(
                InlineKeyboardButton(
                    text="🔓 Снятие лимита",
                    callback_data="check_type_limit"
                )
            )

            keyboard.add(
                InlineKeyboardButton(
                    text="🎰 Лимит рулетки",
                    callback_data="check_type_roulette_limit"
                )
            )

            keyboard.add(
                InlineKeyboardButton(
                    text=" Отмена",
                    callback_data="check_cancel"
                )
            )

            await message.answer(
                "📝 <b>Выберите тип покупки:</b>\n\n"
                "💰 <b>Покупка монет</b> - если вы покупаете монеты\n"
                "🎖️ <b>Покупка статуса</b> - если вы покупаете статус\n"
                "🔓 <b>Снятие лимита</b> - если хотите снять лимит\n\n"
                "📌 <b>После выбора:</b>\n"
                "1. Отправьте скриншот оплаты\n"
                "2. Укажите детали покупки",
                parse_mode="HTML",
                reply_markup=keyboard
            )

            await CheckStates.waiting_for_check_type.set()

        except Exception as e:
            self.logger.error(f"Error starting check upload: {e}")
            await message.answer(" Произошла ошибка. Попробуйте позже.")
            await state.finish()

    async def handle_check_type_selection(self, callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор типа покупки"""
        try:
            check_type = callback.data

            if check_type == "check_cancel":
                await callback.message.edit_text(" Отправка чека отменена.")
                await state.finish()
                await callback.answer()
                return

            # Сохраняем тип покупки
            await state.update_data(check_type=check_type)

            if check_type == "check_type_coins":
                # Показываем пакеты монет для выбора
                keyboard = InlineKeyboardMarkup(row_width=1)

                for package in COIN_PACKAGES:
                    keyboard.add(
                        InlineKeyboardButton(
                            text=f"💰 {package['amount']:,} монет — {package['rub_price']:,}₽",
                            callback_data=f"coins_{package['amount']}"
                        )
                    )

                keyboard.add(
                    InlineKeyboardButton(
                        text="↩️ Назад",
                        callback_data="check_back_to_type"
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
                    "📌 <b>Или укажите свою сумму вручную в комментарии к чеку</b>",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

                await CheckStates.waiting_for_check_details.set()

            elif check_type == "check_type_status":
                # Показываем статусы для выбора
                keyboard = InlineKeyboardMarkup(row_width=1)

                for status in STATUSES[1:]:  # Пропускаем обычный статус
                    keyboard.add(
                        InlineKeyboardButton(
                            text=f"{status['icon']} {status['name'].title()} — {status['price_rub']:,}₽",
                            callback_data=f"status_{status['id']}"
                        )
                    )

                keyboard.add(
                    InlineKeyboardButton(
                        text="↩️ Назад",
                        callback_data="check_back_to_type"
                    )
                )

                await callback.message.edit_text(
                    "🎖️ <b>Выберите статус:</b>\n\n"
                    "🌑 <b>Бронза</b> — 1.000₽\n"
                    "• Бонус: 500.000 монет/день\n"
                    "• Срок: 30 дней\n\n"
                    "💰 <b>Платина</b> — 2.500₽\n"
                    "• Бонус: 1.500.000 монет/день\n"
                    "• Срок: 30 дней\n\n"
                    "🥇 <b>Золото</b> — 5.000₽\n"
                    "• Бонус: 4.500.000 монет/день\n"
                    "• Срок: 30 дней\n\n"
                    "💎 <b>Бриллиант</b> — 8.000₽\n"
                    "• Бонус: 10.000.000 монет/день\n"
                    "• Срок: 30 дней\n\n"
                    "📌 <b>Или укажите статус вручную в комментарии к чеку</b>",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

                await CheckStates.waiting_for_check_details.set()

            elif check_type == "check_type_limit":
                # Для снятия лимита просто переходим к фото
                await state.update_data(purchase_details="Снятие лимита на передачу монет", purchase_amount=250)

                await callback.message.edit_text(
                    "🔓 <b>Снятие лимита на передачу монет</b>\n\n"
                    "💎 <b>С донатом от 250₽</b> — лимит снимается автоматически\n\n"
                    "📸 <b>Теперь отправьте скриншот оплаты:</b>\n"
                    "1. Сделайте скриншот успешной оплаты\n"
                    "2. Отправьте фото или скриншот в этот чат\n"
                    "3. Убедитесь, что чек читаемый\n\n"
                    "⏳ <b>Время обработки:</b> до 24 часов\n"
                    "👨‍💼 <b>Проверяет:</b> администратор\n\n"
                    "⚠️ <b>Внимание:</b>\n"
                    "• Отправляйте только реальные чеки\n"
                    "• Фальшивые чеки приведут к бану",
                    parse_mode="HTML"
                )

                await CheckStates.waiting_for_check_photo.set()

            elif check_type == "check_type_roulette_limit":
                # НОВАЯ ОПЦИЯ: Снятие лимита рулетки
                await state.update_data(
                    purchase_details="Снятие лимита рулетки в группе",
                    purchase_amount=500,
                    purchase_type="roulette_limit"
                )

                await callback.message.edit_text(
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
                    "• Отправляйте только реальные чеки",
                    parse_mode="HTML"
                )

                # Переходим к запросу ID группы
                await CheckStates.waiting_for_group_id.set()

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling check type selection: {e}")
            await callback.message.edit_text(" Произошла ошибка. Попробуйте снова.")
            await state.finish()

    async def handle_purchase_details_selection(self, callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор деталей покупки"""
        try:
            data = callback.data

            if data == "check_back_to_type":
                # Возвращаемся к выбору типа
                await self.start_check_upload(callback.message, state)
                await callback.answer()
                return

            state_data = await state.get_data()
            check_type = state_data.get('check_type')

            if check_type == "check_type_coins" and data.startswith("coins_"):
                amount = int(data.split("_")[1])

                # Находим пакет
                package = next((p for p in COIN_PACKAGES if p['amount'] == amount), None)
                if package:
                    purchase_details = f"Покупка {amount:,} монет"
                    await state.update_data(
                        purchase_details=purchase_details,
                        purchase_amount=package['rub_price'],
                        purchase_coins=amount
                    )

            elif check_type == "check_type_status" and data.startswith("status_"):
                status_id = int(data.split("_")[1])

                # Находим статус
                status = next((s for s in STATUSES if s['id'] == status_id), None)
                if status:
                    purchase_details = f"Покупка статуса {status['name'].title()}"
                    await state.update_data(
                        purchase_details=purchase_details,
                        purchase_amount=status['price_rub'],
                        purchase_status_id=status_id,
                        purchase_status_name=status['name']
                    )

            # Просим отправить фото
            purchase_text = (await state.get_data()).get('purchase_details', 'Не указано')
            await callback.message.edit_text(
                "📸 <b>Теперь отправьте скриншот оплаты:</b>\n\n"
                "ℹ️ <b>Инструкция:</b>\n"
                "1. Сделайте скриншот успешной оплаты\n"
                "2. Отправьте фото или скриншот в этот чат\n"
                "3. Убедитесь, что чек читаемый\n\n"
                f"📝 <b>Ваша покупка:</b> {purchase_text}\n\n"
                "⏳ <b>Время обработки:</b> до 24 часов\n"
                "👨‍💼 <b>Проверяет:</b> администратор\n\n"
                "⚠️ <b>Внимание:</b>\n"
                "• Отправляйте только реальные чеки\n"
                "• Фальшивые чеки приведут к бану\n"
                "• Чек должен быть читаемым",
                parse_mode="HTML"
            )

            await CheckStates.waiting_for_check_photo.set()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling purchase details: {e}")
            await callback.message.edit_text(" Произошла ошибка. Попробуйте снова.")
            await state.finish()

    async def handle_check_photo(self, message: types.Message, state: FSMContext):
        """Обрабатывает фото чека"""
        try:
            user_id = message.from_user.id
            chat_id = message.chat.id
            username = message.from_user.username or ""
            first_name = message.from_user.first_name or ""

            # Проверяем, не забанен ли пользователь
            is_banned, reason = self.check_repo.is_user_banned(user_id)
            if is_banned:
                await message.reply(f" Вы забанены. Причина: {reason}")
                await state.finish()
                return

            # Получаем данные из state
            state_data = await state.get_data()
            check_type = state_data.get('check_type')
            purchase_details = state_data.get('purchase_details', 'Не указано')
            purchase_amount = state_data.get('purchase_amount')

            # Получаем file_id фото
            if message.photo:
                photo_id = message.photo[-1].file_id
            else:
                await message.reply(" Пожалуйста, отправьте фото или скриншот.")
                return

            # Проверяем есть ли подпись/комментарий
            user_comment = ""
            if message.caption:
                user_comment = message.caption

            # Создаем полное описание
            full_notes = f"{purchase_details} — {purchase_amount}₽"
            if user_comment:
                full_notes += f"\n📝 Комментарий: {user_comment}"

            # Создаем запись о чеке с детальной информацией
            additional_data = {
                'check_type': check_type,
                'purchase_details': purchase_details,
                'purchase_amount': purchase_amount,
                'purchase_coins': state_data.get('purchase_coins'),
                'purchase_status_id': state_data.get('purchase_status_id'),
                'purchase_status_name': state_data.get('purchase_status_name'),
                'user_comment': user_comment,
                'group_id': state_data.get('group_id')
            }

            # ОТЛАДКА
            self.logger.info(f"DEBUG Creating check with additional_data: {additional_data}")

            success, check_id = self.check_repo.create_check(
                user_id=user_id,
                chat_id=chat_id,
                username=username,
                first_name=first_name,
                photo_id=photo_id,
                notes=full_notes,
                amount=purchase_amount,
                additional_data=additional_data
            )

            if not success:
                await message.reply(" Ошибка при обработке чека. Попробуйте позже.")
                await state.finish()
                return

            # Отправляем уведомление пользователю
            await message.reply(
                f"✅ <b>Чек отправлен на проверку!</b>\n\n"
                f"📝 <b>Номер заявки:</b> <code>#{check_id}</code>\n"
                f"🛒 <b>Покупка:</b> {purchase_details}\n"
                f"💰 <b>Сумма:</b> {purchase_amount}₽\n"
                f"⏳ <b>Статус:</b> Ожидает проверки\n\n"
                f"👨‍💼 <b>Администратор проверит ваш платёж</b>\n"
                f"⏰ <b>Время проверки:</b> до 24 часов\n\n"
                f"📊 <b>Проверить статус:</b> /check_status {check_id}",
                parse_mode="HTML"
            )

            # Пересылаем чек в админ-группу
            await self.forward_to_admin_group(message, check_id, user_id, username, full_notes)

            await state.finish()

        except Exception as e:
            self.logger.error(f"Error handling check photo: {e}")
            await message.answer(" Произошла ошибка при обработке чека.")
            await state.finish()

    async def forward_to_admin_group(self, message: types.Message, check_id: int,
                                     user_id: int, username: str, notes: str):
        """Пересылает чек в админ-группу с кнопками и информацией"""
        try:
            # Формируем подробную информацию о пользователе и покупке
            user_info = (
                f"👤 <b>Пользователь:</b>\n"
                f"• ID: <code>{user_id}</code>\n"
                f"• Username: @{username if username else 'нет'}\n"
                f"• Имя: {message.from_user.first_name or 'Не указано'}\n\n"
                f"📝 <b>Информация о покупке:</b>\n"
                f"{notes}\n\n"
                f"🆔 <b>Номер заявки:</b> <code>#{check_id}</code>"
            )

            # Создаем кнопки
            keyboard = InlineKeyboardMarkup(row_width=2)

            keyboard.add(
                InlineKeyboardButton(
                    text=CHECK_BUTTONS["approve"],
                    callback_data=check_callback.new(
                        action="approve",
                        check_id=check_id
                    )
                ),
                InlineKeyboardButton(
                    text=CHECK_BUTTONS["ban"],
                    callback_data=check_callback.new(
                        action="ban",
                        check_id=check_id
                    )
                )
            )

            keyboard.add(
                InlineKeyboardButton(
                    text=CHECK_BUTTONS["remove_limit"],
                    callback_data=check_callback.new(
                        action="remove_limit",
                        check_id=check_id
                    )
                )
            )

            # Пересылаем фото и добавляем информацию
            if message.photo:
                await message.bot.send_photo(
                    chat_id=ADMIN_GROUP_ID,
                    photo=message.photo[-1].file_id,
                    caption=CHECK_MESSAGES["admin_check_received"] + "\n\n" + user_info,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

            self.logger.info(f"Check {check_id} forwarded to admin group with details: {notes}")

        except Exception as e:
            self.logger.error(f"Error forwarding to admin group: {e}")

    async def handle_check_callback(self, callback: types.CallbackQuery,
                                    callback_data: Dict[str, str]):
        """Обрабатывает нажатия на кнопки в админ-группе"""
        try:
            action = callback_data["action"]
            check_id = int(callback_data["check_id"])

            # Получаем информацию о чеке
            check_info = self.check_repo.get_check(check_id)
            if not check_info:
                await callback.answer(" Чек не найден", show_alert=True)
                return

            if action == "approve":
                await self.handle_approve_check(callback, check_id, check_info)
            elif action == "ban":
                await self.handle_ban_user(callback, check_id, check_info)
            elif action == "remove_limit":
                await self.handle_remove_limit(callback, check_id, check_info)

        except Exception as e:
            self.logger.error(f"Error handling check callback: {e}")
            await callback.answer(" Произошла ошибка", show_alert=True)

    async def handle_approve_check(self, callback: types.CallbackQuery,
                                   check_id: int, check_info: Dict[str, Any]):
        """Обрабатывает подтверждение чека - ИСПРАВЛЕННЫЙ МЕТОД"""
        try:
            # Получаем дополнительные данные из чека
            additional_data = check_info.get('additional_data', {})
            check_type = additional_data.get('check_type')

            if not check_type:
                # Если тип не определен, используем старый метод
                await self._request_amount_for_coins(callback, check_id, check_info)
                return

            if check_type == "check_type_status":
                # Для статуса - подтверждаем автоматически
                await self._approve_status_check(callback, check_id, check_info, additional_data)
            elif check_type == "check_type_coins":
                # Для монет - подтверждаем автоматически
                await self._approve_coins_check(callback, check_id, check_info, additional_data)
            elif check_type == "check_type_limit":
                # Для снятия лимита - сразу обрабатываем
                await self._approve_limit_check(callback, check_id, check_info, additional_data)
            elif check_type == "check_type_roulette_limit":
                # Для снятия лимита рулетки - сразу обрабатываем
                await self._approve_roulette_limit_check(callback, check_id, check_info, additional_data)
            else:
                await self._request_amount_for_coins(callback, check_id, check_info)

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_approve_check: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def _approve_status_check(self, callback: types.CallbackQuery,
                                   check_id: int, check_info: Dict[str, Any], additional_data: dict):
        """Подтверждает покупку статуса - АВТОМАТИЧЕСКИ"""
        try:
            status_id = additional_data.get('purchase_status_id')
            status_name = additional_data.get('purchase_status_name')
            amount = additional_data.get('purchase_amount')

            if not status_id or not amount:
                await callback.message.answer(
                    f" <b>Ошибка подтверждения статуса</b>\n\n"
                    f"Не удалось определить данные статуса.\n"
                    f"ID: {status_id}, Сумма: {amount}\n\n"
                    f"📋 <b>Ручное подтверждение:</b>\n"
                    f"1. Найдите статус вручную\n"
                    f"2. Используйте команду /status",
                    parse_mode="HTML"
                )
                return

            # Находим статус
            status_info = next((s for s in STATUSES if s["id"] == status_id), None)
            if not status_info:
                await callback.message.answer(f" Статус ID {status_id} не найден в системе")
                return

            # Подтверждаем чек
            success, result_msg = self.check_repo.approve_check(
                check_id=check_id,
                admin_id=callback.from_user.id,
                admin_username=callback.from_user.username or "",
                amount=amount,
                purchased_status_id=status_id
            )

            if success:
                # Активируем статус
                self.status_repo.set_user_status(
                    user_id=check_info['user_id'],
                    status_id=status_id,
                    days=30,
                    admin_id=callback.from_user.id
                )

                # Формируем сообщение для админа
                response = (
                    f"✅ <b>СТАТУС ПОДТВЕРЖДЕН АВТОМАТИЧЕСКИ!</b>\n\n"
                    f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                    f"💰 Сумма: {amount}₽\n"
                    f"🎖️ Статус: {status_info['name'].title()} {status_info['icon']}\n"
                    f"⏰ Срок: 30 дней\n"
                    f"🎁 Ежедневный бонус: {status_info['bonus_amount']:,} монет\n"
                    f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}"
                )

                await callback.message.reply(response, parse_mode="HTML")

                # Отправляем уведомление пользователю
                try:
                    await callback.bot.send_message(
                        chat_id=check_info['user_id'],
                        text=(
                            f"✅ <b>Ваш статус подтверждён!</b>\n\n"
                            f"🎖️ <b>Статус:</b> {status_info['name'].title()} {status_info['icon']}\n"
                            f"💰 <b>Сумма:</b> {amount}₽\n"
                            f"⏰ <b>Срок:</b> 30 дней\n"
                            f"🎁 <b>Ежедневный бонус:</b> {status_info['bonus_amount']:,} монет\n\n"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error sending status notification: {e}")

                # Обновляем сообщение в админ-группе (УБИРАЕМ КНОПКИ ПОСЛЕ ПОДТВЕРЖДЕНИЯ)
                try:
                    await callback.message.edit_caption(
                        caption=(
                            f"✅ <b>СТАТУС ПОДТВЕРЖДЕН АВТОМАТИЧЕСКИ</b>\n\n"
                            f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                            f"🎖️ Статус: {status_info['name'].title()} {status_info['icon']}\n"
                            f"💰 Сумма: {amount}₽\n"
                            f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error editing caption: {e}")

            else:
                await callback.message.reply(f" Ошибка: {result_msg}")

        except Exception as e:
            self.logger.error(f"Error in _approve_status_check: {e}")
            await callback.message.reply(f" Критическая ошибка: {e}")

    async def _approve_roulette_limit_check(self, callback: types.CallbackQuery,
                                          check_id: int, check_info: Dict[str, Any], additional_data: dict):
        """Подтверждает снятие лимита рулетки - АВТОМАТИЧЕСКИ"""
        try:
            purchase_details = additional_data.get('purchase_details', '')
            # Извлекаем ID группы из описания или purchase_details
            # В handler мы сохраняли детали как "Снятие лимита рулетки в группе"
            # Но нам нужен group_id, который мы должны были сохранить где-то
            # В check_handler.py в start_check_upload мы не сохраняли group_id в additional_data
            # Но мы можем попробовать найти его в notes или purchase_details, если он там есть
            
            # ВАЖНО: В текущей реализации мы не сохранили group_id в additional_data при создании чека?
            # Давайте посмотрим на handlers.donate.handlers, там мы сохраняем:
            # purchase_details="Снятие лимита рулетки в группе"
            
            # А где сам ID группы? 
            # В handlers.donate.handlers после ввода ID группы мы обновляем state data
            # но при создании чека в check_handler.py мы берем данные из state
            # Надо проверить, передается ли group_id в additional_data
            
            group_id = additional_data.get('group_id')
            if not group_id:
                # Пытаемся найти в user_comment, если там сохранили
                user_comment = additional_data.get('user_comment', '')
                if user_comment.startswith('-100') or user_comment.startswith('-'):
                    try:
                        group_id = int(user_comment.split()[0])
                    except:
                        pass
            
            # Если всё ещё нет ID, спросим у админа ввести вручную, но лучше чтобы было автоматически
            # Если ID нет, мы не можем снять лимит автоматически
            
            amount = additional_data.get('purchase_amount', 500)
            
            # Если мы не нашли group_id, то придется просить админа ввести его (как fallback)
            # Но в идеале код создания чека должен был сохранить group_id. 
            # Если сейчас его нет, то добавим логику запроса ID у админа?
            # Или просто предположим, что он есть.
            
            # В handlers.donate.handlers:
            # await state.update_data(group_id=group_id)
            # При создании чека в check_handler.py:
            # additional_data.update(state_data)
            # Значит group_id должен быть там!
            
            if not group_id:
                 await callback.message.answer("⚠️ Не удалось автоматически определить ID группы. Пожалуйста, снимите лимит вручную командой !rul_unlock в группе.")
                 # Но чек всё равно пометим как, или нет?
                 # Лучше попросить ввести ID группы? Нет, это сложно в текущем flow.
                 return

            # Снимаем лимит
            from handlers.roulette.state_manager import state_manager
            # Получаем user_id из check_info
            limit_remover_id = check_info['user_id']
            state_manager.unlock_roulette_with_donation(int(group_id), limit_remover_id)
            
            # Подтверждаем чек в БД
            success, result_msg = self.check_repo.approve_check(
                check_id=check_id,
                admin_id=callback.from_user.id,
                admin_username=callback.from_user.username or "",
                amount=amount,
                is_limit_removal=True
            )

            if success:
                # Формируем сообщение
                response = (
                    f"✅ <b>ЛИМИТ РУЛЕТКИ СНЯТ!</b>\n\n"
                    f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                    f"🆔 Группа: <code>{group_id}</code>\n"
                    f"💰 Сумма: {amount}₽\n"
                    f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}"
                )

                await callback.message.reply(response, parse_mode="HTML")
                
                # Убираем кнопки
                await callback.message.edit_caption(
                    caption=response,
                    parse_mode="HTML"
                )

                # Уведомляем пользователя
                try:
                    await callback.bot.send_message(
                        chat_id=check_info['user_id'],
                        text=(
                            f"✅ <b>Лимит рулетки снят!</b>\n\n"
                            f"Теперь в вашей группе можно играть без ограничений.\n"
                            f"Приятной игры!"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                     self.logger.error(f"Error sending notification: {e}")

            else:
                 await callback.message.reply(f" Ошибка БД: {result_msg}")

        except Exception as e:
            self.logger.error(f"Error in _approve_roulette_limit_check: {e}")
            await callback.message.reply(f" Ошибка: {e}")

    async def _approve_coins_check(self, callback: types.CallbackQuery,
                                  check_id: int, check_info: Dict[str, Any], additional_data: dict):
        """Подтверждает покупку монет - АВТОМАТИЧЕСКИ"""
        try:
            amount = additional_data.get('purchase_amount')
            coins_amount = additional_data.get('purchase_coins')

            if amount and coins_amount:
                # Если сумма и количество монет известны - подтверждаем автоматически
                success, result_msg = self.check_repo.approve_check(
                    check_id=check_id,
                    admin_id=callback.from_user.id,
                    admin_username=callback.from_user.username or "",
                    amount=amount,
                    coins_amount=coins_amount
                )

                if success:
                    # Получаем пользователя для баланса
                    from database import get_db
                    db = next(get_db())
                    user = UserRepository.get_user_by_telegram_id(db, check_info['user_id'])

                    # Формируем сообщение
                    response = (
                        f"✅ <b>ДОНАТ ПОДТВЕРЖДЕН!</b>\n\n"
                        f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                        f"💰 Сумма: {amount}₽\n"
                        f"🎁 Монеты: {coins_amount:,}\n"
                        f"🔓 Лимит на передачу: Снят\n"
                        f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}"
                    )

                    await callback.message.reply(response, parse_mode="HTML")

                    # Отправляем уведомление пользователю
                    try:
                        await callback.bot.send_message(
                            chat_id=check_info['user_id'],
                            text=(
                                f"✅ <b>Ваш донат подтверждён!</b>\n\n"
                                f"💰 <b>Сумма:</b> {amount}₽\n"
                                f"🎁 <b>Начислено монет:</b> {coins_amount:,}\n"
                                f"🔓 <b>Лимит на передачу:</b> Снят\n\n"
                            ),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        self.logger.error(f"Error sending coins notification: {e}")

                    # Обновляем сообщение (УБИРАЕМ КНОПКИ ПОСЛЕ ПОДТВЕРЖДЕНИЯ)
                    try:
                        await callback.message.edit_caption(
                            caption=(
                                f"✅ <b>ДОНАТ ПОДТВЕРЖДЕН</b>\n\n"
                                f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                                f"💰 Сумма: {amount}₽\n"
                                f"🎁 Монеты: {coins_amount:,}\n"
                                f"🔓 Лимит на передачу: Снят\n"
                                f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}"
                            ),
                            parse_mode="HTML"
                        )
                    except:
                        pass
                else:
                    await callback.message.reply(f" {result_msg}")
            else:
                # Если данные не полные, используем старый метод
                await self._request_amount_for_coins(callback, check_id, check_info)

        except Exception as e:
            self.logger.error(f"Error in _approve_coins_check: {e}")
            await callback.message.reply(f" Ошибка: {e}")

    async def _approve_limit_check(self, callback: types.CallbackQuery,
                                   check_id: int, check_info: Dict[str, Any], additional_data: dict):
        """Подтверждает снятие лимита - обновленный для работы с обоими типами лимитов"""
        try:
            amount = additional_data.get('purchase_amount', 250)
            purchase_type = additional_data.get('purchase_type', 'transfer_limit')  # По умолчанию лимит на передачу

            success, result_msg = self.check_repo.approve_check(
                check_id=check_id,
                admin_id=callback.from_user.id,
                admin_username=callback.from_user.username or "",
                amount=amount,
                is_limit_removal=True
            )

            if success:
                # Проверяем тип лимита
                if purchase_type == 'roulette_limit':
                    # Лимит рулетки - получаем ID группы
                    group_id = additional_data.get('group_id')
                    if not group_id:
                        await callback.message.reply("❌ Ошибка: ID группы не указан в чеке")
                        return

                    # Снимаем лимит рулетки
                    from handlers.roulette.state_manager import state_manager
                    state_manager.unlock_roulette_with_donation(group_id, check_info['user_id'])

                    response = (
                        f"✅ <b>ЛИМИТ РУЛЕТКИ СНЯТ АВТОМАТИЧЕСКИ!</b>\n\n"
                        f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                        f"🎰 Тип: Лимит рулетки в группе\n"
                        f"🏷️ ID группы: <code>{group_id}</code>\n"
                        f"💰 Сумма: {amount}₽\n"
                        f"🔓 Рулетка теперь доступна без ограничений\n"
                        f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}"
                    )

                    # Отправляем уведомление пользователю
                    try:
                        await callback.bot.send_message(
                            chat_id=check_info['user_id'],
                            text=(
                                f"✅ <b>Ваш лимит рулетки подтверждён!</b>\n\n"
                                f"🎰 <b>Тип:</b> Снятие лимита рулетки в группе\n"
                                f"🏷️ <b>ID группы:</b> <code>{group_id}</code>\n"
                                f"💰 <b>Сумма:</b> {amount}₽\n"
                                f"🔓 <b>Статус:</b> Рулетка теперь доступна без ограничений"
                            ),
                            parse_mode="HTML"
                        )
                    except:
                        pass

                else:
                    # Лимит на передачу монет (существующая логика)
                    response = (
                        f"✅ <b>ЛИМИТ СНЯТ АВТОМАТИЧЕСКИ!</b>\n\n"
                        f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                        f"🎰 Тип: Лимит на передачу монет\n"
                        f"💰 Минимальный донат: {amount}₽\n"
                        f"🔓 Лимит на передачу снят\n"
                        f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}"
                    )

                    # Отправляем уведомление пользователю
                    try:
                        await callback.bot.send_message(
                            chat_id=check_info['user_id'],
                            text="✅ Лимит на передачу монет снят!",
                            parse_mode="HTML"
                        )
                    except:
                        pass

                await callback.message.reply(response, parse_mode="HTML")

                # Обновляем сообщение в админ-группе
                try:
                    await callback.message.edit_caption(
                        caption=(
                            f"✅ <b>ЛИМИТ СНЯТ АВТОМАТИЧЕСКИ</b>\n\n"
                            f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                            f"💰 Сумма: {amount}₽\n"
                            f"{'🏷️ ID группы: ' + str(additional_data.get('group_id', '')) if additional_data.get('group_id') else ''}\n"
                            f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}"
                        ),
                        parse_mode="HTML"
                    )
                except:
                    pass
            else:
                await callback.message.reply(f"❌ {result_msg}")

        except Exception as e:
            self.logger.error(f"Error in _approve_limit_check: {e}")
            await callback.message.reply(f"❌ Ошибка: {e}")

    async def handle_group_id_input(self, message: types.Message, state: FSMContext):
        """Обработка ввода ID группы для снятия лимита рулетки"""
        try:
            user_input = message.text.strip()

            # Проверяем, что введен ID группы (должен начинаться с -100 для супергрупп)
            if not user_input.startswith("-100"):
                await message.answer(
                    "❌ <b>Неверный формат ID группы!</b>\n\n"
                    "📌 <b>Правильный формат:</b>\n"
                    "<code>-1001234567890</code>\n\n"
                    "ℹ️ <b>Как получить ID группы:</b>\n"
                    "1. Добавьте бота в группу\n"
                    "2. Используйте команду /id в группе\n"
                    "3. Скопируйте ID (начинается с -100)\n\n"
                    "Пожалуйста, введите правильный ID группы:",
                    parse_mode="HTML"
                )
                return

            try:
                group_id = int(user_input)
            except ValueError:
                await message.answer(
                    "❌ ID группы должен быть числом!\n"
                    "Пример: <code>-1001234567890</code>\n\n"
                    "Пожалуйста, введите правильный ID:",
                    parse_mode="HTML"
                )
                return

            # Сохраняем ID группы в state
            await state.update_data(group_id=group_id)

            # Просим отправить фото чека
            await message.answer(
                "✅ <b>ID группы сохранен!</b>\n\n"
                "📸 <b>Теперь отправьте скриншот оплаты:</b>\n\n"
                "💎 <b>Сумма:</b> 500₽\n"
                "🎰 <b>Услуга:</b> Снятие лимита рулетки в группе\n"
                "🏷️ <b>Группа:</b> <code>{}</code>\n\n"
                "ℹ️ <b>Инструкция:</b>\n"
                "1. Сделайте скриншот успешной оплаты\n"
                "2. Отправьте фото или скриншот в этот чат\n"
                "3. Убедитесь, что чек читаемый\n\n"
                "⏳ <b>Время обработки:</b> до 24 часов\n"
                "👨‍💼 <b>Проверяет:</b> администратор\n\n"
                "⚠️ <b>Внимание:</b>\n"
                "• Отправляйте только реальные чеки\n"
                "• Фальшивые чеки приведут к бану".format(group_id),
                parse_mode="HTML"
            )

            # Переходим к состоянию ожидания фото
            await CheckStates.waiting_for_check_photo.set()

        except Exception as e:
            self.logger.error(f"Error in handle_group_id_input: {e}")
            await message.answer(
                "❌ Произошла ошибка при обработке ID группы.\n"
                "Пожалуйста, попробуйте снова или обратитесь к администратору."
            )
            await state.finish()

    async def _request_amount_for_coins(self, callback: types.CallbackQuery,
                                        check_id: int, check_info: Dict[str, Any]):
        """Запрашивает сумму для подтверждения чека (старый метод, если не удалось определить автоматически)"""
        await callback.message.answer(
            f"💳 <b>Подтверждение чека #{check_id}</b>\n\n"
            f"👤 Пользователь: @{check_info['username'] or 'без username'} "
            f"(ID: <code>{check_info['user_id']}</code>)\n\n"
            f"💰 <b>Введите сумму доната в рублях:</b>\n"
            f"📝 <b>Примечание:</b> Монеты начисляются автоматически (1 рубль = 10,000 монет)",
            parse_mode="HTML"
        )

        # Сохраняем данные для дальнейшей обработки
        from aiogram.dispatcher.filters.state import State, StatesGroup

        class ApproveStates(StatesGroup):
            waiting_for_amount = State()

        state = Dispatcher.get_current().current_state()
        await state.set_state(ApproveStates.waiting_for_amount)
        await state.update_data(
            check_id=check_id,
            user_id=check_info['user_id'],
            username=check_info['username'],
            callback_message_id=callback.message.message_id
        )

    async def process_amount_input(self, message: types.Message, state: FSMContext):
        """Обрабатывает ввод суммы (для старого метода)"""
        try:
            data = await state.get_data()
            check_id = data['check_id']

            # Получаем информацию о чеке
            check_info = self.check_repo.get_check(check_id)
            if not check_info:
                await message.reply(" Чек не найден")
                await state.finish()
                return

            # Проверяем, что введено число
            try:
                amount = float(message.text.replace(',', '.'))
                if amount <= 0:
                    await message.reply(" Сумма должна быть больше 0")
                    return
            except ValueError:
                await message.reply(" Пожалуйста, введите число (например: 1000)")
                return

            # Рассчитываем количество монет (курс 1 рубль = 10,000 монет)
            coins_amount = int(amount * 10000)

            # Подтверждаем чек
            success, result_msg = self.check_repo.approve_check(
                check_id=check_id,
                admin_id=message.from_user.id,
                admin_username=message.from_user.username or "",
                amount=amount,
                coins_amount=coins_amount
            )

            if success:
                # Получаем пользователя
                from database import get_db
                db = next(get_db())
                user = UserRepository.get_user_by_telegram_id(db, check_info['user_id'])

                response = (
                    f"✅ <b>Донат подтвержден!</b>\n\n"
                    f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                    f"💰 Сумма: {amount}₽\n"
                    f"🎁 Монеты: {coins_amount:,}\n"
                    f"👨‍💼 Админ: @{message.from_user.username or 'неизвестен'}"
                )

                await message.reply(response, parse_mode="HTML")

                # Отправляем уведомление пользователю
                try:
                    await message.bot.send_message(
                        chat_id=check_info['user_id'],
                        text=(
                            f"✅ <b>Ваш донат подтверждён!</b>\n\n"
                            f"💰 <b>Сумма:</b> {amount}₽\n"
                            f"🎁 <b>Начислено монет:</b> {coins_amount:,}\n\n"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error sending notification: {e}")

                # Обновляем сообщение в админ-группе (УБИРАЕМ КНОПКИ ПОСЛЕ ПОДТВЕРЖДЕНИЯ)
                try:
                    await message.bot.edit_message_caption(
                        chat_id=ADMIN_GROUP_ID,
                        message_id=data['callback_message_id'],
                        caption=(
                            f"✅ <b>ДОНАТ ПОДТВЕРЖДЕН</b>\n\n"
                            f"👤 Пользователь: @{check_info['username'] or check_info['first_name']}\n"
                            f"💰 Сумма: {amount}₽\n"
                            f"🎁 Монеты: {coins_amount:,}\n"
                            f"👨‍💼 Админ: @{message.from_user.username or 'неизвестен'}"
                        ),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

            else:
                await message.reply(f" {result_msg}")

            await state.finish()

        except Exception as e:
            self.logger.error(f"Error processing amount input: {e}")
            await message.reply(" Произошла ошибка")
            await state.finish()

    async def handle_ban_user(self, callback: types.CallbackQuery,
                              check_id: int, check_info: Dict[str, Any]):
        """Обрабатывает бан пользователя"""
        try:
            # Баним пользователя
            success, result_msg = self.check_repo.ban_user_for_check(
                check_id=check_id,
                admin_id=callback.from_user.id,
                admin_username=callback.from_user.username or "",
                reason="Фальшивый чек"
            )

            if success:
                # Отправляем сообщение в админ-группу
                admin_msg = CHECK_MESSAGES["admin_user_banned"].format(
                    username=check_info['username'] or "без username"
                )

                await callback.message.reply(f"✅ {admin_msg}")

                # Отправляем уведомление пользователю
                try:
                    await callback.bot.send_message(
                        chat_id=check_info['user_id'],
                        text=CHECK_MESSAGES["user_banned"],
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error sending ban notification: {e}")

                # Обновляем сообщение в админ-группе
                await callback.message.edit_caption(
                    caption=f" <b>Пользователь забанен</b>\n\n"
                            f"👤 Пользователь: @{check_info['username']}\n"
                            f"📛 Причина: Фальшивый чек\n"
                            f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}",
                    parse_mode="HTML"
                )

            else:
                await callback.answer(f" {result_msg}", show_alert=True)

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling ban user: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    async def handle_remove_limit(self, callback: types.CallbackQuery,
                                  check_id: int, check_info: Dict[str, Any]):
        """Обрабатывает снятие лимита"""
        try:
            # Снимаем лимит
            success, result_msg = self.check_repo.remove_limit_for_check(
                check_id=check_id,
                admin_id=callback.from_user.id,
                admin_username=callback.from_user.username or ""
            )

            if success:
                # Отправляем сообщение в админ-группу
                admin_msg = CHECK_MESSAGES["admin_limit_removed"].format(
                    username=check_info['username'] or "без username"
                )

                await callback.message.reply(f"✅ {admin_msg}")

                # Отправляем уведомление пользователю
                try:
                    await callback.bot.send_message(
                        chat_id=check_info['user_id'],
                        text=CHECK_MESSAGES["user_limit_removed"],
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error sending limit removal notification: {e}")

                # Обновляем сообщение в админ-группе
                await callback.message.edit_caption(
                    caption=f"🔓 <b>Лимит снят</b>\n\n"
                            f"👤 Пользователь: @{check_info['username']}\n"
                            f"✅ Лимит на передачу монет снят\n"
                            f"👨‍💼 Админ: @{callback.from_user.username or 'неизвестен'}",
                    parse_mode="HTML"
                )

            else:
                await callback.answer(f" {result_msg}", show_alert=True)

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error handling remove limit: {e}")
            await callback.answer(" Ошибка", show_alert=True)

    # ДОБАВЛЯЕМ ОТЛАДОЧНУЮ КОМАНДУ
    async def debug_check_command(self, message: types.Message):
        """Отладочная команда для проверки чеков"""
        if not self.check_repo.is_admin(message.from_user.id):
            return

        try:
            args = message.get_args().split()
            if not args:
                await message.answer("Использование: /debug_check [номер_чека]")
                return

            check_id = int(args[0])
            check_info = self.check_repo.get_check(check_id)

            if not check_info:
                await message.answer(f" Чек {check_id} не найден")
                return

            response = f"📋 <b>Чек #{check_id}</b>\n\n"
            response += f"👤 User ID: {check_info['user_id']}\n"
            response += f"💰 Amount: {check_info['amount']}\n"
            response += f"📝 Notes: {check_info['notes']}\n"
            response += f"📊 Status: {check_info['status']}\n"

            # Additional data
            if check_info.get('additional_data'):
                response += f"\n🔧 <b>Additional Data:</b>\n"
                for key, value in check_info['additional_data'].items():
                    response += f"• {key}: {value}\n"
            else:
                response += f"\n⚠️ <b>Additional Data:</b> None\n"

            await message.answer(response, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error in debug_check_command: {e}")
            await message.answer(f" Ошибка: {e}")

    async def check_status_command(self, message: types.Message):
        """Команда для проверки статуса чека"""
        try:
            args = message.get_args().split()
            if not args:
                await message.answer(
                    "📊 <b>Проверка статуса чека</b>\n\n"
                    "Использование: <code>/check_status [номер чека]</code>\n"
                    "Пример: <code>/check_status 123</code>\n\n"
                    "Чтобы получить номер чека, отправьте чек боту.",
                    parse_mode="HTML"
                )
                return

            check_id = int(args[0])
            check_info = self.check_repo.get_check(check_id)

            if not check_info:
                await message.answer(" Чек с таким номером не найден.")
                return

            # Проверяем, что пользователь запрашивает свой чек
            if message.from_user.id != check_info['user_id'] and not self.check_repo.is_admin(message.from_user.id):
                await message.answer(" Вы можете проверять только свои чеки.")
                return

            # Формируем статус
            status_icons = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '',
                'banned': '🚫',
                'limit_removed': '🔓'
            }

            status_texts = {
                'pending': 'Ожидает проверки',
                'approved': 'Подтвержден',
                'rejected': 'Отклонен',
                'banned': 'Пользователь забанен',
                'limit_removed': 'Лимит снят'
            }

            icon = status_icons.get(check_info['status'], '❓')
            status_text = status_texts.get(check_info['status'], 'Неизвестен')

            response = (
                f"📄 <b>Информация о чеке #{check_id}</b>\n\n"
                f"{icon} <b>Статус:</b> {status_text}\n"
                f"📅 <b>Дата отправки:</b> {check_info['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
            )

            if check_info['processed_at']:
                response += f"📅 <b>Дата обработки:</b> {check_info['processed_at'].strftime('%d.%m.%Y %H:%M')}\n"

            if check_info['amount']:
                response += f"💰 <b>Сумма доната:</b> {check_info['amount']} руб.\n"

            if check_info['coins_given']:
                response += f"🎁 <b>Начислено монет:</b> {check_info['coins_given']:,}\n"

            if check_info['notes']:
                response += f"📝 <b>Примечание:</b> {check_info['notes']}\n"


            await message.answer(response, parse_mode="HTML")

        except ValueError:
            await message.answer(" Неверный формат номера чека.")
        except Exception as e:
            self.logger.error(f"Error in check_status_command: {e}")
            await message.answer(" Произошла ошибка.")

    async def check_history_command(self, message: types.Message):
        """Команда для просмотра истории чеков"""
        try:
            user_id = message.from_user.id
            checks = self.check_repo.get_user_checks(user_id, limit=10)

            if not checks:
                await message.answer(
                    "📭 <b>История чеков пуста</b>\n\n"
                    "Вы еще не отправляли чеки на проверку.\n"
                    "Чтобы отправить чек, просто отправьте фото или скриншот боту.",
                    parse_mode="HTML"
                )
                return

            response = "📋 <b>История ваших чеков</b>\n\n"

            for check in checks:
                status_icons = {
                    'pending': '⏳',
                    'approved': '✅',
                    'rejected': '',
                    'banned': '🚫',
                    'limit_removed': '🔓'
                }

                icon = status_icons.get(check['status'], '❓')
                date_str = check['created_at'].strftime('%d.%m')

                line = f"{icon} <b>#{check['id']}</b> ({date_str})"

                if check['coins_given']:
                    line += f" - {check['coins_given']:,} монет"

                response += line + "\n"

            response += f"\n📊 <b>Всего чеков:</b> {len(checks)}"

            await message.answer(response, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error in check_history_command: {e}")
            await message.answer(" Произошла ошибка.")

    # Админ-команды
    async def admin_checks_command(self, message: types.Message):
        """Команда для просмотра всех ожидающих чеков (админ)"""
        if not self.check_repo.is_admin(message.from_user.id):
            await message.answer(" У вас нет прав для этой команды.")
            return

        try:
            checks = self.check_repo.get_pending_checks(limit=20)

            if not checks:
                await message.answer("✅ Нет ожидающих проверки чеков.")
                return

            response = "⏳ <b>Ожидающие проверки чеков</b>\n\n"

            for i, check in enumerate(checks, 1):
                time_ago = (datetime.now() - check['created_at']).total_seconds() / 3600
                hours = int(time_ago)
                minutes = int((time_ago - hours) * 60)

                response += (
                    f"{i}. <b>#{check['id']}</b> - @{check['username'] or 'нет'} "
                    f"(ID: <code>{check['user_id']}</code>)\n"
                    f"   👤 {check['first_name']}\n"
                    f"   ⏰ {hours}ч {minutes}м назад\n\n"
                )

            response += f"📊 <b>Всего:</b> {len(checks)} чеков"

            await message.answer(response, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error in admin_checks_command: {e}")
            await message.answer(" Произошла ошибка.")

    async def admin_logs_command(self, message: types.Message):
        """Команда для просмотра логов (админ)"""
        if not self.check_repo.is_admin(message.from_user.id):
            await message.answer(" У вас нет прав для этой команды.")
            return

        try:
            args = message.get_args().split()
            user_id = None
            admin_id = None
            action = None

            # Парсим аргументы
            i = 0
            while i < len(args):
                if args[i] == "-u" and i + 1 < len(args):
                    user_id = int(args[i + 1])
                    i += 2
                elif args[i] == "-a" and i + 1 < len(args):
                    admin_id = int(args[i + 1])
                    i += 2
                elif args[i] == "-t" and i + 1 < len(args):
                    action = args[i + 1]
                    i += 2
                else:
                    i += 1

            logs = self.check_repo.get_action_logs(
                user_id=user_id,
                admin_id=admin_id,
                action=action,
                limit=50
            )

            if not logs:
                await message.answer("📭 Логи не найдены.")
                return

            response = "📊 <b>Логи действий</b>\n\n"

            action_icons = {
                'check_created': '📸',
                'approve': '✅',
                'ban': '',
                'unban': '🔓',
                'remove_limit': '🔓',
                'reject': ''
            }

            for log in logs[:20]:  # Ограничиваем вывод
                icon = action_icons.get(log['action'], '📝')
                date_str = log['created_at'].strftime('%d.%m %H:%M')

                response += (
                    f"{icon} <b>{log['action']}</b>\n"
                    f"👤 User: <code>{log['user_id']}</code>\n"
                    f"👨‍💼 Admin: <code>{log['admin_id']}</code>\n"
                    f"📅 {date_str}\n"
                )

                if log['amount']:
                    response += f"💰 {log['amount']} руб.\n"

                if log['notes']:
                    response += f"📝 {log['notes']}\n"

                response += "\n"

            if len(logs) > 20:
                response += f"\n📋 ... и еще {len(logs) - 20} записей"

            await message.answer(response, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error in admin_logs_command: {e}")
            await message.answer(" Произошла ошибка.")

    async def admin_ban_command(self, message: types.Message):
        """Команда для бана пользователя (админ)"""
        if not self.check_repo.is_admin(message.from_user.id):
            await message.answer(" У вас нет прав для этой команды.")
            return

        try:
            args = message.get_args().split()
            if len(args) < 2:
                await message.answer(
                    " Использование: <code>/admin_ban [ID] [причина]</code>\n"
                    "Пример: <code>/admin_ban 123456 Нарушение правил</code>",
                    parse_mode="HTML"
                )
                return

            user_id = int(args[0])
            reason = " ".join(args[1:])

            # Создаем фиктивный чек для логирования
            from datetime import datetime
            with self.check_repo._db_session() as db:
                fake_check = Check(
                    user_id=user_id,
                    chat_id=0,
                    username="",
                    first_name="",
                    check_photo_id="",
                    status='banned',
                    admin_id=message.from_user.id,
                    admin_username=message.from_user.username or "",
                    processed_at=datetime.now(),
                    notes=f"Бан через команду: {reason}"
                )
                db.add(fake_check)
                db.commit()
                db.refresh(fake_check)

                # Баним пользователя
                success, result_msg = self.check_repo.ban_user_for_check(
                    check_id=fake_check.id,
                    admin_id=message.from_user.id,
                    admin_username=message.from_user.username or "",
                    reason=reason
                )

            if success:
                await message.answer(
                    f"✅ Пользователь <code>{user_id}</code> забанен.\n"
                    f"📝 Причина: {reason}",
                    parse_mode="HTML"
                )

                # Отправляем уведомление пользователю
                try:
                    await message.bot.send_message(
                        chat_id=user_id,
                        text=f" Вы были забанены администратором.\n"
                             f"Причина: {reason}\n\n"
                             f"Для разбана обратитесь к администратору."
                    )
                except:
                    pass
            else:
                await message.answer(f" {result_msg}")

        except ValueError:
            await message.answer(" Неверный формат ID.")
        except Exception as e:
            self.logger.error(f"Error in admin_ban_command: {e}")
            await message.answer(" Произошла ошибка.")

    async def admin_unban_command(self, message: types.Message):
        """Команда для разбана пользователя (админ)"""
        if not self.check_repo.is_admin(message.from_user.id):
            await message.answer(" У вас нет прав для этой команды.")
            return

        try:
            args = message.get_args().split()
            if len(args) < 2:
                await message.answer(
                    " Использование: <code>/admin_unban [ID] [причина]</code>\n"
                    "Пример: <code>/admin_unban 123456 Ошибка</code>",
                    parse_mode="HTML"
                )
                return

            user_id = int(args[0])
            reason = " ".join(args[1:])

            success, result_msg = self.check_repo.unban_user(
                user_id=user_id,
                admin_id=message.from_user.id,
                reason=reason
            )

            if success:
                await message.answer(
                    f"✅ Пользователь <code>{user_id}</code> разбанен.\n"
                    f"📝 Причина: {reason}",
                    parse_mode="HTML"
                )

                # Отправляем уведомление пользователю
                try:
                    await message.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Вы были разбанены администратором.\n"
                             f"Причина: {reason}"
                    )
                except:
                    pass
            else:
                await message.answer(f" {result_msg}")

        except ValueError:
            await message.answer(" Неверный формат ID.")
        except Exception as e:
            self.logger.error(f"Error in admin_unban_command: {e}")
            await message.answer(" Произошла ошибка.")