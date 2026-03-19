# bot_search_handler.py
import logging
import asyncio
from typing import List, Tuple, Optional, Dict
from datetime import datetime, timedelta
from aiogram import types, Dispatcher
from aiogram.utils.exceptions import MessageToDeleteNotFound, MessageCantBeDeleted
from aiogram.dispatcher.filters import Command
from database import get_db
from database.models import UserChatSearch, UserNickSearch, UserPurchase
from database.crud import BotSearchRepository, ShopRepository, UserRepository
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

# Список команд для сбора данных
COMMANDS_TO_LOG = [
    'start', 'help', 'menu', 'profile', 'settings', 'б', 'Б',
    'профиль', 'рулетка', 'донат', 'подарки', 'магазин', 'ссылки',
    'баланс', 'топ', 'перевод', 'кража', 'полиция', 'вор', 'кубик'
]

# ID товаров защиты от поиска
PROTECTION_ITEM_IDS = [4]  # ID товаров из магазина


class BotSearchHandler:
    def __init__(self):
        self.logger = logger
        self.MAX_CHATS = 50
        self.MAX_NICKS = 20
        self.MAX_MESSAGE_LENGTH = 4000
        self.cooldown_dict = {}
        self.cache = {}
        self.CACHE_TTL = 300
        self.stats = {
            'total_searches': 0,
            'data_logged': 0,
            'cache_hits': 0,
            'errors': 0,
            'protected_users': 0,
            'protection_notifications': 0
        }
        self.search_history = {}

    def has_search_protection(self, user_id: int, chat_id: int) -> bool:
        """Проверяет, есть ли у пользователя защита от 'бот ищи' - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        db = next(get_db())
        try:
            print(f"🔍 ДЕТАЛЬНАЯ ПРОВЕРКА ЗАЩИТЫ ОТ ПОИСКА:")
            print(f"   👤 Пользователь: {user_id}")
            print(f"   💬 Чат: {chat_id}")

            # Способ 1: Проверка через has_active_purchase (глобальная)
            for item_id in PROTECTION_ITEM_IDS:
                if ShopRepository.has_active_purchase(db, user_id, item_id):
                    print(f"   ✅ Способ 1: Глобальная защита (товар {item_id})")
                    return True

            # Способ 2: Проверка через get_active_purchases
            active_purchases = ShopRepository.get_active_purchases(db, user_id)
            print(f"   🛍️ Все активные покупки: {active_purchases}")

            for item_id in PROTECTION_ITEM_IDS:
                if item_id in active_purchases:
                    print(f"   ✅ Способ 2: Защита через активные покупки (товар {item_id})")
                    return True

            # Способ 3: Прямая проверка в базе данных
            current_time = datetime.now()
            protection_purchases = db.query(UserPurchase).filter(
                UserPurchase.user_id == user_id,
                UserPurchase.item_id.in_(PROTECTION_ITEM_IDS),
            ).all()

            print(f"   📊 Найдено покупок защиты в чате: {len(protection_purchases)}")

            for purchase in protection_purchases:
                print(f"   🛒 Покупка: item_id={purchase.item_id}, expires_at={purchase.expires_at}")
                if purchase.expires_at is None or purchase.expires_at > current_time:
                    print(f"   ✅ Способ 3: Активная защита в чате (товар {purchase.item_id})")
                    return True

            print(f"    Все способы проверки: ЗАЩИТЫ НЕТ")
            return False

        except Exception as e:
            print(f" Ошибка детальной проверки защиты: {e}")
            return False
        finally:
            db.close()

    async def log_user_command(self, message: types.Message):
        """Логирует только команды пользователя для сбора данных"""
        try:
            # Пропускаем если это не команда из списка
            if not self._is_command_to_log(message):
                return

            user_id = message.from_user.id
            nick = message.from_user.full_name.strip()
            chat_id = message.chat.id
            chat_title = getattr(message.chat, "title", "Личные сообщения")

            # Проверяем защиту от поиска
            if self.has_search_protection(user_id, chat_id):
                logger.info(f"🛡️ Skipping data logging for protected user {user_id} in chat {chat_id}")
                self.stats['protected_users'] += 1

                # Отправляем уведомление о срабатывании защиты (только в группах)
                if message.chat.type != "private":
                    try:
                        protection_notification = await message.reply(
                            f"🛡️ <b>Защита активирована!</b>\n\n"
                            f"👤 <b>{self._escape_html(message.from_user.full_name)}</b>, "
                            f"ваши данные защищены от сбора командой 'бот ищи'.\n\n"
                            f"💡 <i>Эта защита предотвращает сбор информации о ваших чатах и никах</i>",
                            parse_mode="HTML"
                        )
                        self.stats['protection_notifications'] += 1

                        # Удаляем уведомление через 5 секунд
                        asyncio.create_task(self._safe_delete_message(protection_notification, 5))
                    except Exception as e:
                        logger.error(f"Error sending protection notification: {e}")

                return

            # Валидация данных
            if not nick or len(nick) > 255:
                nick = "Неизвестно"

            if not chat_title or len(chat_title) > 255:
                chat_title = "Без названия"

            db = next(get_db())
            try:
                # Безопасное добавление чата пользователя
                chat_added = self._safe_add_user_chat(db, user_id, chat_id, chat_title)

                # Безопасное добавление ника пользователя
                nick_added = self._safe_add_user_nick(db, user_id, nick)

                if chat_added or nick_added:
                    db.commit()
                    self.stats['data_logged'] += 1
                    self.logger.debug(f"✅ Logged command data for user {user_id} in chat {chat_id}: {message.text}")

            except Exception as e:
                db.rollback()
                if "unique constraint" not in str(e).lower() and "duplicate" not in str(e).lower():
                    self.logger.error(f" Database error in log_user_command: {e}")
                    self.stats['errors'] += 1
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f" Error in log_user_command: {e}")
            self.stats['errors'] += 1

    async def bot_search(self, message: types.Message):
        """Команда 'бот ищи' - показывает информацию о пользователе"""
        try:
            self.stats['total_searches'] += 1
            self.logger.info(f"🔍 Получена команда поиска от {message.from_user.id}: {message.text}")

            # Проверка кулдауна
            if not self._check_cooldown(message.from_user.id, "search"):
                await message.reply("⏳ Подождите 3 секунды перед следующим запросом.")
                return

            # Парсим команду для извлечения ID пользователя или username
            target_user = await self._parse_search_target(message)
            if not target_user:
                await self._show_search_help(message)
                return

            user_id = target_user.id
            self.logger.info(f"🎯 Цель поиска: {target_user.full_name} (ID: {user_id})")

            # Проверки безопасности
            validation_error = await self._validate_search_request(message, target_user)
            if validation_error:
                await message.reply(validation_error)
                return

            # ВАЖНОЕ ИСПРАВЛЕНИЕ: Проверяем защиту от поиска ДО поиска в базе
            if self.has_search_protection(user_id, message.chat.id):
                self.stats['protected_users'] += 1
                self.logger.info(f"🛡️ Защита сработала для пользователя {user_id} в чате {message.chat.id}")

                # Получаем информацию о защите для красивого сообщения
                protection_info = await self._get_protection_info(user_id, message.chat.id)

                protection_msg = await message.reply("🛡️ <i>Проверяем защиту пользователя...</i>", parse_mode="HTML")

                await protection_msg.edit_text(
                    f"🛡️ <b>Пользователь защищен от поиска!</b>\n\n"
                    f"👤 <b>{self._escape_html(target_user.full_name)}</b> {protection_info}\n\n"
                    f"💡 <i>Информация о пользователе скрыта для вашей безопасности</i>",
                    parse_mode="HTML"
                )

                self._log_search_activity(message.from_user.id, user_id)
                # Удаляем исходное сообщение с командой через 5 секунд
                asyncio.create_task(self._safe_delete_message(message, 5))
                return

            # Проверяем кэш
            cached_result = self._get_cached_result(user_id)
            if cached_result:
                search_msg = await message.reply("⚡ Используем кэшированные данные...")
                await search_msg.edit_text(cached_result, parse_mode="HTML")
                self._log_search_activity(message.from_user.id, user_id)
                asyncio.create_task(self._safe_delete_message(message, 2))
                return

            db = next(get_db())
            try:
                # Показываем что идет поиск
                search_msg = await message.reply("🔍 <i>Ищем информацию в базе данных...</i>", parse_mode="HTML")

                # Получаем чаты пользователя (простая версия)
                chats = UserRepository.get_user_chats(db, user_id)

                # Получаем ники пользователя
                nicks = BotSearchRepository.get_user_nicks(db, user_id, self.MAX_NICKS)

                # Формируем результат с простой информацией о чатах
                result = self._format_search_result_simple(target_user, chats, nicks, message.from_user.id)

                # Сохраняем в кэш
                self._set_cached_result(user_id, result)

                # Отправляем результат
                await search_msg.edit_text(result, parse_mode="HTML")

                # Логируем активность
                self._log_search_activity(message.from_user.id, user_id)

                # Удаляем исходное сообщение с командой через 2 секунды
                asyncio.create_task(self._safe_delete_message(message, 2))

            except Exception as e:
                self.logger.error(f" Database error in bot_search: {e}")
                self.stats['errors'] += 1
                await message.reply(" Произошла ошибка при поиске информации.")
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f" Error in bot_search: {e}")
            self.stats['errors'] += 1
            await message.reply(" Произошла ошибка при обработке команды.")

    def _format_search_result_simple(self, target: types.User, chats: List[Tuple[int, str]], nicks: List[str],
                                     searcher_id: int) -> str:
        """Форматирует результат поиска с простой информацией о чатах"""
        result = [
            f"🔍 <b>Информация о пользователе:</b>",
            f"👤 <b>{self._escape_html(target.full_name)}</b> (ID: <code>{target.id}</code>)",
            ""
        ]

        if target.username:
            result.append(f"📱 @{target.username}")
            result.append("")

        if chats:
            result.append(f"💬 <b>Чаты пользователя ({len(chats)}):</b>")

            for i, (chat_id, chat_title) in enumerate(chats[:15], 1):
                result.append(f"{i}. {self._escape_html(chat_title)} (ID: <code>{chat_id}</code>)")

            if len(chats) > 15:
                result.append(f"\n📋 <i>... и еще {len(chats) - 15} чатов</i>")
        else:
            result.append("💬 <b>Чаты:</b> не найдено")

        result.append("")

        if nicks:
            result.append(f"📛 <b>История ников ({len(nicks)}):</b>")
            for i, nick in enumerate(nicks[:10], 1):
                result.append(f"{i}. {self._escape_html(nick)}")

            if len(nicks) > 10:
                result.append(f"<i>... и еще {len(nicks) - 10} ников</i>")
        else:
            result.append("📛 <b>Ники:</b> не найдено")

        return "\n".join(result)

    async def _parse_search_target(self, message: types.Message) -> Optional[types.User]:
        """Парсит цель поиска из сообщения"""
        # ВАЖНОЕ ИСПРАВЛЕНИЕ: Сначала проверяем ответ на сообщение
        if message.reply_to_message and message.reply_to_message.from_user:
            target_user = message.reply_to_message.from_user
            self.logger.info(f"🔍 Поиск по ответу: {target_user.full_name} (ID: {target_user.id})")
            return target_user

        text = message.text.lower().strip()
        self.logger.info(f"🔍 Текст команды: {text}")

        # Парсим аргументы команды
        parts = text.split()
        if len(parts) < 2:
            self.logger.info(" Недостаточно аргументов в команде")
            return None

        # Проверяем разные варианты команд
        first_part = parts[0].lower()
        valid_commands = ['бот', '!бот', '/бот', '/ботищи', '/bot_search']

        if first_part not in valid_commands:
            self.logger.info(f" Неизвестная команда: {first_part}")
            return None

        # Проверяем вторую часть команды - ТОЧНОЕ СОВПАДЕНИЕ
        second_part = parts[1].lower()
        if second_part not in ['ищи', 'поиск']:
            self.logger.info(f" Неизвестная подкоманда: {second_part}")
            return None

        # Если есть третья часть - это цель поиска
        if len(parts) >= 3:
            target_arg = parts[2].strip()
            self.logger.info(f"🔍 Аргумент поиска: {target_arg}")

            # Если это username (начинается с @)
            if target_arg.startswith('@'):
                username = target_arg[1:]
                try:
                    user = await self._get_user_by_username(message, username)
                    if user:
                        self.logger.info(f"🔍 Найден пользователь по username: {user.full_name}")
                    return user
                except Exception as e:
                    self.logger.error(f" Ошибка поиска по username: {e}")
                    return None

            # Если это числовой ID
            elif target_arg.isdigit():
                user_id = int(target_arg)
                try:
                    user = await self._get_user_by_id(message, user_id)
                    if user:
                        self.logger.info(f"🔍 Найден пользователь по ID: {user.full_name}")
                    return user
                except Exception as e:
                    self.logger.error(f" Ошибка поиска по ID: {e}")
                    return None

        self.logger.info(" Не удалось определить цель поиска")
        return None

    async def _get_user_by_username(self, message: types.Message, username: str) -> Optional[types.User]:
        """Получает пользователя по username"""
        try:
            # Пытаемся найти пользователя в чате
            chat_members = await message.chat.get_members()
            for member in chat_members:
                if member.user.username and member.user.username.lower() == username.lower():
                    return member.user
            return None
        except Exception as e:
            self.logger.error(f"Error getting user by username: {e}")
            return None

    async def _get_user_by_id(self, message: types.Message, user_id: int) -> Optional[types.User]:
        """Получает пользователя по ID"""
        try:
            # Пытаемся получить информацию о пользователе через get_chat
            user = await message.bot.get_chat(user_id)
            return user
        except Exception as e:
            self.logger.error(f"Error getting user by ID {user_id}: {e}")
            return None

    async def _validate_search_request(self, message: types.Message, target: types.User) -> Optional[str]:
        """Проверяет валидность запроса поиска"""
        try:
            bot_user = await message.bot.get_me()

            if target.id == bot_user.id:
                return " Нельзя искать информацию о боте!"

            if target.id == message.from_user.id:
                return " Для поиска информации о себе используйте профиль Telegram!"

            if hasattr(target, 'is_bot') and target.is_bot:
                return " Нельзя искать информацию о других ботах!"

            return None
        except Exception as e:
            self.logger.error(f"Error in validation: {e}")
            return " Ошибка при проверке запроса"

    async def _get_protection_info(self, user_id: int, chat_id: int) -> str:
        """Получает информацию о защите пользователя"""
        db = next(get_db())
        try:
            current_time = datetime.now()

            # Ищем активные покупки защиты
            active_protections = db.query(UserPurchase).filter(
                UserPurchase.user_id == user_id,
                UserPurchase.item_id.in_(PROTECTION_ITEM_IDS),
                UserPurchase.chat_id == chat_id
            ).all()

            protection_items = []
            for purchase in active_protections:
                if purchase.expires_at is None or purchase.expires_at > current_time:
                    if purchase.item_id == 4:
                        protection_items.append("'Невидимка от !бот ищи'")
                    elif purchase.item_id == 6:
                        protection_items.append("'Защита от !!мут и !бот стоп'")

            if protection_items:
                return f"приобрел {', '.join(protection_items)}"
            else:
                return "имеет защиту от поиска"

        except Exception as e:
            logger.error(f"Error getting protection info: {e}")
            return "имеет защиту от поиска"
        finally:
            db.close()

    async def debug_protection_command(self, message: types.Message):
        """Команда для отладки защиты"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        # Проверяем защиту
        has_protection = self.has_search_protection(user_id, chat_id)

        # Получаем детальную информацию
        db = next(get_db())
        try:
            # Все покупки пользователя
            all_purchases = db.query(UserPurchase).filter(
                UserPurchase.user_id == user_id
            ).all()

            # Покупки защиты
            protection_purchases = db.query(UserPurchase).filter(
                UserPurchase.user_id == user_id,
                UserPurchase.item_id.in_(PROTECTION_ITEM_IDS)
            ).all()

            # Активные покупки через ShopRepository
            active_purchases = ShopRepository.get_active_purchases(db, user_id)

            debug_info = (
                f"🔍 <b>Отладка защиты от поиска:</b>\n\n"
                f"👤 User ID: {user_id}\n"
                f"💬 Chat ID: {chat_id}\n"
                f"🛡️ Защита активна: {'✅ ДА' if has_protection else ' НЕТ'}\n\n"
                f"📊 <b>Статистика покупок:</b>\n"
                f"• Всего покупок: {len(all_purchases)}\n"
                f"• Покупок защиты: {len(protection_purchases)}\n"
                f"• Активных покупок: {len(active_purchases)}\n"
                f"• Активные ID: {active_purchases}\n\n"
                f"🛒 <b>Покупки защиты:</b>\n"
            )

            for purchase in protection_purchases:
                status = "✅ АКТИВНА" if (
                        purchase.expires_at is None or purchase.expires_at > datetime.now()) else " ИСТЕКЛА"
                debug_info += f"• ID {purchase.item_id} в чате {purchase.chat_id} - {status}\n"
                debug_info += f"  Срок: {purchase.expires_at}\n"

            await message.reply(debug_info, parse_mode="HTML")

        except Exception as e:
            await message.reply(f" Ошибка отладки: {e}")
        finally:
            db.close()

    async def _show_search_help(self, message: types.Message):
        """Показывает справку по использованию команды"""
        help_text = (
            "🔍 <b>Как использовать команду 'бот ищи':</b>\n\n"
            "<b>Способ 1 (рекомендуемый):</b>\n"
            "Ответьте на сообщение пользователя командой:\n"
            "• <code>бот ищи</code>\n"
            "• <code>!бот ищи</code>\n\n"
            "<b>Способ 2:</b>\n"
            "Отправьте команду с ID пользователя:\n"
            "• <code>бот ищи 123456789</code>\n\n"
            "🛡️ <i>Некоторые пользователи могут иметь защиту от поиска</i>\n"
            "📊 <i>Бот покажет информацию о чатах и историю ников пользователя</i>"
        )
        await message.reply(help_text, parse_mode="HTML")

    # Остальные вспомогательные методы остаются без изменений...
    def _check_cooldown(self, user_id: int, command: str) -> bool:
        """Проверка кулдауна для защиты от флуда"""
        current_time = asyncio.get_event_loop().time()
        key = f"{user_id}_{command}"

        if key in self.cooldown_dict:
            if current_time - self.cooldown_dict[key] < 3:
                return False
        self.cooldown_dict[key] = current_time
        return True

    async def _safe_delete_message(self, message: types.Message, delay: int = 0):
        """Безопасное удаление сообщения с задержкой"""
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            await message.delete()
        except (MessageToDeleteNotFound, MessageCantBeDeleted):
            pass
        except Exception as e:
            self.logger.debug(f"Could not delete message: {e}")

    def _get_cached_result(self, user_id: int) -> Optional[str]:
        """Получает закэшированный результат"""
        if user_id in self.cache:
            result, timestamp = self.cache[user_id]
            current_time = asyncio.get_event_loop().time()
            if current_time - timestamp < self.CACHE_TTL:
                self.stats['cache_hits'] += 1
                return result
            else:
                del self.cache[user_id]
        return None

    def _set_cached_result(self, user_id: int, result: str):
        """Сохраняет результат в кэш"""
        self.cache[user_id] = (result, asyncio.get_event_loop().time())

    def _log_search_activity(self, searcher_id: int, target_id: int):
        """Логирует активность поиска"""
        if searcher_id not in self.search_history:
            self.search_history[searcher_id] = []

        now = datetime.now()
        self.search_history[searcher_id] = [
            dt for dt in self.search_history[searcher_id]
            if now - dt < timedelta(hours=1)
        ]
        self.search_history[searcher_id].append(now)

    def _is_command_to_log(self, message: types.Message) -> bool:
        """Проверяет, является ли сообщение командой для сбора данных"""
        if not message.text:
            return False

        text = message.text.lower().strip()

        # Пропускаем команды поиска
        if any(text.startswith(cmd) for cmd in ['бот ищи', '!бот ищи', '/ботищи', '/bot_search']):
            return False

        if text.startswith('/'):
            command = text[1:].split('@')[0].split()[0]
            if command in COMMANDS_TO_LOG:
                return True

        for cmd in COMMANDS_TO_LOG:
            if text == cmd or text.startswith(cmd + ' '):
                return True

        return False

    def _get_search_stats(self, user_id: int) -> Dict[str, int]:
        """Получает статистику поисков для пользователя"""
        if user_id not in self.search_history:
            return {'last_hour': 0, 'today': 0}

        now = datetime.now()
        searches = self.search_history[user_id]
        last_hour = len([dt for dt in searches if now - dt < timedelta(hours=1)])
        today = len([dt for dt in searches if dt.date() == now.date()])

        return {'last_hour': last_hour, 'today': today}

    def _escape_html(self, text: str) -> str:
        """Экранирование HTML-символов"""
        if not text:
            return ""
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    # Методы safe_add_user_chat и safe_add_user_nick остаются без изменений
    def _safe_add_user_chat(self, db, user_id: int, chat_id: int, chat_title: str) -> bool:
        """Безопасное добавление чата пользователя"""
        try:
            existing_count = db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id
            ).count()

            if existing_count >= self.MAX_CHATS:
                records_to_delete = existing_count - self.MAX_CHATS + 1
                oldest_records = db.query(UserChatSearch).filter(
                    UserChatSearch.user_id == user_id
                ).order_by(UserChatSearch.created_at.asc()).limit(records_to_delete).all()

                for record in oldest_records:
                    db.delete(record)

            existing = db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id,
                UserChatSearch.chat_id == chat_id
            ).first()

            if not existing:
                record = UserChatSearch(
                    user_id=user_id,
                    chat_id=chat_id,
                    chat_title=chat_title
                )
                db.add(record)
                return True
            elif existing.chat_title != chat_title:
                existing.chat_title = chat_title
                return True

            return False
        except IntegrityError:
            db.rollback()
            return False
        except Exception as e:
            self.logger.error(f" Error in _safe_add_user_chat: {e}")
            return False

    def _safe_add_user_nick(self, db, user_id: int, nick: str) -> bool:
        """Безопасное добавление ника пользователя"""
        try:
            existing_count = db.query(UserNickSearch).filter(
                UserNickSearch.user_id == user_id
            ).count()

            if existing_count >= self.MAX_NICKS:
                records_to_delete = existing_count - self.MAX_NICKS + 1
                oldest_records = db.query(UserNickSearch).filter(
                    UserNickSearch.user_id == user_id
                ).order_by(UserNickSearch.created_at.asc()).limit(records_to_delete).all()

                for record in oldest_records:
                    db.delete(record)

            existing = db.query(UserNickSearch).filter(
                UserNickSearch.user_id == user_id,
                UserNickSearch.nick == nick
            ).first()

            if not existing:
                record = UserNickSearch(
                    user_id=user_id,
                    nick=nick
                )
                db.add(record)
                return True
            return False
        except IntegrityError:
            db.rollback()
            return False
        except Exception as e:
            self.logger.error(f" Error in _safe_add_user_nick: {e}")
            return False

    async def bot_search_clear(self, message: types.Message):
        """Команда для очистки данных о себе"""
        try:
            user_id = message.from_user.id
            self.logger.info(f"🧹 Запрос очистки данных от пользователя {user_id}")

            db = next(get_db())
            try:
                chats_deleted = db.query(UserChatSearch).filter(
                    UserChatSearch.user_id == user_id
                ).delete()

                nicks_deleted = db.query(UserNickSearch).filter(
                    UserNickSearch.user_id == user_id
                ).delete()

                db.commit()

                if user_id in self.cache:
                    del self.cache[user_id]

                await message.reply(
                    f"✅ <b>Ваши данные очищены!</b>\n\n"
                    f"🗑️ Удалено:\n"
                    f"• Чатов: {chats_deleted}\n"
                    f"• Ников: {nicks_deleted}\n\n"
                    f"💡 <i>Новые данные будут собираться при следующих командах</i>\n"
                    f"⚡ <i>Кэш также очищен</i>",
                    parse_mode="HTML"
                )

            except Exception as e:
                db.rollback()
                self.logger.error(f" Database error in bot_search_clear: {e}")
                self.stats['errors'] += 1
                await message.reply(" Произошла ошибка при очистке данных.")
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f" Error in bot_search_clear: {e}")
            self.stats['errors'] += 1
            await message.reply(" Произошла ошибка при обработке команды.")

    async def bot_search_stats(self, message: types.Message):
        """Команда для просмотра статистики системы"""
        try:
            stats_text = (
                f"📊 <b>Статистика системы поиска:</b>\n\n"
                f"🔍 Всего поисков: {self.stats['total_searches']}\n"
                f"💾 Данных записано: {self.stats['data_logged']}\n"
                f"⚡ Кэш-попаданий: {self.stats['cache_hits']}\n"
                f"🛡️ Защищенных пользователей: {self.stats['protected_users']}\n"
                f"🔔 Уведомлений о защите: {self.stats['protection_notifications']}\n"
                f"📈 Кэшировано: {len(self.cache)} запросов\n"
                f" Ошибок: {self.stats['errors']}\n\n"
                f"💡 <i>Система работает в штатном режиме</i>"
            )

            await message.reply(stats_text, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f" Error in bot_search_stats: {e}")
            await message.reply(" Ошибка при получении статистики.")


