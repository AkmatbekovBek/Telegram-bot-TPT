# handlers/modroul/__init__.py

import logging

logger = logging.getLogger(__name__)

# ИСПРАВЛЕННЫЕ ИМПОРТЫ - используем правильные имена файлов
from .bot_search_handler import BotSearchHandler, register_bot_search_handlers
from .bot_stop_handler import SimpleBotStopHandler, register_bot_stop_handlers
from .shop import ShopHandler, register_shop_handlers  # ИСПРАВЛЕНО: shop вместо shop_handler

# Реэкспорт основных функций
__all__ = [
    'BotSearchHandler',
    'SimpleBotStopHandler',
    'ShopHandler',
    'register_all_handlers',
]


def register_all_handlers(dp):
    """Регистрация всех обработчиков модуля"""
    try:
        logger.info("🔄 Начинаем регистрацию modroul обработчиков...")

        register_bot_search_handlers(dp)
        logger.info("✅ bot_search зарегистрирован")

        register_bot_stop_handlers(dp)
        logger.info("✅ bot_stop зарегистрирован")


        register_shop_handlers(dp)
        logger.info("✅ shop зарегистрирован")

        logger.info("✅ Все обработчики модуля modroul зарегистрированы")
        return True
    except Exception as e:
        logger.error(f" Ошибка регистрации обработчиков modroul: {e}")
        return False