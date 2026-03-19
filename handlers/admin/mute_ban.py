# handlers/mute_ban.py
import asyncio
import re
import time
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from random import choice

from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Command
from aiogram.utils.exceptions import BadRequest

from database import get_db
from database.crud import UserRepository, ModerationLogRepository, TransactionRepository, ActiveMuteRepository
from database.models import ModerationAction

# Конфигурация
ADMIN_IDS = [6090751674, 1054684037]
# Конфигурация платного мута
PAID_MUTE_COST = 200000000  # 200 лямов Монет
PAID_MUTE_DURATION_MINUTES = 1  # Длительность мута по умолчанию

# Файлы хранения
BOT_BAN_STORAGE_FILE = "active_bans.json"

logger = logging.getLogger(__name__)


class BotBanManager:
    """Менеджер для управления банами в боте"""

    def __init__(self, mute_ban_manager):
        self.mute_ban_manager = mute_ban_manager
        self.bot = None
        self.bot_bans = self._load_bot_bans()
        self.cleanup_task = None
        self.recently_unbanned = set()
        self.middleware = None

    def _load_bot_bans(self) -> Dict:
        """Загружает баны из файла"""
        try:
            if os.path.exists(BOT_BAN_STORAGE_FILE):
                with open(BOT_BAN_STORAGE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки банов: {e}")
        return {}

    def _save_bot_bans(self):
        """Сохраняет баны в файл"""
        try:
            with open(BOT_BAN_STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.bot_bans, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения банов: {e}")

    def is_user_bot_banned(self, user_id: int) -> bool:
        """Проверяет, забанен ли пользователь в боте"""
        try:
            user_id_str = str(user_id)

            # Проверка недавно разбаненных
            if user_id in self.recently_unbanned:
                return False

            if user_id_str in self.bot_bans:
                ban_data = self.bot_bans[user_id_str]
                expires_at = ban_data.get('expires_at')

                # Удаление истекших банов
                if expires_at and time.time() > expires_at:
                    del self.bot_bans[user_id_str]
                    self._save_bot_bans()
                    return False
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки бана: {e}")
            return False

    async def ban_user_in_bot(self, user_id: int, admin_id: int,
                              reason: str = "Не указана", seconds: int = None) -> bool:
        """Банит пользователя в боте"""
        try:
            # Проверяем, не является ли пользователь админом БОТА
            if await self.mute_ban_manager._is_bot_admin(user_id):
                logger.warning(f"Попытка бана админа бота: {user_id}")
                return False

            user_id_str = str(user_id)
            ban_data = {
                'user_id': user_id,
                'admin_id': admin_id,
                'reason': reason,
                'banned_at': time.time(),
                'banned_at_text': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            if seconds:
                seconds = min(seconds, 315360000)  # Макс 10 лет
                ban_data['expires_at'] = time.time() + seconds
                ban_data['expires_at_text'] = (datetime.now() + timedelta(seconds=seconds)).strftime(
                    "%Y-%m-%d %H:%M:%S")

            self.bot_bans[user_id_str] = ban_data
            self._save_bot_bans()

            # Удаляем из недавно разбаненных
            self.recently_unbanned.discard(user_id)

            logger.info(f"Пользователь {user_id} забанен в боте на {seconds}с, причина: {reason}")
            return True
        except Exception as e:
            logger.error(f"Ошибка бана в боте: {e}")
            return False

    async def unban_user_in_bot(self, user_id: int) -> bool:
        """Разбанивает пользователя в боте"""
        try:
            user_id_str = str(user_id)
            if user_id_str in self.bot_bans:
                del self.bot_bans[user_id_str]
                self._save_bot_bans()

                # Добавляем в недавно разбаненных
                self.recently_unbanned.add(user_id)

                # Уведомляем middleware о разбане
                if self.middleware:
                    self.middleware.add_recently_unbanned(user_id)

                logger.info(f"Пользователь {user_id} разбанен в боте")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка разбана в боте: {e}")
            return False

    def get_ban_info(self, user_id: int) -> Optional[Dict]:
        """Получает информацию о бане"""
        try:
            return self.bot_bans.get(str(user_id))
        except Exception:
            return None

    def add_recently_unbanned(self, user_id: int):
        """Добавляет пользователя в недавно разбаненных"""
        self.recently_unbanned.add(user_id)

    def set_middleware(self, middleware):
        """Устанавливает ссылку на middleware"""
        self.middleware = middleware

    def set_bot(self, bot):
        """Устанавливает бота"""
        self.bot = bot

    def start_cleanup_task(self):
        """Запускает задачу очистки истекших банов"""
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_expired_bans())

    async def stop_cleanup_task(self):
        """Останавливает задачу очистки"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_expired_bans(self):
        """Фоновая задача очистки истекших банов"""
        while True:
            try:
                current_time = time.time()
                expired = []

                for user_id_str, ban_data in list(self.bot_bans.items()):
                    expires_at = ban_data.get('expires_at')
                    if expires_at and current_time > expires_at:
                        expired.append(user_id_str)
                        user_id = int(user_id_str)
                        self.add_recently_unbanned(user_id)

                        # Уведомляем middleware об авторазбане
                        if self.middleware:
                            self.middleware.add_recently_unbanned(user_id)

                for user_id_str in expired:
                    del self.bot_bans[user_id_str]

                if expired:
                    self._save_bot_bans()

                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в задаче очистки: {e}")
                await asyncio.sleep(300)

    async def restore_bans_after_restart(self):
        """Восстанавливает баны после перезапуска"""
        current_time = time.time()
        expired = []

        for user_id_str, ban_data in list(self.bot_bans.items()):
            expires_at = ban_data.get('expires_at')
            if expires_at and current_time > expires_at:
                expired.append(user_id_str)

        for user_id_str in expired:
            del self.bot_bans[user_id_str]

        if expired:
            self._save_bot_bans()

        logger.info(f"Восстановлено {len(self.bot_bans)} активных банов, удалено {len(expired)} истекших")


# Текстовые ответы
class ResponseTexts:
    """Класс с текстовыми ответами для модерации"""

    # Сообщения для мута
    MUTE_SUCCESS = [
        "✅ {user} успешно отправлен в режим тишины на {time}.",
        "🔇 {user} получил тишину на {time}. Отличная возможность подумать.",
        "🤫 {user} получил {time} на размышления. Говорить нельзя.",
        "📵 Режим тишины для {user} активирован на {time}. Время для медитации."
    ]

    # Сообщения для размута
    UNMUTE_SUCCESS = [
        "🔊 {user} получает голос обратно.\nГовори, но помни — стены тоже слушают.",
        "🎤 Микрофон для {user} снова включен. Будь осторожен со словами.",
        "🗣️ {user} получает право голоса. Используй его с умом.",
        "🎵 Звук для {user} вернулся в чат. Продолжаем общение."
    ]

    # Сообщения для бана
    BAN_SUCCESS = [
        "🚫 {user} исключён из чата без права возврата.",
        "⛔ {user} дверь захлопнулась навсегда. Прощай.",
        "🔒 {user} доступ закрыт. Возврата нет.",
        "👋 {user} прощание навсегда. Путь назад отрезан."
    ]

    # Сообщения для разбана
    UNBAN_SUCCESS = [
        "🔓 Дверь для {user} снова открыта. Можешь вернуться.",
        "🌅 Запрет для {user} снят. Добро пожаловать обратно.",
        "✅ {user} может вернуться в чат.",
        "🚪 Возвращение {user} разрешено. Входи."
    ]

    # Сообщения для кика
    KICK_SUCCESS = [
        "👢 {user} выгнан из чата. Может вернуться по приглашению.",
        "💨 Ветер перемен вынес {user} из чата.",
        "🚶‍♂️ {user} временно исключён. Возврат возможен.",
        "🏃‍♂️ Быстрый выход для {user}. Дверь остаётся открытой."
    ]

    # Сообщения для бана в боте
    BOTBAN_SUCCESS = [
        "🤖 {user} заблокирован в боте на {time}.",
        "🚫 Бот больше не будет отвечать {user} на {time}.",
        "⚡ Доступ к боту для {user} ограничен на {time}.",
        "🔐 Замок на боте для {user} установлен на {time}."
    ]

    # Сообщения для разбана в боте
    BOTUNBAN_SUCCESS = [
        "🤖 Блокировка {user} в боте снята.",
        "✅ {user} снова может общаться с ботом.",
        "🔓 Доступ к боту для {user} восстановлен.",
        "🌐 Связь с ботом для {user} возобновлена."
    ]

    # Ошибки
    ERROR_NO_RIGHTS = "Недостаточно прав для выполнения команды."
    ERROR_BOT_NO_RIGHTS = "У бота нет необходимых прав для модерации."
    ERROR_NO_REPLY = "Команду нужно использовать в ответ на сообщение пользователя."
    ERROR_ADMIN_TARGET = "Модерация администратора запрещена."
    ERROR_ALREADY_MUTED = "Пользователь уже ограничен в общении."
    ERROR_NOT_MUTED = "На пользователя не наложены ограничения."
    ERROR_NOT_BANNED = "Пользователь не находится в бане."
    ERROR_GENERAL = "Операцию не удалось выполнить."
    ERROR_INVALID_TIME = "Некорректно указано время."
    ERROR_BOT_ADMIN_ONLY = "Команда доступна только администраторам бота."
    ERROR_CANT_BAN_BOT_ADMIN = "Запрещено блокировать администратора бота."

    @classmethod
    def get_mute_success(cls, time_text: str, user_text: str) -> str:
        """Возвращает случайное сообщение об успешном муте"""
        return choice(cls.MUTE_SUCCESS).format(time=time_text, user=user_text)

    @classmethod
    def get_unmute_success(cls, user_text: str) -> str:
        """Возвращает случайное сообщение об успешном размуте"""
        return choice(cls.UNMUTE_SUCCESS).format(user=user_text)

    @classmethod
    def get_ban_success(cls, user_text: str) -> str:
        """Возвращает случайное сообщение об успешном бане"""
        return choice(cls.BAN_SUCCESS).format(user=user_text)

    @classmethod
    def get_unban_success(cls, user_text: str) -> str:
        """Возвращает случайное сообщение об успешном разбане"""
        return choice(cls.UNBAN_SUCCESS).format(user=user_text)

    @classmethod
    def get_kick_success(cls, user_text: str) -> str:
        """Возвращает случайное сообщение об успешном кике"""
        return choice(cls.KICK_SUCCESS).format(user=user_text)

    @classmethod
    def get_botban_success(cls, time_text: str = "всегда", user_text: str = "Пользователь") -> str:
        """Возвращает случайное сообщение об успешном бане в боте"""
        return choice(cls.BOTBAN_SUCCESS).format(time=time_text, user=user_text)

    @classmethod
    def get_botunban_success(cls, user_text: str = "Пользователь") -> str:
        """Возвращает случайное сообщение об успешном разбане в боте"""
        return choice(cls.BOTUNBAN_SUCCESS).format(user=user_text)


class MuteBanManager:
    """Менеджер модерации с полным функционалом"""

    def __init__(self):
        self.bot = None
        self.bot_ban_manager = BotBanManager(self)
        self.active_mutes = {}
        self.cleanup_task = None

    def set_bot(self, bot):
        """Устанавливает экземпляр бота"""
        self.bot = bot
        self.bot_ban_manager.set_bot(bot)

    # ===== ПРОВЕРКИ ПРАВ =====

    def is_global_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь глобальным админом"""
        return user_id in ADMIN_IDS

    async def _is_bot_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь админом бота (добавленным через админ-панель)"""
        # Глобальные админы всегда имеют доступ
        if self.is_global_admin(user_id):
            return True

        # Проверяем в базе данных
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            is_admin = bool(user and user.is_admin)
            db.close()
            return is_admin
        except Exception as e:
            logger.error(f"Ошибка проверки админа бота: {e}")
            return False

    async def is_chat_admin(self, user_id: int, chat_id: int) -> bool:
        """Проверяет, является ли пользователь админом чата"""
        if not self.bot:
            return False

        try:
            member = await self.bot.get_chat_member(chat_id, user_id)
            return member.status in ["administrator", "creator"]
        except Exception as e:
            logger.error(f"Ошибка проверки админа чата: {e}")
            return False

    async def _is_user_admin(self, user_id: int, chat_id: int = None) -> bool:
        """Проверяет, является ли пользователь администратором"""
        # Глобальные админы
        if self.is_global_admin(user_id):
            return True

        # Админы в БД
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if user and user.is_admin:
                db.close()
                return True
            db.close()
        except Exception as e:
            logger.error(f"Ошибка проверки админа в БД: {e}")

        # Админы чата (если указан chat_id)
        if chat_id and self.bot:
            return await self.is_chat_admin(user_id, chat_id)

        return False

    async def _check_admin(self, message: types.Message) -> bool:
        """Проверяет права администратора у отправителя"""
        if not message or not message.from_user:
            return False
        return await self._is_user_admin(message.from_user.id, message.chat.id if message.chat else None)

    async def _check_bot_admin(self, message: types.Message) -> bool:
        """Проверяет права администратора бота у отправителя"""
        if not message or not message.from_user:
            return False
        return await self._is_bot_admin(message.from_user.id)

    async def _check_bot_permissions(self, chat_id: int) -> bool:
        """Проверяет права бота в чате"""
        if not self.bot:
            return False

        try:
            bot_member = await self.bot.get_chat_member(chat_id, self.bot.id)

            if bot_member.status == "administrator":
                return bot_member.can_restrict_members
            elif bot_member.status == "restricted":
                return hasattr(bot_member, 'can_restrict_members') and bot_member.can_restrict_members
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки прав бота: {e}")
            return False

    async def _check_target_is_admin(self, chat_id: int, user_id: int) -> bool:
        """Проверяет, является ли целевой пользователь админом"""
        # Проверка глобального админа
        if self.is_global_admin(user_id):
            return True

        # Проверка админа чата
        if chat_id:
            return await self.is_chat_admin(user_id, chat_id)

        return False

    async def _check_user_mute_status(self, chat_id: int, user_id: int) -> Optional[bool]:
        """Проверяет статус мута пользователя"""
        if not self.bot:
            return None

        try:
            member = await self.bot.get_chat_member(chat_id, user_id)

            # Если пользователь админ или создатель, у него нет мута
            if member.status in ["administrator", "creator"]:
                return False

            # Если пользователь ограничен, проверяем права
            if member.status == "restricted":
                # В зависимости от версии aiogram, атрибут может называться по-разному
                if hasattr(member, 'can_send_messages'):
                    permissions = member.can_send_messages
                elif hasattr(member, 'permissions'):
                    permissions = member.permissions.can_send_messages
                else:
                    return None
                return not permissions  # True если замучен (не может отправлять сообщения)

            # Если обычный участник или покинувший
            return False

        except Exception as e:
            logger.error(f"Ошибка проверки статуса мута: {e}")
            return None

    # ===== УТИЛИТЫ ДЛЯ ПОЛУЧЕНИЯ ИМЕН ПОЛЬЗОВАТЕЛЕЙ =====

    async def _get_user_info_for_message(self, chat_id: int, user_id: int, from_db: bool = False) -> str:
        """Получает информацию о пользователе для отображения в сообщении"""
        try:
            # Пробуем получить пользователя из чата
            user = await self.bot.get_chat(user_id)

            # Формируем имя пользователя
            if user.username:
                user_name = f"@{user.username}"
            elif user.first_name and user.last_name:
                user_name = f"{user.first_name} {user.last_name}"
            elif user.first_name:
                user_name = user.first_name
            else:
                user_name = f"Пользователь ID: {user_id}"

            return f"<b>{user_name}</b>"

        except Exception as e:
            logger.warning(f"Не удалось получить информацию о пользователе {user_id}: {e}")

            # Если не получилось из чата, пробуем из базы данных
            if from_db:
                try:
                    db = next(get_db())
                    db_user = UserRepository.get_user_by_telegram_id(db, user_id)
                    db.close()

                    if db_user and db_user.username:
                        return f"@{db_user.username}"
                    elif db_user and db_user.full_name:
                        return f"<b>{db_user.full_name}</b>"
                except Exception as db_error:
                    logger.warning(f"Не удалось получить пользователя {user_id} из БД: {db_error}")

            return f"<b>Пользователь ID: {user_id}</b>"

    async def _get_user_info_by_id(self, user_id: int) -> str:
        """Получает информацию о пользователе только по ID"""
        try:
            user = await self.bot.get_chat(user_id)

            if user.username:
                user_name = f"@{user.username}"
            elif user.first_name and user.last_name:
                user_name = f"{user.first_name} {user.last_name}"
            elif user.first_name:
                user_name = user.first_name
            else:
                user_name = f"Пользователь ID: {user_id}"

            return f"<b>{user_name}</b>"

        except Exception as e:
            logger.warning(f"Не удалось получить информацию о пользователе {user_id}: {e}")
            return f"<b>Пользователь ID: {user_id}</b>"

    # ===== ОСНОВНЫЕ МЕТОДЫ МОДЕРАЦИИ =====

    async def mute_user(self, chat_id: int, user_id: int, admin_id: int,
                        duration_minutes: int = 30, reason: str = "Без причины") -> Tuple[bool, str]:
        """Мутит пользователя. Возвращает (успех, сообщение)"""
        if not self.bot:
            return False, ResponseTexts.ERROR_GENERAL

        try:
            # Проверка админа цели
            if await self.is_chat_admin(user_id, chat_id):
                return False, ResponseTexts.ERROR_ADMIN_TARGET

            # Проверяем, не замучен ли уже пользователь
            mute_status = await self._check_user_mute_status(chat_id, user_id)
            if mute_status is True:
                return False, ResponseTexts.ERROR_ALREADY_MUTED
            elif mute_status is None:
                logger.warning(f"Не удалось проверить статус пользователя {user_id}")

            # Рассчитываем until_date
            if duration_minutes <= 0:
                return False, ResponseTexts.ERROR_INVALID_TIME

            # Преобразуем минуты в секунды для until_date
            until_date = int(time.time()) + (duration_minutes * 60)

            # Минимальное время мута в Telegram - 30 секунд
            if until_date <= int(time.time()) + 30:
                until_date = int(time.time()) + 30

            permissions = types.ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )

            # Получаем информацию о пользователе для отображения
            user_info = await self._get_user_info_for_message(chat_id, user_id)

            # Используем until_date как timestamp (int)
            await self.bot.restrict_chat_member(chat_id, user_id, permissions, until_date=until_date)

            # === ЛОГИРОВАНИЕ В БАЗУ ДАННЫХ ===
            try:
                db = next(get_db())

                # 1. Логируем действие
                ModerationLogRepository.add_moderation_log(
                    db=db,
                    user_id=user_id,
                    admin_id=admin_id,
                    action_type="mute",
                    duration=duration_minutes * 60,  # в секундах
                    reason=reason,
                    chat_id=chat_id
                )

                # 2. Сохраняем активный мут
                muted_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
                ActiveMuteRepository.add_active_mute(
                    db=db,
                    user_id=user_id,
                    chat_id=chat_id,
                    admin_id=admin_id,
                    muted_until=muted_until,
                    reason=reason
                )

                db.close()
                logger.info(f"✅ Мут записан в БД: {user_id} на {duration_minutes} мин")

            except Exception as e:
                logger.error(f" Ошибка записи мута в БД: {e}")

            # Сохранение для авторазмута
            if chat_id not in self.active_mutes:
                self.active_mutes[chat_id] = {}

            # Сохраняем время размута как datetime
            self.active_mutes[chat_id][user_id] = datetime.utcnow() + timedelta(minutes=duration_minutes)

            # Формируем текст времени
            time_text = self._format_duration(duration_minutes)

            logger.info(
                f"Пользователь {user_id} замучен в {chat_id} на {duration_minutes} мин (until_date={until_date})")

            # Используем имя пользователя в сообщении
            return True, ResponseTexts.get_mute_success(time_text, user_info)

        except BadRequest as e:
            error_msg = str(e)
            if "User is an administrator of the chat" in error_msg:
                return False, ResponseTexts.ERROR_ADMIN_TARGET
            elif "Not enough rights" in error_msg or "CHAT_ADMIN_REQUIRED" in error_msg:
                return False, "Недостаточно прав у бота"
            elif "USER_NOT_PARTICIPANT" in error_msg or "User not found" in error_msg:
                return False, "Пользователь не найден в чате"
            elif "Can't remove chat owner" in error_msg:
                return False, "Нельзя мутить создателя чата"
            else:
                logger.error(f"Ошибка мута: {e}")
                return False, f"Ошибка: {error_msg[:100]}"
        except Exception as e:
            logger.error(f"Ошибка мута: {e}")
            return False, ResponseTexts.ERROR_GENERAL

    async def unmute_user(self, chat_id: int, user_id: int, admin_id: int) -> Tuple[bool, str]:
        """Размучивает пользователя. Возвращает (успех, сообщение)"""
        if not self.bot:
            return False, ResponseTexts.ERROR_GENERAL

        try:
            # Проверяем статус пользователя
            mute_status = await self._check_user_mute_status(chat_id, user_id)

            # Если пользователь админ
            if await self.is_chat_admin(user_id, chat_id):
                # Удаляем из активных мутов если был там
                if chat_id in self.active_mutes and user_id in self.active_mutes[chat_id]:
                    del self.active_mutes[chat_id][user_id]
                    if not self.active_mutes[chat_id]:
                        del self.active_mutes[chat_id]
                return False, "Пользователь является администратором"

            # Получаем информацию о пользователе для отображения
            user_info = await self._get_user_info_for_message(chat_id, user_id)

            # Если статус неизвестен или пользователь замучен - пробуем размутить
            permissions = types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )

            # Устанавливаем права без ограничения времени
            await self.bot.restrict_chat_member(chat_id, user_id, permissions)

            # === ЛОГИРОВАНИЕ В БАЗУ ДАННЫХ ===
            try:
                db = next(get_db())

                # 1. Логируем действие
                ModerationLogRepository.add_moderation_log(
                    db=db,
                    user_id=user_id,
                    admin_id=admin_id,
                    action_type="unmute",
                    duration=None,
                    reason="Ручной размут",
                    chat_id=chat_id
                )

                # 2. Удаляем активный мут
                ActiveMuteRepository.remove_active_mute(db, user_id, chat_id)

                db.close()
                logger.info(f"✅ Размут записан в БД: {user_id}")

            except Exception as e:
                logger.error(f" Ошибка записи размута в БД: {e}")

            # Удаляем из активных мутов
            if chat_id in self.active_mutes and user_id in self.active_mutes[chat_id]:
                del self.active_mutes[chat_id][user_id]
                if not self.active_mutes[chat_id]:
                    del self.active_mutes[chat_id]

            logger.info(f"Пользователь {user_id} размучен в {chat_id}")

            # Используем имя пользователя в сообщении
            return True, ResponseTexts.get_unmute_success(user_info)

        except BadRequest as e:
            error_msg = str(e)
            if "User is an administrator of the chat" in error_msg:
                return False, "Пользователь является администратором"
            elif "Not enough rights" in error_msg or "CHAT_ADMIN_REQUIRED" in error_msg:
                return False, "Недостаточно прав у бота"
            elif "USER_NOT_PARTICIPANT" in error_msg or "User not found" in error_msg:
                return True, "Пользователь не найден в чате"
            elif "Can't remove chat owner" in error_msg:
                return False, "Нельзя размутить создателя чата"
            else:
                logger.error(f"Ошибка размута: {e}")
                return False, f"Ошибка: {error_msg[:100]}"
        except Exception as e:
            logger.error(f"Ошибка размута: {e}")
            return False, ResponseTexts.ERROR_GENERAL

    async def ban_user(self, chat_id: int, user_id: int, admin_id: int,
                       reason: str = "Без причины") -> Tuple[bool, str]:
        """Банит пользователя (не может вернуться). Возвращает (успех, сообщение)"""
        if not self.bot:
            return False, ResponseTexts.ERROR_GENERAL

        try:
            # Проверка админа цели
            if await self.is_chat_admin(user_id, chat_id):
                logger.warning(f"Попытка бана админа чата {user_id}")
                return False, ResponseTexts.ERROR_ADMIN_TARGET

            # Получаем информацию о пользователе для отображения
            user_info = await self._get_user_info_for_message(chat_id, user_id)

            # Бан с запретом возвращения
            await self.bot.kick_chat_member(chat_id, user_id)

            # === ЛОГИРОВАНИЕ В БАЗУ ДАННЫХ ===
            try:
                db = next(get_db())

                ModerationLogRepository.add_moderation_log(
                    db=db,
                    user_id=user_id,
                    admin_id=admin_id,
                    action_type="ban",
                    duration=None,  # перманентный бан
                    reason=reason,
                    chat_id=chat_id
                )

                db.close()
                logger.info(f"✅ Бан записан в БД: {user_id}")

            except Exception as e:
                logger.error(f" Ошибка записи бана в БД: {e}")

            logger.info(f"Пользователь {user_id} забанен в {chat_id}")

            # Используем имя пользователя в сообщении
            return True, ResponseTexts.get_ban_success(user_info)

        except BadRequest as e:
            if "User is an administrator of the chat" in str(e):
                logger.warning(f"Не удалось забанить админа чата {user_id}")
                return False, ResponseTexts.ERROR_ADMIN_TARGET
            logger.error(f"Ошибка бана: {e}")
            return False, ResponseTexts.ERROR_GENERAL
        except Exception as e:
            logger.error(f"Ошибка бана: {e}")
            return False, ResponseTexts.ERROR_GENERAL

    async def unban_user(self, chat_id: int, user_id: int, admin_id: int) -> Tuple[bool, str]:
        """Разбанивает пользователя. Возвращает (успех, сообщение)"""
        if not self.bot:
            return False, ResponseTexts.ERROR_GENERAL

        try:
            # Получаем информацию о пользователе для отображения
            user_info = await self._get_user_info_for_message(chat_id, user_id, from_db=True)

            await self.bot.unban_chat_member(chat_id, user_id)

            # === ЛОГИРОВАНИЕ В БАЗУ ДАННЫХ ===
            try:
                db = next(get_db())

                ModerationLogRepository.add_moderation_log(
                    db=db,
                    user_id=user_id,
                    admin_id=admin_id,
                    action_type="unban",
                    duration=None,
                    reason="Ручной разбан",
                    chat_id=chat_id
                )

                db.close()
                logger.info(f"✅ Разбан записан в БД: {user_id}")

            except Exception as e:
                logger.error(f" Ошибка записи разбана в БД: {e}")

            logger.info(f"Пользователь {user_id} разбанен в {chat_id}")

            # Используем имя пользователя в сообщении
            return True, ResponseTexts.get_unban_success(user_info)

        except BadRequest as e:
            error_msg = str(e)
            if "USER_NOT_PARTICIPANT" in error_msg or "User not found" in error_msg:
                logger.info(f"Пользователь {user_id} не является участником чата {chat_id}")
                return True, "Пользователь не найден в чате"
            elif "Not enough rights" in error_msg or "CHAT_ADMIN_REQUIRED" in error_msg:
                logger.warning(f"Недостаточно прав для разбана {user_id} в {chat_id}")
                return False, "Недостаточно прав у бота"
            else:
                logger.error(f"Ошибка разбана: {e}")
                return False, f"Ошибка: {error_msg[:100]}"
        except Exception as e:
            logger.error(f"Ошибка разбана: {e}")
            return False, ResponseTexts.ERROR_GENERAL

    async def kick_user(self, chat_id: int, user_id: int, admin_id: int,
                        reason: str = "Без причины") -> Tuple[bool, str]:
        """Кикает пользователя (может вернуться). Возвращает (успех, сообщение)"""
        if not self.bot:
            return False, ResponseTexts.ERROR_GENERAL

        try:
            # Проверка админа цели
            if await self.is_chat_admin(user_id, chat_id):
                logger.warning(f"Попытка кика админа чата {user_id}")
                return False, ResponseTexts.ERROR_ADMIN_TARGET

            # Получаем информацию о пользователе для отображения
            user_info = await self._get_user_info_for_message(chat_id, user_id)

            # Сначала разбаниваем если забанен
            try:
                await self.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
            except:
                pass

            # Кикаем (удаляем) пользователя без бана
            await self.bot.kick_chat_member(chat_id, user_id)
            # Моментально разрешаем вернуться
            await asyncio.sleep(0.1)
            await self.bot.unban_chat_member(chat_id, user_id)

            # === ЛОГИРОВАНИЕ В БАЗУ ДАННЫХ ===
            try:
                db = next(get_db())

                ModerationLogRepository.add_moderation_log(
                    db=db,
                    user_id=user_id,
                    admin_id=admin_id,
                    action_type="kick",
                    duration=None,
                    reason=reason,
                    chat_id=chat_id
                )

                db.close()
                logger.info(f"✅ Кик записан в БД: {user_id}")

            except Exception as e:
                logger.error(f" Ошибка записи кика в БД: {e}")

            logger.info(f"Пользователь {user_id} кикнут из {chat_id}")

            # Используем имя пользователя в сообщении
            return True, ResponseTexts.get_kick_success(user_info)

        except BadRequest as e:
            if "User is an administrator of the chat" in str(e):
                logger.warning(f"Не удалось кикнуть админа чата {user_id}")
                return False, ResponseTexts.ERROR_ADMIN_TARGET
            logger.error(f"Ошибка кика: {e}")
            return False, ResponseTexts.ERROR_GENERAL
        except Exception as e:
            logger.error(f"Ошибка кика: {e}")
            return False, ResponseTexts.ERROR_GENERAL

    # ===== БАН В БОТЕ =====

    async def check_bot_ban(self, user_id: int) -> bool:
        """Проверяет бан в боте"""
        return self.bot_ban_manager.is_user_bot_banned(user_id)

    async def ban_in_bot(self, user_id: int, admin_id: int,
                         reason: str = "Не указана", seconds: int = None) -> Tuple[bool, str]:
        """Банит пользователя в боте. Возвращает (успех, сообщение)"""
        # Проверяем, не пытаемся ли забанить админа бота
        if await self._is_bot_admin(user_id):
            logger.warning(f"Попытка бана админа бота: {user_id}")
            return False, ResponseTexts.ERROR_CANT_BAN_BOT_ADMIN

        # Получаем информацию о пользователе
        user_info = await self._get_user_info_by_id(user_id)

        success = await self.bot_ban_manager.ban_user_in_bot(user_id, admin_id, reason, seconds)

        if success:
            # === ЛОГИРОВАНИЕ В БАЗУ ДАННЫХ ===
            try:
                db = next(get_db())

                ModerationLogRepository.add_moderation_log(
                    db=db,
                    user_id=user_id,
                    admin_id=admin_id,
                    action_type="botban",
                    duration=seconds,
                    reason=reason,
                    chat_id=None  # Бан в боте, не в чате
                )

                db.close()
                logger.info(f"✅ Бан в боте записан в БД: {user_id}")

            except Exception as e:
                logger.error(f" Ошибка записи бана в боте в БД: {e}")

            # Формируем сообщение с именем пользователя
            time_text = "всегда"
            if seconds:
                minutes = seconds // 60
                time_text = self._format_duration(minutes, "m") if minutes > 0 else self._format_duration(seconds, "s")

            return True, ResponseTexts.get_botban_success(time_text, user_info)

        return False, ResponseTexts.ERROR_GENERAL

    async def unban_in_bot(self, user_id: int) -> Tuple[bool, str]:
        """Разбанивает пользователя в боте. Возвращает (успех, сообщение)"""
        # Получаем информацию о пользователе
        user_info = await self._get_user_info_by_id(user_id)

        success = await self.bot_ban_manager.unban_user_in_bot(user_id)

        if success:
            # === ЛОГИРОВАНИЕ В БАЗУ ДАННЫХ ===
            try:
                db = next(get_db())

                # Для разбана нужен admin_id, берем из последнего бана
                ban_info = self.bot_ban_manager.get_ban_info(user_id)
                admin_id = ban_info.get('admin_id') if ban_info else 0

                ModerationLogRepository.add_moderation_log(
                    db=db,
                    user_id=user_id,
                    admin_id=admin_id,
                    action_type="botunban",
                    duration=None,
                    reason="Ручной разбан",
                    chat_id=None
                )

                db.close()
                logger.info(f"✅ Разбан в боте записан в БД: {user_id}")

            except Exception as e:
                logger.error(f" Ошибка записи разбана в боте в БД: {e}")

            return True, ResponseTexts.get_botunban_success(user_info)

        return False, "Пользователь не был забанен в боте"

    async def restore_mutes_after_restart(self):
        """Восстанавливает муты после перезапуска из базы данных"""
        logger.info("🔄 Восстановление мутов после перезапуска")

        try:
            db = next(get_db())

            # Получаем ВСЕ активные муты (без фильтра по chat_id)
            active_mutes = ActiveMuteRepository.get_chat_active_mutes(db)

            for mute in active_mutes:
                chat_id = mute.chat_id
                user_id = mute.user_id

                # Проверяем не истек ли мут
                if mute.muted_until < datetime.utcnow():
                    continue  # Пропускаем истекшие

                if chat_id not in self.active_mutes:
                    self.active_mutes[chat_id] = {}

                self.active_mutes[chat_id][user_id] = mute.muted_until
                logger.info(f"✅ Восстановлен мут: {user_id} в {chat_id} до {mute.muted_until}")

            logger.info(f"✅ Восстановлено {len(active_mutes)} активных мутов из БД")
            db.close()

        except Exception as e:
            logger.error(f" Ошибка восстановления мутов: {e}")
            try:
                db.close()
            except:
                pass

    async def get_bot_ban_info(self, user_id: int) -> Optional[Dict]:
        """Получает информацию о бане пользователя в боте"""
        return self.bot_ban_manager.get_ban_info(user_id)

    # ===== УТИЛИТЫ =====

    TIME_MULTIPLIERS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}

    def parse_time(self, text: str) -> Optional[dict]:
        """Парсит время из строки"""
        if not text:
            return None

        text = text.lower().strip()

        # Если просто число, считаем что это минуты
        if text.isdigit():
            value = int(text)
            seconds = value * 60  # минуты по умолчанию
            time_text = self._format_duration(value, "m")
            return {'seconds': seconds, 'text': time_text, 'minutes': value, 'unit': 'm'}

        ru_to_en = {'с': 's', 'м': 'm', 'ч': 'h', 'д': 'd', 'н': 'w'}

        for ru, en in ru_to_en.items():
            text = text.replace(ru, en)

        match = re.match(r"^(\d+)([smhdw]?)$", text)
        if not match:
            return None

        value, unit = match.groups()
        value = int(value)

        if not unit:
            unit = 'm'  # По умолчанию минуты

        if unit not in self.TIME_MULTIPLIERS:
            return None

        seconds = value * self.TIME_MULTIPLIERS[unit]
        seconds = min(seconds, 315360000)  # Макс 10 лет

        # Форматируем для отображения
        time_text = self._format_duration(value, unit)

        return {'seconds': seconds, 'text': time_text, 'value': value, 'unit': unit}

    def _format_duration(self, value: int, unit: str = "m") -> str:
        """Форматирует длительность для отображения"""
        unit_display = {
            's': ['секунда', 'секунды', 'секунд'],
            'm': ['минута', 'минуты', 'минут'],
            'h': ['час', 'часа', 'часов'],
            'd': ['день', 'дня', 'дней'],
            'w': ['неделя', 'недели', 'недель']
        }

        if unit not in unit_display:
            return f"{value} мин"

        forms = unit_display[unit]

        if value % 10 == 1 and value % 100 != 11:
            return f"{value} {forms[0]}"
        elif 2 <= value % 10 <= 4 and (value % 100 < 10 or value % 100 >= 20):
            return f"{value} {forms[1]}"
        else:
            return f"{value} {forms[2]}"

    def _extract_time_and_reason(self, text: str) -> Tuple[Optional[int], Optional[str], str]:
        """Извлекает время и причину из текста"""
        if not text:
            return None, None, "Не указана"

        parts = text.strip().split()
        if not parts:
            return None, None, "Не указана"

        # Пробуем распарсить первое слово как время
        time_data = self.parse_time(parts[0])

        if time_data:
            seconds = time_data['seconds']
            time_text = time_data['text']
            reason = ' '.join(parts[1:]) if len(parts) > 1 else "Не указана"
            return seconds, time_text, reason
        else:
            # Если первое слово не время, то всё - причина
            return None, None, text

    # ===== ФОНОВЫЕ ЗАДАЧИ =====

    def start_cleanup_tasks(self):
        """Запускает фоновые задачи"""
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._unmute_scheduler())
        self.bot_ban_manager.start_cleanup_task()

        # Запускаем очистку БД при старте
        asyncio.create_task(self._db_cleanup_task())

    async def stop_cleanup_tasks(self):
        """Останавливает фоновые задачи"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        await self.bot_ban_manager.stop_cleanup_task()

    async def _unmute_scheduler(self):
        """Автоматический размут с обновлением БД"""
        while True:
            try:
                now = datetime.utcnow()
                to_remove = []

                for chat_id, mutes in list(self.active_mutes.items()):
                    for user_id, unmute_time in list(mutes.items()):
                        if now >= unmute_time:
                            try:
                                # Проверяем, замучен ли еще пользователь
                                mute_status = await self._check_user_mute_status(chat_id, user_id)
                                if mute_status is True:
                                    perms = types.ChatPermissions(
                                        can_send_messages=True,
                                        can_send_media_messages=True,
                                        can_send_other_messages=True,
                                        can_add_web_page_previews=True
                                    )
                                    await self.bot.restrict_chat_member(chat_id, user_id, perms)

                                    # Удаляем из БД
                                    try:
                                        db = next(get_db())
                                        ActiveMuteRepository.remove_active_mute(db, user_id, chat_id)
                                        db.close()
                                    except Exception as db_error:
                                        logger.error(f"Ошибка удаления мута из БД: {db_error}")

                                    logger.info(f"Автоматический анмут {user_id} в {chat_id}")
                                else:
                                    logger.info(f"Пользователь {user_id} уже не замучен, пропускаем авторазмут")
                            except Exception as e:
                                logger.warning(f"Не удалось размутить {user_id} в {chat_id}: {e}")
                            to_remove.append((chat_id, user_id))

                for chat_id, user_id in to_remove:
                    self.active_mutes[chat_id].pop(user_id, None)
                    if not self.active_mutes[chat_id]:
                        self.active_mutes.pop(chat_id, None)

                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                await asyncio.sleep(60)

    async def _db_cleanup_task(self):
        """Фоновая задача очистки БД"""
        while True:
            try:
                db = next(get_db())

                # Очищаем истекшие муты
                deleted_mutes = ActiveMuteRepository.cleanup_expired_mutes(db)
                if deleted_mutes > 0:
                    logger.info(f"Очищено {deleted_mutes} истекших мутов из БД")

                db.close()
                await asyncio.sleep(3600)  # Проверяем каждый час

            except Exception as e:
                logger.error(f"Ошибка в задаче очистки БД: {e}")
                await asyncio.sleep(3600)

    async def check_user_balance_for_paid_mute(self, user_id: int) -> Tuple[bool, int]:
        """Проверяет баланс пользователя для платного мута"""
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if user:
                has_enough = user.coins >= PAID_MUTE_COST
                current_balance = user.coins
                db.close()
                return has_enough, current_balance
            db.close()
            return False, 0
        except Exception as e:
            logger.error(f"Ошибка проверки баланса: {e}")
            return False, 0

    async def process_paid_mute(self, from_user_id: int, target_user_id: int, chat_id: int) -> Tuple[bool, str]:
        """Обрабатывает платный мут"""
        if not self.bot:
            return False, "Ошибка бота"

        try:
            # 1. Проверяем баланс
            has_enough, current_balance = await self.check_user_balance_for_paid_mute(from_user_id)

            if not has_enough:
                needed = PAID_MUTE_COST - current_balance
                return False, f"Недостаточно Монет для применения мут-команды (нужно 200 000 000).\nУ вас: {format_number(current_balance)}\nНе хватает: {format_number(needed)}"

            # 2. Снимаем Монеты
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, from_user_id)
            if user:
                new_balance = user.coins - PAID_MUTE_COST
                UserRepository.update_user_balance(db, from_user_id, new_balance)

                # Создаем транзакцию
                TransactionRepository.create_transaction(
                    db=db,
                    from_user_id=from_user_id,
                    to_user_id=None,
                    amount=PAID_MUTE_COST,
                    description="платный мут"
                )
                db.commit()

            db.close()

            # 3. Мутим пользователя
            success, mute_message = await self.mute_user(
                chat_id=chat_id,
                user_id=target_user_id,
                admin_id=from_user_id,
                duration_minutes=PAID_MUTE_DURATION_MINUTES,
                reason="Платный мут"
            )

            if success:
                # 4. Формируем сообщение об успехе
                from_user = await self.bot.get_chat(from_user_id)
                target_user = await self.bot.get_chat(target_user_id)

                result_message = (
                    f"💸 <b>Платный мут применен!</b>\n"
                    f"👤 {target_user.mention if hasattr(target_user, 'mention') else f'@{target_user.username}' if target_user.username else target_user.first_name} получил мут на {PAID_MUTE_DURATION_MINUTES} минуту от {from_user.mention if hasattr(from_user, 'mention') else f'@{from_user.username}' if from_user.username else from_user.first_name}\n"
                    f"💰 Списано: {format_number(PAID_MUTE_COST)} Монет\n"
                )
                return True, result_message

            else:
                # 5. Возвращаем деньги если не удалось замутить
                db = next(get_db())
                UserRepository.update_user_balance(db, from_user_id, current_balance)
                db.commit()
                db.close()
                return False, f"Не удалось применить мут: {mute_message}"

        except Exception as e:
            logger.error(f"Ошибка платного мута: {e}")
            return False, "Произошла ошибка при обработке платного мута"


# Глобальный экземпляр
mute_ban_manager = MuteBanManager()


# ===== ОБРАБОТЧИКИ КОМАНД =====

def format_number(number: int) -> str:
    """Форматирует число с разделителями"""
    return f"{number:,}".replace(",", " ")


async def cmd_mute(message: types.Message):
    """Обработчик команды /mute"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS, parse_mode="HTML")
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    # Проверка цели
    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user

    # Проверка админа цели
    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET, parse_mode="HTML")
        return

    # Парсинг времени из аргументов
    args = message.get_args()
    duration_minutes = 30  # По умолчанию 30 минут

    if args:
        time_data = mute_ban_manager.parse_time(args)
        if time_data:
            duration_minutes = time_data['seconds'] // 60
            if duration_minutes < 1:
                duration_minutes = 1  # Минимум 1 минута
            logger.info(f"Парсинг времени '{args}': {duration_minutes} минут")
        else:
            logger.warning(f"Не удалось распарсить время из '{args}'")

    # Выполнение мута
    success, result_message = await mute_ban_manager.mute_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        duration_minutes=duration_minutes,
        reason="Модерация"
    )

    await message.answer(result_message, parse_mode="HTML")


async def cmd_unmute(message: types.Message):
    """Обработчик команды /unmute"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS, parse_mode="HTML")
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user

    # Размучиваем
    success, result_message = await mute_ban_manager.unmute_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id
    )

    await message.answer(result_message, parse_mode="HTML")


