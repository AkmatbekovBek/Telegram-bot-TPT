import asyncio
import logging
import signal
import sys
from sqlalchemy import text
from handlers.admin.mute_ban import register_handlers as register_mute_ban_handlers
from aiogram import executor, Dispatcher, types
from aiogram.types import AllowedUpdates
from handlers.clan import (
    register_clan_handlers,
    start_clan_auto_updater,
    stop_clan_auto_updater
)
from handlers.basket import register_basket_handlers
from handlers.donate import register_donate_admin_commands
from middlewares.auto_register_middleware import AutoRegisterMiddleware
from middlewares.bot_ban_middleware import BotBanMiddleware
from handlers.admin.link_texts_admin import register_link_texts_admin
from handlers.cleanup_scheduler import CleanupScheduler
from config import dp
from database import engine, SessionLocal
from database.models import Base
from middlewares.roulette_state_middleware import RouletteStateMiddleware
from handlers.slot.slot_handler import register_slot_handlers

# Импорты доната
from handlers.donate import (
    register_donate_handlers,
    start_donate_scheduler,
    stop_donate_scheduler
)

# Импорты системы чеков
from handlers.donate.check_registration import register_check_handlers, stop_check_handler

import os
import warnings

# Устанавливаем часовой пояс для Кыргызстана
os.environ['TZ'] = 'Asia/Bishkek'

# Игнорируем предупреждения tzlocal о несоответствии часовых поясов
warnings.filterwarnings("ignore", category=UserWarning, module="tzlocal")
warnings.filterwarnings("ignore", message="Timezone offset does not match system offset")

# Добавляем модуль чеков в список обработчиков
HANDLERS = [
    ("marriage", "register_marriage_handlers"),
    ("admin", "register_all_admin_handlers"),
    ("donate", "register_donate_handlers"),
    ("callback", "register_callback_handlers"),
    ("reference", "register_reference_handlers"),
    ("transfer", "register_transfer_handlers"),
    ("history_service", "register_history_handlers"),
    ("record", "register_record_handlers"),
    ("roulette", "register_all_roulette_handlers"),
    ("thief", "register_thief_handlers"),
    ("police", "register_police_handlers"),
    # ("slot", "register_slot_handlers"),
    ("chat_handlers", "register_chat_handlers"),
    ("admin.cleanup_handler", "register_cleanup_handlers"),
    ("raffle.raffle", "register_raffle_handlers"),
    ("chat_activity", "register_chat_activity_handlers"),
]

# Модули в папке modroul
MODROUL_HANDLERS = [
    ("modroul.shop", "register_shop_handlers"),
    ("modroul.bot_search_handler", "register_bot_search_handlers"),
    ("modroul.bot_stop_handler", "register_bot_stop_handlers"),
]

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Глобальные переменные
cleanup_scheduler = None
donate_scheduler = None


def setup_database() -> bool:
    """Настройка базы данных (синхронная)"""
    try:
        # Импортируем все модели
        from database.models import Base as MainBase
        from database.clan_models import Base as ClanBase
        # Импортируем ChatActivity, чтобы она зарегистрировалась в metadata
        from database.chat_activity import ChatActivity

        logger.info(f"📋 Tables to create: {MainBase.metadata.tables.keys()}")

        # Создаем таблицы для всех моделей
        MainBase.metadata.create_all(bind=engine)
        ClanBase.metadata.create_all(bind=engine)
        
        # Явно создаем таблицу chat_activity (на случай проблем с метаданными)
        try:
            ChatActivity.__table__.create(bind=engine, checkfirst=True)
            logger.info("✅ Таблица chat_activity проверена/создана явно")
        except Exception as e:
            logger.error(f" Ошибка явного создания chat_activity: {e}")

        logger.info("✅ Все таблицы базы данных созданы")

        # Проверяем подключение (синхронно) с использованием text()
        db = SessionLocal()
        try:
            db.expire_all()
            db.execute(text("SELECT 1"))
            db.commit()
            logger.info("✅ Подключение к базе данных установлено")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f" Ошибка проверки подключения к БД: {e}")
            return False
        finally:
            db.close()

    except Exception as e:
        logger.error(f" Ошибка настройки БД: {e}")
        return False


