# handlers/history/base_handler.py
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session


class BaseHistoryHandler:
    """Базовый класс для всех обработчиков истории"""

    def __init__(self):
        self.handler_type = "base"

    def _format_datetime(self, timestamp) -> str:
        """Format timestamp to [DD.MM HH:MM:SS] or [HH:MM:SS] for today"""
        try:
            if not timestamp:
                return '[--:--:--]'

            if isinstance(timestamp, datetime):
                dt = timestamp
            else:
                # Пробуем распарсить строку
                timestamp_str = str(timestamp)
                formats = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M:%S.%f',
                    '%H:%M:%S',
                    '%H:%M:%S.%f'
                ]
                for fmt in formats:
                    try:
                        dt = datetime.strptime(timestamp_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return '[--:--:--]'

            # Проверяем, сегодня ли это
            if dt.date() == date.today():
                # Для сегодняшнего дня: [HH:MM:SS]
                return dt.strftime('[%H:%M:%S]')
            else:
                # Для старых дней: [DD.MM HH:MM]
                return dt.strftime('[%d.%m %H:%M]')
        except Exception:
            return '[--:--:--]'

    def _format_time_only(self, timestamp) -> str:
        """Format timestamp to [HH:MM:SS] only (без даты)"""
        try:
            if not timestamp:
                return '[--:--:--]'

            if isinstance(timestamp, datetime):
                return timestamp.strftime('[%H:%M:%S]')

            # Для строк
            timestamp_str = str(timestamp)
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f',
                '%H:%M:%S',
                '%H:%M:%S.%f'
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    return dt.strftime('[%H:%M:%S]')
                except ValueError:
                    continue
            return '[--:--:--]'
        except Exception:
            return '[--:--:--]'

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю для конкретного пользователя"""
        raise NotImplementedError("Метод должен быть реализован в дочернем классе")