async def cmd_ban(message: types.Message):
    """Обработчик команды /ban"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS, parse_mode="HTML")
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET, parse_mode="HTML")
        return

    success, result_message = await mute_ban_manager.ban_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        reason="Модерация"
    )

    await message.answer(result_message, parse_mode="HTML")


async def cmd_unban(message: types.Message):
    """Обработчик команды /unban"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS, parse_mode="HTML")
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    # Получаем user_id из аргументов или reply
    user_id = None

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        args = message.get_args()
        if args:
            try:
                user_id = int(args)
            except ValueError:
                await message.answer(" Укажите ID пользователя или ответьте на сообщение!", parse_mode="HTML")
                return

    if not user_id:
        await message.answer(" Укажите ID пользователя или ответьте на сообщение!", parse_mode="HTML")
        return

    success, result_message = await mute_ban_manager.unban_user(
        chat_id=message.chat.id,
        user_id=user_id,
        admin_id=message.from_user.id
    )

    await message.answer(result_message, parse_mode="HTML")


async def cmd_kick(message: types.Message):
    """Обработчик команды /kick"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS, parse_mode="HTML")
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET, parse_mode="HTML")
        return

    success, result_message = await mute_ban_manager.kick_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        reason="Модерация"
    )

    await message.answer(result_message, parse_mode="HTML")


async def cmd_botban(message: types.Message):
    """Обработчик команды /botban - только для админов бота"""
    # Проверяем что пользователь админ бота
    if not await mute_ban_manager._check_bot_admin(message):
        await message.answer(ResponseTexts.ERROR_BOT_ADMIN_ONLY, parse_mode="HTML")
        return

    args = message.get_args()

    # Получение пользователя
    user_id = None
    user_name = "Пользователь"

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_name = message.reply_to_message.from_user.full_name or f"ID {user_id}"
    elif args:
        parts = args.split()
        try:
            user_id = int(parts[0])
            user_name = f"ID {user_id}"
            args = ' '.join(parts[1:]) if len(parts) > 1 else ""
        except ValueError:
            await message.answer(" Укажите ID пользователя или ответьте на сообщение!", parse_mode="HTML")
            return
    else:
        await message.answer(" Использование: /botban [ID/username] [время] [причина] или ответ на сообщение",
                             parse_mode="HTML")
        return

    # Проверка админа цели
    if await mute_ban_manager._is_bot_admin(user_id):
        await message.answer(ResponseTexts.ERROR_CANT_BAN_BOT_ADMIN, parse_mode="HTML")
        return

    # Парсинг времени и причины
    seconds = None
    time_text = "всегда"
    reason = "Не указана"

    if args:
        seconds, time_text, reason = mute_ban_manager._extract_time_and_reason(args)
        if not seconds:
            time_text = "всегда"

    # Бан в боте
    success, result_message = await mute_ban_manager.ban_in_bot(
        user_id=user_id,
        admin_id=message.from_user.id,
        reason=reason,
        seconds=seconds
    )

    await message.answer(result_message, parse_mode="HTML")


async def cmd_botunban(message: types.Message):
    """Обработчик команды /botunban - только для админов бота"""
    # Проверяем что пользователь админ бота
    if not await mute_ban_manager._check_bot_admin(message):
        await message.answer(ResponseTexts.ERROR_BOT_ADMIN_ONLY, parse_mode="HTML")
        return

    args = message.get_args()

    # Получение пользователя
    user_id = None

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    elif args:
        try:
            user_id = int(args.split()[0])
        except ValueError:
            await message.answer(" Укажите ID пользователя или ответьте на сообщение!", parse_mode="HTML")
            return
    else:
        await message.answer(" Использование: /botunban [ID] или ответ на сообщение", parse_mode="HTML")
        return

    # Разбан в боте
    success, result_message = await mute_ban_manager.unban_in_bot(user_id)

    await message.answer(result_message, parse_mode="HTML")


# ===== ОБРАБОТЧИКИ ТЕКСТОВЫХ КОМАНД (с поддержкой времени) =====

async def text_mute(message: types.Message):
    """Текстовая команда 'мут' и её вариации с поддержкой времени"""
    if not message.text:
        return

    text = message.text.lower().strip()

    # Варианты команд для мута
    mute_commands = [
        'мут', '!мут',
        'чушш', '!чушш',
        'жап оозунду', '!жап оозунду',
        'стяни ебло', '!стяни ебло',
        'ĸолл', '!ĸолл'
    ]

    # Проверяем начинается ли текст с любой из команд
    command = None
    for cmd in mute_commands:
        if text.startswith(cmd):
            command = cmd
            break

    if not command:
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET, parse_mode="HTML")
        return

    # Извлекаем время из команды
    duration_minutes = 30  # По умолчанию 30 минут

    # Убираем команду из текста
    remaining_text = text[len(command):].strip()

    if remaining_text:
        time_data = mute_ban_manager.parse_time(remaining_text)
        if time_data:
            duration_minutes = time_data['seconds'] // 60
            if duration_minutes < 1:
                duration_minutes = 1
            logger.info(f"Текстовая команда мут '{command}' время '{remaining_text}': {duration_minutes} минут")
        else:
            logger.warning(f"Не удалось распарсить время из текстовой команды '{remaining_text}'")

    success, result_message = await mute_ban_manager.mute_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        duration_minutes=duration_minutes,
        reason="Модерация"
    )

    await message.answer(result_message, parse_mode="HTML")


async def text_unmute(message: types.Message):
    """Текстовая команда 'размут' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'размут':
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user

    # Размучиваем
    success, result_message = await mute_ban_manager.unmute_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id
    )

    await message.answer(result_message, parse_mode="HTML")


