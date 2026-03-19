# handlers/roulette/game_stats_updater.py
import logging
from typing import Dict, Any
from database import get_db
from database.crud import UserRepository

logger = logging.getLogger(__name__)


class GameStatsUpdater:
    """Обновляет статистику игр в реальном времени"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def update_roulette_stats(self, user_id: int, net_profit: int, bet_amount: int):
        """Обновляет статистику рулетки для пользователя"""
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                self.logger.warning(f"Пользователь {user_id} не найден для обновления статистики")
                return False

            # Обновляем счетчик игр
            user.roulette_games_count = (user.roulette_games_count or 0) + 1

            # Обновляем максимальную ставку
            if bet_amount > (user.roulette_max_bet or 0):
                user.roulette_max_bet = bet_amount

            # Обновляем статистику выигрышей/проигрышей
            if net_profit > 0:
                # Выигрыш
                user.roulette_total_wins = (user.roulette_total_wins or 0) + net_profit
                if net_profit > (user.roulette_max_win or 0):
                    user.roulette_max_win = net_profit
            else:
                # Проигрыш
                loss_amount = abs(net_profit)
                user.roulette_total_losses = (user.roulette_total_losses or 0) + loss_amount
                if loss_amount > (user.roulette_max_loss or 0):
                    user.roulette_max_loss = loss_amount

            # Также обновляем общую статистику для обратной совместимости
            if net_profit > 0:
                user.win_coins = (user.win_coins or 0) + net_profit
                if net_profit > (user.max_win_coins or 0):
                    user.max_win_coins = net_profit
            else:
                loss_amount = abs(net_profit)
                user.defeat_coins = (user.defeat_coins or 0) + loss_amount

            # Обновляем максимальную ставку в общей статистике
            if bet_amount > (user.max_bet or 0):
                user.max_bet = bet_amount

            db.commit()
            self.logger.info(f"Статистика рулетки обновлена для {user_id}: net_profit={net_profit}, bet={bet_amount}")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка обновления статистики рулетки: {e}")
            return False
        finally:
            db.close()

    async def update_bandit_stats(self, user_id: int, net_profit: int, bet_amount: int):
        """Обновляет статистику бандита для пользователя"""
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                self.logger.warning(f"Пользователь {user_id} не найден для обновления статистики")
                return False

            # Обновляем счетчик игр
            user.bandit_games_count = (user.bandit_games_count or 0) + 1

            # Обновляем максимальную ставку
            if bet_amount > (user.bandit_max_bet or 0):
                user.bandit_max_bet = bet_amount

            # Обновляем статистику выигрышей/проигрышей
            if net_profit > 0:
                # Выигрыш
                user.bandit_total_wins = (user.bandit_total_wins or 0) + net_profit
                if net_profit > (user.bandit_max_win or 0):
                    user.bandit_max_win = net_profit
            else:
                # Проигрыш
                loss_amount = abs(net_profit)
                user.bandit_total_losses = (user.bandit_total_losses or 0) + loss_amount
                if loss_amount > (user.bandit_max_loss or 0):
                    user.bandit_max_loss = loss_amount

            # Также обновляем общую статистику
            if net_profit > 0:
                user.win_coins = (user.win_coins or 0) + net_profit
                if net_profit > (user.max_win_coins or 0):
                    user.max_win_coins = net_profit
            else:
                loss_amount = abs(net_profit)
                user.defeat_coins = (user.defeat_coins or 0) + loss_amount

            # Обновляем максимальную ставку в общей статистике
            if bet_amount > (user.max_bet or 0):
                user.max_bet = bet_amount

            db.commit()
            self.logger.info(f"Статистика бандита обновлена для {user_id}: net_profit={net_profit}, bet={bet_amount}")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка обновления статистики бандита: {e}")
            return False
        finally:
            db.close()