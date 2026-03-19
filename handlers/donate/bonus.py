# handlers/donate/bonus.py

import logging
import time
from typing import Dict, Any, Tuple, List
from contextlib import contextmanager
from datetime import datetime, timedelta
from aiogram import types
from sqlalchemy import text
from .config import BONUS_AMOUNT, BONUS_COOLDOWN_HOURS, \
    PRIVILEGE_BONUS_COOLDOWN_HOURS
from database import get_db
from database.crud import UserRepository, DonateRepository

logger = logging.getLogger(__name__)


class BonusManager:
    """Класс для управления бонусами с ручным начислением по кнопке"""

    def __init__(self):
        self._init_bonus_table()

    def _init_bonus_table(self):
        """Создает таблицу для бонусов если ее нет и добавляет недостающие колонки"""
        with self._db_session() as db:
            try:
                # Создаем таблицу если ее нет
                db.execute(text('''
                                CREATE TABLE IF NOT EXISTS user_bonuses
                                (
                                    id
                                    SERIAL
                                    PRIMARY
                                    KEY,
                                    telegram_id
                                    BIGINT
                                    UNIQUE
                                    NOT
                                    NULL,
                                    last_bonus_time
                                    BIGINT
                                    DEFAULT
                                    0,
                                    bonus_count
                                    INTEGER
                                    DEFAULT
                                    0,
                                    last__bonus_time
                                    BIGINT
                                    DEFAULT
                                    0,
                                    last__bonus_time
                                    BIGINT
                                    DEFAULT
                                    0,
                                    _bonus_count
                                    INTEGER
                                    DEFAULT
                                    0,
                                    _bonus_count
                                    INTEGER
                                    DEFAULT
                                    0,
                                    created_at
                                    TIMESTAMP
                                    DEFAULT
                                    CURRENT_TIMESTAMP
                                )
                                '''))

                # Убираем авто-бонус колонки, они больше не нужны
                db.commit()
                logger.info("✅ Таблица user_bonuses создана/проверена")
            except Exception as e:
                logger.error(f" Ошибка создания таблицы бонусов: {e}")
                db.rollback()

    @contextmanager
    def _db_session(self):
        """Контекстный менеджер для безопасной работы с БД"""
        session = None
        try:
            session = next(get_db())
            yield session
        except Exception as e:
            logger.error(f"Database connection error in BonusManager: {e}")
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()

    async def claim_daily_bonus(self, user_id: int) -> Dict[str, Any]:
        """Выдает ежедневный бонус по кнопке"""
        with self._db_session() as db:
            try:
                current_time = int(time.time())

                # Проверяем, когда был последний бонус
                bonus_info = db.execute(
                    text("SELECT last_bonus_time FROM user_bonuses WHERE telegram_id = :user_id"),
                    {"user_id": user_id}
                ).fetchone()

                # ИСПРАВЛЕНИЕ: Безопасное получение last_bonus_time
                last_bonus_time = 0
                if bonus_info and bonus_info[0] is not None:
                    last_bonus_time = int(bonus_info[0])

                cooldown_seconds = BONUS_COOLDOWN_HOURS * 3600

                # ИСПРАВЛЕНИЕ: Безопасная проверка кулдауна
                time_since_last_bonus = current_time - last_bonus_time

                if time_since_last_bonus < cooldown_seconds:
                    remaining_seconds = cooldown_seconds - time_since_last_bonus
                    hours_left = remaining_seconds // 3600
                    minutes_left = (remaining_seconds % 3600) // 60
                    return {
                        "success": False,
                        "available": False,
                        "hours_left": int(hours_left),
                        "minutes_left": int(minutes_left),
                        "bonus_amount": 0
                    }

                # Получаем активные привилегии пользователя
                user_purchases = DonateRepository.get_user_active_purchases(db, user_id)
                purchased_ids = [p.item_id for p in user_purchases]
                has_ = 1 in purchased_ids
                has_ = 2 in purchased_ids

                # Начисляем бонусы
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    return {
                        "success": False,
                        "error": "Пользователь не найден",
                        "bonus_amount": 0
                    }

                bonus_amount = 0
                bonuses_claimed = []

                # Базовый бонус для всех
                user.coins += BONUS_AMOUNT
                bonus_amount += BONUS_AMOUNT
                bonuses_claimed.append("daily")

                # Обновляем время последнего бонуса
                db.execute(
                    text("""
                         INSERT INTO user_bonuses (telegram_id, last_bonus_time, bonus_count)
                         VALUES (:user_id, :time, 1) ON CONFLICT (telegram_id)
                                    DO
                         UPDATE SET last_bonus_time = EXCLUDED.last_bonus_time,
                             bonus_count = user_bonuses.bonus_count + 1
                         """),
                    {"user_id": user_id, "time": current_time}
                )

                db.commit()

                logger.info(f"✅ Бонус выдан пользователю {user_id}: {bonus_amount} Монет, типы: {bonuses_claimed}")

                return {
                    "success": True,
                    "available": True,
                    "bonus_amount": bonus_amount,
                    "bonuses_claimed": bonuses_claimed,
                    "has_": has_,
                    "has_": has_
                }

            except Exception as e:
                logger.error(f" Ошибка выдачи бонуса: {e}")
                db.rollback()
                return {
                    "success": False,
                    "error": str(e),
                    "bonus_amount": 0
                }

    async def check_daily_bonus(self, user_id: int) -> Dict[str, Any]:
        """Проверяет доступность ежедневного бонуса"""
        with self._db_session() as db:
            try:
                result = db.execute(
                    text("SELECT last_bonus_time FROM user_bonuses WHERE telegram_id = :user_id"),
                    {"user_id": user_id}
                ).fetchone()

                current_time = int(time.time())

                # Если записи нет или last_bonus_time None, бонус доступен
                if not result or result[0] is None:
                    return {"available": True, "hours_left": 0, "minutes_left": 0}

                last_bonus_time = result[0]

                # Добавляем проверку на None и преобразуем к int
                if last_bonus_time is None:
                    return {"available": True, "hours_left": 0, "minutes_left": 0}

                last_bonus_time = int(last_bonus_time)
                time_since_last_bonus = current_time - last_bonus_time
                cooldown_seconds = BONUS_COOLDOWN_HOURS * 3600

                if time_since_last_bonus >= cooldown_seconds:
                    return {"available": True, "hours_left": 0, "minutes_left": 0}
                else:
                    remaining_seconds = cooldown_seconds - time_since_last_bonus
                    hours_left = remaining_seconds // 3600
                    minutes_left = (remaining_seconds % 3600) // 60
                    return {
                        "available": False,
                        "hours_left": int(hours_left),
                        "minutes_left": int(minutes_left)
                    }
            except Exception as e:
                logger.error(f" Ошибка проверки ежедневного бонуса: {e}")
                return {"available": True, "hours_left": 0, "minutes_left": 0}

    async def check_privilege_bonus(self, user_id: int) -> Dict[str, Any]:
        """Проверяет доступность бонусов за привилегии"""
        with self._db_session() as db:
            try:
                # Получаем активные привилегии пользователя
                user_purchases = DonateRepository.get_user_active_purchases(db, user_id)
                purchased_ids = [p.item_id for p in user_purchases]
                has_ = 1 in purchased_ids
                has_ = 2 in purchased_ids

                # Используем ту же логику, что и для обычного бонуса
                bonus_info = await self.check_daily_bonus(user_id)

                return {
                    "available": bonus_info["available"],
                    "hours_left": bonus_info["hours_left"],
                    "minutes_left": bonus_info["minutes_left"],
                    "has_": has_,
                    "has_": has_
                }

            except Exception as e:
                logger.error(f" Ошибка проверки бонусов за привилегии: {e}")
                return {
                    "available": False,
                    "hours_left": 0,
                    "minutes_left": 0,
                    "has_": False,
                    "has_": False
                }

    async def debug_user_privileges(self, user_id: int):
        """Отладочная информация о привилегиях пользователя"""
        with self._db_session() as db:
            try:
                debug_info = {
                    'user_id': user_id,
                    'active_privileges': []
                }

                # Получаем активные привилегии через DonateRepository
                active_purchases = DonateRepository.get_user_active_purchases(db, user_id)
                debug_info['active_privileges'] = [{
                    'item_id': p.item_id,
                    'item_name': p.item_name,
                    'expires_at': p.expires_at
                } for p in active_purchases]

                return debug_info

            except Exception as e:
                logger.error(f" Ошибка отладки привилегий: {e}")
                return {'error': str(e)}