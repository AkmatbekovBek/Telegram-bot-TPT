import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy import text, and_, or_, desc, func
from contextlib import contextmanager
from database import get_db
from .config import STATUSES
from database.models import UserStatus, UserBonus, StatusTransaction, DailyBonusLog, TelegramUser
import asyncio

logger = logging.getLogger(__name__)


class StatusRepository:
    """Класс для работы с донат-статусами в БД"""

    def __init__(self):
        self.logger = logger

    @contextmanager
    def _db_session(self):
        """Контекстный менеджер для безопасной работы с БД"""
        session = None
        try:
            session = next(get_db())
            yield session
        except Exception as e:
            self.logger.error(f"Database connection error in StatusRepository: {e}")
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()

    def get_user_active_status(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает активный статус пользователя"""
        with self._db_session() as db:
            try:
                result = db.query(UserStatus).filter(
                    and_(
                        UserStatus.user_id == user_id,
                        UserStatus.is_active == True,
                        or_(
                            UserStatus.expires_at.is_(None),
                            UserStatus.expires_at > datetime.now()
                        )
                    )
                ).order_by(UserStatus.created_at.desc()).first()

                if result:
                    # Вычисляем оставшиеся дни
                    days_left = 0
                    if result.expires_at:
                        now = datetime.now()
                        if result.expires_at > now:
                            delta = result.expires_at - now
                            days_left = delta.days
                            if delta.seconds > 0:
                                days_left += 1

                    # Маппинг иконок из ТЗ
                    status_icons_tz = {
                        1: "🐾",  # Обычный
                        2: "🌑",  # Бронза
                        3: "💰",  # Платина
                        4: "🥇",  # Золото
                        5: "💎",  # Бриллиант
                    }

                    return {
                        "id": result.id,
                        "user_id": result.user_id,
                        "status_id": result.status_id,
                        "status_name": result.status_name,
                        "status_icon": status_icons_tz.get(result.status_id, "🐾"),
                        "is_active": result.is_active,
                        "expires_at": result.expires_at,
                        "link_url": result.link_url,
                        "link_text": result.link_text,
                        "days_left": days_left,
                        "created_at": result.created_at
                    }
                return None

            except Exception as e:
                self.logger.error(f"Error getting user active status: {e}")
                return None

    def get_user_bonus_amount(self, user_id: int) -> int:
        """Получает сумму бонуса для пользователя (автоматически определяет статус)"""
        status = self.get_user_active_status(user_id)
        if status:
            # Для платных статусов возвращаем соответствующий бонус
            status_config = next((s for s in STATUSES if s["id"] == status["status_id"]), None)
            if status_config:
                return status_config.get("bonus_amount", 1_000_000)
        # Для всех остальных - обычный бонус 1.000.000
        return 25_000

    def can_receive_bonus(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Проверяет, может ли пользователь получить бонус (для ручного получения)"""
        with self._db_session() as db:
            try:
                # Проверяем последний автоматический бонус
                last_bonus = db.query(DailyBonusLog).filter(
                    DailyBonusLog.user_id == user_id
                ).order_by(DailyBonusLog.created_at.desc()).first()

                if not last_bonus:
                    return True, None  # Никогда не получал бонус

                # Проверяем, прошло ли 24 часа
                time_since_last_bonus = datetime.now() - last_bonus.created_at
                hours_since = time_since_last_bonus.total_seconds() / 3600

                if hours_since >= 24:
                    return True, None
                else:
                    hours_left = 24 - hours_since
                    hours_int = int(hours_left)
                    minutes_left = int((hours_left - hours_int) * 60)

                    if hours_int > 0:
                        time_left = f"{hours_int}ч {minutes_left}м"
                    else:
                        time_left = f"{minutes_left}м"

                    return False, time_left

            except Exception as e:
                self.logger.error(f"Error checking bonus eligibility: {e}")
                # При ошибке возвращаем False, чтобы избежать злоупотреблений
                return False, "Ошибка проверки"

    def award_automatic_bonus(self, user_id: int) -> Tuple[bool, str, int]:
        """Начисляет автоматический бонус пользователю (вызывается планировщиком)"""
        with self._db_session() as db:
            try:
                # Проверяем, прошел ли час с последнего автоматического начисления
                last_auto_bonus = db.query(DailyBonusLog).filter(
                    DailyBonusLog.user_id == user_id,
                    DailyBonusLog.is_automatic == True
                ).order_by(DailyBonusLog.created_at.desc()).first()

                if last_auto_bonus:
                    # Проверяем, прошло ли 24 часа
                    time_since_last = datetime.now() - last_auto_bonus.created_at
                    if time_since_last.total_seconds() < 24 * 3600:
                        hours_left = 24 - (time_since_last.total_seconds() / 3600)
                        return False, f"До следующего бонуса: {int(hours_left)}ч", 0

                # Получаем активный статус
                status = self.get_user_active_status(user_id)

                # Определяем сумму бонуса
                if status:
                    status_config = next((s for s in STATUSES if s["id"] == status["status_id"]), None)
                    if status_config:
                        bonus_amount = status_config.get("bonus_amount", 25_000)
                    else:
                        bonus_amount = 25_000
                else:
                    # Обычный статус - 1.000.000
                    bonus_amount = 25_000

                # Получаем пользователя
                user = db.query(TelegramUser).filter(TelegramUser.telegram_id == user_id).first()
                if not user:
                    return False, "Пользователь не найден", 0

                # Начисляем бонус
                user.coins += bonus_amount

                # Создаем запись о бонусе
                bonus_log = DailyBonusLog(
                    user_id=user_id,
                    status_id=status["status_id"] if status else 1,
                    status_name=status["status_name"] if status else "обычный",
                    bonus_amount=bonus_amount,
                    total_bonus_amount=user.coins,
                    is_automatic=True
                )
                db.add(bonus_log)

                # Обновляем статистику бонусов
                user_bonus = db.query(UserBonus).filter(UserBonus.user_id == user_id).first()
                if user_bonus:
                    user_bonus.last_bonus_time = datetime.now()
                    user_bonus.bonus_count += 1
                    user_bonus.total_bonus_amount += bonus_amount
                else:
                    user_bonus = UserBonus(
                        user_id=user_id,
                        last_bonus_time=datetime.now(),
                        bonus_count=1,
                        total_bonus_amount=bonus_amount
                    )
                    db.add(user_bonus)

                db.commit()

                self.logger.info(f"✅ Автоматический бонус начислен пользователю {user_id}: {bonus_amount} Монет")
                return True, f"Начислен бонус: {bonus_amount:,} Монет", bonus_amount

            except Exception as e:
                db.rollback()
                self.logger.error(f" Ошибка начисления автоматического бонуса: {e}")
                return False, f"Ошибка: {str(e)}", 0

    def award_manual_bonus(self, user_id: int) -> Tuple[bool, str, int]:
        """Начисляет бонус при ручном запросе (кнопка)"""
        return self.award_automatic_bonus(user_id)

    def get_users_for_automatic_bonus(self) -> List[int]:
        """Получает список пользователей, которым нужно начислить автоматический бонус"""
        with self._db_session() as db:
            try:
                # Получаем всех пользователей
                all_users = db.query(TelegramUser.telegram_id).all()
                all_user_ids = [user_id for (user_id,) in all_users]

                # Фильтруем тех, кому можно начислить бонус
                result_ids = []
                for user_id in all_user_ids:
                    # Проверяем последний автоматический бонус
                    last_bonus = db.query(DailyBonusLog).filter(
                        DailyBonusLog.user_id == user_id,
                        DailyBonusLog.is_automatic == True
                    ).order_by(DailyBonusLog.created_at.desc()).first()

                    if not last_bonus:
                        result_ids.append(user_id)
                    else:
                        # Проверяем, прошло ли 24 часа
                        time_since_last = datetime.now() - last_bonus.created_at
                        if time_since_last.total_seconds() >= 24 * 3600:
                            result_ids.append(user_id)

                return result_ids

            except Exception as e:
                self.logger.error(f" Ошибка получения пользователей для бонуса: {e}")
                return []

    def set_user_status(self, user_id: int, status_id: int, days: int = 30,
                        admin_id: int = None, link_url: str = None,
                        link_text: str = None) -> Tuple[bool, str]:
        """Устанавливает статус пользователю"""
        with self._db_session() as db:
            try:
                # Находим информацию о статусе
                status_info = next((s for s in STATUSES if s["id"] == status_id), None)
                if not status_info:
                    return False, "Статус не найден"

                # Деактивируем старые статусы
                db.query(UserStatus).filter(
                    and_(
                        UserStatus.user_id == user_id,
                        UserStatus.is_active == True
                    )
                ).update({"is_active": False})

                # Вычисляем дату истечения
                expires_at = None
                if days > 0:
                    expires_at = datetime.now() + timedelta(days=days)

                # Создаем новый статус
                new_status = UserStatus(
                    user_id=user_id,
                    status_id=status_id,
                    status_name=status_info["name"],
                    is_active=True,
                    expires_at=expires_at,
                    link_url=link_url,
                    link_text=link_text
                )
                db.add(new_status)

                # Записываем транзакцию
                transaction = StatusTransaction(
                    user_id=user_id,
                    status_id=status_id,
                    status_name=status_info["name"],
                    action="admin_give" if admin_id else "purchase",
                    amount_rub=status_info.get("price_rub"),
                    amount_tenge=status_info.get("price_tenge"),
                    days=days,
                    admin_id=admin_id,
                    link_url=link_url,
                    link_text=link_text
                )
                db.add(transaction)

                db.commit()

                self.logger.info(f"Status {status_id} set for user {user_id} for {days} days")
                return True, f"Статус '{status_info['name']}' успешно выдан на {days} дней"

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error setting user status: {e}")
                return False, f"Ошибка при выдаче статуса: {e}"

    def remove_user_status(self, user_id: int, status_id: int = None) -> Tuple[bool, str]:
        """Удаляет статус у пользователя"""
        with self._db_session() as db:
            try:
                if status_id:
                    # Деактивируем конкретный статус
                    status = db.query(UserStatus).filter(
                        and_(
                            UserStatus.user_id == user_id,
                            UserStatus.status_id == status_id,
                            UserStatus.is_active == True
                        )
                    ).first()

                    if status:
                        status.is_active = False
                        affected_rows = 1
                        status_name = status.status_name
                    else:
                        return False, "Активный статус не найден"
                else:
                    # Деактивируем все статусы пользователя
                    result = db.query(UserStatus).filter(
                        and_(
                            UserStatus.user_id == user_id,
                            UserStatus.is_active == True
                        )
                    ).update({"is_active": False})

                    affected_rows = result
                    status_name = "все статусы"

                if affected_rows > 0:
                    db.commit()
                    self.logger.info(f"Removed status(es) for user {user_id}: {status_name}")
                    return True, f"Статус '{status_name}' успешно удален"
                else:
                    return False, "Не найдено активных статусов для удаления"

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error removing user status: {e}")
                return False, f"Ошибка при удалении статуса: {e}"

    def deactivate_expired_statuses(self) -> int:
        """Деактивирует истекшие статусы и возвращает количество деактивированных"""
        with self._db_session() as db:
            try:
                expired_statuses = db.query(UserStatus).filter(
                    and_(
                        UserStatus.is_active == True,
                        UserStatus.expires_at.isnot(None),
                        UserStatus.expires_at <= datetime.now()
                    )
                ).all()

                deactivated_count = 0
                for status in expired_statuses:
                    status.is_active = False
                    deactivated_count += 1

                if deactivated_count > 0:
                    db.commit()
                    self.logger.info(f"Deactivated {deactivated_count} expired statuses")

                return deactivated_count

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error deactivating expired statuses: {e}")
                return 0

    def get_expiring_statuses(self, days_before: int = 1) -> List[Dict[str, Any]]:
        """Получает статусы, которые истекают через указанное количество дней"""
        with self._db_session() as db:
            try:
                cutoff_date = datetime.now() + timedelta(days=days_before)

                statuses = db.query(UserStatus).filter(
                    and_(
                        UserStatus.is_active == True,
                        UserStatus.expires_at.isnot(None),
                        UserStatus.expires_at <= cutoff_date,
                        UserStatus.expires_at > datetime.now()
                    )
                ).all()

                result = []
                for status in statuses:
                    result.append({
                        "user_id": status.user_id,
                        "status_id": status.status_id,
                        "status_name": status.status_name,
                        "expires_at": status.expires_at,
                        "days_left": (status.expires_at - datetime.now()).days
                    })

                return result

            except Exception as e:
                self.logger.error(f"Error getting expiring statuses: {e}")
                return []

    def get_expired_statuses(self) -> List[Dict[str, Any]]:
        """Получает истекшие статусы"""
        with self._db_session() as db:
            try:
                statuses = db.query(UserStatus).filter(
                    and_(
                        UserStatus.is_active == True,
                        UserStatus.expires_at.isnot(None),
                        UserStatus.expires_at <= datetime.now()
                    )
                ).all()

                result = []
                for status in statuses:
                    result.append({
                        "user_id": status.user_id,
                        "status_id": status.status_id,
                        "status_name": status.status_name,
                        "expires_at": status.expires_at
                    })

                return result

            except Exception as e:
                self.logger.error(f"Error getting expired statuses: {e}")
                return []

    def get_user_info_for_profile(self, user_id: int) -> Dict[str, Any]:
        """Получает информацию о пользователе для профиля"""
        with self._db_session() as db:
            try:
                # Получаем пользователя
                user = db.query(TelegramUser).filter(TelegramUser.telegram_id == user_id).first()
                if not user:
                    return {"error": "Пользователь не найден"}

                # Получаем активный статус
                active_status = self.get_user_active_status(user_id)

                # Получаем статистику бонусов
                user_bonus = db.query(UserBonus).filter(UserBonus.user_id == user_id).first()
                bonus_stats = {
                    "bonus_count": user_bonus.bonus_count if user_bonus else 0,
                    "total_bonus_amount": user_bonus.total_bonus_amount if user_bonus else 0,
                    "last_bonus_time": user_bonus.last_bonus_time if user_bonus else None
                }

                # Проверяем доступность бонуса
                can_receive, time_left = self.can_receive_bonus(user_id)

                # Получаем сумму ежедневного бонуса
                daily_bonus_amount = self.get_user_bonus_amount(user_id)

                # Получаем информацию о статусе для профиля
                if active_status:
                    # Форматируем дату истечения
                    expires_at = active_status.get('expires_at')
                    expires_text = expires_at.strftime('%d.%m.%Y %H:%M') if expires_at else 'бессрочно'

                    # Вычисляем оставшиеся дни
                    days_left = active_status.get('days_left', 0)

                    # Формируем информацию о ссылке если есть
                    link_info = ""
                    if active_status.get('link_url'):
                        link_info = f"{active_status['link_url']}|{active_status.get('link_text', '')}"

                    status_info = {
                        "status_id": active_status['status_id'],
                        "status_name": active_status['status_name'],
                        "status_icon": active_status['status_icon'],
                        "expires_at": expires_at,
                        "expires_text": expires_text,
                        "days_left": days_left,
                        "link_url": active_status.get('link_url'),
                        "link_text": active_status.get('link_text'),
                        "link_info": link_info
                    }
                else:
                    status_info = None

                return {
                    "user_id": user_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "coins": user.coins,
                    "active_status": status_info,
                    "bonus_stats": bonus_stats,
                    "can_receive_bonus": can_receive,
                    "next_bonus_time": time_left if time_left else "доступен сейчас",
                    "daily_bonus_amount": daily_bonus_amount
                }

            except Exception as e:
                self.logger.error(f"Error getting user info for profile: {e}")
                return {"error": str(e)}


    def extend_user_status(self, user_id: int, days: int, status_id: int = None) -> Tuple[bool, str]:
        """Продлевает активный статус пользователя"""
        with self._db_session() as db:
            try:
                if days <= 0:
                    return False, "Количество дней должно быть положительным"

                if status_id:
                    # Продлеваем конкретный статус
                    status = db.query(UserStatus).filter(
                        and_(
                            UserStatus.user_id == user_id,
                            UserStatus.status_id == status_id,
                            UserStatus.is_active == True
                        )
                    ).first()
                else:
                    # Продлеваем текущий активный статус
                    status = db.query(UserStatus).filter(
                        and_(
                            UserStatus.user_id == user_id,
                            UserStatus.is_active == True
                        )
                    ).first()

                if not status:
                    return False, "Активный статус не найден"

                # Обновляем дату истечения
                current_expires = status.expires_at
                if current_expires and current_expires > datetime.now():
                    new_expires = current_expires + timedelta(days=days)
                else:
                    new_expires = datetime.now() + timedelta(days=days)

                status.expires_at = new_expires
                status.updated_at = datetime.now()

                # Записываем транзакцию продления
                transaction = StatusTransaction(
                    user_id=user_id,
                    status_id=status.status_id,
                    status_name=status.status_name,
                    action="extend",
                    days=days,
                    admin_id=None
                )
                db.add(transaction)

                db.commit()

                self.logger.info(f"Extended status for user {user_id} by {days} days")
                return True, f"Статус '{status.status_name}' продлен на {days} дней. Истекает: {new_expires.strftime('%d.%m.%Y %H:%M')}"

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error extending user status: {e}")
                return False, f"Ошибка при продлении статуса: {e}"

    def search_users_by_status(self, status_id: int = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Ищет пользователей по статусу"""
        with self._db_session() as db:
            try:
                query = db.query(UserStatus).join(
                    TelegramUser, UserStatus.user_id == TelegramUser.telegram_id
                ).filter(
                    UserStatus.is_active == True
                )

                if status_id:
                    query = query.filter(UserStatus.status_id == status_id)

                # Фильтруем только не истекшие статусы
                query = query.filter(
                    or_(
                        UserStatus.expires_at.is_(None),
                        UserStatus.expires_at > datetime.now()
                    )
                )

                results = query.order_by(desc(UserStatus.created_at)).limit(limit).all()

                users = []
                for status in results:
                    user = status.user
                    days_left = None
                    if status.expires_at:
                        days_left = (status.expires_at - datetime.now()).days
                        if days_left < 0:
                            days_left = 0

                    users.append({
                        "user_id": user.telegram_id,
                        "username": user.username,
                        "first_name": user.first_name,
                        "status_id": status.status_id,
                        "status_name": status.status_name,
                        "expires_at": status.expires_at,
                        "days_left": days_left
                    })

                return users

            except Exception as e:
                self.logger.error(f"Error searching users by status: {e}")
                return []

    def get_user_bonus_stats(self, user_id: int) -> Dict[str, Any]:
        """Получает статистику бонусов пользователя"""
        with self._db_session() as db:
            try:
                user_bonus = db.query(UserBonus).filter(UserBonus.user_id == user_id).first()

                if user_bonus:
                    return {
                        "last_bonus_time": user_bonus.last_bonus_time,
                        "bonus_count": user_bonus.bonus_count,
                        "total_bonus_amount": user_bonus.total_bonus_amount
                    }

                return {
                    "last_bonus_time": None,
                    "bonus_count": 0,
                    "total_bonus_amount": 0
                }

            except Exception as e:
                self.logger.error(f"Error getting user bonus stats: {e}")
                return {
                    "last_bonus_time": None,
                    "bonus_count": 0,
                    "total_bonus_amount": 0
                }

    def get_status_bonus_amount(self, status_id: int) -> int:
        """Получает сумму бонуса для статуса"""
        status = next((s for s in STATUSES if s["id"] == status_id), None)
        if status:
            return status.get("bonus_amount", 25_000)
        return 25_000  # Базовый бонус

    def update_user_last_bonus(self, user_id: int, bonus_amount: int) -> Tuple[bool, str]:
        """Обновляет время последнего получения бонуса"""
        with self._db_session() as db:
            try:
                # Получаем или создаем запись о бонусе
                user_bonus = db.query(UserBonus).filter(UserBonus.user_id == user_id).first()

                if user_bonus:
                    user_bonus.last_bonus_time = datetime.now()
                    user_bonus.bonus_count += 1
                    user_bonus.total_bonus_amount += bonus_amount
                else:
                    user_bonus = UserBonus(
                        user_id=user_id,
                        last_bonus_time=datetime.now(),
                        bonus_count=1,
                        total_bonus_amount=bonus_amount
                    )
                    db.add(user_bonus)

                # Записываем лог бонуса
                active_status = self.get_user_active_status(user_id)
                bonus_log = DailyBonusLog(
                    user_id=user_id,
                    status_id=active_status["status_id"] if active_status else None,
                    status_name=active_status["status_name"] if active_status else "обычный",
                    bonus_amount=bonus_amount,
                    total_bonus_amount=user_bonus.total_bonus_amount
                )
                db.add(bonus_log)

                db.commit()
                return True, "Бонус успешно зарегистрирован"

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error updating user last bonus: {e}")
                return False, f"Ошибка при регистрации бонуса: {e}"