def cleanup_old_limits() -> None:
    """Очистка старых записей лимитов (синхронная)"""
    try:
        from database.crud import TransferLimitRepository

        db = SessionLocal()
        try:
            db.expire_all()
            deleted_count = TransferLimitRepository.clean_old_transfers(db)
            if deleted_count > 0:
                logger.info(f"✅ Очищено {deleted_count} старых записей лимитов")
            else:
                logger.info("✅ Старые записи лимитов не найдены")
        except Exception as e:
            logger.error(f" Ошибка при очистке лимитов: {e}")
            db.rollback()
        finally:
            db.close()

    except Exception as e:
        logger.error(f" Ошибка инициализации очистки лимитов: {e}")


async def setup_bot_ban_middleware(mute_ban_manager):
    """Настройка BotBanMiddleware после получения менеджера"""
    if mute_ban_manager:
        bot_ban_middleware = BotBanMiddleware(mute_ban_manager)
        dp.middleware.setup(bot_ban_middleware)
        logger.info("✅ BotBanMiddleware зарегистрирован")
        return True
    else:
        logger.warning("⚠️ BotBanMiddleware не зарегистрирован - mute_ban_manager не найден")
        return False


async def start_cleanup_tasks(mute_ban_manager):
    """Запуск задач очистки и проверки банов"""
    try:
        # Запускаем планировщик очистки БД
        global cleanup_scheduler
        cleanup_scheduler = CleanupScheduler()
        asyncio.create_task(cleanup_scheduler.start_daily_cleanup())
        logger.info("✅ Планировщик очистки БД запущен")

        # Запускаем задачи проверки мутов/банов если есть менеджер
        if mute_ban_manager:
            mute_ban_manager.start_cleanup_tasks()
            logger.info("✅ Задачи проверки мутов/банов запущены")

            # Восстанавливаем активные муты после перезапуска
            try:
                await mute_ban_manager.restore_mutes_after_restart()
                logger.info("✅ Активные муты восстановлены после перезапуска")
            except Exception as e:
                logger.error(f" Ошибка восстановления мутов: {e}")

    except Exception as e:
        logger.error(f" Ошибка запуска задач очистки: {e}")
        raise


async def start_donate_scheduler():
    """Запуск планировщика донат-задач"""
    try:
        from handlers.donate.scheduler import DonateScheduler

        global donate_scheduler
        donate_scheduler = DonateScheduler(dp.bot)
        asyncio.create_task(donate_scheduler.start_scheduler())
        logger.info("✅ Планировщик донат-задач запущен")

    except ImportError as e:
        logger.error(f" Ошибка импорта DonateScheduler: {e}")
    except Exception as e:
        logger.error(f" Ошибка запуска планировщика донат-задач: {e}")


async def stop_donate_scheduler():
    """Остановка планировщика донат-задач"""
    global donate_scheduler
    if donate_scheduler:
        try:
            await donate_scheduler.stop_scheduler()
            logger.info("✅ Планировщик донат-задач остановлен")
        except Exception as e:
            logger.error(f" Ошибка остановки планировщика донат-задач: {e}")


