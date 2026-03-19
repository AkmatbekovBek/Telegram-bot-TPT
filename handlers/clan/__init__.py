# handlers/clan/__init__.py
from .clan_handler import register_clan_handlers, ClanHandler
from .clan_handler import register_clan_handlers, ClanHandler
from .clan_balance_updater import ClanBalanceUpdater

# Инициализация автообновления
clan_updater = ClanBalanceUpdater()

def start_clan_auto_updater():
    """Запустить автообновление кланов"""
    clan_updater.start()

def stop_clan_auto_updater():
    """Остановить автообновление кланов"""
    clan_updater.stop()

# Для обратной совместимости, можно оставить эти экспорты
__all__ = [
    'register_clan_handlers',
    'ClanHandler',
    'ClanBalanceUpdater',
    'start_clan_auto_updater',
    'stop_clan_auto_updater'
]


