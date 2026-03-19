# handlers/history/transfer_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class TransferHistoryHandler(BaseHistoryHandler):
    """Обработчик истории переводов"""

    def __init__(self):
        super().__init__()
        self.handler_type = "transfer"

    def _get_user_display_name(self, db: Session, user_id: int) -> str:
        """Получает отображаемое имя пользователя"""
        try:
            from database.models import TelegramUser
            user = db.query(TelegramUser).filter(
                TelegramUser.telegram_id == user_id
            ).first()

            if not user:
                return f"ID:{user_id}"

            if user.first_name:
                name = user.first_name
                # Ограничиваем длину имени
                if len(name) > 20:
                    name = name[:17] + "..."
                return name
            elif user.username:
                return f"@{user.username}"
            else:
                return f"ID:{user_id}"
        except:
            return f"ID:{user_id}"

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю переводов пользователя ВСЕХ типов (отправленные и полученные)"""
        try:
            from database.models import Transaction

            # Получаем все транзакции пользователя
            transactions = db.query(Transaction).filter(
                (Transaction.from_user_id == user_id) |
                (Transaction.to_user_id == user_id)
            ).order_by(Transaction.timestamp.desc()).limit(100).all()  # Увеличили лимит

            history_entries = []

            for transaction in transactions:
                time_str = self._format_datetime(transaction.timestamp)
                description = transaction.description or ""

                # Пропускаем специфические типы транзакций, которые обрабатываются другими обработчиками
                if any(marker in description.lower() for marker in [
                    'баскетбол:', 'слот:', 'рулетк', 'roulette', 'гонк', 'race',
                    'кубик', 'dice', 'кнб', 'раффл', 'розыгрыш', '🎉', '🏆',
                    'донат', 'donate', '💎', 'админ пополнение', 'админ обнуление',
                    'марафон', 'игра', 'ставка', 'реферал', 'награда'
                ]):
                    continue

                # Обрабатываем переводы
                if transaction.from_user_id == user_id:
                    # Исходящий перевод (мы отправляли кому-то)
                    if transaction.to_user_id:
                        target_name = self._get_user_display_name(db, transaction.to_user_id)
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 💸 Перевод: -{transaction.amount:,} для {target_name}"
                        })
                else:
                    # Входящий перевод (нам кто-то отправил)
                    if transaction.from_user_id:
                        source_name = self._get_user_display_name(db, transaction.from_user_id)
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 💰 Получено: +{transaction.amount:,} от {source_name}"
                        })

            return history_entries

        except Exception as e:
            print(f" Ошибка получения истории переводов: {e}")
            return []