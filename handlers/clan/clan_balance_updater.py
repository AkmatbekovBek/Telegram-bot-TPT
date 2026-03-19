import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from database import SessionLocal
from .clan_database import ClanDatabase

logger = logging.getLogger(__name__)


class ClanBalanceUpdater:
    """Класс для автоматического обновления баланса кланов"""

    _instance: Optional['ClanBalanceUpdater'] = None
    _scheduler: Optional[AsyncIOScheduler] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ClanBalanceUpdater, cls).__new__(cls)
            cls._instance._scheduler = None
        return cls._instance

    def start(self):
        """Запустить планировщик автообновления"""
        if self._scheduler is None:
            self._scheduler = AsyncIOScheduler()

            # Обновление всех кланов каждые 30 минут
            self._scheduler.add_job(
                self.update_all_clans,
                trigger=IntervalTrigger(minutes=30),
                id='clan_full_update',
                replace_existing=True
            )

            # Обновление устаревших кланов каждые 5 минут
            self._scheduler.add_job(
                self.auto_update_stale_clans,
                trigger=IntervalTrigger(minutes=5),
                id='clan_stale_update',
                replace_existing=True
            )

            self._scheduler.start()
            logger.info("✅ Планировщик автообновления кланов запущен")

            # Сразу обновляем все кланы при запуске
            asyncio.create_task(self.update_all_clans())

    def stop(self):
        """Остановить планировщик"""
        if self._scheduler:
            self._scheduler.shutdown()
            self._scheduler = None
            logger.info("🛑 Планировщик автообновления кланов остановлен")

    @staticmethod
    async def update_all_clans():
        """Обновить капитал всех кланов"""
        try:
            db = SessionLocal()
            clan_db = ClanDatabase(db)

            try:
                success = clan_db.update_all_clans_coins()
                if success:
                    logger.info("✅ Автоматически обновлен капитал всех кланов")
                else:
                    logger.warning("⚠️ Не удалось обновить капитал всех кланов")

            except Exception as e:
                logger.error(f" Ошибка обновления всех кланов: {e}")

            finally:
                db.close()

        except Exception as e:
            logger.error(f" Ошибка подключения к БД для обновления всех кланов: {e}")

    @staticmethod
    async def auto_update_stale_clans():
        """Автоматически обновить устаревшие кланы"""
        try:
            db = SessionLocal()
            clan_db = ClanDatabase(db)

            try:
                updated_count = clan_db.auto_update_stale_clans()
                if updated_count > 0:
                    logger.info(f"✅ Автообновлено {updated_count} устаревших кланов")

            except Exception as e:
                logger.error(f" Ошибка автообновления кланов: {e}")

            finally:
                db.close()

        except Exception as e:
            logger.error(f" Ошибка подключения к БД для автообновления: {e}")

    @staticmethod
    def update_user_clan_coins(user_id: int):
        """Обновить капитал клана пользователя при изменении его баланса"""
        try:
            db = SessionLocal()
            clan_db = ClanDatabase(db)

            try:
                # Находим клан пользователя
                clan = clan_db.get_user_clan(user_id)
                if clan:
                    # Проверяем, когда было последнее обновление
                    if clan.last_updated and datetime.now() - clan.last_updated < timedelta(minutes=1):
                        logger.debug(f"ℹ️ Клан {clan.name} обновлялся недавно, пропускаем")
                        return

                    # Обновляем капитал клана
                    clan_db.force_update_clan_coins(clan.id)
                    logger.debug(f"✅ Автоматически обновлен капитал клана {clan.name} для пользователя {user_id}")
                else:
                    logger.debug(f"ℹ️ Пользователь {user_id} не состоит в клане")

            except Exception as e:
                logger.error(f" Ошибка обновления капитала клана для пользователя {user_id}: {e}")

            finally:
                db.close()

        except Exception as e:
            logger.error(f" Ошибка подключения к БД для обновления клана: {e}")

    @staticmethod
    def manual_update_all_clans() -> bool:
        """Ручное обновление всех кланов"""
        try:
            db = SessionLocal()
            clan_db = ClanDatabase(db)

            try:
                success = clan_db.update_all_clans_coins()
                if success:
                    logger.info("✅ Ручное обновление: капитал всех кланов обновлен")
                    return True
                else:
                    logger.warning("⚠️ Ручное обновление: не удалось обновить капитал")
                    return False

            finally:
                db.close()

        except Exception as e:
            logger.error(f" Ошибка при ручном обновлении кланов: {e}")
            return False

    @staticmethod
    def manual_update_clan(clan_id: int) -> bool:
        """Ручное обновление конкретного клана"""
        try:
            db = SessionLocal()
            clan_db = ClanDatabase(db)

            try:
                clan = clan_db.get_clan_by_id(clan_id)
                if not clan:
                    logger.warning(f"⚠️ Ручное обновление: клан ID:{clan_id} не найден")
                    return False

                success = clan_db.force_update_clan_coins(clan_id)
                if success:
                    logger.info(f"✅ Ручное обновление: капитал клана {clan.name} обновлен")
                    return True
                else:
                    logger.warning(f"⚠️ Ручное обновление: не удалось обновить клан ID:{clan_id}")
                    return False

            finally:
                db.close()

        except Exception as e:
            logger.error(f" Ошибка при ручном обновлении клана: {e}")
            return False