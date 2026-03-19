import threading


class GameLock:
    """
    Глобальная блокировка для игр - предотвращает одновременное участие 
    пользователя в нескольких играх (рулетка, слоты, баскет и т.д.)
    
    Использует threading.Lock для thread-safety в async среде.
    """
    _instance = None
    _active_users = set()
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GameLock, cls).__new__(cls)
        return cls._instance

    def lock(self, user_id: int) -> bool:
        """Попытка захватить блокировку. Возвращает True, если успешно."""
        with self._lock:
            if user_id in self._active_users:
                return False
            self._active_users.add(user_id)
            return True

    def unlock(self, user_id: int):
        """Снятие блокировки."""
        with self._lock:
            self._active_users.discard(user_id)

    def is_locked(self, user_id: int) -> bool:
        """Проверка, играет ли пользователь."""
        with self._lock:
            return user_id in self._active_users


game_lock = GameLock()

