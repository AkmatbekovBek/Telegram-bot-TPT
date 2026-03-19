import logging
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware

from .services import RecordService
from .record_core import RecordCore


class AutoTopMiddleware(BaseMiddleware):
    """Middleware для автоматической регистрации пользователей в топе"""

    def __init__(self):
        self.core = RecordCore()
        self.service = RecordService(self.core)
        self.logger = logging.getLogger(__name__)
        super().__init__()

    async def on_pre_process_message(self, message: types.Message, data: dict):
        """Автоматически регистрирует пользователя в топе при ЛЮБОМ сообщении"""
        try:
            # Пропускаем служебные сообщения и команды
            if not message.from_user:
                return

            # Пропускаем команды, чтобы не дублировать регистрацию
            if message.text and message.text.startswith('/'):
                return

            user_id = message.from_user.id
            chat_id = message.chat.id
            username = message.from_user.username
            first_name = message.from_user.first_name

            # Автоматическая регистрация в топе
            await self.service.auto_register_user_in_top(user_id, chat_id, username, first_name)

        except Exception as e:
            self.logger.error(f"Error in AutoTopMiddleware: {e}")