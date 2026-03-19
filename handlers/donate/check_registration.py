"""
Регистрация обработчиков системы чеков
"""
import logging
from aiogram import Dispatcher
from aiogram.dispatcher.filters import Command

from .check_handler import CheckHandler, check_callback
from .check_states import CheckStates
from .check_config import ADMIN_IDS

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения обработчика
check_handler_instance = None

def register_check_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков системы чеков"""
    global check_handler_instance
    check_handler_instance = CheckHandler()

    # Команды для пользователей
    dp.register_message_handler(
        check_handler_instance.start_check_upload,
        commands=["чек", "check", "донатчек"],
        state="*"
    )

    # Отладочная команда
    dp.register_message_handler(
        check_handler_instance.debug_check_command,
        Command(commands=["debug_check"]),
        state="*"
    )

    # Callback обработчики для выбора типа покупки
    dp.register_callback_query_handler(
        check_handler_instance.handle_check_type_selection,
        lambda c: c.data.startswith("check_"),
        state=CheckStates.waiting_for_check_type
    )

    # Обработка ввода ID группы для снятия лимита рулетки
    dp.register_message_handler(
        check_handler_instance.handle_group_id_input,
        state=CheckStates.waiting_for_group_id
    )

    # Callback обработчики для выбора деталей покупки
    dp.register_callback_query_handler(
        check_handler_instance.handle_purchase_details_selection,
        lambda c: c.data.startswith(("coins_", "status_", "check_back")),
        state=CheckStates.waiting_for_check_details
    )

    # Обработка фото чеков
    dp.register_message_handler(
        check_handler_instance.handle_check_photo,
        content_types=["photo"],
        state=CheckStates.waiting_for_check_photo
    )

    dp.register_message_handler(
        check_handler_instance.check_status_command,
        commands=["check_status", "статусчека"],
        state="*"
    )

    dp.register_message_handler(
        check_handler_instance.check_history_command,
        commands=["check_history", "историячеков"],
        state="*"
    )

    # Callback обработчики для кнопок в админ-группе
    dp.register_callback_query_handler(
        check_handler_instance.handle_check_callback,
        check_callback.filter(),
        state="*"
    )

    # Админ-команды с фильтром
    async def admin_filter(message):
        """Фильтр для админ-команд"""
        is_admin = message.from_user.id in ADMIN_IDS
        return is_admin

    # Админ команды
    dp.register_message_handler(
        check_handler_instance.admin_checks_command,
        Command(commands=["чеки"]),
        admin_filter,
        state="*"
    )

    dp.register_message_handler(
        check_handler_instance.admin_logs_command,
        Command(commands=["логи"]),
        admin_filter,
        state="*"
    )

    dp.register_message_handler(
        check_handler_instance.admin_ban_command,
        Command(commands=["бан"]),
        admin_filter,
        state="*"
    )

    dp.register_message_handler(
        check_handler_instance.admin_unban_command,
        Command(commands=["разбан"]),
        admin_filter,
        state="*"
    )

    logger.info("✅ Система обработки чеков зарегистрирована")
    return check_handler_instance

async def stop_check_handler():
    """Останавливает обработчик чеков"""
    global check_handler_instance
    check_handler_instance = None
    logger.info("✅ Система чеков остановлена")