# handlers/record/game_stats_service.py
import logging
from typing import Dict, Any, List, Tuple
from sqlalchemy import func, desc, or_
from database import get_db
from database.crud import ChatRepository, UserRepository
from database.models import TelegramUser

logger = logging.getLogger(__name__)


class GameStatsService:
    """Сервис для работы со статистикой по играм (Рулетка, Бандит)"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_user_game_stats(self, user_id: int, game_type: str = None) -> Dict[str, Any]:
        """Получает статистику пользователя по играм"""
        db = next(get_db())
        try:
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                return {}

            if game_type == "roulette":
                return {
                    'game': '🎰 Рулетка',
                    'coins': user.coins or 0,
                    'total_wins': getattr(user, 'roulette_total_wins', 0) or 0,
                    'total_losses': getattr(user, 'roulette_total_losses', 0) or 0,
                    'max_win': getattr(user, 'roulette_max_win', 0) or 0,
                    'max_loss': getattr(user, 'roulette_max_loss', 0) or 0,
                    'max_bet': getattr(user, 'roulette_max_bet', 0) or 0,
                    'games_count': getattr(user, 'roulette_games_count', 0) or 0,
                    'balance': user.coins or 0
                }
            elif game_type == "bandit":
                return {
                    'game': '🃏 Бандит',
                    'coins': user.coins or 0,
                    'total_wins': getattr(user, 'bandit_total_wins', 0) or 0,
                    'total_losses': getattr(user, 'bandit_total_losses', 0) or 0,
                    'max_win': getattr(user, 'bandit_max_win', 0) or 0,
                    'max_loss': getattr(user, 'bandit_max_loss', 0) or 0,
                    'max_bet': getattr(user, 'bandit_max_bet', 0) or 0,
                    'games_count': getattr(user, 'bandit_games_count', 0) or 0,
                    'balance': user.coins or 0
                }
            else:
                # Общая статистика
                return {
                    'game': '📊 Общая',
                    'coins': user.coins or 0,
                    'total_wins': user.win_coins or 0,
                    'total_losses': user.defeat_coins or 0,
                    'max_win': user.max_win_coins or 0,
                    'max_loss': user.defeat_coins or 0,  # Для общей статистики берем defeat_coins
                    'max_bet': user.max_bet or 0,
                    'balance': user.coins or 0
                }
        finally:
            db.close()

    def update_game_stats(self, user_id: int, game_type: str, stats: Dict[str, Any]) -> bool:
        """Обновляет статистику пользователя для конкретной игры"""
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                return False

            if game_type == "roulette":
                # Обновляем статистику рулетки
                if 'total_wins' in stats:
                    user.roulette_total_wins = (user.roulette_total_wins or 0) + stats['total_wins']
                if 'total_losses' in stats:
                    user.roulette_total_losses = (user.roulette_total_losses or 0) + stats['total_losses']
                if 'max_win' in stats and stats['max_win'] > (user.roulette_max_win or 0):
                    user.roulette_max_win = stats['max_win']
                if 'max_loss' in stats and stats['max_loss'] > (user.roulette_max_loss or 0):
                    user.roulette_max_loss = stats['max_loss']
                if 'max_bet' in stats and stats['max_bet'] > (user.roulette_max_bet or 0):
                    user.roulette_max_bet = stats['max_bet']
                if 'games_count' in stats:
                    user.roulette_games_count = (user.roulette_games_count or 0) + stats['games_count']

            elif game_type == "bandit":
                # Обновляем статистику бандита
                if 'total_wins' in stats:
                    user.bandit_total_wins = (user.bandit_total_wins or 0) + stats['total_wins']
                if 'total_losses' in stats:
                    user.bandit_total_losses = (user.bandit_total_losses or 0) + stats['total_losses']
                if 'max_win' in stats and stats['max_win'] > (user.bandit_max_win or 0):
                    user.bandit_max_win = stats['max_win']
                if 'max_loss' in stats and stats['max_loss'] > (user.bandit_max_loss or 0):
                    user.bandit_max_loss = stats['max_loss']
                if 'max_bet' in stats and stats['max_bet'] > (user.bandit_max_bet or 0):
                    user.bandit_max_bet = stats['max_bet']
                if 'games_count' in stats:
                    user.bandit_games_count = (user.bandit_games_count or 0) + stats['games_count']

            # Также обновляем общую статистику
            if 'total_wins' in stats:
                user.win_coins = (user.win_coins or 0) + stats.get('total_wins', 0)
            if 'total_losses' in stats:
                user.defeat_coins = (user.defeat_coins or 0) + stats.get('total_losses', 0)
            if 'max_win' in stats and stats['max_win'] > (user.max_win_coins or 0):
                user.max_win_coins = stats['max_win']
            if 'max_bet' in stats and stats['max_bet'] > (user.max_bet or 0):
                user.max_bet = stats['max_bet']

            # Обновляем баланс
            if 'balance_change' in stats:
                user.coins = (user.coins or 0) + stats['balance_change']
                if user.coins < 0:
                    user.coins = 0

            db.commit()
            return True

        except Exception as e:
            self.logger.error(f"Error updating game stats: {e}")
            return False
        finally:
            db.close()

    def get_top_by_balance(self, chat_id: int, limit: int = 10, game_type: str = None) -> List[Tuple]:
        """Получает топ пользователей по балансу"""
        db = next(get_db())
        try:
            if game_type == "roulette":
                # Показываем общий баланс (так как баланс общий)
                users = db.query(
                    TelegramUser.telegram_id,
                    TelegramUser.username,
                    TelegramUser.first_name,
                    TelegramUser.coins
                ).filter(
                    TelegramUser.coins > 0
                ).order_by(
                    desc(TelegramUser.coins)
                ).limit(limit).all()

                return [(u.telegram_id, u.username, u.first_name, u.coins) for u in users]
            else:
                # Общий топ (через ChatRepository)
                return ChatRepository.get_top_rich_in_chat(db, chat_id, limit)
        finally:
            db.close()

    def get_top_by_stat(self, chat_id: int, stat_type: str, limit: int = 10, game_type: str = None) -> List[Tuple]:
        """Получает топ по статистике (выигрыши, проигрыши, ставки)"""
        db = next(get_db())
        try:
            stat_field_mapping = {
                'max_win': {
                    'roulette': 'roulette_max_win',
                    'bandit': 'bandit_max_win',
                    'general': 'max_win_coins'
                },
                'max_loss': {
                    'roulette': 'roulette_max_loss',
                    'bandit': 'bandit_max_loss',
                    'general': 'defeat_coins'
                },
                'max_bet': {
                    'roulette': 'roulette_max_bet',
                    'bandit': 'bandit_max_bet',
                    'general': 'max_bet'
                },
                'total_wins': {
                    'roulette': 'roulette_total_wins',
                    'bandit': 'bandit_total_wins',
                    'general': 'win_coins'
                },
                'total_losses': {
                    'roulette': 'roulette_total_losses',
                    'bandit': 'bandit_total_losses',
                    'general': 'defeat_coins'
                }
            }

            if game_type and game_type in ['roulette', 'bandit']:
                stat_field = getattr(TelegramUser, stat_field_mapping.get(stat_type, {}).get(game_type, 'coins'))
            else:
                stat_field = getattr(TelegramUser, stat_field_mapping.get(stat_type, {}).get('general', 'coins'))

            users = db.query(
                TelegramUser.telegram_id,
                TelegramUser.username,
                TelegramUser.first_name,
                stat_field
            ).filter(
                stat_field > 0
            ).order_by(
                desc(stat_field)
            ).limit(limit).all()

            return [(u.telegram_id, u.username, u.first_name,
                     getattr(u, stat_field_mapping[stat_type][game_type if game_type else 'general'])) for u in users]

        except Exception as e:
            self.logger.error(f"Error getting top by stat: {e}")
            return []
        finally:
            db.close()