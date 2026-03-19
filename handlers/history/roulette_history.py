# handlers/history/roulette_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class RouletteHistoryHandler(BaseHistoryHandler):
    """Обработчик истории рулетки"""

    def __init__(self):
        super().__init__()
        self.handler_type = "roulette"

    def _calculate_net_profit(self, transaction) -> int:
        """Рассчитывает чистую прибыль для ставки в рулетке"""
        try:
            # Для рулетки profit уже содержит чистую прибыль
            if hasattr(transaction, 'profit') and transaction.profit is not None:
                return int(transaction.profit)
            elif transaction.is_win:
                # Если win, выигрыш = ставка * 2, чистая прибыль = ставка
                return int(transaction.amount)
            else:
                # Если проигрыш, чистая прибыль = -ставка
                return -int(transaction.amount)
        except:
            return 0

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю ставок в рулетке"""
        try:
            from database.models import RouletteTransaction

            # Получаем историю ставок БЕЗ фильтра по сегодняшнему дню
            bet_history = db.query(RouletteTransaction).filter(
                RouletteTransaction.user_id == user_id
            ).order_by(RouletteTransaction.created_at.desc()).limit(50).all()  # Увеличили лимит

            history_entries = []

            for bet in bet_history:
                # Убрали проверку на сегодняшний день
                net_profit = self._calculate_net_profit(bet)
                time_str = self._format_datetime(bet.created_at)  # Используем новый метод с датой

                if net_profit > 0:
                    history_entries.append({
                        'timestamp': bet.created_at,
                        'text': f"{time_str} Выигрыш в рулетку: +{net_profit:,}"
                    })
                elif net_profit < 0:
                    history_entries.append({
                        'timestamp': bet.created_at,
                        'text': f"{time_str} Проигрыш в рулетку: {net_profit:,}"
                    })
                else:
                    history_entries.append({
                        'timestamp': bet.created_at,
                        'text': f"{time_str} Ничья в рулетку: 0"
                    })

            return history_entries

        except Exception as e:
            print(f" Ошибка получения истории рулетки: {e}")
            return []