async def register_standard_handlers():
    """Регистрация стандартных обработчиков (кроме кланов)"""
    logger.info("🔄 Регистрация стандартных обработчиков...")

    mute_ban_manager = None
    registered_count = 0

    for module_name, register_func_name in HANDLERS:
        try:
            if module_name == "mute_ban":
                # Регистрируем mute_ban отдельно для получения менеджера
                mute_ban_manager = register_mute_ban_handlers(dp)
                logger.info(f"✅ mute_ban обработчики зарегистрированы")
                registered_count += 1
            else:
                module = __import__(f"handlers.{module_name}", fromlist=[register_func_name])
                register_func = getattr(module, register_func_name)
                register_func(dp)
                logger.info(f"✅ {module_name} обработчики зарегистрированы")
                registered_count += 1

        except (ImportError, AttributeError) as e:
            logger.error(f" Ошибка регистрации {module_name}: {e}")
        except Exception as e:
            logger.error(f" Неожиданная ошибка при регистрации {module_name}: {e}")

    # Регистрируем обработчики из папки modroul
    for module_name, register_func_name in MODROUL_HANDLERS:
        try:
            module = __import__(f"handlers.{module_name}", fromlist=[register_func_name])
            register_func = getattr(module, register_func_name)
            register_func(dp)
            logger.info(f"✅ {module_name} обработчики зарегистрированы")
            registered_count += 1
        except (ImportError, AttributeError) as e:
            logger.error(f" Ошибка регистрации {module_name}: {e}")
            logger.error(f" Неожиданная ошибка при регистрации {module_name}: {e}")


    logger.info(f"✅ Всего зарегистрировано {registered_count} модулей обработчиков")
    return mute_ban_manager


async def register_clan_system():
    """Регистрация системы кланов"""
    logger.info("🏰 Регистрация системы кланов...")

    try:
        # Регистрация системы кланов с username бота
        from handlers.clan import register_clan_handlers
        bot_username = (await dp.bot.get_me()).username
        register_clan_handlers(dp, bot_username)
        logger.info("✅ clan обработчики зарегистрированы")

        # Запускаем автообновление кланов
        start_clan_auto_updater()
        logger.info("✅ Автообновление кланов запущено")

        return True
    except Exception as e:
        logger.error(f" Ошибка регистрации системы кланов: {e}")
        return False


async def on_startup(_):
    """Действия при запуске бота"""
    logger.info("🚀 Запуск бота...")

    # 0. СНАЧАЛА ЗАРЕГИСТРИРУЙТЕ START ОБРАБОТЧИКИ
    try:
        from handlers.start import register_start_handler
        register_start_handler(dp)
        logger.info("✅ Стартовые обработчики зарегистрированы (ПЕРВЫМИ)")
    except Exception as e:
        logger.error(f" Ошибка регистрации стартовых обработчиков: {e}")

        # Запасной вариант
        @dp.message_handler(commands=['start'])
        async def fallback_start(message: types.Message):
            await message.answer("🚀 Бот запущен!")

    # 1. Настройка middleware
    dp.middleware.setup(AutoRegisterMiddleware())
    roulette_state_middleware = RouletteStateMiddleware()
    dp.middleware.setup(roulette_state_middleware)
    logger.info("✅ RouletteStateMiddleware зарегистрирован")

    # 2. Настройка БД
    logger.info("📊 Настройка базы данных...")
    if not setup_database():
        raise RuntimeError("Не удалось настроить базу данных")

    # 3. Очистка старых данных
    logger.info("🧹 Очистка старых данных...")
    try:
        cleanup_old_limits()
    except Exception as e:
        logger.error(f"⚠️ Ошибка при очистке старых данных (но продолжаем работу): {e}")

    # 4. Регистрация специальных модулей
    # register_basket_handlers(dp)
    # logger.info("✅ basket обработчики зарегистрированы")

    register_donate_admin_commands(dp)
    logger.info("✅ Админ-команды системы статусов зарегистрированы")

    # register_slot_handlers(dp)
    # logger.info("✅ slot обработчики зарегистрированы")

    # 5. Регистрация системы чеков (ДО стандартных обработчиков!)
    logger.info("💳 Регистрация системы проверки чеков...")
    try:
        register_check_handlers(dp)
        logger.info("✅ Система проверки чеков зарегистрирована")
    except Exception as e:
        logger.error(f" Ошибка регистрации системы чеков: {e}")

    # 6. Регистрация системы кланов
    logger.info("🏰 Регистрация системы кланов...")
    clan_success = await register_clan_system()
    if not clan_success:
        logger.warning("⚠️ Система кланов не загружена, но продолжаем работу")

    # 7. Регистрация стандартных обработчиков
    logger.info("📝 Регистрация стандартных обработчиков...")
    mute_ban_manager = await register_standard_handlers()

    if mute_ban_manager:
        if not mute_ban_manager.bot and dp.bot:
            mute_ban_manager.set_bot(dp.bot)
            logger.info("✅ Бот установлен в MuteBanManager")

        # Создаем и регистрируем middleware
        bot_ban_middleware = BotBanMiddleware(mute_ban_manager)
        dp.middleware.setup(bot_ban_middleware)

        # Связываем менеджер с middleware
        if hasattr(mute_ban_manager, 'bot_ban_manager'):
            mute_ban_manager.bot_ban_manager.set_middleware(bot_ban_middleware)

        logger.info("✅ BotBanMiddleware зарегистрирован и связан с менеджером")

        # Восстанавливаем баны после перезапуска
        try:
            if hasattr(mute_ban_manager, 'bot_ban_manager'):
                await mute_ban_manager.bot_ban_manager.restore_bans_after_restart()
                logger.info("✅ Баны восстановлены после перезапуска")
        except Exception as e:
            logger.error(f" Ошибка восстановления банов: {e}")
    else:
        logger.warning("⚠️ BotBanMiddleware не зарегистрирован - mute_ban_manager не найден")

    # 8. Задачи очистки
    logger.info("⏰ Запуск задач очистки...")
    await start_cleanup_tasks(mute_ban_manager)

    # 9. Запуск планировщика донат-задач
    logger.info("💷 Запуск планировщика донат-задач...")
    await start_donate_scheduler()

    logger.info("✅ Бот успешно запущен")


