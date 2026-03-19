import logging
from typing import List
from aiogram.dispatcher.handler import SkipHandler
from aiogram import types
from aiogram.dispatcher import Dispatcher
from database import SessionLocal
from database.chat_activity import ChatActivityRepository

logger = logging.getLogger(__name__)


class ChatActivityHandler:
    """Обработчик активности в чатах"""

    def __init__(self):
        # Импортируем UserFormatter из start.py
        from handlers.start import UserFormatter
        self.user_formatter = UserFormatter()

    async def track_message(self, message: types.Message):
        """Отслеживание сообщений пользователей"""
        # Не отслеживаем служебные сообщения и команды
        if not message.text:
            return

        # Пропускаем команду магазин, чтобы ее обработал другой хендлер
        if message.text.lower().strip() in ['магазин', 'shop', 'маг']:
            raise SkipHandler()

        if message.text.startswith('!'):
            raise SkipHandler()

        # Отслеживаем только в группах/супергруппах
        if message.chat.type not in ['group', 'supergroup']:
            return

        user = message.from_user
        chat_id = message.chat.id

        db = SessionLocal()
        try:
            ChatActivityRepository.get_or_create(
                db=db,
                chat_id=chat_id,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name
            )
        except Exception as e:
            logger.error(f"Ошибка при отслеживании сообщения: {e}")
        finally:
            db.close()

    async def show_activity(self, message: types.Message):
        """Показ активности чата"""
        chat_id = message.chat.id
        user_id = message.from_user.id

        db = SessionLocal()
        try:
            # Получаем топ активных пользователей
            top_users = ChatActivityRepository.get_chat_top_active(db, chat_id, limit=10)

            if not top_users:
                await message.reply(
                    "📊 Статистика активности пуста.\n"
                    "Начните общаться, чтобы появилась статистика!",
                    parse_mode=types.ParseMode.HTML
                )
                return

            # Получаем общее количество сообщений
            total_messages = ChatActivityRepository.get_total_messages(db, chat_id)

            # Получаем место текущего пользователя в рейтинге
            user_position = ChatActivityRepository.get_user_position(db, chat_id, user_id)

            # Получаем количество сообщений текущего пользователя
            user_message_count = ChatActivityRepository.get_user_message_count(db, chat_id, user_id)

            # Формируем список пользователей
            user_lines = []
            for i, activity in enumerate(top_users, 1):
                # Форматируем имя пользователя
                if activity.first_name:
                    display_name = activity.first_name
                elif activity.username:
                    display_name = f"@{activity.username}"
                else:
                    display_name = f"User{activity.user_id}"

                # Создаем ссылку на пользователя
                user_link = self.user_formatter.get_user_link_html(
                    activity.user_id,
                    display_name
                )

                # Добавляем строку
                user_lines.append(
                    f"[{i}] {user_link}: {activity.message_count}"
                )

            # Формируем строку с местом текущего пользователя
            user_position_text = ""
            if user_position:
                # Всегда показываем место, даже если это 1000 или больше
                user_position_text = f"\n<b>Ваше место:</b> {user_position} ({user_message_count} сообщ.)"
            elif user_message_count > 0:
                # Если пользователь есть в базе, но не получил позицию (маловероятно)
                user_position_text = f"\n<b>Ваше место:</b> - ({user_message_count} сообщ.)"
            else:
                user_position_text = "\n<b>Ваше место:</b> пока нет сообщений"

            # Формируем итоговое сообщение
            activity_text = (
                "📊 <b>Активность чата</b>\n\n"
                f"{chr(10).join(user_lines)}"
                f"{user_position_text}\n\n"
                f"<b>Всего сообщений:</b> {total_messages}"
            )

            await message.reply(activity_text, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            logger.error(f"Ошибка при показе активности: {e}")
            await message.reply("Ошибка загрузки статистики")
        finally:
            db.close()

    async def reset_activity(self, message: types.Message):
        """Сброс статистики активности (только для админов)"""
        # Проверяем права администратора
        chat_member = await message.bot.get_chat_member(
            chat_id=message.chat.id,
            user_id=message.from_user.id
        )

        if chat_member.status not in ['creator', 'administrator']:
            await message.reply("Эта команда доступна только администраторам чата!")
            return

        db = SessionLocal()
        try:
            ChatActivityRepository.reset_chat_activity(db, message.chat.id)
            await message.reply("✅ Статистика активности сброшена!")
        except Exception as e:
            logger.error(f"Ошибка при сбросе статистики: {e}")
            await message.reply("Ошибка сброса статистики")
        finally:
            db.close()


def register_chat_activity_handlers(dp: Dispatcher):
    """Регистрация обработчиков активности чатов"""
    handler = ChatActivityHandler()

    # Текстовый обработчик команды !актив
    dp.register_message_handler(
        handler.show_activity,
        lambda message: message.text and message.text.strip().lower() == '!актив',
        state='*'
    )

    # Обработчик отслеживания сообщений
    dp.register_message_handler(
        handler.track_message,
        content_types=['text', 'photo', 'sticker', 'animation', 'document'],
        state='*'
    )

    # Команда сброса статистики
    dp.register_message_handler(
        handler.reset_activity,
        lambda message: message.text and message.text.strip().lower() == '!сброситьактив',
        state='*'
    )

    logging.info("✅ Обработчики активности чатов зарегистрированы")