async def text_ban(message: types.Message):
    """Текстовая команда 'бан' и её вариации"""
    if not message.text:
        return

    text = message.text.lower().strip()

    # Варианты команд для бана (точное совпадение)
    ban_commands = [
        'бан', '!бан',
        'сигил', '!сигил',
        'иди нахуй', '!иди нахуй',
        'пшлнх', '!пшлнх'
    ]

    if text not in ban_commands:
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET, parse_mode="HTML")
        return

    success, result_message = await mute_ban_manager.ban_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        reason="Модерация"
    )

    await message.answer(result_message, parse_mode="HTML")


async def text_unban(message: types.Message):
    """Текстовая команда 'разбан' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'разбан':
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    # Для команды "разбан" только точное слово - нужно reply
    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    user_id = message.reply_to_message.from_user.id

    success, result_message = await mute_ban_manager.unban_user(
        chat_id=message.chat.id,
        user_id=user_id,
        admin_id=message.from_user.id
    )

    await message.answer(result_message, parse_mode="HTML")


async def text_kick(message: types.Message):
    """Текстовая команда 'кик' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'кик':
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS, parse_mode="HTML")
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET, parse_mode="HTML")
        return

    success, result_message = await mute_ban_manager.kick_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        reason="Модерация"
    )

    await message.answer(result_message, parse_mode="HTML")


