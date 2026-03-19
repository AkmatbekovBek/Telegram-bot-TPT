# handlers/admin/user_info_handler.py

import logging
from datetime import datetime, timedelta

import pytz
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from database import get_db, models
from database.crud import UserRepository, TransactionRepository, ShopRepository
from handlers.admin.admin_helpers import check_admin_async, format_number
from handlers.admin.user_info_states import UserInfoStates


# ИМПОРТ ДЛЯ ИСТОРИИ
from handlers.history.merge_handler import HistoryMergeHandler

logger = logging.getLogger(__name__)


class UserInfoHandler:
    """Обработчик команды /id для отображения информации о пользователе"""

    def __init__(self):
        self.logger = logger
        self.utc = pytz.UTC  # Добавляем UTC часовой пояс
        self.history_merge_handler = HistoryMergeHandler()  # Инициализируем обработчик истории

    async def idgroup_command(self, message: types.Message):
        """Показывает ID текущей группы"""
        await message.reply(
            f"🆔 <b>ID:</b> <code>{message.chat.id}</code>",
            parse_mode="HTML"
        )

    def _normalize_datetime(self, dt_obj):
        """Приводит datetime к offset-naive (убирает часовой пояс)"""
        if not dt_obj:
            return None

        if hasattr(dt_obj, 'tzinfo') and dt_obj.tzinfo is not None:
            # Если есть часовой пояс, преобразуем в UTC и убираем его
            utc_dt = dt_obj.astimezone(self.utc)
            return utc_dt.replace(tzinfo=None)

        return dt_obj

    def _get_user_max_loss(self, db, user_id: int):
        """Получает максимальный проигрыш пользователя"""
        try:
            # Получаем из RouletteTransaction
            from database.crud import RouletteRepository
            from sqlalchemy import func

            max_loss_result = db.query(
                func.min(models.RouletteTransaction.profit)
            ).filter(
                models.RouletteTransaction.user_id == user_id
            ).scalar()

            if max_loss_result and max_loss_result < 0:
                return abs(max_loss_result)
            return 0
        except Exception as e:
            self.logger.error(f"Error getting max loss: {e}")
            return 0

    def _is_in_date_range(self, date_to_check, start_date, end_date):
        """Проверяет, находится ли дата в диапазоне"""
        if not start_date and not end_date:
            return True

        if not date_to_check:  # Если дата не определена, пропускаем
            return False

        # Приводим все даты к naive datetime (без часового пояса)
        # ПРЕОБРАЗУЕМ В UTC СНАЧАЛА, ЗАТЕМ УБИРАЕМ ЧАСОВОЙ ПОЯС
        if hasattr(date_to_check, 'tzinfo') and date_to_check.tzinfo is not None:
            date_to_check = date_to_check.astimezone(self.utc).replace(tzinfo=None)

        if start_date:
            if hasattr(start_date, 'tzinfo') and start_date.tzinfo is not None:
                start_date = start_date.astimezone(self.utc).replace(tzinfo=None)
            if date_to_check < start_date:
                return False

        if end_date:
            if hasattr(end_date, 'tzinfo') and end_date.tzinfo is not None:
                end_date = end_date.astimezone(self.utc).replace(tzinfo=None)
            if date_to_check > end_date:
                return False

        return True

    def _get_donate_status_info(self, db, user_id: int):
        """Получает информацию о донат-статусе пользователя"""
        try:
            from handlers.donate.status_repository import StatusRepository
            status_repo = StatusRepository()
            active_status = status_repo.get_user_active_status(user_id)

            status_icons = {
                1: "🐾",  # Обычный
                2: "🌑",  # Бронза
                3: "💰",  # Платина
                4: "🥇",  # Золото
                5: "💎",  # Бриллиант
            }

            if active_status:
                status_id = active_status['status_id']
                status_icon = status_icons.get(status_id, "🐾")
                status_name = active_status['status_name'].title()
                return f"{status_name}{status_icon}"
            else:
                return None
        except Exception as e:
            self.logger.error(f"Error getting donate status: {e}")
            return None


    def _get_license_info(self, db, user_id: int):
        """Получает информацию о лицензиях"""
        try:
            from sqlalchemy import text

            # Подсчитываем обычные лицензии (item_id = 3)
            standard_result = db.execute(
                text("""
                     SELECT COUNT(*) as count
                     FROM user_purchases
                     WHERE user_id = :user_id
                       AND item_id = 3
                       AND (expires_at IS NULL
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
                       AND (expires_at IS NULL
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
            self.logger.error(f"Error getting license info: {e}")
            return {'standard': 0, 'vip': 0}

    async def show_user_info(self, message: types.Message):
        """Показывает информацию о пользователе по ID из команды /123456789"""
        if not await check_admin_async(message):
            return

        try:
            # Получаем ID из текста команды (например: /123456789)
            command_text = message.text.strip()

            # Проверяем разные варианты команд
            if command_text.startswith('/'):
                # Убираем слэш и проверяем, это число ли
                potential_id = command_text[1:].strip()

                # Если есть пробел после ID (например: /123456789 или /123456789 текст)
                if ' ' in potential_id:
                    potential_id = potential_id.split()[0]

                # Проверяем, что это число
                if not potential_id.isdigit():
                    await self._show_help_message(message)
                    return

                user_id = int(potential_id)

                # Проверяем, что ID разумный (больше 0 и меньше максимального 64-битного числа)
                if user_id <= 0 or user_id > 9223372036854775807:
                    await message.answer(" Неверный формат ID пользователя")
                    return

                await self._display_user_info(message, user_id)
            else:
                await self._show_help_message(message)

        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in show_user_info: {e}")
            await message.answer(" Произошла ошибка при получении информации о пользователе")

    def _show_help_message(self, message: types.Message):
        """Показывает сообщение о помощи"""
        help_text = (
            "🔍 <b>Использование команды:</b>\n\n"
            "Чтобы посмотреть информацию о пользователе, используйте:\n"
            "<code>/123456789</code> - где 123456789 это ID пользователя\n\n"
            "<b>Или ответьте на сообщение пользователя:</b>\n"
            "1. Ответьте на сообщение пользователя\n"
            "2. Отправьте команду <code>/id</code>\n\n"
            "📝 <b>Примеры:</b>\n"
            "• <code>/123456789</code>\n"
            "• <code>/987654321</code>\n"
            "• Ответ на сообщение + <code>/id</code>\n\n"
            "👮‍♂️ <i>Доступно только для администраторов</i>"
        )
        message.answer(help_text, parse_mode="HTML")

    async def show_user_info_reply(self, message: types.Message):
        """Показывает информацию о пользователе из reply сообщения"""
        if not await check_admin_async(message):
            return

        try:
            # Проверяем, что это команда /id и есть reply
            if message.text and message.text.strip().lower() == '/id':
                if message.reply_to_message and message.reply_to_message.from_user:
                    user_id = message.reply_to_message.from_user.id
                    await self._display_user_info(message, user_id)
                else:
                    await message.answer(
                        " Для использования этой команды ответьте на сообщение пользователя\n\n"
                        "💡 <b>Как использовать:</b>\n"
                        "1. Найдите сообщение пользователя\n"
                        "2. Ответьте на него (reply)\n"
                        "3. Отправьте <code>/id</code>",
                        parse_mode="HTML"
                    )

        except Exception as e:
            self.logger.error(f"Error in show_user_info_reply: {e}")
            await message.answer(" Произошла ошибка при получении информации о пользователе")

    async def _display_user_info(self, message: types.Message, user_id: int):
        """Отображает информацию о пользователе (первоначальный показ)"""
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await message.answer(f" Пользователь с ID {user_id} не найден")
                db.close()
                return

            # Получаем максимальный проигрыш
            max_loss = self._get_user_max_loss(db, user_id)

            # Получаем информацию о донат-статусе и лицензиях
            donate_status = self._get_donate_status_info(db, user_id)
            license_info = self._get_license_info(db, user_id)

            # Формируем информацию
            info_text = (
                f"👤 <b>Информация о пользователе</b>\n\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                f"📛 <b>Никнейм:</b> {self._get_user_display_name(user)}\n"
            )
            
            if donate_status:
                info_text += f"💎 <b>Status:</b> {donate_status}\n"
                
            info_text += (
                f"📋 <b>Лицензий:</b> {license_info['standard']}\n"
                f"⭐ <b>VIP-лицензий:</b> {license_info['vip']}\n\n"
                f"💰 <b>Баланс:</b> {format_number(user.coins)} Монет\n"
                f"✅ <b>Выиграно всего:</b> {format_number(user.win_coins or 0)} Монет\n"
                f" <b>Проиграно всего:</b> {format_number(user.defeat_coins or 0)} Монет\n"
                f"🎯 <b>Максимальная ставка:</b> {format_number(user.max_bet or 0)}\n"
                f"📉 <b>Максимальный проигрыш:</b> {format_number(max_loss)}\n"
                f"📈 <b>Максимальный выигрыш:</b> {format_number(user.max_win_coins or 0)}\n"
            )

            # Добавляем информацию о бане в боте (через mute_ban.py)
            try:
                from handlers.admin.mute_ban import mute_ban_manager
                is_banned = mute_ban_manager.bot_ban_manager.is_user_bot_banned(user_id)
                if is_banned:
                    info_text += f"\n🚫 <b>Статус:</b> Забанен в боте"
            except Exception as e:
                self.logger.warning(f"Could not check bot ban status: {e}")

            # Добавляем информацию о регистрации
            if hasattr(user, 'created_at') and user.created_at:
                info_text += f"\n📅 <b>Зарегистрирован:</b> {user.created_at.strftime('%d.%m.%Y %H:%M')}"

            # Создаем клавиатуру с кнопками
            keyboard = self._create_user_info_keyboard(user_id)

            await message.answer(info_text, parse_mode="HTML", reply_markup=keyboard)
            db.close()

        except Exception as e:
            self.logger.error(f"Error in _display_user_info: {e}")
            await message.answer(" Ошибка при формировании информации")
            try:
                db.close()
            except:
                pass

    def _get_user_display_name(self, user) -> str:
        """Возвращает отображаемое имя пользователя"""
        if user.username:
            return f"@{user.username}"
        elif user.first_name:
            return user.first_name
        else:
            return f"Пользователь {user.telegram_id}"

    def _create_user_info_keyboard(self, user_id: int) -> types.InlineKeyboardMarkup:
        """Создает клавиатуру с действиями для пользователя"""
        keyboard = types.InlineKeyboardMarkup(row_width=2)

        # Основные кнопки
        keyboard.row(
            types.InlineKeyboardButton("🔢 Обнулить", callback_data=f"user_reset_{user_id}"),
            types.InlineKeyboardButton("🚫 Забанить", callback_data=f"user_ban_{user_id}")
        )

        keyboard.row(
            types.InlineKeyboardButton("✅ Разбанить", callback_data=f"user_unban_{user_id}"),
            types.InlineKeyboardButton("🔓 Снять лимит", callback_data=f"user_unlimit_{user_id}")
        )

        keyboard.row(
            types.InlineKeyboardButton("🔒 Выдать лимит", callback_data=f"user_limit_{user_id}"),
            types.InlineKeyboardButton("📋 История", callback_data=f"user_history_{user_id}")
        )

        keyboard.row(
            types.InlineKeyboardButton("📜 Выдать лицензию", callback_data=f"user_givelicense_{user_id}")
        )

        return keyboard

    async def handle_reset_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Обнулить"""
        try:
            user_id = int(callback.data.split('_')[-1])

            # Создаем клавиатуру для выбора что обнулить
            keyboard = types.InlineKeyboardMarkup(row_width=2)

            keyboard.row(
                types.InlineKeyboardButton("💰 Баланс", callback_data=f"reset_balance_{user_id}"),
                types.InlineKeyboardButton("✅ Выигрыши", callback_data=f"reset_wins_{user_id}")
            )

            keyboard.row(
                types.InlineKeyboardButton(" Проигрыши", callback_data=f"reset_losses_{user_id}"),
                types.InlineKeyboardButton("🎯 Макс ставка", callback_data=f"reset_maxbet_{user_id}")
            )

            keyboard.row(
                types.InlineKeyboardButton("📉 Макс проигрыш", callback_data=f"reset_maxloss_{user_id}"),
                types.InlineKeyboardButton("📈 Макс выигрыш", callback_data=f"reset_maxwin_{user_id}")
            )

            keyboard.add(
                types.InlineKeyboardButton("🗑️ Всё сразу", callback_data=f"reset_all_{user_id}")
            )

            keyboard.add(
                types.InlineKeyboardButton("⬅️ Назад", callback_data=f"user_back_{user_id}")
            )

            await callback.message.edit_text(
                f"🔢 <b>Обнуление данных пользователя</b>\n\n"
                f"👤 Пользователь: <code>{user_id}</code>\n\n"
                f"⚠️ <b>Выберите что обнулить:</b>\n"
                f"• <code>💰 Баланс</code> - установит баланс в 0\n"
                f"• <code>✅ Выигрыши</code> - обнулит счетчик выигрышей\n"
                f"• <code> Проигрыши</code> - обнулит счетчик проигрышей\n"
                f"• <code>🎯 Макс ставка</code> - обнулит максимальную ставку\n"
                f"• <code>📉 Макс проигрыш</code> - обнулит максимальный проигрыш\n"
                f"• <code>📈 Макс выигрыш</code> - обнулит максимальный выигрыш\n\n"
                f"<i>После выбора потребуется подтверждение</i>",
                parse_mode="HTML",
                reply_markup=keyboard
            )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_reset_button: {e}")
            await callback.answer(" Ошибка при обработке кнопки")

    async def handle_reset_confirm(self, callback: types.CallbackQuery):
        """Подтверждение обнуления"""
        try:
            data_parts = callback.data.split('_')
            reset_type = data_parts[1]  # balance, wins, losses и т.д.
            user_id = int(data_parts[-1])

            # Получаем информацию о пользователе
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await callback.answer(" Пользователь не найден", show_alert=True)
                db.close()
                return

            # Создаем клавиатуру подтверждения
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton("✅ Да, обнулить", callback_data=f"confirm_reset_{reset_type}_{user_id}"),
                types.InlineKeyboardButton(" Нет, отмена", callback_data=f"user_reset_{user_id}")
            )

            reset_names = {
                'balance': 'баланс',
                'wins': 'выигрыши',
                'losses': 'проигрыши',
                'maxbet': 'максимальную ставку',
                'maxloss': 'максимальный проигрыш',
                'maxwin': 'максимальный выигрыш',
                'all': 'все данные'
            }

            try:
                await callback.message.edit_text(
                    f"⚠️ <b>ПОДТВЕРЖДЕНИЕ ОБНУЛЕНИЯ</b>\n\n"
                    f"👤 Пользователь: {self._get_user_display_name(user)} (<code>{user_id}</code>)\n"
                    f"📛 Обнулить: <b>{reset_names.get(reset_type, reset_type)}</b>\n\n"
                    f"❓ <b>Вы уверены, что хотите обнулить эти данные?</b>\n\n"
                    f"<i>Это действие нельзя отменить!</i>",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            except Exception as e:
                # Игнорируем ошибку, если сообщение не изменилось
                if "message is not modified" in str(e).lower():
                    pass
                else:
                    raise e

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_reset_confirm: {e}")
            await callback.answer(" Ошибка при подтверждении")

    async def execute_reset(self, callback: types.CallbackQuery):
        """Выполняет обнуление данных"""
        try:
            data_parts = callback.data.split('_')
            reset_type = data_parts[2]  # Тип обнуления
            user_id = int(data_parts[3])

            db = next(get_db())

            try:
                if reset_type == 'balance':
                    # Обнуляем баланс
                    UserRepository.update_user_balance(db, user_id, 0)
                    # Создаем транзакцию обнуления
                    TransactionRepository.create_transaction(
                        db=db,
                        from_user_id=user_id,
                        to_user_id=None,
                        amount=0,
                        description="админ обнуление баланса"
                    )

                elif reset_type == 'wins':
                    # Обнуляем выигрыши
                    UserRepository.update_user_stats(db, user_id, win_coins=0)

                elif reset_type == 'losses':
                    # Обнуляем проигрыши
                    UserRepository.update_user_stats(db, user_id, defeat_coins=0)

                elif reset_type == 'maxbet':
                    # Обнуляем максимальную ставку
                    UserRepository.update_user_stats(db, user_id, max_bet=0)

                elif reset_type == 'maxloss':
                    # Обнуляем максимальный проигрыш (удаляем записи из RouletteTransaction)
                    from database.crud import RouletteRepository
                    # Здесь можно удалить записи или обнулить поле
                    # В зависимости от вашей структуры базы данных
                    pass

                elif reset_type == 'maxwin':
                    # Обнуляем максимальный выигрыш
                    UserRepository.update_user_stats(db, user_id, max_win_coins=0)

                elif reset_type == 'all':
                    # Обнуляем всё
                    UserRepository.update_user_balance(db, user_id, 0)
                    UserRepository.update_user_stats(db, user_id,
                                                     win_coins=0,
                                                     defeat_coins=0,
                                                     max_win_coins=0,
                                                     min_win_coins=0
                                                     )
                    # Создаем транзакцию обнуления
                    TransactionRepository.create_transaction(
                        db=db,
                        from_user_id=user_id,
                        to_user_id=None,
                        amount=0,
                        description="админ полное обнуление"
                    )

                db.commit()

                # Логируем действие
                admin_id = callback.from_user.id
                self.logger.info(f"Admin {admin_id} reset {reset_type} for user {user_id}")

                await callback.message.edit_text(
                    f"✅ <b>Данные успешно обнулены!</b>\n\n"
                    f"👤 Пользователь: <code>{user_id}</code>\n"
                    f"📛 Тип обнуления: {reset_type}\n"
                    f"👮‍♂️ Администратор: {callback.from_user.first_name}\n\n"
                    f"<i>Действие выполнено успешно</i>",
                    parse_mode="HTML"
                )

            except Exception as db_error:
                db.rollback()
                self.logger.error(f"Database error in execute_reset: {db_error}")
                await callback.message.edit_text(
                    " <b>Ошибка базы данных!</b>\n\n"
                    "Не удалось обнулить данные. Попробуйте позже.",
                    parse_mode="HTML"
                )

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in execute_reset: {e}")
            await callback.answer(" Ошибка при выполнении обнуления")

    async def handle_ban_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Забанить - использует mute_ban_manager"""
        try:
            user_id = int(callback.data.split('_')[-1])

            # Получаем информацию о пользователе
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await callback.answer(" Пользователь не найден", show_alert=True)
                db.close()
                return

            # Проверяем, не забанен ли уже через mute_ban_manager
            from handlers.admin.mute_ban import mute_ban_manager
            is_banned = mute_ban_manager.bot_ban_manager.is_user_bot_banned(user_id)

            if is_banned:
                await callback.answer("ℹ️ Пользователь уже забанен в боте", show_alert=True)
                db.close()
                return

            # Запрашиваем причину бана
            await callback.message.edit_text(
                f"🚫 <b>Забанить пользователя в боте</b>\n\n"
                f"👤 Пользователь: {self._get_user_display_name(user)} (<code>{user_id}</code>)\n\n"
                f"📝 <b>Введите причину бана:</b>\n"
                f"• Причина будет отправлена пользователю\n"
                f"• Можно использовать обычный текст\n"
                f"• Нажмите /cancel для отмены\n\n"
                f"<i>Пользователь будет заблокирован в боте до снятия бана</i>",
                parse_mode="HTML"
            )

            # Сохраняем user_id в state
            from aiogram.dispatcher import FSMContext
            state = Dispatcher.get_current().current_state()
            await state.update_data(ban_user_id=user_id)

            # Запускаем FSM для ввода причины
            from handlers.admin.user_info_states import UserInfoStates
            await UserInfoStates.waiting_for_ban_reason.set()

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_ban_button: {e}")
            await callback.answer(" Ошибка при обработке бана")

    async def handle_unban_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Разбанить - использует mute_ban_manager"""
        try:
            user_id = int(callback.data.split('_')[-1])

            # Проверяем, забанен ли пользователь через mute_ban_manager
            from handlers.admin.mute_ban import mute_ban_manager
            is_banned = mute_ban_manager.bot_ban_manager.is_user_bot_banned(user_id)

            if not is_banned:
                await callback.answer("ℹ️ Пользователь не забанен в боте", show_alert=True)
                return

            # Разбаниваем пользователя через mute_ban_manager
            success = await mute_ban_manager.unban_in_bot(user_id)

            if success:
                # Отправляем уведомление пользователю
                try:
                    await callback.bot.send_message(
                        chat_id=user_id,
                        text="✅ Вы разбанены в боте. Теперь вы можете пользоваться и играть в боте."
                    )
                except:
                    pass  # Игнорируем ошибки отправки

                await callback.message.edit_text(
                    f"✅ <b>Пользователь разбанен в боте!</b>\n\n"
                    f"👤 ID: <code>{user_id}</code>\n"
                    f"👮‍♂️ Администратор: {callback.from_user.first_name}\n\n"
                    f"<i>Пользователь получил уведомление о разбане</i>",
                    parse_mode="HTML"
                )

                # Логируем действие
                admin_id = callback.from_user.id
                self.logger.info(f"Admin {admin_id} unbanned user {user_id} in bot")
            else:
                await callback.message.edit_text(
                    " <b>Ошибка при разбане в боте!</b>\n\n"
                    "Не удалось разбанить пользователя. Попробуйте позже.",
                    parse_mode="HTML"
                )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_unban_button: {e}")
            await callback.answer(" Ошибка при разбане")

    async def handle_unlimit_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Снять лимит"""
        try:
            user_id = int(callback.data.split('_')[-1])

            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await callback.answer(" Пользователь не найден", show_alert=True)
                db.close()
                return

            # Проверяем, не снят ли уже лимит через ShopRepository
            from database.crud import ShopRepository
            user_purchases = ShopRepository.get_user_purchases(db, user_id)

            # Проверяем наличие привилегии unlimit (ID 3)
            if 3 in user_purchases:
                await callback.answer("ℹ️ У пользователя уже снят лимит", show_alert=True)
                db.close()
                return

            # Выдаем привилегию unlimit
            try:
                from handlers.admin.admin_constants import PRIVILEGES, SHOP_ITEMS

                ShopRepository.add_user_purchase(
                    db,
                    user_id,
                    SHOP_ITEMS["unlimited_transfers"],  # ID 3
                    PRIVILEGES["unlimit"]["name"],  # "🔐 Снятие лимита перевода"
                    0  # навсегда
                )
                db.commit()

                await callback.message.edit_text(
                    f"✅ <b>Лимит переводов снят!</b>\n\n"
                    f"👤 Пользователь: {self._get_user_display_name(user)} (<code>{user_id}</code>)\n"
                    f"👮‍♂️ Администратор: {callback.from_user.first_name}\n\n"
                    f"<i>Пользователь может переводить неограниченные суммы</i>",
                    parse_mode="HTML"
                )

                # Логируем действие
                admin_id = callback.from_user.id
                self.logger.info(f"Admin {admin_id} removed transfer limit for user {user_id}")

            except Exception as db_error:
                db.rollback()
                self.logger.error(f"Database error in handle_unlimit_button: {db_error}")
                await callback.message.edit_text(
                    " <b>Ошибка базы данных!</b>\n\n"
                    "Не удалось снять лимит. Попробуйте позже.",
                    parse_mode="HTML"
                )

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_unlimit_button: {e}")
            await callback.answer(" Ошибка при снятии лимита")

    async def handle_limit_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Выдать лимит"""
        try:
            user_id = int(callback.data.split('_')[-1])

            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await callback.answer(" Пользователь не найден", show_alert=True)
                db.close()
                return

            # Проверяем, установлен ли уже лимит через ShopRepository
            from database.crud import ShopRepository
            user_purchases = ShopRepository.get_user_purchases(db, user_id)

            # Проверяем наличие привилегии unlimit (ID 3)
            if 3 not in user_purchases:
                await callback.answer("ℹ️ У пользователя уже установлен лимит", show_alert=True)
                db.close()
                return

            # Удаляем привилегию unlimit
            from handlers.admin.admin_constants import SHOP_ITEMS

            try:
                # Удаляем по ID привилегии
                ShopRepository.remove_user_purchase(db, user_id, SHOP_ITEMS["unlimited_transfers"])
                db.commit()

                await callback.message.edit_text(
                    f"✅ <b>Лимит переводов установлен!</b>\n\n"
                    f"👤 Пользователь: {self._get_user_display_name(user)} (<code>{user_id}</code>)\n"
                    f"👮‍♂️ Администратор: {callback.from_user.first_name}\n\n"
                    f"<i>Пользователь теперь ограничен стандартными лимитами переводов</i>",
                    parse_mode="HTML"
                )

                # Логируем действие
                admin_id = callback.from_user.id
                self.logger.info(f"Admin {admin_id} added transfer limit for user {user_id}")

            except Exception as db_error:
                db.rollback()
                self.logger.error(f"Database error in handle_limit_button: {db_error}")
                await callback.message.edit_text(
                    " <b>Ошибка базы данных!</b>\n\n"
                    "Не удалось установить лимит. Попробуйте позже.",
                    parse_mode="HTML"
                )

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_limit_button: {e}")
            await callback.answer(" Ошибка при установке лимита")

    async def handle_history_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки История"""
        try:
            user_id = int(callback.data.split('_')[-1])

            # Показываем меню фильтров истории
            keyboard = types.InlineKeyboardMarkup(row_width=2)

            # Основные фильтры по типу (весь период)
            keyboard.row(
                types.InlineKeyboardButton("📊 Вся история", callback_data=f"history_all_0_{user_id}"),
                types.InlineKeyboardButton("✅ Выигрыши", callback_data=f"history_wins_0_{user_id}")
            )

            keyboard.row(
                types.InlineKeyboardButton(" Проигрыши", callback_data=f"history_losses_0_{user_id}"),
                types.InlineKeyboardButton("🔄 Переводы", callback_data=f"history_transfers_0_{user_id}")
            )

            keyboard.add(
                types.InlineKeyboardButton("⬅️ Назад", callback_data=f"user_back_{user_id}")
            )

            await callback.message.edit_text(
                f"📋 <b>История операций пользователя</b>\n\n"
                f"👤 Пользователь: <code>{user_id}</code>\n\n"
                f"📊 <b>Выберите тип операций:</b>\n"
                f"• <code>📊 Вся история</code> - все операции\n"
                f"• <code>✅ Выигрыши</code> - только выигрыши\n"
                f"• <code> Проигрыши</code> - только проигрыши\n"
                f"• <code>🔄 Переводы</code> - переводы Монет\n\n"
                f"<i>Будет показано по 20 операций за раз</i>",
                parse_mode="HTML",
                reply_markup=keyboard
            )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_history_button: {e}")
            await callback.answer(" Ошибка при загрузке истории")

    async def show_user_history(self, callback: types.CallbackQuery):
        """Показывает историю операций пользователя с пагинацией"""
        try:
            # Парсим callback data: history_type_page_userId
            data_parts = callback.data.split('_')

            if len(data_parts) < 4:
                await callback.answer(" Ошибка формата данных", show_alert=True)
                return

            history_type = data_parts[1]  # all, wins, losses, transfers
            page = int(data_parts[2])  # номер страницы
            user_id = int(data_parts[3])  # ID пользователя

            self.logger.info(f"History request: type={history_type}, page={page}, user_id={user_id}")

            # Получаем историю через HistoryMergeHandler
            db = next(get_db())

            try:
                # Получаем полную историю (все игры будут видны)
                complete_history = self.history_merge_handler.get_complete_history(
                    db,
                    user_id,
                    limit=1000  # Получаем больше для пагинации
                )

                self.logger.info(f"Got {len(complete_history)} history entries")

                if not complete_history:
                    history_text = "📊 <b>История операций пользователя</b>\n\n"
                    history_text += f"👤 Пользователь: <code>{user_id}</code>\n\n"
                    history_text += "📭 <i>Операций не найдено</i>"

                    # Создаем клавиатуру только с кнопкой назад
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(
                        types.InlineKeyboardButton(
                            "⬅️ Назад",
                            callback_data=f"user_back_{user_id}"
                        )
                    )
                else:
                    # СОРТИРУЕМ ПО ДАТЕ: НОВЫЕ СВЕРХУ (РЕВЕРС)
                    # Предполагаем, что записи имеют поле 'date' или 'datetime'
                    # Если нет, пытаемся извлечь из текста
                    sorted_history = sorted(
                        complete_history,
                        key=lambda x: self._extract_datetime_for_sorting(x),
                        reverse=True  # Новые сверху
                    )

                    # Фильтруем по типу если нужно
                    filtered_history = self._filter_history_by_type_fixed(
                        sorted_history,  # Используем отсортированный список
                        history_type
                    )

                    # Пагинация: 20 операций на страницу
                    operations_per_page = 20
                    total_pages = (len(filtered_history) + operations_per_page - 1) // operations_per_page

                    # Корректируем номер страницы
                    if page < 0:
                        page = 0
                    elif page >= total_pages:
                        page = total_pages - 1

                    # Выбираем записи для страницы
                    start_idx = page * operations_per_page
                    end_idx = start_idx + operations_per_page
                    page_entries = filtered_history[start_idx:end_idx]

                    # Форматируем историю
                    history_text = self._format_history_with_pagination(
                        page_entries,
                        user_id,
                        history_type,
                        page,
                        total_pages,
                        len(filtered_history)
                    )

                    # Создаем клавиатуру с пагинацией
                    keyboard = self._create_history_pagination_keyboard(
                        history_type, page, total_pages, user_id
                    )

                # Проверяем длину текста
                if len(history_text) > 4000:
                    history_text = history_text[:3900] + "...\n\n⚠️ <i>Текст обрезан</i>"

                # Редактируем сообщение вместо отправки нового
                await callback.message.edit_text(
                    history_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

            except Exception as history_error:
                self.logger.error(f"Error getting history: {history_error}", exc_info=True)

                # Создаем клавиатуру с кнопкой назад
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data=f"user_back_{user_id}"
                    )
                )

                await callback.message.edit_text(
                    " <b>Ошибка загрузки истории</b>\n\n"
                    "Не удалось получить историю операций. Попробуйте позже.",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

            finally:
                db.close()

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in show_user_history: {e}", exc_info=True)
            await callback.answer(" Ошибка при загрузке истории")

    # В классе UserInfoHandler добавьте метод:

    def _extract_datetime_for_sorting(self, entry):
        """Извлекает дату-время из записи для сортировки"""
        try:
            # Пытаемся получить дату из записи
            if hasattr(entry, 'date'):
                return entry.date
            elif hasattr(entry, 'datetime'):
                return entry.datetime
            elif isinstance(entry, dict):
                if 'timestamp' in entry:
                    return entry['timestamp']
                elif 'date' in entry:
                    return entry['date']
                elif 'datetime' in entry:
                    return entry['datetime']

                # Пытаемся извлечь из текста
                text = entry.get('text', '')
                # Ищем паттерн времени с датой в формате [DD.MM HH:MM]
                import re
                date_time_match = re.search(r'\[(\d{1,2}\.\d{1,2} \d{1,2}:\d{2})\]', text)
                if date_time_match:
                    date_time_str = date_time_match.group(1)
                    try:
                        # Парсим дату и время
                        dt = datetime.strptime(date_time_str, "%d.%m %H:%M")
                        # Добавляем текущий год
                        dt = dt.replace(year=datetime.now().year)
                        return dt
                    except:
                        pass

                # Ищем паттерн только времени в формате [HH:MM:SS]
                time_match = re.search(r'\[(\d{1,2}:\d{2}:\d{2})\]', text)
                if time_match:
                    time_str = time_match.group(1)
                    try:
                        # Создаем дату сегодняшнюю с временем из записи
                        today = datetime.now().date()
                        time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
                        return datetime.combine(today, time_obj)
                    except:
                        pass

            # Если ничего не нашли, возвращаем минимальную дату
            return datetime.min
        except Exception as e:
            print(f" Ошибка извлечения даты: {e}")
            return datetime.min

    def _format_history_with_pagination(self, history_entries, user_id: int,
                                        history_type: str, page: int,
                                        total_pages: int, total_operations: int):
        """Форматирует историю с информацией о пагинации"""
        # Заголовок
        type_names = {
            "all": "Все операции",
            "wins": "Выигрыши",
            "losses": "Проигрыши",
            "transfers": "Переводы"
        }

        title = f"📊 <b>История операций</b>\n"
        title += f"👤 ID: <code>{user_id}</code>\n"
        title += f"📋 Тип: {type_names.get(history_type, 'Все операции')}\n"
        title += f"📄 Страница: {page + 1}/{total_pages}\n"
        title += f"📈 Всего операций: {total_operations}\n"

        if not history_entries:
            return title + "\n📭 <i>Операций не найдено</i>"

        # Форматируем записи
        history_lines = []
        # Нумерация с 1 для читаемости
        entry_number = page * 20 + 1  # Номер первой записи на странице

        for entry in history_entries:
            text = entry.get('text', '')

            # Упрощаем текст для читаемости
            if len(text) > 80:
                text = text[:77] + "..."

            history_lines.append(f"{entry_number}. {text}")
            entry_number += 1

        history_text = title + "\n" + "\n".join(history_lines)

        return history_text

    def _create_history_pagination_keyboard(self, history_type: str, page: int,
                                            total_pages: int, user_id: int):
        """Создает клавиатуру с пагинацией для истории"""
        keyboard = types.InlineKeyboardMarkup(row_width=3)

        # Кнопки пагинации
        buttons = []

        # Кнопка "Далее" если не первая страница (для перехода к более старым)
        if page > 0:
            buttons.append(
                types.InlineKeyboardButton(
                    "◀️ Новее",
                    callback_data=f"history_{history_type}_{page - 1}_{user_id}"
                )
            )

        # Кнопка возврата в меню истории
        buttons.append(
            types.InlineKeyboardButton(
                "📋 Меню",
                callback_data=f"user_history_{user_id}"
            )
        )

        # Кнопка "Назад" если не последняя страница (для перехода к более старым)
        if page < total_pages - 1:
            buttons.append(
                types.InlineKeyboardButton(
                    "Старее ▶️",
                    callback_data=f"history_{history_type}_{page + 1}_{user_id}"
                )
            )

        keyboard.row(*buttons)

        # Кнопка возврата к пользователю
        keyboard.add(
            types.InlineKeyboardButton(
                "⬅️ Назад к пользователю",
                callback_data=f"user_back_{user_id}"
            )
        )

        return keyboard

    def _filter_history_by_type_fixed(self, history_entries, history_type: str):
        """Фильтрует историю по типу операций"""
        if history_type == "all":
            return history_entries

        filtered = []
        for entry in history_entries:
            text = entry.get('text', '')

            if history_type == "wins":
                # Выигрыши: содержат + или слово выигрыш
                if '+' in text or 'Выигрыш' in text or 'Попадание' in text or 'Выпал' in text:
                    filtered.append(entry)

            elif history_type == "losses":
                # Проигрыши: содержат - или слово проигрыш/ставка
                if '-' in text and ('Проигрыш' in text or 'Ставка' in text):
                    filtered.append(entry)


            elif history_type == "transfers":
                if '💸 Перевод:' in text or '💰 Получено:' in text:
                    filtered.append(entry)

        return filtered

    async def handle_back_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Назад - редактирует сообщение вместо отправки нового"""
        try:
            user_id = int(callback.data.split('_')[-1])

            # Возвращаемся к информации о пользователе
            await self._display_user_info_edit(callback.message, user_id, callback.from_user)

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_back_button: {e}")
            await callback.answer(" Ошибка при возврате")

    async def _display_user_info_edit(self, message: types.Message, user_id: int, from_user: types.User):
        """Отображает информацию о пользователе путем редактирования сообщения"""
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await message.edit_text(f" Пользователь с ID {user_id} не найден")
                db.close()
                return

            # Получаем максимальный проигрыш
            max_loss = self._get_user_max_loss(db, user_id)

            # Получаем информацию о донат-статусе, супруге и лицензиях
            donate_status = self._get_donate_status_info(db, user_id)
            spouse_info = await self._get_spouse_info(user_id, message.chat.id, message.bot)
            license_info = self._get_license_info(db, user_id)

            # Формируем информацию
            info_text = (
                f"👤 <b>Информация о пользователе</b>\n\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                f"📛 <b>Никнейм:</b> {self._get_user_display_name(user)}\n"
                f"💎 <b>Status:</b> {donate_status}\n"
                f"👫 <b>Жена/Муж:</b> {spouse_info}\n"
                f"📋 <b>Лицензий:</b> {license_info['standard']}\n"
                f"⭐ <b>VIP-лицензий:</b> {license_info['vip']}\n\n"
                f"💰 <b>Баланс:</b> {format_number(user.coins)} Монет\n"
                f"✅ <b>Выиграно всего:</b> {format_number(user.win_coins or 0)} Монет\n"
                f" <b>Проиграно всего:</b> {format_number(user.defeat_coins or 0)} Монет\n"
                f"🎯 <b>Максимальная ставка:</b> {format_number(user.max_bet or 0)}\n"
                f"📉 <b>Максимальный проигрыш:</b> {format_number(max_loss)}\n"
                f"📈 <b>Максимальный выигрыш:</b> {format_number(user.max_win_coins or 0)}\n"
            )

            # Добавляем информацию о бане в боте
            try:
                from handlers.admin.mute_ban import mute_ban_manager
                is_banned = mute_ban_manager.bot_ban_manager.is_user_bot_banned(user_id)
                if is_banned:
                    info_text += f"\n🚫 <b>Статус:</b> Забанен в боте"
            except Exception as e:
                self.logger.warning(f"Could not check bot ban status: {e}")

            # Добавляем информацию о регистрации
            if hasattr(user, 'created_at') and user.created_at:
                info_text += f"\n📅 <b>Зарегистрирован:</b> {user.created_at.strftime('%d.%m.%Y %H:%M')}"

            # Создаем клавиатуру с кнопками
            keyboard = self._create_user_info_keyboard(user_id)

            await message.edit_text(info_text, parse_mode="HTML", reply_markup=keyboard)
            db.close()

        except Exception as e:
            self.logger.error(f"Error in _display_user_info_edit: {e}")
            try:
                await message.edit_text(" Ошибка при формировании информации")
            except:
                pass
            try:
                db.close()
            except:
                pass

    async def handle_ban_reason(self, message: types.Message, state: FSMContext):
        """Обработка причины бана - использует mute_ban_manager"""
        try:
            # Проверяем команду отмены
            if message.text and message.text.lower() == '/cancel':
                await state.finish()
                await message.answer(" Бан отменен")
                return

            reason = message.text
            data = await state.get_data()
            user_id = data.get('ban_user_id')

            if not user_id:
                await message.answer(" Ошибка: не найден ID пользователя")
                await state.finish()
                return

            if not reason or len(reason.strip()) < 3:
                await message.answer(" Причина должна содержать минимум 3 символа")
                return

            reason = reason.strip()

            # Баним пользователя через mute_ban_manager
            from handlers.admin.mute_ban import mute_ban_manager
            admin_id = message.from_user.id

            success = await mute_ban_manager.ban_in_bot(
                user_id=user_id,
                admin_id=admin_id,
                reason=reason,
                seconds=None  # навсегда
            )

            if success:
                # Отправляем уведомление пользователю
                try:
                    await message.bot.send_message(
                        chat_id=user_id,
                        text=f"🚫 Вы забанены в боте.\nПричина: {reason}"
                    )
                except:
                    pass  # Игнорируем ошибки отправки

                await message.answer(
                    f"✅ <b>Пользователь забанен в боте!</b>\n\n"
                    f"👤 ID: <code>{user_id}</code>\n"
                    f"📝 Причина: {reason}\n"
                    f"👮‍♂️ Администратор: {message.from_user.first_name}\n\n"
                    f"<i>Пользователь получил уведомление о бане</i>",
                    parse_mode="HTML"
                )

                # Логируем действие
                self.logger.info(f"Admin {admin_id} banned user {user_id} in bot. Reason: {reason}")
            else:
                await message.answer(
                    " <b>Ошибка при бане в боте!</b>\n\n"
                    "Не удалось забанить пользователя. Возможно, он является администратором бота.",
                    parse_mode="HTML"
                )

            await state.finish()

        except Exception as e:
            self.logger.error(f"Error in handle_ban_reason: {e}")
            await message.answer(" Ошибка при обработке причины бана")
            await state.finish()



    async def handle_givelicense_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Выдать лицензию"""
        try:
            user_id = int(callback.data.split('_')[-1])

            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton("📜 Обычная лицензия (5M)", callback_data=f"givelic_2_{user_id}"),
                types.InlineKeyboardButton("🧧 VIP Лицензия (10M)", callback_data=f"givelic_1_{user_id}"),
                types.InlineKeyboardButton("⬅️ Назад", callback_data=f"user_back_{user_id}")
            )

            await callback.message.edit_text(
                f"📜 <b>Выдача лицензии</b>\n\n"
                f"👤 Пользователь: <code>{user_id}</code>\n"
                f"Выберите тип лицензии для выдачи:",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer()
        except Exception as e:
            self.logger.error(f"Error in handle_givelicense_button: {e}")
            await callback.answer(" Ошибка")

    async def handle_givelicense_confirm(self, callback: types.CallbackQuery):
        """Обработчик выбора лицензии для выдачи"""
        try:
            # data: givelic_TYPE_USERID
            parts = callback.data.split('_')
            license_type = int(parts[1])
            user_id = int(parts[2])

            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                await callback.answer(" Пользователь не найден", show_alert=True)
                db.close()
                return

            # Определяем параметры лицензии
            if license_type == 1:
                item_name = "VIP-ЛИЦЕНЗИЯ"
                price = 10000000
                benefit = "VIP-лицензия предоставляет особые привилегии"
            else:
                item_name = "обычная лицензия"
                price = 5000000
                benefit = "Базовая лицензия для доступа к функциям"

            try:
                # Добавляем покупку (без списания средств, т.к. выдает админ)
                ShopRepository.add_user_purchase(
                    db,
                    user_id,
                    license_type,
                    item_name,
                    price, # Записываем номинальную стоимость
                    0 # chat_id=0 (глобально)
                )
                db.commit()

                # Уведомляем пользователя
                try:
                    await callback.bot.send_message(
                        user_id,
                        f"🎁 <b>Вам выдана лицензия!</b>\n\n"
                        f"📦 Тип: {item_name}\n"
                        f"💎 Преимущество: {benefit}\n"
                        f"👮‍♂️ Выдал администратор",
                        parse_mode="HTML"
                    )
                except:
                    pass

                await callback.message.edit_text(
                    f"✅ <b>Лицензия успешно выдана!</b>\n\n"
                    f"👤 Пользователь: {self._get_user_display_name(user)}\n"
                    f"📦 Тип: {item_name}\n"
                    f"👮‍♂️ Администратор: {callback.from_user.first_name}",
                    parse_mode="HTML",
                    reply_markup=self._create_user_info_keyboard(user_id)
                )

                # Логируем
                self.logger.info(f"Admin {callback.from_user.id} gave license {license_type} to user {user_id}")

            except Exception as db_e:
                db.rollback()
                self.logger.error(f"DB Error giving license: {db_e}")
                await callback.answer(" Ошибка базы данных", show_alert=True)
            
            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_givelicense_confirm: {e}")
            await callback.answer(" Ошибка")


def register_user_info_handlers(dp: Dispatcher):
    """Регистрирует обработчики для команды /id"""
    handler = UserInfoHandler()

    # Команда /id для reply сообщений
    dp.register_message_handler(
        handler.show_user_info_reply,
        commands=['id']
    )

    # Команды вида /123456789 (где 123456789 - ID пользователя)
    # Регистрируем через фильтр по regex
    dp.register_message_handler(
        handler.show_user_info,
        regexp=r'^/\d+(\s|$)'
    )

    # Также обрабатываем команды вида /123456789 с текстом после
    dp.register_message_handler(
        handler.show_user_info,
        regexp=r'^/\d+\s+.*$'
    )

    dp.register_message_handler(
        handler.idgroup_command,
        commands=["idgroup"]
    )

    # Callback обработчики для кнопок
    dp.register_callback_query_handler(
        handler.handle_reset_button,
        lambda c: c.data.startswith("user_reset_")
    )

    dp.register_callback_query_handler(
        handler.handle_reset_confirm,
        lambda c: c.data.startswith("reset_")
    )

    dp.register_callback_query_handler(
        handler.execute_reset,
        lambda c: c.data.startswith("confirm_reset_")
    )

    dp.register_callback_query_handler(
        handler.handle_ban_button,
        lambda c: c.data.startswith("user_ban_")
    )

    dp.register_callback_query_handler(
        handler.handle_unban_button,
        lambda c: c.data.startswith("user_unban_")
    )

    dp.register_callback_query_handler(
        handler.handle_unlimit_button,
        lambda c: c.data.startswith("user_unlimit_")
    )

    dp.register_callback_query_handler(
        handler.handle_limit_button,
        lambda c: c.data.startswith("user_limit_")
    )

    dp.register_callback_query_handler(
        handler.handle_history_button,
        lambda c: c.data.startswith("user_history_")
    )

    # Исправленный обработчик истории с поддержкой разных форматов
    dp.register_callback_query_handler(
        handler.show_user_history,
        lambda c: c.data.startswith("history_")
    )

    dp.register_callback_query_handler(
        handler.handle_givelicense_button,
        lambda c: c.data.startswith("user_givelicense_")
    )

    dp.register_callback_query_handler(
        handler.handle_givelicense_confirm,
        lambda c: c.data.startswith("givelic_")
    )

    dp.register_callback_query_handler(
        handler.handle_back_button,
        lambda c: c.data.startswith("user_back_")
    )

    # FSM для ввода причины бана
    dp.register_message_handler(
        handler.handle_ban_reason,
        state=UserInfoStates.waiting_for_ban_reason
    )

    logger.info("✅ Обработчики команды /id и /idgroup зарегистрированы")
    return handler