# handlers/history/slot_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class SlotHistoryHandler(BaseHistoryHandler):
    """Обработчик истории игры в слот"""

    def __init__(self):
        super().__init__()
        self.handler_type = "slot"

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю игры в слот"""
        try:
            from database.models import Transaction

            # Ищем транзакции связанные с игрой в слот БЕЗ фильтра по сегодняшнему дню
            transactions = db.query(Transaction).filter(
                (Transaction.from_user_id == user_id) |
                (Transaction.to_user_id == user_id)
            ).order_by(Transaction.timestamp.desc()).limit(50).all()  # Увеличили лимит

            history_entries = []

            for transaction in transactions:
                time_str = self._format_datetime(transaction.timestamp)  # Используем новый метод с датой
                description = transaction.description or ""

                # Проверяем, является ли транзакция связанной со слотами
                if description.startswith("Слот:"):
                    # Для слота просто оставляем описание как есть
                    if transaction.to_user_id == user_id:
                        # Это выигрыш (деньги поступили пользователю)
                        entry_text = f"{time_str} Выигрыш в слоте: +{transaction.amount:,}"
                    else:
                        # Это ставка или проигрыш (деньги ушли от пользователя)
                        if "Ставка" in description:
                            entry_text = f"{time_str} Проигрыш в слоте: -{transaction.amount:,}"
                        else:
                            entry_text = f"{time_str} Проигрыш в слоте: -{transaction.amount:,}"

                    history_entries.append({
                        'timestamp': transaction.timestamp,
                        'text': entry_text
                    })

            return history_entries

        except Exception as e:
            print(f" Ошибка получения истории слотов: {e}")
            return []

    def _format_slot_description(self, description: str) -> str:
        """Форматирует описание для отображения в истории"""
        # Убираем префикс "Слот:"
        desc = description.replace("Слот:", "").strip()

        # Русские названия для разных типов
        desc_map = {
            "Ставка": "Ставка в слоте",
            "Проигрыш": "Проигрыш в слоте",
            "Выигрыш": "Выигрыш в слоте",
            "Джекпот 777": "ДЖЕКПОТ 777",
            "3 барабана": "Выигрыш: 3 барабана",
            "2 барабана": "Выигрыш: 2 барабана",
            "1 барабан": "Выигрыш: 1 барабан"
        }

        return desc_map.get(desc, desc)