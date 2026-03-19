import logging
import json

from sqlalchemy import and_, or_, desc
from datetime import datetime
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple

from database import get_db
from database.models import TelegramUser
from database.crud import UserRepository
from .check_config import ADMIN_IDS
from .check_model import Check, BanList, CheckLog

logger = logging.getLogger(__name__)


class CheckRepository:
    """Репозиторий для работы с чеками с учетом безопасности"""

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
            self.logger.error(f"Database connection error: {e}")
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()

    def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором"""
        return user_id in ADMIN_IDS

    def create_check(self, user_id: int, chat_id: int,
                     username: str, first_name: str,
                     photo_id: str, notes: str = None,
                     amount: float = None, additional_data: dict = None) -> Tuple[bool, int]:
        """Создает запись о чеке с дополнительными данными"""
        with self._db_session() as db:
            try:
                # Преобразуем additional_data в JSON
                additional_data_json = None
                if additional_data:
                    additional_data_json = json.dumps(additional_data, ensure_ascii=False)

                check = Check(
                    user_id=user_id,
                    chat_id=chat_id,
                    username=username,
                    first_name=first_name,
                    check_photo_id=photo_id,
                    status='pending',
                    notes=notes,
                    amount=amount,
                    additional_data=additional_data_json,
                    created_at=datetime.now()
                )
                db.add(check)
                db.commit()
                db.refresh(check)

                # Логируем создание чека
                self.log_action(
                    check_id=check.id,
                    user_id=user_id,
                    action='check_created',
                    admin_id=0,
                    notes=f'Пользователь отправил чек: {notes[:100] if notes else "без описания"}'
                )

                self.logger.info(f"Check created for user {user_id}, check_id: {check.id}, notes: {notes}")
                return True, check.id

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error creating check: {e}")
                return False, 0

    def get_check(self, check_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о чеке"""
        with self._db_session() as db:
            try:
                check = db.query(Check).filter(Check.id == check_id).first()
                if not check:
                    return None

                # Безопасно получаем additional_data
                additional_data = {}
                if check.additional_data:
                    if isinstance(check.additional_data, str):
                        try:
                            additional_data = json.loads(check.additional_data)
                        except:
                            additional_data = {}
                    else:
                        additional_data = check.additional_data or {}

                return {
                    'id': check.id,
                    'user_id': check.user_id,
                    'username': check.username,
                    'first_name': check.first_name,
                    'chat_id': check.chat_id,
                    'check_photo_id': check.check_photo_id,
                    'status': check.status,
                    'amount': check.amount,
                    'coins_given': check.coins_given,
                    'admin_id': check.admin_id,
                    'admin_username': check.admin_username,
                    'created_at': check.created_at,
                    'processed_at': check.processed_at,
                    'notes': check.notes,
                    'additional_data': additional_data
                }
            except Exception as e:
                self.logger.error(f"Error getting check: {e}")
                return None

    # В методе approve_check в check_repository.py
    def approve_check(self, check_id: int, admin_id: int, admin_username: str,
                      amount: float = None, coins_amount: int = None,
                      purchased_status_id: int = None, is_limit_removal: bool = False) -> Tuple[bool, str]:
        """Подтверждает чек - ИСПРАВЛЕННЫЙ МЕТОД"""
        with self._db_session() as db:
            try:
                check = db.query(Check).filter(Check.id == check_id).first()
                if not check:
                    return False, "Чек не найден"

                if check.status != 'pending':
                    return False, "Чек уже обработан"

                # Получаем пользователя
                user = db.query(TelegramUser).filter(
                    TelegramUser.telegram_id == check.user_id
                ).first()

                if not user:
                    return False, "Пользователь не найден в БД"

                # ОТЛАДОЧНАЯ ИНФОРМАЦИЯ
                self.logger.info(f"DEBUG approve_check: check_id={check_id}, amount={amount}, "
                                 f"coins_amount={coins_amount}, status_id={purchased_status_id}, "
                                 f"limit_removal={is_limit_removal}")

                # Если это покупка монет - начисляем
                if coins_amount and coins_amount > 0:
                    user.coins += coins_amount
                    check.coins_given = coins_amount
                    action_type = 'approve_coins'
                    notes = f'Начислено {coins_amount:,} монет'

                    # Всегда снимаем лимит при покупке монет
                    success = self._remove_transfer_limit(db, check.user_id)
                    if not success:
                        return False, "Ошибка при снятии лимита"
                    notes += ' (лимит снят)'

                # Если это только снятие лимита
                elif is_limit_removal:
                    # ВЫПОЛНЯЕМ ФАКТИЧЕСКОЕ СНЯТИЕ ЛИМИТА
                    success = self._remove_transfer_limit(db, check.user_id)
                    if not success:
                        return False, "Ошибка при снятии лимита"

                    action_type = 'remove_limit'
                    notes = 'Лимит на передачу монет снят'

                # Если это покупка статуса
                elif purchased_status_id:
                    action_type = 'approve_status'
                    notes = f'Активирован статус ID: {purchased_status_id}'
                    # При покупке статуса также снимаем лимит
                    success = self._remove_transfer_limit(db, check.user_id)
                    if not success:
                        return False, "Ошибка при снятии лимита"
                else:
                    action_type = 'approve'
                    notes = 'Подтвержден администратором'

                # Обновляем информацию о чеке
                check.status = 'approved'
                check.amount = amount
                check.admin_id = admin_id
                check.admin_username = admin_username
                check.processed_at = datetime.now()
                check.notes = notes

                # Логируем действие
                self.log_action(
                    check_id=check_id,
                    user_id=check.user_id,
                    action=action_type,
                    admin_id=admin_id,
                    amount=amount,
                    notes=notes
                )

                db.commit()

                self.logger.info(
                    f"Check {check_id} approved by admin {admin_id}. "
                    f"Amount: {amount}, coins: {coins_amount}, status: {purchased_status_id}, "
                    f"limit_removed: {is_limit_removal}"
                )

                return True, "Чек подтвержден"

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error approving check: {e}")
                return False, f"Ошибка: {str(e)}"

    def _remove_transfer_limit(self, db, user_id: int) -> bool:
        """Выполняет фактическое снятие лимита переводов"""
        try:
            # Импортируем здесь, чтобы избежать циклических импортов
            from database.crud import ShopRepository

            # Проверяем, не снят ли уже лимит
            user_purchases = ShopRepository.get_user_purchases(db, user_id)

            # ID привилегии unlimit (из admin_constants.py)
            UNLIMIT_ITEM_ID = 3  # Обычно это ID 3 для снятия лимита

            if UNLIMIT_ITEM_ID in user_purchases:
                self.logger.info(f"User {user_id} already has unlimit privilege")
                return True

            # Выдаем привилегию unlimit
            from handlers.admin.admin_constants import PRIVILEGES, SHOP_ITEMS

            success = ShopRepository.add_user_purchase(
                db,
                user_id,
                SHOP_ITEMS["unlimited_transfers"],  # ID 3
                PRIVILEGES["unlimit"]["name"],  # "🔐 Снятие лимита перевода"
                0  # навсегда
            )

            if success:
                self.logger.info(f"Successfully removed transfer limit for user {user_id}")
                return True
            else:
                self.logger.error(f"Failed to add unlimit purchase for user {user_id}")
                return False

        except Exception as e:
            self.logger.error(f"Error in _remove_transfer_limit: {e}")
            return False

    def ban_user_for_check(self, check_id: int, admin_id: int,
                           admin_username: str, reason: str = "Фальшивый чек") -> Tuple[bool, str]:
        """Банит пользователя за фальшивый чек"""
        with self._db_session() as db:
            try:
                check = db.query(Check).filter(Check.id == check_id).first()
                if not check:
                    return False, "Чек не найден"

                if check.status != 'pending':
                    return False, "Чек уже обработан"

                # Проверяем, не забанен ли уже пользователь
                existing_ban = db.query(BanList).filter(
                    BanList.user_id == check.user_id
                ).first()

                if existing_ban:
                    return False, "Пользователь уже забанен"

                # Добавляем в бан-лист
                ban = BanList(
                    user_id=check.user_id,
                    username=check.username,
                    reason=reason,
                    admin_id=admin_id,
                    banned_at=datetime.now()
                )
                db.add(ban)

                # Обновляем статус чека
                check.status = 'banned'
                check.admin_id = admin_id
                check.admin_username = admin_username
                check.processed_at = datetime.now()
                check.notes = f"Бан: {reason}"

                # Логируем действие
                self.log_action(
                    check_id=check_id,
                    user_id=check.user_id,
                    action='ban',
                    admin_id=admin_id,
                    notes=f'Причина: {reason}'
                )

                db.commit()

                self.logger.info(
                    f"User {check.user_id} banned by admin {admin_id}. "
                    f"Reason: {reason}"
                )

                return True, "Пользователь забанен"

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error banning user: {e}")
                return False, f"Ошибка: {str(e)}"

    def remove_limit_for_check(self, check_id: int, admin_id: int,
                               admin_username: str) -> Tuple[bool, str]:
        """Снимает лимит с пользователя"""
        with self._db_session() as db:
            try:
                check = db.query(Check).filter(Check.id == check_id).first()
                if not check:
                    return False, "Чек не найден"

                if check.status != 'pending':
                    return False, "Чек уже обработан"

                # Здесь нужно интегрировать с системой лимитов вашего бота
                user = db.query(TelegramUser).filter(
                    TelegramUser.telegram_id == check.user_id
                ).first()

                if not user:
                    return False, "Пользователь не найден"

                # TODO: Снять лимит
                # user.has_transfer_limit = False

                # Обновляем статус чека
                check.status = 'limit_removed'
                check.admin_id = admin_id
                check.admin_username = admin_username
                check.processed_at = datetime.now()
                check.notes = "Лимит на передачу снят"

                # Логируем действие
                self.log_action(
                    check_id=check_id,
                    user_id=check.user_id,
                    action='remove_limit',
                    admin_id=admin_id,
                    notes='Снят лимит на передачу монет'
                )

                db.commit()

                self.logger.info(
                    f"Limit removed for user {check.user_id} by admin {admin_id}"
                )

                return True, "Лимит снят"

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error removing limit: {e}")
                return False, f"Ошибка: {str(e)}"

    def reject_check(self, check_id: int, admin_id: int, admin_username: str,
                     reason: str) -> Tuple[bool, str]:
        """Отклоняет чек"""
        with self._db_session() as db:
            try:
                check = db.query(Check).filter(Check.id == check_id).first()
                if not check:
                    return False, "Чек не найден"

                if check.status != 'pending':
                    return False, "Чек уже обработан"

                check.status = 'rejected'
                check.admin_id = admin_id
                check.admin_username = admin_username
                check.processed_at = datetime.now()
                check.notes = f"Отклонено: {reason}"

                # Логируем действие
                self.log_action(
                    check_id=check_id,
                    user_id=check.user_id,
                    action='reject',
                    admin_id=admin_id,
                    notes=f'Причина: {reason}'
                )

                db.commit()

                self.logger.info(
                    f"Check {check_id} rejected by admin {admin_id}. "
                    f"Reason: {reason}"
                )

                return True, "Чек отклонен"

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error rejecting check: {e}")
                return False, f"Ошибка: {str(e)}"

    def get_pending_checks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получает список ожидающих проверки чеков"""
        with self._db_session() as db:
            try:
                checks = db.query(Check).filter(
                    Check.status == 'pending'
                ).order_by(desc(Check.created_at)).limit(limit).all()

                result = []
                for check in checks:
                    result.append({
                        'id': check.id,
                        'user_id': check.user_id,
                        'username': check.username,
                        'first_name': check.first_name,
                        'created_at': check.created_at,
                        'check_photo_id': check.check_photo_id
                    })

                return result
            except Exception as e:
                self.logger.error(f"Error getting pending checks: {e}")
                return []

    def get_user_checks(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Получает историю чеков пользователя"""
        with self._db_session() as db:
            try:
                checks = db.query(Check).filter(
                    Check.user_id == user_id
                ).order_by(desc(Check.created_at)).limit(limit).all()

                result = []
                for check in checks:
                    result.append({
                        'id': check.id,
                        'status': check.status,
                        'amount': check.amount,
                        'coins_given': check.coins_given,
                        'created_at': check.created_at,
                        'processed_at': check.processed_at,
                        'notes': check.notes
                    })

                return result
            except Exception as e:
                self.logger.error(f"Error getting user checks: {e}")
                return []

    def is_user_banned(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Проверяет, забанен ли пользователь"""
        with self._db_session() as db:
            try:
                ban = db.query(BanList).filter(BanList.user_id == user_id).first()
                if ban:
                    return True, ban.reason
                return False, None
            except Exception as e:
                self.logger.error(f"Error checking user ban: {e}")
                return False, None

    def unban_user(self, user_id: int, admin_id: int, reason: str) -> Tuple[bool, str]:
        """Разбанивает пользователя"""
        with self._db_session() as db:
            try:
                ban = db.query(BanList).filter(BanList.user_id == user_id).first()
                if not ban:
                    return False, "Пользователь не забанен"

                # Логируем действие разбана
                self.log_action(
                    check_id=0,  # 0 = без привязки к чеку
                    user_id=user_id,
                    action='unban',
                    admin_id=admin_id,
                    notes=f'Причина: {reason}'
                )

                db.delete(ban)
                db.commit()

                self.logger.info(f"User {user_id} unbanned by admin {admin_id}")
                return True, "Пользователь разбанен"

            except Exception as e:
                db.rollback()
                self.logger.error(f"Error unbanning user: {e}")
                return False, f"Ошибка: {str(e)}"

    def get_action_logs(self, user_id: int = None, admin_id: int = None,
                        action: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Получает логи действий"""
        with self._db_session() as db:
            try:
                query = db.query(CheckLog)

                if user_id:
                    query = query.filter(CheckLog.user_id == user_id)
                if admin_id:
                    query = query.filter(CheckLog.admin_id == admin_id)
                if action:
                    query = query.filter(CheckLog.action == action)

                logs = query.order_by(desc(CheckLog.created_at)).limit(limit).all()

                result = []
                for log in logs:
                    result.append({
                        'id': log.id,
                        'check_id': log.check_id,
                        'user_id': log.user_id,
                        'action': log.action,
                        'amount': log.amount,
                        'admin_id': log.admin_id,
                        'created_at': log.created_at,
                        'notes': log.notes
                    })

                return result
            except Exception as e:
                self.logger.error(f"Error getting action logs: {e}")
                return []

    def log_action(self, check_id: int, user_id: int, action: str,
                   admin_id: int, amount: float = None, notes: str = None):
        """Логирует действие администратора"""
        with self._db_session() as db:
            try:
                log = CheckLog(
                    check_id=check_id,
                    user_id=user_id,
                    action=action,
                    amount=amount,
                    admin_id=admin_id,
                    notes=notes,
                    created_at=datetime.now()
                )
                db.add(log)
                db.commit()
            except Exception as e:
                self.logger.error(f"Error logging action: {e}")