async def text_botban(message: types.Message):
    """Текстовая команда 'ботбан' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'ботбан':
        return

    # Проверяем что пользователь админ бота
    if not await mute_ban_manager._check_bot_admin(message):
        await message.answer(ResponseTexts.ERROR_BOT_ADMIN_ONLY, parse_mode="HTML")
        return

    # Для команды "ботбан" только точное слово - нужно reply
    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    user_id = message.reply_to_message.from_user.id
    user_name = message.reply_to_message.from_user.full_name or f"ID {user_id}"

    # Проверка админа цели
    if await mute_ban_manager._is_bot_admin(user_id):
        await message.answer(ResponseTexts.ERROR_CANT_BAN_BOT_ADMIN, parse_mode="HTML")
        return

    # Бан в боте навсегда (без времени)
    success, result_message = await mute_ban_manager.ban_in_bot(
        user_id=user_id,
        admin_id=message.from_user.id,
        reason="Команда ботбан",
        seconds=None
    )

    await message.answer(result_message, parse_mode="HTML")


async def text_botunban(message: types.Message):
    """Текстовая команда 'разботбан' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'разботбан':
        return

    # Проверяем что пользователь админ бота
    if not await mute_ban_manager._check_bot_admin(message):
        await message.answer(ResponseTexts.ERROR_BOT_ADMIN_ONLY, parse_mode="HTML")
        return

    # Для команды "разботбан" только точное слово - нужно reply
    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY, parse_mode="HTML")
        return

    user_id = message.reply_to_message.from_user.id

    # Разбан в боте
    success, result_message = await mute_ban_manager.unban_in_bot(user_id)

    await message.answer(result_message, parse_mode="HTML")