async def on_shutdown(dp: Dispatcher):
    """Корректное завершение работы с улучшенной обработкой ошибок"""
    logger.info("🛑 Завершение работы бота...")

    try:
        # Останавливаем планировщик очистки
        global cleanup_scheduler
        if cleanup_scheduler:
            try:
                await cleanup_scheduler.stop()
                logger.info("✅ Планировщик очистки остановлен")
            except Exception as e:
                logger.error(f" Ошибка остановки планировщика: {e}")

        # Останавливаем планировщик донат-задач
        await stop_donate_scheduler()

        # Останавливаем систему чеков
        await stop_check_handler()
        logger.info("✅ Система чеков остановлена")

        # Останавливаем автообновление кланов
        stop_clan_auto_updater()
        logger.info("🛑 Система кланов остановлена")

        # Закрываем соединения с БД
        try:
            from database import engine
            engine.dispose()
            logger.info("✅ Соединения с БД закрыты")
        except Exception as e:
            logger.error(f" Ошибка закрытия БД: {e}")

        # Останавливаем диспетчер
        try:
            await dp.storage.close()
            await dp.storage.wait_closed()
            logger.info("✅ Хранилище диспетчера закрыто")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка закрытия хранилища: {e}")

    except Exception as e:
        logger.error(f"💥 Критическая ошибка при завершении: {e}")
    finally:
        logger.info("✅ Бот остановлен")


def main():
    """Основная функция запуска бота"""
    # Регистрируем обработчики сигналов
    def signal_handler(signum, frame):
        logger.info(f"📞 Получен сигнал {signum}. Завершение работы...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info("🔄 Запуск бота")

        # Запускаем бота
        executor.start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            timeout=60,
            allowed_updates=AllowedUpdates.all(),
            relax=0.5
        )

    except KeyboardInterrupt:
        logger.info("⏹️ Остановка по запросу пользователя")
    except Exception as e:
        logger.critical(f" Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()