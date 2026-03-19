import re
import logging
from typing import List, Tuple
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.crud import ChatRepository, UserRepository
from .record_core import RecordCore


class TopHandlers:
    """Обработчики топов и рейтингов"""

    def __init__(self, record_core: RecordCore):
        self.core = record_core
        self.logger = logging.getLogger(__name__)

    async def show_top_menu(self, message: types.Message, limit: int = 10):
        """Показывает меню выбора топа с 3 кнопками (доступно всем)"""
        # УБРАЛИ проверку админских прав
        keyboard = InlineKeyboardMarkup(row_width=2)

        # ВЕРХНИЙ РЯД: 2 кнопки
        buttons_top_row = [
            InlineKeyboardButton("рулетка", callback_data=f"top_roulette_{limit}"),
            InlineKeyboardButton("баскетбол", callback_data=f"top_basketball_{limit}"),
        ]

        # ВТОРОЙ РЯД: 2 кнопки
        buttons_second_row = [
            InlineKeyboardButton("слоты", callback_data=f"top_slots_{limit}"),
            InlineKeyboardButton("богатеи", callback_data=f"top_rich_{limit}"),
        ]

        # Добавляем кнопки в строки
        keyboard.add(*buttons_top_row)  # рулетка и баскетбол в одной строке
        keyboard.add(*buttons_second_row)  # слоты и богатеи во второй строке

        await message.reply(f"Какой топ Вас интересует?", reply_markup=keyboard)

    async def handle_top_callback(self, callback_query: types.CallbackQuery):
        """Обработчик callback'ов для топов (доступно всем)"""
        self.logger.info(f"🔍 Начало обработки callback: {callback_query.data}")

        try:
            # УБРАЛИ проверку админских прав

            chat_id = callback_query.message.chat.id
            user_id = callback_query.from_user.id
            username = callback_query.from_user.username
            first_name = callback_query.from_user.first_name

            await self.core.ensure_user_registered(user_id, chat_id, username, first_name)
            callback_data = callback_query.data

            self.logger.info(f"🔍 Обработка callback_data: {callback_data}")

            # Обработка кнопки "Назад" с форматом {limit}_top_back
            if callback_data.endswith('_top_back'):
                self.logger.info(f"🔍 Обработка кнопки Назад: {callback_data}")
                try:
                    limit_str = callback_data.replace('_top_back', '')
                    limit = int(limit_str)
                    await self._show_back_to_main(callback_query, limit)
                    await callback_query.answer()  # Важно: подтверждаем callback
                    return
                except ValueError as e:
                    self.logger.error(f"Error parsing limit from back button: {e}")
                    # Если не удалось распарсить limit, используем значение по умолчанию
                    limit = self.core.config.DEFAULT_TOP_LIMIT
                    await self._show_back_to_main(callback_query, limit)
                    await callback_query.answer()  # Важно: подтверждаем callback
                    return

            if callback_data.startswith('top_'):
                # Убираем префикс "top_"
                data_without_prefix = callback_data[4:]  # убираем "top_"

                # Ищем последнее подчеркивание, которое отделяет limit
                last_underscore_index = data_without_prefix.rfind('_')

                if last_underscore_index != -1:
                    top_type = data_without_prefix[:last_underscore_index]
                    limit_str = data_without_prefix[last_underscore_index + 1:]

                    self.logger.info(f"🔍 Разобранные части: top_type={top_type}, limit_str={limit_str}")

                    if limit_str.isdigit():
                        limit = int(limit_str)

                        # Ограничиваем максимум 100
                        limit = min(limit, self.core.config.MAX_TOP_LIMIT)
                        self.logger.info(f"🔍 Обработка: top_type={top_type}, limit={limit}")

                        if top_type == "others":
                            # Показываем меню остальных топов
                            self.logger.info("🔍 Показ меню остальных топов")
                            await self._show_others_menu(callback_query, limit)
                        elif top_type == "roulette":
                            # Показываем меню статистики для рулетки (ДЛЯ ТЕКУЩЕГО ЧАТА)
                            self.logger.info("🔍 Показ меню статистики рулетки для чата")
                            await self._show_roulette_stats_menu(callback_query, limit)
                        elif top_type in ["basketball", "slots"]:
                            # Показываем сообщение "в разработке" для баскетбола и слотов
                            self.logger.info(f"🔍 Показ сообщения о разработке {top_type}")
                            await self._show_game_development(callback_query, top_type)
                        elif top_type == "rich":
                            # Показываем топ богатеев (ТОЛЬКО ДЛЯ ТЕКУЩЕГО ЧАТА)
                            self.logger.info("🔍 Показ топа богатеев для текущего чата")
                            await self._show_rich_top_internal(callback_query, chat_id, user_id, limit)
                        elif top_type in ["total_win", "total_loss", "max_win", "max_loss", "max_bet"]:
                            # Показываем статистические топы для рулетки (ТОЛЬКО ДЛЯ ТЕКУЩЕГО ЧАТА)
                            self.logger.info(f"🔍 Показ статистического топа для чата: {top_type}")
                            await self._show_roulette_stat_top(callback_query, chat_id, user_id, top_type, limit)
                        elif top_type in ["maxwin", "maxloss", "maxbet"]:
                            # Для обратной совместимости
                            self.logger.info(f"🔍 Обработка старого формата: {top_type}")
                            db_top_type = {
                                "maxwin": "max_win",
                                "maxloss": "max_loss",
                                "maxbet": "max_bet"
                            }[top_type]
                            await self._show_stats_top_internal(callback_query, chat_id, user_id, db_top_type, limit)
                        else:
                            self.logger.warning(f"⚠️ Неизвестный тип топа: {top_type}")
                            await callback_query.answer(" Неизвестный тип топа", show_alert=True)
                        return

            self.logger.warning(f"⚠️ Необработанный callback: {callback_data}")
            await callback_query.answer(" Ошибка обработки запроса", show_alert=True)

        except Exception as e:
            self.logger.error(f" Error in handle_top_callback: {e}", exc_info=True)
            await callback_query.answer(" Ошибка при получении топа", show_alert=True)

    async def _show_back_to_main(self, callback_query: types.CallbackQuery, limit: int):
        """Возврат в главное меню топов"""
        try:
            keyboard = InlineKeyboardMarkup(row_width=2)

            # ВЕРХНИЙ РЯД: 2 кнопки
            buttons_top_row = [
                InlineKeyboardButton("рулетка", callback_data=f"top_roulette_{limit}"),
                InlineKeyboardButton("баскетбол", callback_data=f"top_basketball_{limit}"),
            ]

            # ВТОРОЙ РЯД: 2 кнопки
            buttons_second_row = [
                InlineKeyboardButton("слоты", callback_data=f"top_slots_{limit}"),
                InlineKeyboardButton("богатеи", callback_data=f"top_rich_{limit}"),
            ]

            # Добавляем кнопки в строки
            keyboard.add(*buttons_top_row)  # рулетка и баскетбол в одной строке
            keyboard.add(*buttons_second_row)  # слоты и богатеи во второй строке

            await callback_query.message.edit_text(
                f"Какой топ Вас интересует?",
                reply_markup=keyboard
            )
            await callback_query.answer()

        except Exception as e:
            self.logger.error(f"Error in _show_back_to_main: {e}")
            await callback_query.answer(" Ошибка при возврате", show_alert=True)

    async def _show_roulette_stats_menu(self, callback_query: types.CallbackQuery, limit: int):
        """Показывает меню статистических топов для рулетки (только для текущего чата)"""
        try:
            keyboard = InlineKeyboardMarkup(row_width=1)

            # Кнопки для статистических топов рулетки (только для текущего чата)
            buttons = [
                InlineKeyboardButton("Выиграно", callback_data=f"top_total_win_{limit}"),
                InlineKeyboardButton("Проиграно", callback_data=f"top_total_loss_{limit}"),
                InlineKeyboardButton("Макс. выигрыш", callback_data=f"top_max_win_{limit}"),
                InlineKeyboardButton("Макс. проигрыш", callback_data=f"top_max_loss_{limit}"),
                InlineKeyboardButton("Макс. ставка", callback_data=f"top_max_bet_{limit}"),
                InlineKeyboardButton("◀️ Назад", callback_data=f"{limit}_top_back"),
            ]

            for button in buttons:
                keyboard.add(button)

            await callback_query.message.edit_text(
                f"Какой топ Вас интересует?",
                reply_markup=keyboard
            )
            await callback_query.answer()

        except Exception as e:
            self.logger.error(f"Error in _show_roulette_stats_menu: {e}")
            await callback_query.answer(" Ошибка при показе меню", show_alert=True)

    async def _show_roulette_stat_top(self, callback_query: types.CallbackQuery, chat_id: int,
                                      user_id: int, stat_type: str, limit: int):
        """Показывает топ по конкретной статистике рулетки ТОЛЬКО ДЛЯ ТЕКУЩЕГО ЧАТА"""
        try:
            # Определяем заголовки в зависимости от типа статистики
            headers = {
                "total_win": f"[Топ в рулетке по сумме выигрышей]\nТолько для этого чата\n\n",
                "total_loss": f"[Топ в рулетке по сумме проигрышей]\nТолько для этого чата\n\n",
                "max_win": f"[Топ в рулетке по максимальному выигрышу]\nТолько для этого чата\n\n",
                "max_loss": f"[Топ в рулетке по максимальному проигрышу]\nТолько для этого чата\n\n",
                "max_bet": f"[Топ в рулетке по максимальной ставке]\nТолько для этого чата\n\n",
            }

            # Определяем поля из таблицы TelegramUser для каждого типа статистики
            stat_fields = {
                "total_win": "roulette_total_wins",  # Выиграно в рулетке
                "total_loss": "roulette_total_losses",  # Проиграно в рулетке
                "max_win": "roulette_max_win",  # Макс. выигрыш в рулетке
                "max_loss": "roulette_max_loss",  # Макс. проигрыш в рулетке
                "max_bet": "roulette_max_bet",  # Макс. ставка в рулетке
            }

            header = headers.get(stat_type, f"[Топ {limit}]\n\n")
            stat_field_name = stat_fields.get(stat_type)

            if not stat_field_name:
                await callback_query.answer(" Неизвестный тип статистики", show_alert=True)
                return

            with self.core.db_session() as db:
                # Получаем топ пользователей по указанной статистике ТОЛЬКО для пользователей в этом чате
                from database.models import TelegramUser, UserChat
                from sqlalchemy import desc, func

                # Определяем поле для сортировки
                stat_field = getattr(TelegramUser, stat_field_name)

                # Получаем пользователей, которые состоят в этом чате
                top_users = db.query(
                    TelegramUser.telegram_id,
                    TelegramUser.username,
                    TelegramUser.first_name,
                    stat_field
                ).join(
                    UserChat, TelegramUser.telegram_id == UserChat.user_id
                ).filter(
                    UserChat.chat_id == chat_id,
                    stat_field > 0
                ).order_by(
                    desc(stat_field)
                ).limit(limit).all()

                if not top_users:
                    await callback_query.message.edit_text(
                        f"📊 Пока нет данных для этого топа в этом чате.",
                        reply_markup=None
                    )
                    await callback_query.answer()
                    return

                # Формируем текст ответа
                reply_text = header

                for i, (telegram_id, username, first_name, value) in enumerate(top_users, start=1):
                    display_name = first_name if first_name else username or "Аноним"
                    if telegram_id == user_id:
                        reply_text += f"{i}. {display_name} [{value:,}] (Вы!)\n"
                    else:
                        reply_text += f"{i}. {display_name} [{value:,}]\n"

                # Получаем позицию текущего пользователя в этом чате
                user_stats_value = db.query(
                    stat_field
                ).filter(
                    TelegramUser.telegram_id == user_id
                ).scalar() or 0

                # Считаем количество пользователей с более высокими значениями в этом чате
                user_position_query = db.query(func.count()).filter(
                    TelegramUser.telegram_id == UserChat.user_id,
                    UserChat.chat_id == chat_id,
                    stat_field > user_stats_value
                ).scalar()

                user_position = user_position_query + 1 if user_position_query is not None else None

                if user_position and user_position > limit and user_stats_value > 0:
                    current_user_name = callback_query.from_user.first_name or callback_query.from_user.username or "Аноним"
                    reply_text += f"\n{user_position}. {current_user_name} [{user_stats_value:,}]"
                elif user_position and user_position <= limit:
                    reply_text += f"\nВаша позиция в этом чате: #{user_position}"

                # Добавляем кнопку "Назад"
                keyboard = InlineKeyboardMarkup()
                keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data=f"top_roulette_{limit}"))

                await callback_query.message.edit_text(
                    reply_text,
                    parse_mode=None,
                    reply_markup=keyboard
                )
                await callback_query.answer()

        except Exception as e:
            self.logger.error(f"Error in _show_roulette_stat_top: {e}")
            await callback_query.answer(" Ошибка при получении топа по рулетке", show_alert=True)

    async def _show_others_menu(self, callback_query: types.CallbackQuery, limit: int):
        """Показывает меню остальных топов"""
        try:
            keyboard = InlineKeyboardMarkup(row_width=1)

            # Кнопка для богатеев (только текущий чат)
            buttons = [
                InlineKeyboardButton("Богатеев", callback_data=f"top_rich_{limit}"),
                InlineKeyboardButton("◀️ Назад", callback_data=f"{limit}_top_back"),
            ]

            for button in buttons:
                keyboard.add(button)

            await callback_query.message.edit_text(
                f"Какой топ Вас интересует?",
                reply_markup=keyboard
            )
            await callback_query.answer()

        except Exception as e:
            self.logger.error(f"Error in _show_others_menu: {e}")
            await callback_query.answer(" Ошибка при показе меню", show_alert=True)

    async def _show_game_development(self, callback_query: types.CallbackQuery, game_type: str):
        """Показывает сообщение о разработке для других игр"""
        try:
            # Получаем limit из callback_data
            parts = callback_query.data.split('_')
            limit = int(parts[2]) if len(parts) >= 3 else 10

            game_names = {
                "basketball": "баскетболе",
                "slots": "слотах"
            }

            game_name = game_names.get(game_type, game_type)

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data=f"{limit}_top_back"))

            await callback_query.message.edit_text(
                f"🛠️ Топ по {game_name} находится в разработке",
                reply_markup=keyboard
            )
            await callback_query.answer()
        except Exception as e:
            self.logger.error(f"Error in _show_game_development: {e}")
            await callback_query.answer(" Ошибка", show_alert=True)

    async def _show_rich_top_internal(self, callback_query: types.CallbackQuery, chat_id: int,
                                      user_id: int, limit: int):
        """Показывает топ богатеев ТОЛЬКО ДЛЯ ТЕКУЩЕГО ЧАТА"""
        try:
            with self.core.db_session() as db:
                # Используем существующий метод из ChatRepository
                top_users = ChatRepository.get_top_rich_in_chat(db, chat_id, limit)

                if not top_users:
                    await callback_query.message.edit_text(
                        f"💰 Пока нет богатеев в этом чате.",
                        reply_markup=None
                    )
                    await callback_query.answer()
                    return

                # Получаем позицию пользователя и его баланс
                user_position = ChatRepository.get_user_rank_in_chat(db, chat_id, user_id)
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                user_coins = user.coins if user else 0

                reply_text = f"[Топ богатеев]\nТолько для этого чата\n\n"

                for i, (telegram_id, username, first_name, coins) in enumerate(top_users, start=1):
                    display_name = first_name if first_name else username or "Аноним"
                    if telegram_id == user_id:
                        reply_text += f"{i}. {display_name} [{coins:,}] (Вы!)\n"
                    else:
                        reply_text += f"{i}. {display_name} [{coins:,}]\n"

                # Добавляем позицию пользователя если он не в топе
                if user_position and user_position > limit and user_coins > 0:
                    current_user_name = callback_query.from_user.first_name or callback_query.from_user.username or "Аноним"
                    reply_text += f"\n{user_position}. {current_user_name} [{user_coins:,}]"
                elif user_position:
                    reply_text += f"\nВаша позиция в этом чате: #{user_position}"

                # Добавляем кнопку "Назад"
                keyboard = InlineKeyboardMarkup()
                keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data=f"{limit}_top_back"))

                await callback_query.message.edit_text(
                    reply_text,
                    parse_mode=None,
                    reply_markup=keyboard
                )
                await callback_query.answer()

        except Exception as e:
            self.logger.error(f"Error in _show_rich_top_internal: {e}")
            await callback_query.answer(" Ошибка при получении топа богатеев", show_alert=True)

    async def _show_stats_top_internal(self, callback_query: types.CallbackQuery, chat_id: int,
                                       user_id: int, top_type: str, limit: int):
        """Показывает статистические топы ДЛЯ ТЕКУЩЕГО ЧАТА (старая версия для обратной совместимости)"""
        try:
            headers = {
                "max_win": f"🏆 <b>Топ по максимальному выигрышу</b>\nТолько для этого чата\n",
                "max_loss": f"📉 <b>Топ по максимальному проигрышу</b>\nТолько для этого чата\n",
                "max_bet": f"🎲 <b>Топ по максимальной ставке</b>\nТолько для этого чата\n",
            }

            # Сопоставление старых типов с новыми полями
            stat_field_mapping = {
                "max_win": "roulette_max_win",
                "max_loss": "roulette_max_loss",
                "max_bet": "roulette_max_bet"
            }

            header = headers.get(top_type, f"<b>Топ {limit}</b>\n")
            stat_field_name = stat_field_mapping.get(top_type)

            if not stat_field_name:
                await callback_query.answer(" Неизвестный тип топа", show_alert=True)
                return

            with self.core.db_session() as db:
                # Получаем топ для текущего чата с использованием новых полей
                from database.models import TelegramUser, UserChat
                from sqlalchemy import desc, func

                stat_field = getattr(TelegramUser, stat_field_name)

                # Получаем пользователей из этого чата
                top_users = db.query(
                    TelegramUser.telegram_id,
                    TelegramUser.username,
                    TelegramUser.first_name,
                    stat_field
                ).join(
                    UserChat, TelegramUser.telegram_id == UserChat.user_id
                ).filter(
                    UserChat.chat_id == chat_id,
                    stat_field > 0
                ).order_by(
                    desc(stat_field)
                ).limit(limit).all()

                if not top_users:
                    await callback_query.message.edit_text(
                        f"🏆 Пока нет данных для этого топа в этом чате.",
                        reply_markup=None
                    )
                    await callback_query.answer()
                    return

                reply_text = header
                reply_text += "━━━━━━━━━━━━━━━\n\n"

                for i, (telegram_id, username, first_name, value) in enumerate(top_users, start=1):
                    display_name = first_name if first_name else username or "Аноним"
                    if telegram_id == user_id:
                        reply_text += f"🏅 <b>{i}. {display_name} — {value:,}</b>\n"
                    else:
                        reply_text += f"{i}. {display_name} — {value:,}\n"

                # Получаем значение текущего пользователя
                user_stats_value = db.query(
                    stat_field
                ).filter(
                    TelegramUser.telegram_id == user_id
                ).scalar() or 0

                # Получаем позицию пользователя в этом чате
                user_position_query = db.query(func.count()).filter(
                    TelegramUser.telegram_id == UserChat.user_id,
                    UserChat.chat_id == chat_id,
                    stat_field > user_stats_value
                ).scalar()

                user_position = user_position_query + 1 if user_position_query is not None else None

                if user_stats_value > 0:
                    current_user_name = callback_query.from_user.first_name or callback_query.from_user.username or "Аноним"

                    # Добавляем разделитель и позицию пользователя
                    reply_text += "\n━━━━━━━━━━━━━━━\n"
                    if user_position and user_position > limit:
                        reply_text += f"<b>{user_position}. {current_user_name} — {user_stats_value:,}</b>"
                    else:
                        reply_text += f"<b>Ваша позиция в этом чате: #{user_position or '?'}</b>"

                # Добавляем кнопку "Назад"
                keyboard = InlineKeyboardMarkup()
                keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data=f"top_roulette_{limit}"))

                await callback_query.message.edit_text(
                    reply_text,
                    parse_mode=types.ParseMode.HTML,
                    reply_markup=keyboard
                )
                await callback_query.answer()

        except Exception as e:
            self.logger.error(f"Error in _show_stats_top_internal: {e}")
            await callback_query.answer(" Ошибка при получении топа статистики", show_alert=True)

    async def show_rich_top(self, message: types.Message):
        """Обработчик команды 'топ' - показывает меню с кнопками (доступно всем)"""
        try:
            command_text = message.text.lower().strip()

            # Ищем число после "топ" или "top"
            limit_match = re.search(r'(?:топ|top)\s*(\d+)', command_text)

            if limit_match:
                limit = int(limit_match.group(1))
                # Ограничиваем максимум 100
                limit = min(limit, self.core.config.MAX_TOP_LIMIT)
            else:
                # Если число не указано, используем значение по умолчанию
                limit = self.core.config.DEFAULT_TOP_LIMIT

            await self.show_top_menu(message, limit)

        except Exception as e:
            self.logger.error(f"Error in show_rich_top: {e}")
            await message.reply(" Ошибка при получении топа.")