# ТОЧНЫЕ функции проверки команд
def _is_exact_search_command(text: str) -> bool:
    """Проверяет, является ли сообщение ТОЧНОЙ командой поиска"""
    if not text:
        return False

    text_lower = text.lower().strip()

    # ТОЧНЫЕ варианты команд (только начало сообщения)
    exact_commands = [
        'бот ищи',
        '!бот ищи',
        '/бот ищи',
        '/ботищи',
        '/bot_search'
    ]

    # Проверяем точное начало сообщения
    for cmd in exact_commands:
        if text_lower.startswith(cmd):
            # Проверяем что после команды либо конец строки, либо пробел и аргументы
            remaining_text = text_lower[len(cmd):].strip()
            # Если после команды ничего нет или следующий символ пробел - это точная команда
            if not remaining_text or remaining_text[0] == ' ':
                return True

    return False


def _is_exact_clear_command(text: str) -> bool:
    """Проверяет, является ли сообщение ТОЧНОЙ командой очистки"""
    if not text:
        return False

    text_lower = text.lower().strip()

    exact_commands = [
        'бот очисти',
        '!бот очисти',
        '/бот очисти',
        '/боточисти',
        '/bot_clear'
    ]

    for cmd in exact_commands:
        if text_lower.startswith(cmd):
            remaining_text = text_lower[len(cmd):].strip()
            if not remaining_text or remaining_text[0] == ' ':
                return True

    return False


