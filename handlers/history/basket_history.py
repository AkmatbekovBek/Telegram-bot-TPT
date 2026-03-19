# handlers/history/basket_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class BasketHistoryHandler(BaseHistoryHandler):
    """Обработчик истории игры в баскетбол"""

    def __init__(self):
        super().__init__()
        self.handler_type = "basket"

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю игры в баскетбол (только чистые результаты)"""
        try:
            from database.models import Transaction

            # Ищем транзакции связанные с игрой в баскетбол
            transactions = db.query(Transaction).filter(
                (Transaction.from_user_id == user_id) |
                (Transaction.to_user_id == user_id)
            ).order_by(Transaction.timestamp.desc()).limit(50).all()  # Увеличили лимит

            history_entries = []

            for transaction in transactions:
                description = transaction.description or ""

                # Проверяем, является ли транзакция связанной с баскетболом
                if description.startswith("Баскетбол:"):
                    # Форматируем время с датой или без
                    time_formatted = self._format_datetime(transaction.timestamp)

                    # Формируем запись в стиле рулетки
                    if transaction.to_user_id == user_id:
                        # Это чистый выигрыш
                        desc = description.replace("Баскетбол:", "").strip()
                        if "Прямое попадание" in desc:
                            entry_text = f"{time_formatted} Прямое попадание в баскетболе: +{transaction.amount:,}"
                        elif "Попадание с вращением" in desc:
                            entry_text = f"{time_formatted} Попадание с вращением в баскетболе: +{transaction.amount:,}"
                        else:
                            entry_text = f"{time_formatted} Выигрыш в баскетболе: +{transaction.amount:,}"
                    else:
                        # Это чистый проигрыш (ставка)
                        entry_text = f"{time_formatted} Проигрыш в баскетболе: -{transaction.amount:,}"

                    history_entries.append({
                        'timestamp': transaction.timestamp,
                        'text': entry_text
                    })

            return history_entries

        except Exception as e:
            print(f" Ошибка получения истории баскетбола: {e}")
            return []