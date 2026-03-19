import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from database import get_db
from database.crud import RouletteRepository


class RouletteLogger:
    """Класс для логирования результатов рулетки в БД"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def add_game_log(self, chat_id: int, result: int, color_emoji: str):
        """Добавляет запись о результате игры в БД"""
        try:
            db = next(get_db())
            RouletteRepository.add_game_log(db, chat_id, result, color_emoji)
            db.commit()
            self.logger.info(f"✅ Лог рулетки добавлен для чата {chat_id}: {result}{color_emoji}")
        except Exception as e:
            self.logger.error(f" Ошибка добавления лога рулетки: {e}")
            try:
                db.rollback()
            except:
                pass

    def get_recent_logs(self, chat_id: int, count: int = 10) -> List[Dict[str, Any]]:
        """Возвращает последние N записей для чата (последние снизу)"""
        try:
            db = next(get_db())
            logs = RouletteRepository.get_recent_game_logs(db, chat_id, count)

            formatted_logs = []
            for log in logs:
                formatted_logs.append({
                    "result": log.result,
                    "color_emoji": log.color_emoji,
                    "timestamp": log.created_at
                })

            # Важно: SQL возвращает в порядке убывания (DESC), переворачиваем
            # чтобы новые были внизу
            formatted_logs.reverse()

            return formatted_logs

        except Exception as e:
            self.logger.error(f" Ошибка получения логов: {e}")
            return []

    def get_all_logs(self, chat_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Возвращает все логи для чата (до limit записей)"""
        return self.get_recent_logs(chat_id, limit)

    def get_logs_count(self, chat_id: int) -> int:
        """Возвращает количество записей в логах чата из БД"""
        try:
            db = next(get_db())
            from sqlalchemy import func
            from database.models import RouletteGameLog

            count = db.query(func.count(RouletteGameLog.id)).filter(
                RouletteGameLog.chat_id == chat_id
            ).scalar()

            return count if count else 0

        except Exception as e:
            self.logger.error(f" Ошибка подсчета логов: {e}")
            return 0

    def cleanup_old_logs(self, days: int = 30) -> int:
        """Очищает старые логи (старше указанного количества дней)"""
        try:
            db = next(get_db())
            from sqlalchemy import delete
            from database.models import RouletteGameLog
            from datetime import datetime, timedelta

            cutoff_date = datetime.now() - timedelta(days=days)

            deleted_count = db.execute(
                delete(RouletteGameLog).where(
                    RouletteGameLog.created_at < cutoff_date
                )
            ).rowcount

            db.commit()
            self.logger.info(f"✅ Очищено {deleted_count} старых логов рулетки")
            return deleted_count

        except Exception as e:
            self.logger.error(f" Ошибка очистки старых логов: {e}")
            try:
                db.rollback()
            except:
                pass
            return 0

    def get_logs_for_period(self, chat_id: int, start_date: datetime,
                            end_date: datetime = None) -> List[Dict[str, Any]]:
        """Возвращает логи за определенный период"""
        try:
            db = next(get_db())
            from sqlalchemy import between
            from database.models import RouletteGameLog

            if end_date is None:
                end_date = datetime.now()

            logs = db.query(RouletteGameLog).filter(
                RouletteGameLog.chat_id == chat_id,
                between(RouletteGameLog.created_at, start_date, end_date)
            ).order_by(RouletteGameLog.created_at).all()

            formatted_logs = []
            for log in logs:
                formatted_logs.append({
                    "result": log.result,
                    "color_emoji": log.color_emoji,
                    "timestamp": log.created_at
                })

            return formatted_logs

        except Exception as e:
            self.logger.error(f" Ошибка получения логов за период: {e}")
            return []