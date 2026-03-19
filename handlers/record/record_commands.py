import re
import logging
from aiogram import types, Dispatcher

from .record_core import RecordCore
from .top_handlers import TopHandlers
from .services import RecordService
from .auto_top_middleware import AutoTopMiddleware


class RecordCommands:
    """Команды для работы с рекордами"""

    def __init__(self):
        self.core = RecordCore()
        self.top_handlers = TopHandlers(self.core)
        self.service = RecordService(self.core)
        self.logger = logging.getLogger(__name__)

    # =============================================
    # 🔥 ГЛОБАЛЬНЫЕ РЕКОРДЫ ДНЯ
    # =============================================

    async def check_daily_record(self, message: types.Message):
        """Показывает глобальный рекорд дня - 1 выигрыш + 1 проигрыш (только рулетка)"""
        try:
            user_id = message.from_user.id
            username = message.from_user.username
            first_name = message.from_user.first_name

            await self.core.ensure_user_registered(user_id, 0, username, first_name)

            # Получаем 1 лучший выигрыш и 1 лучший проигрыш (только рулетка)
            top_win = self.core._get_global_top_wins_today(1)  # 1 место выигрыша
            top_loss = self.core._get_global_top_losses_today(1)  # 1 место проигрыша

            # Получаем текущую дату
            from datetime import datetime
            current_date = datetime.now().strftime("%d.%m.%Y")

            reply_text = f"<b>Рекорды дня в рулетку:</b> {current_date}\n\n"

            # 🔥 ПЕРВОЕ МЕСТО - выигрыш
            if top_win:
                user_id1, clickable_name1, amount1 = top_win[0]  # УЖЕ кликабельное имя
                reply_text += f"{clickable_name1} <b>выиграл</b> {amount1:,} монет\n"
            else:
                reply_text += "Пока нет рекорда выигрыша\n"

            # 🔥 ПЕРВОЕ МЕСТО - проигрыш
            if top_loss:
                loss_user_id, clickable_loss_name, loss_amount = top_loss[0]  # УЖЕ кликабельное имя
                reply_text += f"{clickable_loss_name} <b>проиграл</b> {loss_amount:,} монет\n"
            else:
                reply_text += "Пока нет рекорда проигрыша\n"

            await message.reply(reply_text, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            self.logger.error(f"Error in check_daily_record: {e}")
            await message.reply(" Ошибка при получении рекордов.")

    # =============================================
    # 🎯 ОБРАБОТЧИК КОМАНДЫ ТОП
    # =============================================

    async def handle_top_command(self, message: types.Message):
        """Обработчик всех вариантов команды топ"""
        await self.top_handlers.show_rich_top(message)


# =============================================
# 📋 РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# =============================================

def register_record_handlers(dp: Dispatcher, record_service: RecordService = None):
    """Регистрация всех обработчиков записей"""
    handler = RecordCommands()

    # Если передан record_service, используем его
    if record_service:
        handler.service = record_service

    # Регистрируем middleware для авто-регистрации в топе
    auto_top_middleware = AutoTopMiddleware()
    dp.middleware.setup(auto_top_middleware)
    handler.logger.info("✅ AutoTopMiddleware зарегистрирован")

    # 🔥 РЕКОРДЫ ДНЯ (доступны всем)
    dp.register_message_handler(
        handler.check_daily_record,
        commands=['record', 'рекорд_дня', 'рекорддня', 'рекорд'],
        commands_prefix='!/'
    )
    dp.register_message_handler(
        handler.check_daily_record,
        lambda m: m.text and re.match(r'^(рекорд(\s*дня)?|record)$', m.text.lower().strip())
    )

    # 🏅 ОБРАБОТЧИКИ КОМАНДЫ ТОП (основное меню) - доступны всем
    dp.register_message_handler(
        handler.handle_top_command,
        commands=['top', 'топ'],
        commands_prefix='!/'
    )
    dp.register_message_handler(
        handler.handle_top_command,
        lambda m: m.text and re.match(r'^(топ|top)\s*\d*$', m.text.lower().strip())
    )

    # 🔘 CALLBACK'И ДЛЯ ИНТЕРАКТИВНЫХ КНОПОК
    dp.register_callback_query_handler(
        handler.top_handlers.handle_top_callback,
        lambda c: c.data.startswith('top_') or c.data.endswith('_top_back')
    )

    handler.logger.info("✅ Обработчики записей зарегистрированы")