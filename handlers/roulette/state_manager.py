# handlers/roulette/state_manager.py
import logging
import threading
from dataclasses import dataclass
from typing import Dict, Any
import json
import os

from sqlalchemy import text

from database import SessionLocal

logger = logging.getLogger(__name__)

# Файл для сохранения состояний в памяти (как backup)
STATE_FILE = "roulette_states.json"


@dataclass
class RouletteGroupLimitState:
    chat_id: int
    free_used: bool
    limit_removed: bool
    donation_paid: bool


class StateManager:
    """Постоянные настройки чата и лимит рулетки для новой группы."""

    def __init__(self):
        self._init_lock = threading.Lock()
        self._initialized = False
        # Для обратной совместимости с кодом, который использует JSON
        self.chat_states = self._load_json_states()

    def _ensure_tables(self):
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return

            db = SessionLocal()
            try:
                db.execute(text("""
                                CREATE TABLE IF NOT EXISTS chat_game_settings
                                (
                                    chat_id
                                    BIGINT
                                    PRIMARY
                                    KEY,
                                    roulette_enabled
                                    BOOLEAN
                                    NOT
                                    NULL
                                    DEFAULT
                                    TRUE,
                                    slot_enabled
                                    BOOLEAN
                                    NOT
                                    NULL
                                    DEFAULT
                                    FALSE,
                                    basket_enabled
                                    BOOLEAN
                                    NOT
                                    NULL
                                    DEFAULT
                                    FALSE,
                                    roulette_session_open
                                    BOOLEAN
                                    NOT
                                    NULL
                                    DEFAULT
                                    FALSE,
                                    created_at
                                    TIMESTAMP
                                    DEFAULT
                                    CURRENT_TIMESTAMP,
                                    updated_at
                                    TIMESTAMP
                                    DEFAULT
                                    CURRENT_TIMESTAMP
                                );
                                """))

                db.execute(text("""
                                CREATE TABLE IF NOT EXISTS roulette_group_limits
                                (
                                    chat_id
                                    BIGINT
                                    PRIMARY
                                    KEY,
                                    free_used
                                    BOOLEAN
                                    NOT
                                    NULL
                                    DEFAULT
                                    FALSE,
                                    limit_removed
                                    BOOLEAN
                                    NOT
                                    NULL
                                    DEFAULT
                                    FALSE,
                                    donation_paid
                                    BOOLEAN
                                    NOT
                                    NULL
                                    DEFAULT
                                    FALSE,
                                    created_at
                                    TIMESTAMP
                                    DEFAULT
                                    CURRENT_TIMESTAMP,
                                    updated_at
                                    TIMESTAMP
                                    DEFAULT
                                    CURRENT_TIMESTAMP
                                );
                                """))

                db.commit()
                self._initialized = True
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to init roulette tables: {e}", exc_info=True)
            finally:
                db.close()

    # ------------------------------------------------------------------
    # JSON backup (для обратной совместимости)
    # ------------------------------------------------------------------
    def _load_json_states(self) -> Dict[int, bool]:
        """Загружает состояния из JSON файла (для обратной совместимости)"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error(f"Ошибка загрузки состояний рулетки из JSON: {e}")
        return {}

    def _save_json_states(self):
        """Сохраняет состояния в JSON файл (для обратной совместимости)"""
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.chat_states, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения состояний рулетки в JSON: {e}")

    # ------------------------------------------------------------------
    # Chat flags
    # ------------------------------------------------------------------
    def _ensure_chat_row(self, db, chat_id: int):
        db.execute(
            text("""
                 INSERT INTO chat_game_settings(chat_id)
                 VALUES (:chat_id) ON CONFLICT(chat_id) DO NOTHING
                 """),
            {"chat_id": int(chat_id)},
        )

    def _ensure_limit_row(self, db, chat_id: int):
        db.execute(
            text("""
                 INSERT INTO roulette_group_limits(chat_id)
                 VALUES (:chat_id) ON CONFLICT(chat_id) DO NOTHING
                 """),
            {"chat_id": int(chat_id)},
        )

    def get_chat_flags(self, chat_id: int) -> Dict[str, bool]:
        """Получает все флаги для чата"""
        self._ensure_tables()
        db = SessionLocal()
        try:
            self._ensure_chat_row(db, chat_id)
            row = db.execute(
                text("""
                     SELECT roulette_enabled, slot_enabled, basket_enabled, roulette_session_open
                     FROM chat_game_settings
                     WHERE chat_id = :chat_id
                     """),
                {"chat_id": int(chat_id)},
            ).fetchone()
            db.commit()
            if not row:
                return {
                    "roulette_enabled": True,
                    "slot_enabled": False,
                    "basket_enabled": False,
                    "roulette_session_open": False,
                }
            return {
                "roulette_enabled": bool(row[0]),
                "slot_enabled": bool(row[1]),
                "basket_enabled": bool(row[2]),
                "roulette_session_open": bool(row[3]),
            }
        except Exception:
            db.rollback()
            # Fallback к JSON
            is_enabled = self.chat_states.get(chat_id, True)
            return {
                "roulette_enabled": is_enabled,
                "slot_enabled": False,
                "basket_enabled": False,
                "roulette_session_open": False,
            }
        finally:
            db.close()

    def set_flag(self, chat_id: int, flag: str, value: bool):
        """Устанавливает флаг для чата"""
        self._ensure_tables()
        if flag not in {"roulette_enabled", "slot_enabled", "basket_enabled", "roulette_session_open"}:
            raise ValueError(f"Unknown flag: {flag}")

        db = SessionLocal()
        try:
            self._ensure_chat_row(db, chat_id)
            db.execute(
                text(f"""
                    UPDATE chat_game_settings 
                    SET {flag}=:val, updated_at=CURRENT_TIMESTAMP 
                    WHERE chat_id=:chat_id
                """),
                {"val": bool(value), "chat_id": int(chat_id)},
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed set_flag {flag} for chat {chat_id}: {e}", exc_info=True)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Compatibility methods (для старого кода)
    # ------------------------------------------------------------------
    def is_roulette_enabled(self, chat_id: int) -> bool:
        """Проверяет, включена ли рулетка в чате (для обратной совместимости)"""
        return self.get_chat_flags(chat_id)["roulette_enabled"]

    def is_slot_enabled(self, chat_id: int) -> bool:
        """Проверяет, включены ли слоты в чате"""
        return self.get_chat_flags(chat_id)["slot_enabled"]

    def is_basket_enabled(self, chat_id: int) -> bool:
        """Проверяет, включен ли баскетбол в чате"""
        return self.get_chat_flags(chat_id)["basket_enabled"]

    def is_roulette_session_open(self, chat_id: int) -> bool:
        """Проверяет, открыта ли сессия рулетки в чате"""
        return self.get_chat_flags(chat_id)["roulette_session_open"]

    # Методы для обратной совместимости со старым кодом
    def enable_roulette(self, chat_id: int):
        """Включает рулетку в чате (старый метод)"""
        self.set_flag(chat_id, "roulette_enabled", True)
        # Также обновляем JSON для обратной совместимости
        self.chat_states[chat_id] = True
        self._save_json_states()

    def disable_roulette(self, chat_id: int):
        """Отключает рулетку в чате (старый метод)"""
        self.set_flag(chat_id, "roulette_enabled", False)
        # Также обновляем JSON для обратной совместимости
        self.chat_states[chat_id] = False
        self._save_json_states()

    def set_slot_enabled(self, chat_id: int, enabled: bool):
        """Включает/выключает слоты в чате"""
        self.set_flag(chat_id, "slot_enabled", enabled)

    def set_basket_enabled(self, chat_id: int, enabled: bool):
        """Включает/выключает баскетбол в чате"""
        self.set_flag(chat_id, "basket_enabled", enabled)

    # ------------------------------------------------------------------
    # Group limit
    # ------------------------------------------------------------------
    def get_group_limit_state(self, chat_id: int) -> RouletteGroupLimitState:
        self._ensure_tables()
        db = SessionLocal()
        try:
            self._ensure_limit_row(db, chat_id)
            row = db.execute(
                text("""
                     SELECT free_used, limit_removed, donation_paid
                     FROM roulette_group_limits
                     WHERE chat_id = :chat_id
                     """),
                {"chat_id": int(chat_id)},
            ).fetchone()
            db.commit()
            if not row:
                return RouletteGroupLimitState(chat_id, False, False, False)
            return RouletteGroupLimitState(chat_id, bool(row[0]), bool(row[1]), bool(row[2]))
        except Exception:
            db.rollback()
            return RouletteGroupLimitState(chat_id, False, False, False)
        finally:
            db.close()

    def consume_free_launch_or_block(self, chat_id: int) -> bool:
        """True = можно запускать рулетку.

        Если лимит не снят и free_used=False — помечаем free_used=True.
        """
        self._ensure_tables()
        db = SessionLocal()
        try:
            db.execute(text("BEGIN"))

            self._ensure_limit_row(db, chat_id)

            row = db.execute(
                text("""
                     SELECT free_used, limit_removed
                     FROM roulette_group_limits
                     WHERE chat_id = :chat_id
                         FOR UPDATE
                     """),
                {"chat_id": int(chat_id)},
            ).fetchone()

            free_used = bool(row[0]) if row else False
            limit_removed = bool(row[1]) if row else False

            if limit_removed:
                db.commit()
                return True

            if not free_used:
                db.execute(
                    text("""
                         UPDATE roulette_group_limits
                         SET free_used= TRUE,
                             updated_at=CURRENT_TIMESTAMP
                         WHERE chat_id = :chat_id
                         """),
                    {"chat_id": int(chat_id)},
                )
                db.commit()
                return True

            db.commit()
            return False

        except Exception as e:
            db.rollback()
            logger.error(f"consume_free_launch_or_block error chat={chat_id}: {e}", exc_info=True)
            return False
        finally:
            db.close()

    def unlock_group_limit_paid(self, chat_id: int):
        """Снять лимит за валюту (100,000,000)"""
        self._ensure_tables()
        db = SessionLocal()
        try:
            self._ensure_limit_row(db, chat_id)
            db.execute(
                text("""
                     UPDATE roulette_group_limits
                     SET limit_removed= TRUE,
                         updated_at=CURRENT_TIMESTAMP
                     WHERE chat_id = :chat_id
                     """),
                {"chat_id": int(chat_id)},
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"unlock_group_limit_paid error chat={chat_id}: {e}")
        finally:
            db.close()

    def unlock_group_limit_donation(self, chat_id: int):
        """Снять лимит за донат (500₽)"""
        self._ensure_tables()
        db = SessionLocal()
        try:
            self._ensure_limit_row(db, chat_id)
            db.execute(
                text("""
                     UPDATE roulette_group_limits
                     SET donation_paid= TRUE,
                         limit_removed= TRUE,
                         updated_at=CURRENT_TIMESTAMP
                     WHERE chat_id = :chat_id
                     """),
                {"chat_id": int(chat_id)},
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"unlock_group_limit_donation error chat={chat_id}: {e}")
        finally:
            db.close()

    def lock_roulette_limit(self, chat_id: int):
        """Вернуть лимит рулетки (обратная операция unlock)"""
        db = SessionLocal()
        try:
            from database.crud import RouletteLimitRepository
            RouletteLimitRepository.lock_limit(db, chat_id)
            logger.info(f"Лимит рулетки возвращен для группы {chat_id}")
        except Exception as e:
            logger.error(f"lock_roulette_limit error chat={chat_id}: {e}")
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Admin check (для обратной совместимости)
    # ------------------------------------------------------------------
    async def check_admin_permissions(self, user_id: int, chat_id: int, bot) -> bool:
        """Проверяет, является ли пользователь администратором группы или бота"""
        try:
            chat_member = await bot.get_chat_member(chat_id, user_id)
            return chat_member.is_chat_admin()
        except Exception:
            return False

    def clear_cache(self, user_id: int = None, chat_id: int = None):
        """Очищает кэш (старый метод для обратной совместимости)"""
        pass  # В новой реализации кэш не используется

    # ------------------------------------------------------------------
    # Group roulette limit methods (НОВЫЕ методы для рулетки)
    # ------------------------------------------------------------------
    def is_roulette_limit_removed(self, chat_id: int) -> bool:
        """Проверяет, снят ли лимит рулетки в группе"""
        db = SessionLocal()
        try:
            from database.crud import RouletteLimitRepository
            return RouletteLimitRepository.is_limit_removed(db, chat_id)
        finally:
            db.close()

    def can_launch_roulette(self, chat_id: int) -> bool:
        """Проверяет, можно ли запускать рулетку в группе (учитывает бесплатный запуск и снятие лимита)"""
        db = SessionLocal()
        try:
            from database.crud import RouletteLimitRepository
            return RouletteLimitRepository.can_launch_roulette(db, chat_id)
        finally:
            db.close()

    def unlock_roulette_with_coins(self, chat_id: int, user_id: int = None):
        """Снять лимит рулетки за монеты (100,000,000)"""
        db = SessionLocal()
        try:
            from database.crud import RouletteLimitRepository
            RouletteLimitRepository.unlock_with_coins(db, chat_id, user_id)
        finally:
            db.close()

    def unlock_roulette_with_donation(self, chat_id: int, user_id: int):
        """Снять лимит рулетки за донат (500₽)"""
        db = SessionLocal()
        try:
            from database.crud import RouletteLimitRepository
            RouletteLimitRepository.unlock_with_donation(db, chat_id, user_id)
        finally:
            db.close()

    def get_roulette_limit_info(self, chat_id: int) -> Dict[str, Any]:
        """Получает информацию о лимите рулетки в группе"""
        db = SessionLocal()
        try:
            from database.crud import RouletteLimitRepository
            return RouletteLimitRepository.get_limit_status(db, chat_id)
        finally:
            db.close()


state_manager = StateManager()