from .admin_commands import register_donate_admin_commands, DonateAdminCommands
from .handlers import DonateHandler, register_donate_handlers
from .texts_simple import donate_texts
from .scheduler import DonateScheduler
from .check_handler import CheckHandler
from .check_repository import CheckRepository
from .check_registration import register_check_handlers, stop_check_handler

__all__ = [
    "DonateHandler",
    "CheckHandler",
    "CheckRepository",
    "register_donate_handlers",
    "register_check_handlers",  # Экспортируем функцию регистрации
    "stop_check_handler",       # Экспортируем функцию остановки
    "donate_texts",
    "DonateAdminCommands",
    "register_donate_admin_commands",
    "DonateScheduler",
]

donate_scheduler = None

async def start_donate_scheduler(bot):
    """Запускает планировщик доната"""
    global donate_scheduler
    donate_scheduler = DonateScheduler(bot)
    await donate_scheduler.start_scheduler()

async def stop_donate_scheduler():
    """Останавливает планировщик доната"""
    global donate_scheduler
    if donate_scheduler:
        await donate_scheduler.stop_scheduler()