import re
import random
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from database import db_session
from database.crud import ShopRepository, UserRepository, ThiefRepository, PoliceRepository

# Добавляем импорт
from handlers.roulette.game_stats_updater import GameStatsUpdater  # Импортируйте правильный класс
from handlers.record.game_stats_service import GameStatsService  # Для записи в топ

logger = logging.getLogger(__name__)


class ThiefService:
    # Константы
    ROB_COOLDOWN_MINUTES = 30
    VICTIM_COOLDOWN_MINUTES = 30
    MIN_STEAL_AMOUNT = 5000
    MAX_STEAL_PERCENT = Decimal('0.6')
    THIEF_PRIVILEGE_ID = 1
    POLICE_PRIVILEGE_ID = 2

    # Временное хранилище для времени последней кражи
    _last_robbery_times = {}
    _cooldown_dict = {}

    # Добавляем сервисы статистики
    _stats_updater = GameStatsUpdater()
    _game_stats_service = GameStatsService()

    @staticmethod
    def _check_flood_cooldown(user_id: int) -> bool:
        """Проверка кулдауна для защиты от флуда"""
        current_time = datetime.now().timestamp()
        if user_id in ThiefService._cooldown_dict:
            if current_time - ThiefService._cooldown_dict[user_id] < 10:
                return False
        ThiefService._cooldown_dict[user_id] = current_time
        return True

    @staticmethod
    def check_thief_permission(user_id: int) -> bool:
        """Проверяет права вора в законе"""
        with db_session() as db:
            purchases = ShopRepository.get_user_purchases(db, user_id)
            return ThiefService.THIEF_PRIVILEGE_ID in purchases

    @staticmethod
    def is_police(user_id: int) -> bool:
        """Проверяет, является ли пользователь полицейским"""
        with db_session() as db:
            purchases = ShopRepository.get_user_purchases(db, user_id)
            return ThiefService.POLICE_PRIVILEGE_ID in purchases

    @staticmethod
    def get_user_balance(user_id: int) -> int:
        """Получает баланс пользователя"""
        with db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            return int(user.coins) if user and user.coins else 0

    @staticmethod
    def is_user_arrested(user_id: int) -> bool:
        """Проверяет, арестован ли пользователь"""
        with db_session() as db:
            arrest = PoliceRepository.get_user_arrest(db, user_id)
            if not arrest:
                return False

            if arrest.release_time <= datetime.now():
                PoliceRepository.unarrest_user(db, user_id)
                db.commit()
                return False

            return True

    @staticmethod
    def _calculate_success_chance(steal_amount: int, victim_balance: int, is_victim_police: bool = False) -> float:
        """Рассчитывает шанс успешной кражи"""
        max_possible = int(victim_balance * ThiefService.MAX_STEAL_PERCENT)
        base_success_chance = 0.5

        if max_possible == 0:
            return base_success_chance

        amount_ratio = steal_amount / max_possible
        success_chance = base_success_chance * (1 - amount_ratio * 0.5)
        success_chance = max(success_chance, 0.25)

        if is_victim_police:
            success_chance *= 0.5

        return success_chance

    @staticmethod
    def _check_steal_cooldowns(thief_id: int, victim_id: int) -> Tuple[bool, Optional[str]]:
        """Проверяет все кулдауны для кражи"""
        with db_session() as db:
            now = datetime.now()

            # Проверяем кулдаун вора
            last_robbery_time = ThiefService._last_robbery_times.get(thief_id)

            if last_robbery_time:
                next_rob_time = last_robbery_time + timedelta(minutes=ThiefService.ROB_COOLDOWN_MINUTES)
                if now < next_rob_time:
                    remaining_time = next_rob_time - now
                    minutes = int(remaining_time.total_seconds() // 60)
                    seconds = int(remaining_time.total_seconds() % 60)
                    return False, f"⏳ Подожди {minutes:02d}:{seconds:02d} до следующей кражи"

            # Проверяем кулдаун жертвы
            last_victim_robbery = ThiefRepository.get_last_steal_time_by_victim(db, victim_id)
            if last_victim_robbery:
                if last_victim_robbery.tzinfo is not None:
                    last_victim_robbery = last_victim_robbery.replace(tzinfo=None)

                next_victim_rob_time = last_victim_robbery + timedelta(minutes=ThiefService.VICTIM_COOLDOWN_MINUTES)

                if now < next_victim_rob_time:
                    remaining_time = next_victim_rob_time - now
                    total_minutes = int(remaining_time.total_seconds() // 60)

                    if total_minutes < 60:
                        return False, f"🛡️ Этого пользователя недавно крали! Подождите еще {total_minutes} минут"
                    else:
                        hours = total_minutes // 60
                        minutes = total_minutes % 60
                        return False, f"🛡️ Этого пользователя недавно крали! Подождите еще {hours}ч {minutes}м"

            return True, None

    @staticmethod
    def rob_user(thief_id: int, victim_id: int, specified_amount: int = 0) -> Tuple[bool, str, Optional[int]]:
        """Основная логика кражи"""
        # Защита от флуда
        if not ThiefService._check_flood_cooldown(thief_id):
            return False, "⏳ Подождите 10 секунд", None

        # ПРОВЕРКА АРЕСТА
        if ThiefService.is_user_arrested(thief_id):
            with db_session() as db:
                arrest = PoliceRepository.get_user_arrest(db, thief_id)
                if arrest:
                    time_left = arrest.release_time - datetime.now()
                    hours = int(time_left.total_seconds() // 3600)
                    minutes = int((time_left.total_seconds() % 3600) // 60)

                    if hours > 0:
                        time_str = f"{hours}ч {minutes}м"
                    else:
                        time_str = f"{minutes}м"

                    return False, f"🔒 Вы арестованы! Кража невозможна еще {time_str}", None

        with db_session() as db:
            try:
                thief = UserRepository.get_user_by_telegram_id(db, thief_id)
                victim = UserRepository.get_user_by_telegram_id(db, victim_id)

                if not thief or not victim:
                    return False, " Пользователь не найден", None

                if not ThiefService.check_thief_permission(thief_id):
                    return False, "🎭 Нужна привилегия «Вор в законе»", None

                if thief_id == victim_id:
                    return False, "🚫 Нельзя грабить себя", None

                if ThiefService.is_police(victim_id):
                    return False, "🚓 Нельзя грабить полицейского!", None

                # Проверка: вор не может грабить вора
                if ThiefService.check_thief_permission(victim_id):
                    return False, "🎭 Нельзя грабить другого вора в законе!", None

                # Проверяем КД
                can_rob, cooldown_msg = ThiefService._check_steal_cooldowns(thief_id, victim_id)
                if not can_rob:
                    return False, cooldown_msg, None

                victim_balance = victim.coins
                if victim_balance < ThiefService.MIN_STEAL_AMOUNT:
                    return False, f"📉 У жертвы недостаточно денег! Минимум: {ThiefService.MIN_STEAL_AMOUNT:,} som", None

                # Определяем сумму кражи
                if specified_amount > 0:
                    steal_amount = specified_amount
                    max_allowed = int(victim_balance * ThiefService.MAX_STEAL_PERCENT)
                    if steal_amount > max_allowed:
                        return False, f" Нельзя украсть больше {int(ThiefService.MAX_STEAL_PERCENT * 100)}% от баланса! Максимум: {max_allowed:,} som", None
                else:
                    min_percent = Decimal('0.01')
                    min_amount = max(ThiefService.MIN_STEAL_AMOUNT, int(victim_balance * min_percent))
                    max_amount = int(victim_balance * ThiefService.MAX_STEAL_PERCENT)

                    if min_amount > max_amount:
                        return False, f"📉 У жертвы недостаточно денег для кражи", None

                    steal_amount = random.randint(min_amount, max_amount)

                if steal_amount > victim_balance:
                    steal_amount = victim_balance

                # Проверяем шанс успеха
                is_victim_police = ThiefService.is_police(victim_id)
                success_chance = ThiefService._calculate_success_chance(steal_amount, victim_balance, is_victim_police)
                is_success = random.random() < success_chance

                if is_success:
                    # Успешная кража
                    victim.coins -= steal_amount
                    thief.coins += steal_amount

                    # Сохраняем время последней кражи
                    ThiefService._last_robbery_times[thief_id] = datetime.now()

                    # Записываем попытку в базу
                    ThiefRepository.record_steal_attempt(db, thief_id, victim_id, True, steal_amount)

                    # ЗАПИСЫВАЕМ СТАТИСТИКУ В ТОП - ВАЖНО!
                    try:
                        # Используем GameStatsUpdater
                        stats_updater = GameStatsUpdater()
                        stats_updater.update_bandit_stats(thief_id, steal_amount, steal_amount)

                        # Также обновляем через GameStatsService для записи в общий топ
                        stats_service = GameStatsService()
                        stats_service.update_game_stats(thief_id, "bandit", {
                            'total_wins': steal_amount,
                            'max_win': steal_amount,
                            'max_bet': steal_amount,
                            'games_count': 1,
                            'balance_change': steal_amount
                        })
                    except Exception as stats_error:
                        logger.error(f"Ошибка записи статистики кражи: {stats_error}")
                        # Не прерываем основную логику из-за ошибки статистики

                    db.commit()
                    return True, f"💰 Украдено {steal_amount:,} som", steal_amount
                else:
                    # Неудачная попытка
                    ThiefRepository.record_steal_attempt(db, thief_id, victim_id, False, steal_amount)

                    # Записываем статистику неудачной попытки
                    try:
                        stats_updater = GameStatsUpdater()
                        stats_updater.update_bandit_stats(thief_id, 0, steal_amount)  # net_profit = 0
                    except Exception as stats_error:
                        logger.error(f"Ошибка записи статистики неудачной кражи: {stats_error}")

                    db.commit()

                    if is_victim_police:
                        return False, "🚨 Полицейский поймал вас с поличным!", None
                    else:
                        return False, " Вас заметили! Попробуйте еще раз.", None

            except Exception as e:
                logger.error(f"Error in rob_user: {e}")
                return False, f" Ошибка: {e}", None

    @staticmethod
    def get_thief_stats(user_id: int) -> Dict[str, Any]:
        """Получает статистику краж для пользователя"""
        with db_session() as db:
            stats = ThiefRepository.get_user_thief_stats(db, user_id)
            return {
                'successful_steals': stats.get('successful_steals', 0),
                'failed_steals': stats.get('failed_steals', 0),
                'total_stolen': stats.get('total_stolen', 0),
                'last_steal_time': stats.get('last_steal_time')
            }

    @staticmethod
    def check_steal_cooldown(user_id: int) -> Tuple[bool, Optional[str]]:
        """Проверяет, можно ли красть сейчас и возвращает оставшееся время КД"""
        now = datetime.now()
        last_robbery_time = ThiefService._last_robbery_times.get(user_id)

        if not last_robbery_time:
            return True, None

        next_rob_time = last_robbery_time + timedelta(minutes=ThiefService.ROB_COOLDOWN_MINUTES)

        if now >= next_rob_time:
            return True, None
        else:
            remaining_time = next_rob_time - now
            minutes = int(remaining_time.total_seconds() // 60)
            seconds = int(remaining_time.total_seconds() % 60)
            return False, f"{minutes:02d}:{seconds:02d}"