# ===== ОБРАБОТЧИКИ ПЛАТНОГО МУТА =====

async def cmd_paid_mute(message: types.Message):
    """Обработчик команды !!мут"""
    if not message.text or not message.text.startswith('!!'):
        return

    # Проверяем что это команда платного мута
    if message.text.lower().strip() not in ['!!мут', '!!помолчи']:
        return

    # Проверяем что команда в чате
    if message.chat.type == 'private':
        await message.answer(" Эта команда работает только в чатах!", parse_mode="HTML")
        return

    # Проверяем что ответ на сообщение
    if not message.reply_to_message:
        await message.answer(" Ответьте на сообщение пользователя, которого хотите замутить!", parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user
    from_user = message.from_user

    # Проверяем что не мутим самого себя
    if target_user.id == from_user.id:
        await message.answer(" Нельзя замутить самого себя!", parse_mode="HTML")
        return

    # Проверяем что не мутим админов
    if await mute_ban_manager.is_chat_admin(target_user.id, message.chat.id):
        await message.answer(" Нельзя мутить администраторов чата!", parse_mode="HTML")
        return

    # Проверяем права бота
    if not await mute_ban_manager._check_bot_permissions(message.chat.id):
        await message.answer(" У бота недостаточно прав для модерации!", parse_mode="HTML")
        return

    # Проверяем что пользователь не админ чата (если не глобальный админ)
    if not mute_ban_manager.is_global_admin(from_user.id):
        if await mute_ban_manager.is_chat_admin(from_user.id, message.chat.id):
            await message.answer(" Администраторы чата не могут использовать платный мут!", parse_mode="HTML")
            return

    # Обрабатываем платный мут
    success, result_message = await mute_ban_manager.process_paid_mute(
        from_user_id=from_user.id,
        target_user_id=target_user.id,
        chat_id=message.chat.id
    )

    await message.answer(result_message, parse_mode="HTML")


# Также добавьте текстовый обработчик для платного мута
async def text_paid_mute(message: types.Message):
    """Текстовый обработчик для !!мут и !!помолчи"""
    if not message.text:
        return

    text = message.text.lower().strip()

    # Проверяем команды платного мута
    paid_mute_commands = ['!!мут', '!!помолчи']

    if text in paid_mute_commands:
        # Вызываем тот же обработчик что и для команд
        await cmd_paid_mute(message)


# ===== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ =====

def register_handlers(dp: Dispatcher):
    """Регистрирует все обработчики"""

    # Проверяем, есть ли бот в менеджере
    if not mute_ban_manager.bot and dp.bot:
        mute_ban_manager.set_bot(dp.bot)
        logger.info("✅ Бот установлен в MuteBanManager при регистрации обработчиков")

    # Слеш-команды (английские)
    dp.register_message_handler(cmd_mute, Command("mute"))
    dp.register_message_handler(cmd_unmute, Command("unmute"))
    dp.register_message_handler(cmd_ban, Command("ban"))
    dp.register_message_handler(cmd_unban, Command("unban"))
    dp.register_message_handler(cmd_kick, Command("kick"))
    dp.register_message_handler(cmd_botban, Command("botban"))
    dp.register_message_handler(cmd_botunban, Command("botunban"))

    # Слеш-команды (русские)
    dp.register_message_handler(cmd_mute, commands=["мут"])
    dp.register_message_handler(cmd_unmute, commands=["размут"])
    dp.register_message_handler(cmd_ban, commands=["бан"])
    dp.register_message_handler(cmd_unban, commands=["разбан"])
    dp.register_message_handler(cmd_kick, commands=["кик"])
    dp.register_message_handler(cmd_botban, commands=["ботбан"])
    dp.register_message_handler(cmd_botunban, commands=["разботбан"])

    # Для "мут" с поддержкой времени (все варианты с ! и без !)
    def check_mute_commands(message):
        if not message.text:
            return False

        text = message.text.lower().strip()

        # Варианты команд для мута
        mute_commands = [
            'мут', '!мут',
            'чушш', '!чушш',
            'жап оозунду', '!жап оозунду',
            'стяни ебло', '!стяни ебло',
            'ĸолл', '!ĸолл'
        ]

        # Проверяем начинается ли текст с любой из команд (с поддержкой времени после команды)
        for cmd in mute_commands:
            if text.startswith(cmd):
                return True
        return False

    dp.register_message_handler(text_mute, check_mute_commands)

    # Для команды "бан" - несколько вариантов текстовых команд (с ! и без !)
    def check_ban_commands(message):
        if not message.text:
            return False

        text = message.text.lower().strip()

        # Варианты команд для бана (точное совпадение)
        ban_commands = [
            'бан', '!бан',
            'сигил', '!сигил',
            'иди нахуй', '!иди нахуй',
            'пшлнх', '!пшлнх'
        ]

        return text in ban_commands

    dp.register_message_handler(text_ban, check_ban_commands)

    # Для остальных команд - только точное слово (с ! и без !)
    dp.register_message_handler(text_unmute, lambda m: m.text and m.text.lower().strip() in ['размут', '!размут'])
    dp.register_message_handler(text_unban, lambda m: m.text and m.text.lower().strip() in ['разбан', '!разбан'])
    dp.register_message_handler(text_kick, lambda m: m.text and m.text.lower().strip() in ['кик', '!кик'])
    dp.register_message_handler(text_botban, lambda m: m.text and m.text.lower().strip() in ['ботбан', '!ботбан'])
    dp.register_message_handler(text_botunban,
                                lambda m: m.text and m.text.lower().strip() in ['разботбан', '!разботбан'])

    # Команды платного мута
    dp.register_message_handler(cmd_paid_mute, lambda m: m.text and m.text.startswith('!!'))

    # Текстовые команды платного мута
    dp.register_message_handler(text_paid_mute, lambda m: m.text and m.text.lower().strip() in ['!!мут', '!!помолчи'])

    logger.info("✅ Обработчики модерации зарегистрированы (ботбан только для админов бота)")

    # Возвращаем mute_ban_manager для использования в middleware
    return mute_ban_manager


# Инициализация при импорте
try:
    from config import dp, bot

    if bot:
        mute_ban_manager.set_bot(bot)
        logger.info("✅ Бот установлен в MuteBanManager через config")

    logger.info("✅ MuteBanManager готов к использованию")
except ImportError:
    logger.warning("⚠️ Не удалось импортировать из config в handlers/mute_ban.py")
    logger.warning("⚠️ Инициализация будет выполнена позже при регистрации обработчиков")
except Exception as e:
    logger.error(f" Ошибка инициализации mute_ban: {e}")