def _is_exact_stats_command(text: str) -> bool:
    """Проверяет, является ли сообщение ТОЧНОЙ командой статистики"""
    if not text:
        return False

    text_lower = text.lower().strip()

    exact_commands = [
        'бот статистика',
        '!бот статистика',
        '/бот статистика',
        '/ботстат',
        '/search_stats'
    ]

    for cmd in exact_commands:
        if text_lower.startswith(cmd):
            remaining_text = text_lower[len(cmd):].strip()
            if not remaining_text or remaining_text[0] == ' ':
                return True

    return False


def register_bot_search_handlers(dp: Dispatcher):
    """Регистрация обработчиков для команды 'бот ищи'"""
    handler = BotSearchHandler()

    # Логируем только команды из списка для сбора данных
    dp.register_message_handler(
        handler.log_user_command,
        lambda msg: msg.text and (
                msg.text.startswith('/') or
                any(msg.text.lower().startswith(cmd + ' ') for cmd in COMMANDS_TO_LOG) or
                msg.text.lower() in COMMANDS_TO_LOG
        ),
        state="*",
        content_types=types.ContentTypes.TEXT,
        run_task=True
    )

    # Регистрируем команду "бот ищи" с ТОЧНЫМИ фильтрами
    dp.register_message_handler(
        handler.bot_search,
        lambda msg: msg.text and _is_exact_search_command(msg.text)
    )

    # Регистрируем команду очистки данных
    dp.register_message_handler(
        handler.bot_search_clear,
        lambda msg: msg.text and _is_exact_clear_command(msg.text)
    )

    # Регистрируем команду статистики
    dp.register_message_handler(
        handler.bot_search_stats,
        lambda msg: msg.text and _is_exact_stats_command(msg.text)
    )

    dp.register_message_handler(
        handler.debug_protection_command,
        commands=["debug_protection"],
        state="*"
    )

    logger.info("✅ Обработчики 'бот ищи' зарегистрированы (упрощенная версия)")
    logger.info(f"📝 Сбор данных включен для {len(COMMANDS_TO_LOG)} команд")
    logger.info(f"🛡️ ID товаров защиты: {PROTECTION_ITEM_IDS}")