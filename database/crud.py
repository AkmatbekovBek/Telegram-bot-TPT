from venv import logger

from aiogram.contrib.middlewares import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, update, select, func, desc
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, date, timedelta
import database.models as models
from handlers.clan.clan_database import ClanDatabase
from . import SessionLocal
from .models import ModerationLog, ModerationAction
from database.models import User
from database.models import ActiveMute

class UserRepository:

    @staticmethod
    def update_bandit_stats(db: Session, user_id: int, **kwargs) -> Optional[models.TelegramUser]:
        """Обновляет статистику бандита (краж) для пользователя"""
        user = UserRepository.get_user_by_telegram_id(db, user_id)

        if not user:
            return None

        try:
            # Обновляем счетчик игр
            if 'games_count' in kwargs:
                user.bandit_games_count = (user.bandit_games_count or 0) + kwargs['games_count']

            # Обновляем общие выигрыши
            if 'total_wins' in kwargs:
                user.bandit_total_wins = (user.bandit_total_wins or 0) + kwargs['total_wins']

            # Обновляем общие проигрыши
            if 'total_losses' in kwargs:
                user.bandit_total_losses = (user.bandit_total_losses or 0) + kwargs['total_losses']

            # Обновляем максимальный выигрыш
            if 'max_win' in kwargs and kwargs['max_win'] > (user.bandit_max_win or 0):
                user.bandit_max_win = kwargs['max_win']

            # Обновляем максимальный проигрыш
            if 'max_loss' in kwargs and kwargs['max_loss'] > (user.bandit_max_loss or 0):
                user.bandit_max_loss = kwargs['max_loss']

            # Обновляем максимальную ставку
            if 'max_bet' in kwargs and kwargs['max_bet'] > (user.bandit_max_bet or 0):
                user.bandit_max_bet = kwargs['max_bet']

            # Обновляем общую статистику для обратной совместимости
            if 'total_wins' in kwargs:
                user.win_coins = (user.win_coins or 0) + kwargs['total_wins']

            if 'max_win' in kwargs and kwargs['max_win'] > (user.max_win_coins or 0):
                user.max_win_coins = kwargs['max_win']

            if 'max_bet' in kwargs and kwargs['max_bet'] > (user.max_bet or 0):
                user.max_bet = kwargs['max_bet']

            db.commit()
            return user

        except Exception as e:
            db.rollback()
            print(f" Ошибка обновления статистики бандита: {e}")
            return None

    @staticmethod
    def get_or_create_user(db: Session, tg_id: int, chat_id: int, username: str = "") -> User:
        user = db.query(User).filter(
            User.tg_id == tg_id,
            User.chat_id == chat_id
        ).first()

        if not user:
            user = User(
                tg_id=tg_id,
                chat_id=chat_id,
                username=username[:32] if username else "",
                coins=0,
                win_coins=0,
                defeat_coins=0,
                max_win_coins=0,
                min_win_coins=0,
                max_bet_coins=0
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # Обновляем username, если изменился
        if username and user.username != username:
            user.username = username[:32]
            db.commit()

        return user

    @staticmethod
    def get_or_create_user(db: Session, telegram_id: int, username: str, first_name: str,
                           last_name: str = None) -> models.TelegramUser:
        # Очищаем и обрезаем данные перед сохранением
        first_name = UserRepository.clean_telegram_field(first_name, 255) if first_name else None
        last_name = UserRepository.clean_telegram_field(last_name, 255) if last_name else None
        username = UserRepository.clean_telegram_field(username, 255) if username else None

        user = db.query(models.TelegramUser).filter(models.TelegramUser.telegram_id == telegram_id).first()
        if not user:
            user = models.TelegramUser(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                coins=5000
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def clean_telegram_field(field: str, max_length: int) -> str:
        """Очищает и обрезает поле пользователя Telegram"""
        if not field:
            return field

        # Удаляем лишние пробелы
        field = ' '.join(field.split())

        # Обрезаем до максимальной длины
        if len(field) > max_length:
            field = field[:max_length]

        return field

    @staticmethod
    def update_admin_status(db: Session, telegram_id: int, is_admin: bool) -> Optional[models.TelegramUser]:
        """Обновляет статус администратора пользователя"""
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            user.is_admin = is_admin
            db.commit()
            db.refresh(user)
            print(f"✅ Обновлен статус администратора для пользователя {telegram_id}: {is_admin}")
        return user

    @staticmethod
    def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[models.TelegramUser]:
        return db.query(models.TelegramUser).filter(models.TelegramUser.telegram_id == telegram_id).first()

    @staticmethod
    def update_user_balance(db: Session, telegram_id: int, coins: int) -> Optional[models.TelegramUser]:
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            user.coins = coins
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def update_user_stats(db: Session, telegram_id: int, win_coins: int, defeat_coins: int, max_win_coins: int,
                          min_win_coins: int) -> Optional[models.TelegramUser]:
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            user.win_coins = win_coins
            user.defeat_coins = defeat_coins
            user.max_win_coins = max_win_coins
            user.min_win_coins = min_win_coins
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def update_reference_link(db: Session, telegram_id: int, link: str) -> Optional[models.TelegramUser]:
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            user.reference_link = link
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def update_user_info(db: Session, telegram_id: int, **kwargs) -> Optional[models.TelegramUser]:
        """
        Обновляет информацию о пользователе
        """
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            # Обрабатываем текстовые поля (обрезаем если нужно)
            text_fields = ['username', 'first_name', 'last_name']
            for field in text_fields:
                if field in kwargs and kwargs[field] is not None:
                    kwargs[field] = UserRepository.clean_telegram_field(kwargs[field], 255)

            # Обновляем поля
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            db.commit()
            db.refresh(user)
            print(f"✅ Обновлена информация пользователя {telegram_id}: {list(kwargs.keys())}")
        return user

    @staticmethod
    def get_user_by_link(db: Session, link: str) -> Optional[models.TelegramUser]:
        return db.query(models.TelegramUser).filter(models.TelegramUser.reference_link == link).first()

    @staticmethod
    def get_all_users(db: Session) -> List[models.TelegramUser]:
        return db.query(models.TelegramUser).all()

    @staticmethod
    def search_users(db: Session, search_term: str) -> List[models.TelegramUser]:
        search_pattern = f"%{search_term}%"
        return db.query(models.TelegramUser).filter(
            or_(
                models.TelegramUser.username.like(search_pattern),
                models.TelegramUser.first_name.like(search_pattern)
            )
        ).all()

    @staticmethod
    def get_total_users_count(db: Session) -> int:
        return db.query(models.TelegramUser).count()

    @staticmethod
    def get_total_coins_sum(db: Session) -> int:
        result = db.query(func.sum(models.TelegramUser.coins)).scalar()
        return result if result else 0

    @staticmethod
    def update_max_bet(db: Session, telegram_id: int, bet_amount: int) -> Optional[models.TelegramUser]:
        """Обновляет максимальную ставку пользователя если текущая ставка больше"""
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            # Если у пользователя нет поля max_bet, создаем его
            if not hasattr(user, 'max_bet'):
                user.max_bet = 0

            # Обновляем только если текущая ставка больше предыдущего максимума
            if bet_amount > user.max_bet:
                user.max_bet = bet_amount
                db.commit()
                db.refresh(user)
                print(f"✅ Обновлена максимальная ставка для пользователя {telegram_id}: {bet_amount}")
            return user
        return None

    @staticmethod
    def create_user_safe(db: Session, telegram_id: int, first_name: str, username: str = None,
                         last_name: str = None, **kwargs) -> models.TelegramUser:
        """
        Безопасное создание пользователя с обработкой длинных полей
        """
        # Очищаем данные
        first_name = UserRepository.clean_telegram_field(first_name, 255) if first_name else None
        last_name = UserRepository.clean_telegram_field(last_name, 255) if last_name else None
        username = UserRepository.clean_telegram_field(username, 255) if username else None

        user = models.TelegramUser(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            coins=5000,
            **kwargs
        )

        try:
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"✅ Создан пользователь: {telegram_id} ({first_name or 'без имени'})")
            return user
        except Exception as e:
            db.rollback()
            print(f" Ошибка создания пользователя {telegram_id}: {e}")
            # Пытаемся получить существующего пользователя
            return UserRepository.get_user_by_telegram_id(db, telegram_id)

    @staticmethod
    def get_admin_users(db: Session):
        """Получить всех администраторов"""
        return db.query(models.TelegramUser).filter(models.TelegramUser.is_admin == True).all()

    @staticmethod
    def update_admin_status(db: Session, telegram_id: int, is_admin: bool) -> Optional[models.TelegramUser]:
        """Обновляет статус администратора пользователя"""
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            user.is_admin = is_admin
            db.commit()
            db.refresh(user)
            print(f"✅ Обновлен статус администратора для пользователя {telegram_id}: {is_admin}")
        return user

    # Добавьте в класс UserRepository:

    @staticmethod
    def get_all_chats(db: Session) -> List[int]:
        """Получает все уникальные chat_id из таблицы UserChat"""
        try:
            # Получаем все уникальные chat_id из UserChat
            chat_ids = db.query(models.UserChat.chat_id).distinct().all()
            return [chat_id[0] for chat_id in chat_ids if chat_id[0] is not None and chat_id[0] != 0]
        except Exception as e:
            print(f" Ошибка получения чатов: {e}")
            return []

    @staticmethod
    def get_active_chats(db: Session, days_active: int = 30) -> List[int]:
        """Получает активные чаты (где есть пользователи)"""
        try:
            # Простая реализация - возвращаем все чаты, где есть пользователи
            # Можно улучшить, добавив поле last_activity в модель UserChat
            chat_ids = db.query(models.UserChat.chat_id).distinct().all()
            return [chat_id[0] for chat_id in chat_ids if chat_id[0] is not None and chat_id[0] != 0]
        except Exception as e:
            print(f" Ошибка получения активных чатов: {e}")
            return []

    @staticmethod
    def get_chat_members_count(db: Session, chat_id: int) -> int:
        """Получает количество участников в чате"""
        try:
            return db.query(models.UserChat).filter(
                models.UserChat.chat_id == chat_id
            ).count()
        except Exception as e:
            print(f" Ошибка получения количества участников чата {chat_id}: {e}")
            return 0

    @staticmethod
    def get_chat_info(db: Session, chat_id: int) -> dict:
        """Получает информацию о чате"""
        try:
            members_count = UserRepository.get_chat_members_count(db, chat_id)

            # Получаем информацию о чате из таблицы Chat (если она существует)
            chat_info = None
            try:
                chat_info = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
            except:
                pass  # Если таблицы Chat нет, игнорируем

            # Определяем активность на основе наличия пользователей
            is_active = members_count > 0

            return {
                'chat_id': chat_id,
                'members_count': members_count,
                'title': getattr(chat_info, 'title', 'Неизвестно'),
                'chat_type': getattr(chat_info, 'chat_type', 'Неизвестно'),
                'is_active': is_active
            }
        except Exception as e:
            print(f" Ошибка получения информации о чате {chat_id}: {e}")
            return {'chat_id': chat_id, 'members_count': 0, 'title': 'Неизвестно', 'is_active': False}

    @staticmethod
    def get_user_chats(db, user_id: int) -> List[Tuple[int, str]]:
        """Получает список чатов, где находится пользователь"""
        try:
            from database.models import UserChatSearch

            chats = db.query(UserChatSearch.chat_id, UserChatSearch.chat_title) \
                .filter(UserChatSearch.user_id == user_id) \
                .order_by(UserChatSearch.created_at.desc()) \
                .all()
            return [(chat_id, chat_title) for chat_id, chat_title in chats]
        except Exception as e:
            logger.error(f"Error getting user chats for {user_id}: {e}")
            return []

    @staticmethod
    def get_user_by_username(db: Session, username: str):
        """Получить пользователя по username"""
        return db.query(models.TelegramUser).filter(models.TelegramUser.username == username).first()

    @staticmethod
    def search_users_by_name(db: Session, name: str, limit: int = 5):
        """Поиск пользователей по имени"""
        return db.query(models.TelegramUser).filter(
            (models.TelegramUser.first_name.ilike(f"%{name}%")) |
            (models.TelegramUser.last_name.ilike(f"%{name}%"))
        ).limit(limit).all()


# Остальные классы остаются без изменений...

class ReferenceRepository:
    @staticmethod
    def add_reference(db: Session, owner_telegram_id: int, reference_telegram_id: int) -> models.ReferenceUser:
        reference = models.ReferenceUser(
            owner_telegram_id=owner_telegram_id,
            reference_telegram_id=reference_telegram_id
        )
        db.add(reference)
        db.commit()
        db.refresh(reference)
        return reference

    @staticmethod
    def get_referrals_count(db: Session, user_id: int) -> int:
        """Получает количество рефералов пользователя"""
        try:
            # ИСПРАВЛЕНИЕ: Используем правильную модель и поле
            count = db.query(models.ReferenceUser).filter(
                models.ReferenceUser.owner_telegram_id == user_id
            ).count()
            return count
        except Exception as e:
            print(f" Ошибка получения количества рефералов: {e}")
            return 0

    @staticmethod
    def check_reference_exists(db: Session, reference_telegram_id: int) -> bool:
        return db.query(models.ReferenceUser).filter(
            models.ReferenceUser.reference_telegram_id == reference_telegram_id
        ).first() is not None

    @staticmethod
    def get_user_references(db: Session, owner_telegram_id: int) -> List[models.ReferenceUser]:
        return db.query(models.ReferenceUser).filter(
            models.ReferenceUser.owner_telegram_id == owner_telegram_id
        ).all()




class TransactionRepository:
    @staticmethod
    def create_transaction(db: Session, from_user_id: int, to_user_id: int, amount: int,
                           description: str = "") -> models.Transaction:
        transaction = models.Transaction(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            amount=amount,
            description=description
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        return transaction

    @staticmethod
    def get_user_transactions(db: Session, user_id: int, limit: int = 10) -> List[models.Transaction]:
        return db.query(models.Transaction).filter(
            or_(
                models.Transaction.from_user_id == user_id,
                models.Transaction.to_user_id == user_id
            )
        ).order_by(desc(models.Transaction.timestamp)).limit(limit).all()


class ChatRepository:
    staticmethod

    @staticmethod
    def get_top_bandit_stats(db: Session, chat_id: int, stat_type: str, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Получает топ по статистике бандита в чате"""
        try:
            # Сначала получаем пользователей чата
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            field_mapping = {
                'games_count': 'bandit_games_count',
                'total_wins': 'bandit_total_wins',
                'max_win': 'bandit_max_win',
                'max_bet': 'bandit_max_bet',
                'total_losses': 'bandit_total_losses',
                'max_loss': 'bandit_max_loss'
            }

            if stat_type not in field_mapping:
                return []

            field_name = field_mapping[stat_type]
            field = getattr(models.TelegramUser, field_name)

            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                field
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).filter(
                field > 0
            ).order_by(
                desc(field)
            ).limit(limit).all()

            return [
                (user_id, first_name or username or "ㅤ", int(value))
                for user_id, username, first_name, value in results
            ]

        except Exception as e:
            print(f" Ошибка получения топа бандита в чате: {e}")
            return []

    def add_user_to_chat(db: Session, user_id: int, chat_id: int, username: str = None,
                         first_name: str = None) -> models.UserChat:
        """Добавляет пользователя в чат, если его там еще нет, с автоматической регистрацией"""
        try:
            # Сначала проверяем, существует ли пользователь
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                # Автоматически создаем пользователя
                user = UserRepository.create_user_safe(
                    db, user_id,
                    first_name=first_name or "Пользователь",
                    username=username
                )

            # Проверяем, существует ли уже запись в чате
            existing = db.query(models.UserChat).filter_by(
                user_id=user_id,
                chat_id=chat_id
            ).first()

            if existing:
                return existing

            # Создаем новую запись
            user_chat = models.UserChat(user_id=user_id, chat_id=chat_id)
            db.add(user_chat)
            db.commit()
            db.refresh(user_chat)
            print(f"✅ Пользователь {user_id} добавлен в чат {chat_id}")
            return user_chat

        except Exception as e:
            db.rollback()
            print(f" Ошибка добавления пользователя в чат: {e}")
            # Пытаемся вернуть существующую запись при ошибке
            existing = db.query(models.UserChat).filter_by(
                user_id=user_id,
                chat_id=chat_id
            ).first()
            return existing

    @staticmethod
    def get_chat_users_count(db: Session, chat_id: int) -> int:
        return db.query(models.UserChat).filter(models.UserChat.chat_id == chat_id).count()

    @staticmethod
    def get_top_rich_in_chat(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, str, int]]:
        """Получает топ богатеев в чате без дубликатов"""
        try:
            # Используем DISTINCT для устранения дубликатов
            from sqlalchemy import distinct

            # Сначала получаем уникальные user_id из чата
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            # Затем получаем данные пользователей
            results = db.query(
                models.TelegramUser.telegram_id,  # Добавляем telegram_id
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.coins
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).order_by(
                desc(models.TelegramUser.coins)
            ).limit(limit).all()

            return [(telegram_id, username or "", first_name or "", coins) for telegram_id, username, first_name, coins
                    in results]

        except Exception as e:
            print(f" Ошибка получения топа богатеев: {e}")
            return []

    @staticmethod
    def get_user_rank_in_chat(db: Session, chat_id: int, user_id: int) -> Optional[int]:
        # Создаем подзапрос для ранжирования пользователей в чате
        subquery = db.query(
            models.TelegramUser.telegram_id,
            func.row_number().over(
                order_by=desc(models.TelegramUser.coins)
            ).label('position')
        ).join(
            models.UserChat,
            models.TelegramUser.telegram_id == models.UserChat.user_id
        ).filter(
            models.UserChat.chat_id == chat_id
        ).subquery()

        result = db.query(subquery.c.position).filter(
            subquery.c.telegram_id == user_id
        ).first()

        return result[0] if result else None

    @staticmethod
    def get_top_wins(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по выигранным ставкам в чате"""
        try:
            # Сначала получаем уникальные user_id из чата
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            # Затем получаем топ по выигрышам
            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.win_coins
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).filter(
                models.TelegramUser.win_coins > 0
            ).order_by(
                desc(models.TelegramUser.win_coins)
            ).limit(limit).all()

            return [(telegram_id, first_name or username or "ㅤ", win_coins)
                    for telegram_id, username, first_name, win_coins in results]

        except Exception as e:
            print(f" Ошибка получения топа выигрышей: {e}")
            return []

    @staticmethod
    def get_top_losses(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по проигранным ставкам в чате"""
        try:
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.defeat_coins
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).filter(
                models.TelegramUser.defeat_coins > 0
            ).order_by(
                desc(models.TelegramUser.defeat_coins)
            ).limit(limit).all()

            return [(telegram_id, first_name or username or "ㅤ", defeat_coins)
                    for telegram_id, username, first_name, defeat_coins in results]

        except Exception as e:
            print(f" Ошибка получения топа проигрышей: {e}")
            return []

    @staticmethod
    def get_top_max_win(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по максимальному выигрышу в чате"""
        try:
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.max_win_coins
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).filter(
                models.TelegramUser.max_win_coins > 0
            ).order_by(
                desc(models.TelegramUser.max_win_coins)
            ).limit(limit).all()

            return [(telegram_id, first_name or username or "ㅤ", max_win_coins)
                    for telegram_id, username, first_name, max_win_coins in results]

        except Exception as e:
            print(f" Ошибка получения топа максимальных выигрышей: {e}")
            return []

    @staticmethod
    def get_top_max_loss(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по максимальному проигрышу в чате (из RouletteTransaction)"""
        try:
            # Сначала получаем уникальные user_id из чата
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            # Получаем максимальные проигрыши из RouletteTransaction
            results = db.query(
                models.RouletteTransaction.user_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                func.min(models.RouletteTransaction.profit).label('max_loss')
            ).join(
                user_ids_subquery,
                models.RouletteTransaction.user_id == user_ids_subquery.c.user_id
            ).join(
                models.TelegramUser,
                models.RouletteTransaction.user_id == models.TelegramUser.telegram_id
            ).filter(
                models.RouletteTransaction.profit < 0  # Только проигрыши
            ).group_by(
                models.RouletteTransaction.user_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name
            ).order_by(
                func.min(models.RouletteTransaction.profit)
                # Сортируем по возрастанию (самые большие по модулю проигрыши)
            ).limit(limit).all()

            # Преобразуем отрицательные значения в положительные для отображения
            return [(user_id, first_name or username or "ㅤ", abs(max_loss))
                    for user_id, username, first_name, max_loss in results]

        except Exception as e:
            print(f" Ошибка получения топа максимальных проигрышей: {e}")
            return []

    @staticmethod
    def get_top_max_bet(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по максимальной ставке в чате"""
        try:
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.max_bet
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).filter(
                models.TelegramUser.max_bet > 0
            ).order_by(
                desc(models.TelegramUser.max_bet)
            ).limit(limit).all()

            return [(telegram_id, first_name or username or "ㅤ", max_bet)
                    for telegram_id, username, first_name, max_bet in results]

        except Exception as e:
            print(f" Ошибка получения топа максимальных ставок: {e}")
            return []

    @staticmethod
    def get_user_stats_rank(db: Session, chat_id: int, user_id: int, stat_type: str) -> Optional[int]:
        """Позиция пользователя в статистике по определенному типу"""
        try:
            if stat_type == "max_loss":
                # Для максимального проигрыша используем данные из RouletteTransaction
                user_ids_subquery = db.query(
                    models.UserChat.user_id
                ).filter(
                    models.UserChat.chat_id == chat_id
                ).distinct().subquery()

                # Создаем подзапрос с ранжированием по максимальным проигрышам
                subquery = db.query(
                    models.RouletteTransaction.user_id,
                    func.min(models.RouletteTransaction.profit).label('max_loss'),
                    func.row_number().over(
                        order_by=func.min(models.RouletteTransaction.profit)
                    ).label('position')
                ).join(
                    user_ids_subquery,
                    models.RouletteTransaction.user_id == user_ids_subquery.c.user_id
                ).filter(
                    models.RouletteTransaction.profit < 0
                ).group_by(models.RouletteTransaction.user_id).subquery()

                result = db.query(subquery.c.position).filter(
                    subquery.c.user_id == user_id
                ).first()

                return result[0] if result else None

            else:
                # Для других типов статистики используем существующую логику
                user_ids_subquery = db.query(
                    models.UserChat.user_id
                ).filter(
                    models.UserChat.chat_id == chat_id
                ).distinct().subquery()

                stat_fields = {
                    'wins': models.TelegramUser.win_coins,
                    'losses': models.TelegramUser.defeat_coins,
                    'max_win': models.TelegramUser.max_win_coins,
                    'max_bet': models.TelegramUser.max_bet
                }

                if stat_type not in stat_fields:
                    return None

                stat_field = stat_fields[stat_type]

                subquery = db.query(
                    models.TelegramUser.telegram_id,
                    func.row_number().over(
                        order_by=desc(stat_field)
                    ).label('position')
                ).join(
                    user_ids_subquery,
                    models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
                ).filter(
                    stat_field > 0
                ).subquery()

                result = db.query(subquery.c.position).filter(
                    subquery.c.telegram_id == user_id
                ).first()

                return result[0] if result else None

        except Exception as e:
            print(f" Ошибка получения позиции пользователя в статистике: {e}")
            return None

    @staticmethod
    def get_user_stats(db: Session, user_id: int, stat_type: str) -> Optional[int]:
        """Статистика пользователя по определенному типу"""
        try:
            if stat_type == "max_loss":
                # Для максимального проигрыша используем данные из RouletteTransaction
                result = db.query(
                    func.min(models.RouletteTransaction.profit)
                ).filter(
                    models.RouletteTransaction.user_id == user_id,
                    models.RouletteTransaction.profit < 0
                ).scalar()

                print(f"🔍 get_user_stats max_loss для {user_id}: raw_result={result}")

                if result is not None:
                    abs_result = abs(result)
                    print(f"🔍 get_user_stats max_loss для {user_id}: absolute_value={abs_result}")
                    return abs_result
                else:
                    print(f"🔍 get_user_stats max_loss для {user_id}: нет данных")
                    return 0

            else:
                # Для других типов статистики используем существующую логику
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    return None

                stat_values = {
                    'wins': user.win_coins,
                    'losses': user.defeat_coins,
                    'max_win': user.max_win_coins,
                    'max_bet': user.max_bet
                }

                return stat_values.get(stat_type)

        except Exception as e:
            print(f" Ошибка получения статистики пользователя: {e}")
            return None

    @staticmethod
    def check_user_losses(db: Session, user_id: int):
        """Проверяет проигрыши конкретного пользователя"""
        user_losses = db.query(models.RouletteTransaction).filter(
            models.RouletteTransaction.user_id == user_id,
            models.RouletteTransaction.profit < 0
        ).all()

        print(f"🔍 Проигрыши пользователя {user_id}: {len(user_losses)} записей")

        if user_losses:
            max_loss = min([loss.profit for loss in user_losses])
            print(f"🔍 Максимальный проигрыш: {max_loss} (абсолютное значение: {abs(max_loss)})")

        return len(user_losses)

    # Добавьте этот метод для отладки
    @staticmethod
    def debug_max_loss_data(db: Session, chat_id: int):
        """Отладочный метод для проверки данных о проигрышах"""
        print("🔍 Проверка данных для максимальных проигрышей:")

        # Проверяем DailyRecord
        daily_records = db.query(models.DailyRecord).filter(
            models.DailyRecord.amount < 0
        ).all()
        print(f"📊 DailyRecord с отрицательными значениями: {len(daily_records)}")

        # Проверяем RouletteTransaction
        roulette_losses = db.query(models.RouletteTransaction).filter(
            models.RouletteTransaction.profit < 0
        ).all()
        print(f"🎰 RouletteTransaction с проигрышами: {len(roulette_losses)}")

        # Проверяем пользователей чата
        chat_users = db.query(models.UserChat.user_id).filter(
            models.UserChat.chat_id == chat_id
        ).distinct().all()
        print(f"👥 Пользователей в чате: {len(chat_users)}")

        return {
            'daily_records_negative': len(daily_records),
            'roulette_losses': len(roulette_losses),
            'chat_users': len(chat_users)
        }



class DailyRecordRepository:
    @staticmethod
    def add_or_update_daily_record(db, user_id: int, username: str, first_name: str, amount: int, chat_id: int = 0):
        from datetime import date
        from database.models import DailyRecord

        today = date.today()

        # Ищем существующую запись за сегодня
        existing_record = db.query(DailyRecord).filter(
            DailyRecord.user_id == user_id,
            DailyRecord.record_date == today,
            DailyRecord.chat_id == chat_id
        ).first()

        if existing_record:
            # Обновляем если новый рекорд больше
            if amount > existing_record.amount:
                existing_record.amount = amount
                existing_record.username = username
                existing_record.first_name = first_name
                db.commit()
                return existing_record
            return existing_record
        else:
            # Создаем новую запись
            new_record = DailyRecord(
                user_id=user_id,
                username=username,
                first_name=first_name,
                amount=amount,
                record_date=today,
                chat_id=chat_id
            )
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            return new_record

    @staticmethod
    def get_top3_today(db: Session, chat_id: int) -> List[Tuple[int, str, int]]:
        today = date.today()
        results = db.query(
            models.DailyRecord.user_id,  # Добавляем user_id
            models.DailyRecord.username,
            models.DailyRecord.first_name,
            models.DailyRecord.amount
        ).filter(
            models.DailyRecord.record_date == today,
            models.DailyRecord.chat_id == chat_id
        ).order_by(
            desc(models.DailyRecord.amount)
        ).limit(3).all()

        top_scores = []
        for user_id, username, first_name, amount in results:
            display_name = first_name if first_name else username
            top_scores.append((user_id, display_name, amount))

        return top_scores

    @staticmethod
    def get_top_today(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Получает топ рекордов за сегодня с динамическим лимитом"""
        today = date.today()
        results = db.query(
            models.DailyRecord.user_id,
            models.DailyRecord.username,
            models.DailyRecord.first_name,
            models.DailyRecord.amount
        ).filter(
            models.DailyRecord.record_date == today,
            models.DailyRecord.chat_id == chat_id
        ).order_by(
            desc(models.DailyRecord.amount)
        ).limit(limit).all()

        top_scores = []
        for user_id, username, first_name, amount in results:
            display_name = first_name if first_name else username
            top_scores.append((user_id, display_name, amount))

        return top_scores

    @staticmethod
    def get_user_rank_today(db: Session, chat_id: int, user_id: int) -> Optional[int]:
        """Позиция пользователя в рекордах за сегодня"""
        today = date.today()

        # Создаем подзапрос для ранжирования
        subquery = db.query(
            models.DailyRecord.user_id,
            func.row_number().over(
                order_by=desc(models.DailyRecord.amount)
            ).label('position')
        ).filter(
            models.DailyRecord.record_date == today,
            models.DailyRecord.chat_id == chat_id
        ).subquery()

        result = db.query(subquery.c.position).filter(
            subquery.c.user_id == user_id
        ).first()

        return result[0] if result else None

    @staticmethod
    def get_user_daily_record_in_chat(db: Session, user_id: int, chat_id: int):
        """Получает рекорд пользователя за сегодня в конкретном чате"""
        today = date.today()
        return db.query(models.DailyRecord).filter(
            models.DailyRecord.user_id == user_id,
            models.DailyRecord.record_date == today,
            models.DailyRecord.chat_id == chat_id
        ).first()

    @staticmethod
    def add_or_update_daily_loss_record(db, user_id: int, username: str, first_name: str, loss_amount: int,
                                        chat_id: int = 0):
        """Добавляет или обновляет рекорд проигрыша за день"""
        from datetime import date
        from database.models import DailyLossRecord

        today = date.today()

        # Ищем существующую запись за сегодня
        existing_record = db.query(DailyLossRecord).filter(
            DailyLossRecord.user_id == user_id,
            DailyLossRecord.record_date == today,
            DailyLossRecord.chat_id == chat_id
        ).first()

        if existing_record:
            # Обновляем если новый рекорд больше (больший проигрыш)
            if loss_amount > existing_record.amount:
                existing_record.amount = loss_amount
                existing_record.username = username
                existing_record.first_name = first_name
                db.commit()
                return existing_record
            return existing_record
        else:
            # Создаем новую запись
            new_record = DailyLossRecord(
                user_id=user_id,
                username=username,
                first_name=first_name,
                amount=loss_amount,
                record_date=today,
                chat_id=chat_id
            )
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            return new_record

    @staticmethod
    def get_top_losses_today(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Получает топ рекордов проигрышей за сегодня"""
        from database.models import DailyLossRecord
        today = date.today()

        results = db.query(
            DailyLossRecord.user_id,
            DailyLossRecord.username,
            DailyLossRecord.first_name,
            DailyLossRecord.amount
        ).filter(
            DailyLossRecord.record_date == today,
            DailyLossRecord.chat_id == chat_id
        ).order_by(
            desc(DailyLossRecord.amount)
        ).limit(limit).all()

        top_losses = []
        for user_id, username, first_name, amount in results:
            display_name = first_name if first_name else username
            top_losses.append((user_id, display_name, amount))

        return top_losses



class RouletteRepository:
    @staticmethod
    def create_roulette_transaction(db: Session, user_id: int, amount: int, is_win: bool,
                                    bet_type: str = None, bet_value: str = None,
                                    result_number: int = None, profit: int = None) -> models.RouletteTransaction:
        if profit is None:
            profit = amount if is_win else -amount

        transaction = models.RouletteTransaction(
            user_id=user_id,
            amount=amount,
            is_win=is_win,
            bet_type=bet_type,
            bet_value=bet_value,
            result_number=result_number,
            profit=profit
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        return transaction

    @staticmethod
    def get_user_bet_history(db: Session, user_id: int, limit: int = 10) -> List[models.RouletteTransaction]:
        return db.query(models.RouletteTransaction).filter(
            models.RouletteTransaction.user_id == user_id
        ).order_by(desc(models.RouletteTransaction.created_at)).limit(limit).all()

    @staticmethod
    def add_game_log(db: Session, chat_id: int, result: int, color_emoji: str) -> models.RouletteGameLog:
        log = models.RouletteGameLog(
            chat_id=chat_id,
            result=result,
            color_emoji=color_emoji
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_recent_game_logs(db: Session, chat_id: int, limit: int = 10) -> List[models.RouletteGameLog]:
        return db.query(models.RouletteGameLog).filter(
            models.RouletteGameLog.chat_id == chat_id
        ).order_by(desc(models.RouletteGameLog.created_at)).limit(limit).all()

    @staticmethod
    def get_user_recent_bets(db: Session, user_id: int, limit: int = 5) -> List:
        """Получает последние ставки пользователя"""
        try:
            bets = db.query(models.RouletteTransaction).filter(
                models.RouletteTransaction.user_id == user_id
            ).order_by(
                desc(models.RouletteTransaction.created_at)
            ).limit(limit).all()
            return bets
        except Exception as e:
            print(f" Ошибка получения истории ставок: {e}")
            return []


class ShopRepository:
    @staticmethod
    def add_user_purchase(db: Session, user_id: int, item_id: int, item_name: str, price: int,
                          chat_id: int = -1, duration_days: int = 0):
        """Добавить покупку с возможностью указать срок действия"""
        from datetime import datetime, timedelta

        expires_at = None
        if duration_days > 0:
            expires_at = datetime.now() + timedelta(days=duration_days)

        # Используем прямую модель UserPurchase с правильными названиями полей
        purchase = models.UserPurchase(
            user_id=user_id,
            item_id=item_id,
            item_name=item_name,
            price=price,
            chat_id=chat_id,
            purchased_at=datetime.now(),
            expires_at=expires_at
        )

        db.add(purchase)
        db.commit()
        db.refresh(purchase)
        return purchase

    @staticmethod
    def has_user_purchased_in_chat(db: Session, user_id: int, item_id: int, chat_id: int) -> bool:
        """Проверяет, купил ли пользователь товар в конкретном чате"""
        purchase = db.query(models.UserPurchase).filter(
            models.UserPurchase.user_id == user_id,
            models.UserPurchase.item_id == item_id,
            models.UserPurchase.chat_id == chat_id
        ).first()

        if not purchase:
            return False

        # Проверяем срок действия если есть
        if purchase.expires_at:
            return purchase.expires_at > datetime.now()

        return True

    @staticmethod
    def get_user_purchases_in_chat(db: Session, user_id: int, chat_id: int) -> list:
        """Получает список ID товаров, купленных пользователем в конкретном чате"""
        purchases = db.query(models.UserPurchase).filter(
            models.UserPurchase.user_id == user_id,
            models.UserPurchase.chat_id == chat_id
        ).all()
        return [purchase.item_id for purchase in purchases]

    @staticmethod
    def get_user_purchases(db: Session, user_id: int, chat_id: int = None) -> List[int]:
        """Получает покупки пользователя, с фильтром по чату если указан"""
        query = db.query(models.UserPurchase.item_id).filter(
            models.UserPurchase.user_id == user_id
        )

        if chat_id is not None:
            query = query.filter(models.UserPurchase.chat_id == chat_id)

        purchases = query.all()
        return [purchase[0] for purchase in purchases]

    # УДАЛИТЕ ДУБЛИРУЮЩИЕСЯ МЕТОДЫ:
    # has_roulette_limit_removal - используйте has_user_purchased_in_chat с item_id=5
    # get_roulette_limit_removal_purchases - используйте get_user_purchases_in_chat с item_id=5

    @staticmethod
    def get_user_purchases_with_details(db, user_id: int):
        """Получить все покупки пользователя с деталями"""
        try:
            purchases = db.query(models.UserPurchase).filter(
                models.UserPurchase.user_id == user_id
            ).all()
            return purchases
        except Exception as e:
            print(f" Ошибка получения покупок: {e}")
            return []

    @staticmethod
    def remove_user_purchase(db, user_id: int, item_id: int):
        """Удалить покупку пользователя"""
        try:
            result = db.query(models.UserPurchase).filter(
                models.UserPurchase.user_id == user_id,
                models.UserPurchase.item_id == item_id
            ).delete()
            db.commit()
            return result > 0
        except Exception as e:
            db.rollback()
            print(f" Ошибка удаления покупки: {e}")
            return False

    @staticmethod
    def extend_user_purchase(db, user_id: int, item_id: int, days: int):
        """Продлить покупку пользователя"""
        purchase = db.query(models.UserPurchase).filter(
            models.UserPurchase.user_id == user_id,
            models.UserPurchase.item_id == item_id
        ).first()

        if purchase and purchase.expires_at:
            from datetime import datetime, timedelta
            # Если срок истек, устанавливаем от текущей даты
            if purchase.expires_at < datetime.now():
                purchase.expires_at = datetime.now() + timedelta(days=days)
            else:
                purchase.expires_at += timedelta(days=days)
            db.commit()
            return True
        return False

    @staticmethod
    def has_active_purchase(db, user_id: int, item_id: int) -> bool:
        """Проверяет, есть ли у пользователя активная покупка товара (в любом чате)"""
        try:
            purchase = db.query(models.UserPurchase).filter(
                models.UserPurchase.user_id == user_id,
                models.UserPurchase.item_id == item_id
            ).first()

            if not purchase:
                return False

            # Если есть срок действия, проверяем не истек ли он
            if purchase.expires_at:
                return purchase.expires_at > datetime.now()

            # Если срока нет - привилегия действует вечно
            return True

        except Exception as e:
            print(f" Ошибка проверки активной покупки: {e}")
            return False

    @staticmethod
    def get_active_purchases(db, user_id: int) -> List[int]:
        """Получает список ID активных покупок пользователя"""
        try:
            purchases = db.query(models.UserPurchase).filter(
                models.UserPurchase.user_id == user_id
            ).all()

            active_purchases = []
            for purchase in purchases:
                if purchase.expires_at:
                    if purchase.expires_at > datetime.now():
                        active_purchases.append(purchase.item_id)
                else:
                    # Привилегии без срока действия считаются активными
                    active_purchases.append(purchase.item_id)

            return active_purchases

        except Exception as e:
            print(f" Ошибка получения активных покупок: {e}")
            return []

    @staticmethod
    def cleanup_expired_purchases(db):
        """Очищает истекшие покупки"""
        try:
            expired_count = db.query(models.UserPurchase).filter(
                models.UserPurchase.expires_at <= datetime.now()
            ).delete()
            db.commit()
            return expired_count
        except Exception as e:
            db.rollback()
            print(f" Ошибка очистки истекших покупок: {e}")
            return 0


class TransferLimitRepository:
    @staticmethod
    def add_transfer_limit(db: Session, user_id: int, amount: int, transfer_time: datetime) -> models.TransferLimit:
        limit = models.TransferLimit(
            user_id=user_id,
            amount=amount,
            transfer_time=transfer_time
        )
        db.add(limit)
        db.commit()
        db.refresh(limit)
        return limit

    @staticmethod
    def get_user_transfers_last_6h(db: Session, user_id: int) -> List[models.TransferLimit]:
        six_hours_ago = datetime.now() - timedelta(hours=6)
        return db.query(models.TransferLimit).filter(
            models.TransferLimit.user_id == user_id,
            models.TransferLimit.transfer_time >= six_hours_ago
        ).order_by(desc(models.TransferLimit.transfer_time)).all()

    @staticmethod
    def clean_old_transfers(db: Session):
        seven_days_ago = datetime.now() - timedelta(days=1)
        deleted_count = db.query(models.TransferLimit).filter(
            models.TransferLimit.transfer_time < seven_days_ago
        ).delete()
        db.commit()
        return deleted_count

    @staticmethod
    def clean_daily_old_data(db: Session):
        """Ежедневная очистка старых данных (вызывать каждый день в 00:00)"""
        deleted_data = {}

        # 1. Очищаем трансферы старше 7 дней
        deleted_data['transfers'] = TransferLimitRepository.clean_old_transfers(db)

        # 2. Очищаем старые лимиты рулетки (старше 7 дней)
        deleted_data['roulette_limits'] = RouletteLimitRepository.cleanup_old_limits(db)

        # 3. Очищаем старые транзакции (старше 30 дней)
        thirty_days_ago = datetime.now() - timedelta(days=3)
        deleted_data['transactions'] = db.query(models.Transaction).filter(
            models.Transaction.timestamp < thirty_days_ago
        ).delete()

        # 4. Очищаем старые ставки в рулетке (старше 30 дней)
        deleted_data['roulette_bets'] = db.query(models.RouletteTransaction).filter(
            models.RouletteTransaction.created_at < thirty_days_ago
        ).delete()

        # 5. Очищаем старые логи игр (старше 14 дней)
        fourteen_days_ago = datetime.now() - timedelta(days=1)
        deleted_data['game_logs'] = db.query(models.RouletteGameLog).filter(
            models.RouletteGameLog.created_at < fourteen_days_ago
        ).delete()

        # 6. Очищаем старые ежедневные рекорды (старше 7 дней)
        seven_days_ago = date.today() - timedelta(days=3)
        deleted_data['daily_records'] = db.query(models.DailyRecord).filter(
            models.DailyRecord.record_date < seven_days_ago
        ).delete()

        db.commit()

        print(f"✅ Ежедневная очистка завершена. Удалено: {deleted_data}")
        return deleted_data



class RouletteLimitRepository:
    @staticmethod
    def get_or_create_limit(db: Session, user_id: int, chat_id: int, target_date: date = None) -> models.RouletteLimit:
        """Получает или создает запись лимита для пользователя в конкретном чате"""
        if target_date is None:
            target_date = date.today()

        # Сначала пытаемся найти существующую запись
        limit = db.query(models.RouletteLimit).filter(
            models.RouletteLimit.user_id == user_id,
            models.RouletteLimit.chat_id == chat_id,
            models.RouletteLimit.date == target_date
        ).first()

        if not limit:
            try:
                # Создаем новую запись
                limit = models.RouletteLimit(
                    user_id=user_id,
                    chat_id=chat_id,
                    date=target_date,
                    spin_count=0
                )
                db.add(limit)
                db.commit()
                db.refresh(limit)
                print(f"✅ Создана новая запись лимита для user_id={user_id}, chat_id={chat_id}, date={target_date}")
            except Exception as e:
                db.rollback()
                # Если произошла ошибка (например, запись уже существует), пытаемся снова найти
                print(f"⚠️ Ошибка создания записи, пытаемся найти существующую: {e}")
                limit = db.query(models.RouletteLimit).filter(
                    models.RouletteLimit.user_id == user_id,
                    models.RouletteLimit.chat_id == chat_id,
                    models.RouletteLimit.date == target_date
                ).first()
                if limit:
                    print(f"✅ Найдена существующая запись после ошибки создания")

        return limit

    @staticmethod
    def increment_spin_count(db: Session, user_id: int, chat_id: int) -> bool:
        """Увеличивает счетчик прокрутов для пользователя в конкретном чате"""
        try:
            today = date.today()
            limit = RouletteLimitRepository.get_or_create_limit(db, user_id, chat_id, today)
            limit.spin_count += 1
            db.commit()
            return True
        except Exception as e:
            print(f" Ошибка увеличения счетчика прокрутов: {e}")
            db.rollback()
            return False

    @staticmethod
    def get_today_spin_count(db: Session, user_id: int, chat_id: int) -> int:
        """Возвращает количество прокрутов пользователя за сегодня в конкретном чате"""
        today = date.today()
        limit = db.query(models.RouletteLimit).filter(
            models.RouletteLimit.user_id == user_id,
            models.RouletteLimit.chat_id == chat_id,  # ДОБАВЬТЕ ЭТУ СТРОКУ
            models.RouletteLimit.date == today
        ).first()

        return limit.spin_count if limit else 0

    @staticmethod
    def cleanup_old_limits(db: Session, days_old: int = 7):
        """Очищает старые записи лимитов"""
        try:
            cutoff_date = date.today() - timedelta(days=days_old)
            deleted_count = db.query(models.RouletteLimit).filter(
                models.RouletteLimit.date < cutoff_date
            ).delete()
            db.commit()
            return deleted_count
        except Exception as e:
            print(f" Ошибка очистки старых лимитов: {e}")
            db.rollback()
            return 0

    @staticmethod
    def get_user_chat_limit_stats(db: Session, user_id: int, chat_id: int) -> dict:
        """Возвращает статистику лимитов пользователя в конкретном чате"""
        today = date.today()

        # Сегодняшняя запись
        today_record = db.query(models.RouletteLimit).filter(
            models.RouletteLimit.user_id == user_id,
            models.RouletteLimit.chat_id == chat_id,
            models.RouletteLimit.date == today
        ).first()

        # Общая статистика по этому чату
        chat_stats = db.query(
            func.count(models.RouletteLimit.id).label('total_days'),
            func.sum(models.RouletteLimit.spin_count).label('total_spins')
        ).filter(
            models.RouletteLimit.user_id == user_id,
            models.RouletteLimit.chat_id == chat_id
        ).first()

        return {
            'today_spins': today_record.spin_count if today_record else 0,
            'total_days_in_chat': chat_stats.total_days or 0,
            'total_spins_in_chat': chat_stats.total_spins or 0
        }

    @staticmethod
    def get_user_purchases_by_chat(db: Session, user_id: int) -> List[models.UserPurchase]:
        """Получает покупки пользователя (для проверки снятия лимита)"""
        return db.query(models.UserPurchase).filter(
            models.UserPurchase.user_id == user_id
        ).all()


class ChatStatsRepository:
    @staticmethod
    def add_chat(db: Session, chat_id: int, chat_title: str = None, chat_type: str = None) -> models.Chat:
        """Добавляет чат в базу данных"""
        try:
            chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
            if not chat:
                chat = models.Chat(
                    chat_id=chat_id,
                    title=chat_title,
                    chat_type=chat_type,
                    is_active=True
                )
                db.add(chat)
                db.commit()
                db.refresh(chat)
                print(f"✅ Добавлен чат: {chat_id} ({chat_title})")
            return chat
        except Exception as e:
            db.rollback()
            print(f" Ошибка добавления чата: {e}")
            return None

    @staticmethod
    def update_chat_title(db: Session, chat_id: int, new_title: str) -> bool:
        """Обновляет название чата"""
        try:
            chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
            if chat:
                chat.title = new_title
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            print(f" Ошибка обновления названия чата: {e}")
            return False

    @staticmethod
    def get_all_chats(db: Session) -> List[int]:
        """Получает все уникальные chat_id из таблицы UserChat"""
        try:
            # Получаем все уникальные chat_id из UserChat
            chat_ids = db.query(models.UserChat.chat_id).distinct().all()
            return [chat_id[0] for chat_id in chat_ids]
        except Exception as e:
            print(f" Ошибка получения чатов: {e}")
            return []

    @staticmethod
    def get_chat_stats(db: Session, chat_id: int) -> dict:
        """Получает статистику чата"""
        try:
            # Базовая информация о чате
            chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
            if not chat:
                return {}

            # Количество участников
            members_count = db.query(models.UserChat).filter(
                models.UserChat.chat_id == chat_id
            ).count()

            # Активность за последнюю неделю
            week_ago = datetime.now() - timedelta(days=7)
            recent_activity = db.query(models.RouletteTransaction).filter(
                models.RouletteTransaction.chat_id == chat_id,
                models.RouletteTransaction.created_at >= week_ago
            ).count()

            # Топ пользователей по балансу в этом чате
            top_users = ChatRepository.get_top_rich_in_chat(db, chat_id, limit=5)

            return {
                'chat_id': chat_id,
                'title': chat.title,
                'type': chat.chat_type,
                'members_count': members_count,
                'recent_activity': recent_activity,
                'top_users': top_users,
                'created_at': chat.created_at
            }
        except Exception as e:
            print(f" Ошибка получения статистики чата: {e}")
            return {}



from datetime import datetime
# database/crud.py (исправленный класс BotStopRepository)
class BotStopRepository:
    @staticmethod
    def create_block_record(db, user_id: int, blocked_user_id: int):
        """Создает запись о блокировке пользователя"""
        # Проверяем, существует ли уже такая запись
        existing = db.query(models.BotStop).filter(
            models.BotStop.user_id == user_id,
            models.BotStop.blocked_user_id == blocked_user_id
        ).first()

        if existing:
            return existing

        record = models.BotStop(
            user_id=user_id,
            blocked_user_id=blocked_user_id,
            created_at=datetime.now()
        )
        db.add(record)
        return record

    @staticmethod
    def get_block_record(db, user_id: int, blocked_user_id: int):
        """Получает запись о блокировке"""
        return db.query(models.BotStop).filter(
            models.BotStop.user_id == user_id,
            models.BotStop.blocked_user_id == blocked_user_id
        ).first()

    @staticmethod
    def delete_block_record(db, user_id: int, blocked_user_id: int):
        """Удаляет запись о блокировке"""
        try:
            # Сначала проверим, существует ли запись
            existing = db.query(models.BotStop).filter(
                models.BotStop.user_id == user_id,
                models.BotStop.blocked_user_id == blocked_user_id
            ).first()

            if existing:
                logger.info(f"🔍 BEFORE DELETE: Найдена запись {user_id} -> {blocked_user_id}")

                # Удаляем запись
                db.query(models.BotStop).filter(
                    models.BotStop.user_id == user_id,
                    models.BotStop.blocked_user_id == blocked_user_id
                ).delete()

                # Проверяем что запись удалена
                after_delete = db.query(models.BotStop).filter(
                    models.BotStop.user_id == user_id,
                    models.BotStop.blocked_user_id == blocked_user_id
                ).first()

                if after_delete is None:
                    logger.info(f"✅ DELETE SUCCESS: Запись {user_id} -> {blocked_user_id} удалена")
                else:
                    logger.error(f" DELETE FAILED: Запись {user_id} -> {blocked_user_id} все еще существует!")
            else:
                logger.warning(f"⚠️ DELETE: Запись {user_id} -> {blocked_user_id} не найдена")

        except Exception as e:
            logger.error(f" DELETE ERROR: Ошибка удаления записи {user_id} -> {blocked_user_id}: {e}")
            raise

    @staticmethod
    def is_reply_blocked(db, current_user_id: int, replied_to_user_id: int) -> bool:
        """
        Проверяет, может ли current_user_id отвечать на сообщения replied_to_user_id
        Возвращает True если ответ ЗАБЛОКИРОВАН

        Правильная логика:
        - user1 использует "бот стоп" на user2 → создается запись (user1, user2)
        - Это означает: "user1 заблокировал user2"
        - Когда user2 отвечает на user1 → проверяем: "user1 заблокировал user2?" = ДА → удаляем
        """
        # Ищем запись где:
        # user_id = replied_to_user_id (тот, на чье сообщение отвечают)
        # blocked_user_id = current_user_id (тот, кто отвечает)
        # Это означает: "replied_to_user_id заблокировал current_user_id"
        record = db.query(models.BotStop).filter(
            models.BotStop.user_id == replied_to_user_id,
            models.BotStop.blocked_user_id == current_user_id
        ).first()

        is_blocked = record is not None
        logger.info(f"🔍 BLOCK CHECK: {replied_to_user_id} заблокировал {current_user_id} = {is_blocked}")
        return is_blocked


# database/crud.py (УЛУЧШЕННЫЙ класс BotSearchRepository)
class BotSearchRepository:
    @staticmethod
    def add_user_chat(db, user_id: int, chat_id: int, chat_title: str):
        """Добавляет или обновляет чат пользователя в базе данных"""
        from database.models import UserChatSearch
        try:
            # Проверяем, существует ли уже такая запись
            existing = db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id,
                UserChatSearch.chat_id == chat_id
            ).first()

            if existing:
                # Обновляем существующую запись
                existing.chat_title = chat_title
                existing.last_activity = datetime.now()
                print(f"🔄 Обновлен чат пользователя {user_id}: {chat_title}")
            else:
                # Создаем новую запись
                record = UserChatSearch(
                    user_id=user_id,
                    chat_id=chat_id,
                    chat_title=chat_title,
                    last_activity=datetime.now()
                )
                db.add(record)
                print(f"✅ Добавлен новый чат пользователя {user_id}: {chat_title}")

            db.commit()
            return True
        except Exception as e:
            db.rollback()
            print(f" Ошибка добавления чата пользователя: {e}")
            return False

    @staticmethod
    def add_user_nick(db, user_id: int, nick: str):
        """Добавляет ник пользователя в базу данных"""
        from database.models import UserNickSearch
        try:
            # Очищаем ник от лишних пробелов
            nick = ' '.join(nick.split()).strip()

            if not nick or len(nick) > 255:
                return False

            # Проверяем, существует ли уже такая запись
            existing = db.query(UserNickSearch).filter(
                UserNickSearch.user_id == user_id,
                UserNickSearch.nick == nick
            ).first()

            if not existing:
                record = UserNickSearch(
                    user_id=user_id,
                    nick=nick
                )
                db.add(record)
                db.commit()
                print(f"✅ Добавлен новый ник пользователя {user_id}: {nick}")
                return True
            return False
        except Exception as e:
            db.rollback()
            print(f" Ошибка добавления ника пользователя: {e}")
            return False

    @staticmethod
    def get_user_chats(db, user_id: int) -> List[Tuple[int, str]]:
        """Получает список чатов, где находится пользователь"""
        try:
            from database.models import UserChatSearch

            chats = db.query(UserChatSearch.chat_id, UserChatSearch.chat_title) \
                .filter(UserChatSearch.user_id == user_id) \
                .order_by(UserChatSearch.created_at.desc()) \
                .all()
            return [(chat_id, chat_title) for chat_id, chat_title in chats]
        except Exception as e:
            logger.error(f"Error getting user chats for {user_id}: {e}")
            return []

    @staticmethod
    def get_user_chats_with_activity(db, user_id: int, limit: int = 50):
        """Получает чаты пользователя с информацией об активности"""
        from database.models import UserChatSearch
        try:
            chats = db.query(
                UserChatSearch.chat_title,
                UserChatSearch.chat_id,
                UserChatSearch.last_activity
            ).filter(
                UserChatSearch.user_id == user_id
            ).order_by(
                UserChatSearch.last_activity.desc().nullslast(),
                UserChatSearch.created_at.desc()
            ).limit(limit).all()
            return chats
        except Exception as e:
            print(f" Ошибка получения чатов с активностью: {e}")
            return []

    @staticmethod
    def get_user_nicks(db, user_id: int, limit: int = 20):
        """Получает список ников пользователя"""
        from database.models import UserNickSearch
        try:
            nicks = db.query(UserNickSearch.nick).filter(
                UserNickSearch.user_id == user_id
            ).order_by(UserNickSearch.created_at.desc()).limit(limit).all()
            return [nick for (nick,) in nicks]
        except Exception as e:
            print(f" Ошибка получения ников пользователя: {e}")
            return []

    @staticmethod
    def get_user_nicks_with_dates(db, user_id: int, limit: int = 20):
        """Получает ники пользователя с датами"""
        from database.models import UserNickSearch
        try:
            nicks = db.query(
                UserNickSearch.nick,
                UserNickSearch.created_at
            ).filter(
                UserNickSearch.user_id == user_id
            ).order_by(
                UserNickSearch.created_at.desc()
            ).limit(limit).all()
            return nicks
        except Exception as e:
            print(f" Ошибка получения ников с датами: {e}")
            return []

    @staticmethod
    def get_first_seen_date(db, user_id: int):
        """Получает дату первого появления пользователя"""
        from database.models import UserChatSearch
        try:
            result = db.query(
                func.min(UserChatSearch.created_at)
            ).filter(
                UserChatSearch.user_id == user_id
            ).scalar()
            return result
        except Exception as e:
            print(f" Ошибка получения даты первого появления: {e}")
            return None

    @staticmethod
    def get_last_seen_date(db, user_id: int):
        """Получает дату последней активности"""
        from database.models import UserChatSearch
        try:
            # Сначала пытаемся получить по last_activity
            result = db.query(
                func.max(UserChatSearch.last_activity)
            ).filter(
                UserChatSearch.user_id == user_id
            ).scalar()

            if result:
                return result

            # Если нет last_activity, используем created_at
            return db.query(
                func.max(UserChatSearch.created_at)
            ).filter(
                UserChatSearch.user_id == user_id
            ).scalar()
        except Exception as e:
            print(f" Ошибка получения даты последней активности: {e}")
            return None

    @staticmethod
    def get_user_command_count(db, user_id: int):
        """Считает общее количество активностей пользователя"""
        from database.models import UserChatSearch
        try:
            return db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id
            ).count()
        except Exception as e:
            print(f" Ошибка получения количества активностей: {e}")
            return 0

    @staticmethod
    def cleanup_old_data(db, days_old: int = 30):
        """Очищает старые данные поиска"""
        from database.models import UserChatSearch, UserNickSearch
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)

            # Удаляем старые записи чатов
            deleted_chats = db.query(UserChatSearch).filter(
                UserChatSearch.last_activity < cutoff_date
            ).delete()

            # Удаляем старые записи ников
            deleted_nicks = db.query(UserNickSearch).filter(
                UserNickSearch.created_at < cutoff_date
            ).delete()

            db.commit()
            print(f"✅ Очищено данных поиска: {deleted_chats} чатов, {deleted_nicks} ников")
            return {'chats': deleted_chats, 'nicks': deleted_nicks}
        except Exception as e:
            db.rollback()
            print(f" Ошибка очистки старых данных: {e}")
            return {'chats': 0, 'nicks': 0}

    @staticmethod
    def get_user_search_stats(db, user_id: int):
        """Получает статистику поиска по пользователю"""
        from database.models import UserChatSearch, UserNickSearch
        try:
            # Количество чатов
            chats_count = db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id
            ).count()

            # Количество ников
            nicks_count = db.query(UserNickSearch).filter(
                UserNickSearch.user_id == user_id
            ).count()

            # Дата первого появления
            first_seen = BotSearchRepository.get_first_seen_date(db, user_id)

            # Дата последней активности
            last_seen = BotSearchRepository.get_last_seen_date(db, user_id)

            return {
                'chats_count': chats_count,
                'nicks_count': nicks_count,
                'first_seen': first_seen,
                'last_seen': last_seen,
                'total_activities': BotSearchRepository.get_user_command_count(db, user_id)
            }
        except Exception as e:
            print(f" Ошибка получения статистики поиска: {e}")
            return {
                'chats_count': 0,
                'nicks_count': 0,
                'first_seen': None,
                'last_seen': None,
                'total_activities': 0
            }

    @staticmethod
    def log_user_activity(db, user_id: int, chat_id: int, chat_title: str, nick: str):
        """Комплексное логирование активности пользователя"""
        try:
            # Логируем чат
            chat_success = BotSearchRepository.add_user_chat(db, user_id, chat_id, chat_title)

            # Логируем ник
            nick_success = BotSearchRepository.add_user_nick(db, user_id, nick)

            return {
                'chat_logged': chat_success,
                'nick_logged': nick_success,
                'timestamp': datetime.now()
            }
        except Exception as e:
            print(f" Ошибка логирования активности: {e}")
            return {
                'chat_logged': False,
                'nick_logged': False,
                'timestamp': datetime.now()
            }

    @staticmethod
    def search_users_by_nick(db, search_term: str, limit: int = 20):
        """Ищет пользователей по нику"""
        from database.models import UserNickSearch
        try:
            search_pattern = f"%{search_term}%"
            results = db.query(
                UserNickSearch.user_id,
                UserNickSearch.nick
            ).filter(
                UserNickSearch.nick.ilike(search_pattern)
            ).distinct().limit(limit).all()

            return [(user_id, nick) for user_id, nick in results]
        except Exception as e:
            print(f" Ошибка поиска пользователей по нику: {e}")
            return []

    @staticmethod
    def get_chat_users(db, chat_id: int, limit: int = 50):
        """Получает пользователей из конкретного чата"""
        from database.models import UserChatSearch
        try:
            users = db.query(
                UserChatSearch.user_id
            ).filter(
                UserChatSearch.chat_id == chat_id
            ).distinct().limit(limit).all()

            return [user_id for (user_id,) in users]
        except Exception as e:
            print(f" Ошибка получения пользователей чата: {e}")
            return []


class Repository:
    @staticmethod
    def get_user_arrest(db, user_id: int):
        """Получает информацию об аресте пользователя"""
        from database.models import Arrest
        return db.query(Arrest).filter(
            Arrest.user_id == user_id,
            Arrest.release_time > datetime.now()
        ).first()

    @staticmethod
    def arrest_user(db, user_id: int, release_time: datetime):
        """Арестовывает пользователя"""
        from database.models import Arrest
        # Удаляем старые аресты
        db.query(Arrest).filter(Arrest.user_id == user_id).delete()

        # Создаем новый арест
        arrest = Arrest(
            user_id=user_id,
            release_time=release_time
        )
        db.add(arrest)

    @staticmethod
    def get_last_steal_time(db, user_id: int):
        """Получает время последней кражи пользователя"""
        from database.models import StealAttempt
        last_attempt = db.query(StealAttempt).filter(
            StealAttempt._id == user_id
        ).order_by(StealAttempt.attempt_time.desc()).first()

        return last_attempt.attempt_time if last_attempt else None

    @staticmethod
    def get_user_balance(db, user_id: int) -> int:
        """Получает баланс пользователя"""
        from database.models import TelegramUser
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == user_id).first()
        return int(user.coins) if user and user.coins else 0

    @staticmethod
    def update_user_balance(user_id: int, amount: int):
        """Обновить баланс пользователя"""
        db = SessionLocal()

        try:
            # Обновляем баланс пользователя
            user = db.query(models.TelegramUser).filter(models.TelegramUser.telegram_id == user_id).first()
            if user:
                user.coins += amount
                db.commit()

                # ОБНОВЛЯЕМ КАПИТАЛ КЛАНА
                clan_db = ClanDatabase(db)
                clan_db.update_clan_coins_on_balance_change(user_id)

        finally:
            db.close()

    @staticmethod
    def record_steal_attempt(db, thief_id: int, victim_id: int, successful: bool, amount: int):
        """Записывает попытку кражи в таблицу StealAttempt"""
        try:
            # Проверяем, не существует ли уже такой записи (дублирование за 1 минуту)
            existing = db.query(models.StealAttempt).filter(
                models.StealAttempt.thief_id == thief_id,
                models.StealAttempt.victim_id == victim_id,
                models.StealAttempt.successful == successful,
                models.StealAttempt.attempt_time >= datetime.now() - timedelta(minutes=1)
            ).first()

            if existing:
                return existing

            # ВАЖНО: Используем autocommit=False для предотвращения конфликтов с ID
            attempt = models.StealAttempt(
                thief_id=thief_id,
                victim_id=victim_id,
                successful=successful,
                amount=amount if successful else 0,  # Сохраняем сумму только при успешной краже
                attempt_time=datetime.now()
            )
            db.add(attempt)

            # Используем flush вместо commit для сохранения ID
            db.flush()

            print(f"✅ Запись кражи добавлена: вор={thief_id}, жертва={victim_id}, сумма={amount}, успех={successful}")

            # Сразу обновляем статистику пользователя
            user = UserRepository.get_user_by_telegram_id(db, thief_id)
            if user:
                # Увеличиваем счетчик игр бандита
                user.bandit_games_count = (user.bandit_games_count or 0) + 1

                if successful:
                    # Успешная кража
                    user.bandit_total_wins = (user.bandit_total_wins or 0) + amount

                    if amount > (user.bandit_max_win or 0):
                        user.bandit_max_win = amount

                    # Общая статистика
                    user.win_coins = (user.win_coins or 0) + amount

                    if amount > (user.max_win_coins or 0):
                        user.max_win_coins = amount
                else:
                    # Неудачная попытка
                    user.bandit_total_losses = (user.bandit_total_losses or 0) + 1

                # Обновляем максимальную ставку (сумму кражи)
                if amount > (user.bandit_max_bet or 0):
                    user.bandit_max_bet = amount

                if amount > (user.max_bet or 0):
                    user.max_bet = amount

                print(f"✅ Статистика бандита обновлена для {thief_id}: успех={successful}, сумма={amount}")

            return attempt

        except Exception as e:
            print(f" Ошибка записи попытки кражи: {e}")
            # Откатываем транзакцию при ошибке
            db.rollback()
            return None

    @staticmethod
    def _fix_sequence(db):
        """Исправляет последовательность для таблицы steal_attempts"""
        from sqlalchemy import text

        try:
            # Для PostgreSQL - исправляем последовательность
            db.execute(text(
                "SELECT setval('steal_attempts_id_seq', (SELECT COALESCE(MAX(id), 0) FROM steal_attempts) + 1, false)"
            ))
            print("✅ Последовательность steal_attempts_id_seq исправлена")
        except Exception as e:
            print(f"⚠️ Не удалось исправить последовательность: {e}")

    @staticmethod
    def get_user__stats(db, user_id: int) -> dict:
        """Получает статистику краж пользователя"""
        from database.models import StealAttempt, Arrest

        # Статистика краж
        successful_steals = db.query(StealAttempt).filter(
            StealAttempt._id == user_id,
            StealAttempt.successful == True
        ).count()

        failed_steals = db.query(StealAttempt).filter(
            StealAttempt._id == user_id,
            StealAttempt.successful == False
        ).count()

        total_stolen = db.query(func.sum(StealAttempt.amount)).filter(
            StealAttempt._id == user_id,
            StealAttempt.successful == True
        ).scalar() or 0

        total_arrests = db.query(Arrest).filter(
            Arrest.user_id == user_id
        ).count()

        last_steal_time = db.query(StealAttempt.attempt_time).filter(
            StealAttempt._id == user_id
        ).order_by(StealAttempt.attempt_time.desc()).first()

        return {
            'successful_steals': successful_steals,
            'failed_steals': failed_steals,
            'total_stolen': int(total_stolen),
            'total_arrests': total_arrests,
            'last_steal_time': last_steal_time[0] if last_steal_time else None
        }

    @staticmethod
    def get_last_steal_time_by_victim(db, victim_id: int):
        """Получает время последней кражи у жертвы"""
        from database.models import StealAttempt
        last_attempt = db.query(StealAttempt).filter(
            StealAttempt.victim_id == victim_id
        ).order_by(StealAttempt.attempt_time.desc()).first()

        return last_attempt.attempt_time if last_attempt else None


# database/crud.py
class Repository:


    @staticmethod
    def get_user_arrest(db, user_id: int):
        """Получает информацию об аресте пользователя"""
        from database.models import UserArrest
        return db.query(UserArrest).filter(
            UserArrest.user_id == user_id,
            UserArrest.release_time > datetime.now()
        ).first()

    @staticmethod
    def unarrest_user(db, user_id: int) -> bool:
        """Снимает арест с пользователя"""
        from database.models import UserArrest
        deleted_count = db.query(UserArrest).filter(UserArrest.user_id == user_id).delete()
        return deleted_count > 0

    @staticmethod
    def get_all_active_arrests(db):
        """Получает все активные аресты"""
        from database.models import UserArrest
        return db.query(UserArrest).filter(
            UserArrest.release_time > datetime.now()
        ).all()

    @staticmethod
    def get_arrests_by_(db, _id: int):
        """Получает все аресты, выполненные конкретным полицейским"""
        from database.models import UserArrest
        return db.query(UserArrest).filter(
            UserArrest.arrested_by == _id
        ).all()


    @staticmethod
    def get_last_arrest_by_(db, _id: int):
        """Получает последний арест, выполненный полицейским"""
        from database.models import UserArrest
        try:
            last_arrest = db.query(UserArrest)\
                .filter(UserArrest.arrested_by == _id)\
                .order_by(UserArrest.release_time.desc())\
                .first()
            return last_arrest
        except Exception as e:
            print(f" Ошибка получения последнего ареста полицейского {_id}: {e}")
            return None


    @staticmethod
    def cleanup_expired_arrests(db) -> int:
        """Очищает истекшие аресты и возвращает количество удаленных"""
        from database.models import UserArrest
        deleted_count = db.query(UserArrest).filter(
            UserArrest.release_time <= datetime.now()
        ).delete()
        return deleted_count

    @staticmethod
    def arrest_user(db, user_id: int, arrested_by: int, release_time: datetime):
        """Арестовывает пользователя с указанием кто арестовал"""
        from database.models import UserArrest

        # Сначала удаляем старую запись если есть
        db.query(UserArrest).filter(UserArrest.user_id == user_id).delete()

        # Создаем новый арест
        arrest = UserArrest(
            user_id=user_id,
            arrested_by=arrested_by,
            release_time=release_time
        )
        db.add(arrest)

# database/crud.py (добавьте в конец файла)
class DonateRepository:
    @staticmethod
    def add_donate_purchase(db, user_id: int, item_id: int, item_name: str, duration_days: int = None):
        """Добавляет покупку донат-привилегии"""
        from database.models import DonatePurchase

        expires_at = None
        if duration_days:
            expires_at = datetime.now() + timedelta(days=duration_days)

        # Удаляем старую запись если есть
        db.query(DonatePurchase).filter(
            DonatePurchase.user_id == user_id,
            DonatePurchase.item_id == item_id
        ).delete()

        purchase = DonatePurchase(
            user_id=user_id,
            item_id=item_id,
            item_name=item_name,
            expires_at=expires_at
        )
        db.add(purchase)
        return purchase

    @staticmethod
    def has_active_purchase(db, user_id: int, item_id: int) -> bool:
        """Проверяет, есть ли у пользователя активная покупка"""
        from database.models import DonatePurchase

        purchase = db.query(DonatePurchase).filter(
            DonatePurchase.user_id == user_id,
            DonatePurchase.item_id == item_id
        ).first()

        return purchase is not None and purchase.is_active()

    @staticmethod
    def get_user_active_purchases(db, user_id: int):
        """Получает активные покупки пользователя с учетом срока действия"""
        from database.models import UserPurchase
        from datetime import datetime

        try:
            current_time = datetime.now()

            # Получаем все покупки пользователя
            purchases = db.query(UserPurchase).filter(
                UserPurchase.user_id == user_id
            ).all()

            active_purchases = []
            for purchase in purchases:
                # Проверяем активность
                if hasattr(purchase, 'is_active') and not purchase.is_active:
                    continue

                # Проверяем срок действия
                if purchase.expires_at and purchase.expires_at <= current_time:
                    # Если привилегия истекла, помечаем как неактивную
                    if hasattr(purchase, 'is_active'):
                        purchase.is_active = False
                        db.commit()
                    continue

                active_purchases.append(purchase)

            return active_purchases

        except Exception as e:
            print(f" Ошибка получения активных покупок: {e}")
            return []



    @staticmethod
    def cleanup_expired_purchases(db):
        """Очищает истекшие покупки"""
        from database.models import DonatePurchase

        deleted_count = db.query(DonatePurchase).filter(
            DonatePurchase.expires_at <= datetime.now()
        ).delete()
        return deleted_count

    @staticmethod
    def can_user_steal(db, user_id: int) -> bool:
        """Проверяет, может ли пользователь красть (вор в законе)"""
        return DonateRepository.has_active_purchase(db, user_id, 1)  # item_id = 1

    @staticmethod
    def can_user_arrest(db, user_id: int) -> bool:
        """Проверяет, может ли пользователь арестовывать (полицейский)"""
        return DonateRepository.has_active_purchase(db, user_id, 2)  # item_id = 2

    @staticmethod
    def has_active_donate_purchase(db, user_id: int, item_id: int) -> bool:
        """Проверяет, есть ли у пользователя активная донат-покупка"""
        try:
            purchase = db.query(models.DonatePurchase).filter(
                models.DonatePurchase.user_id == user_id,
                models.DonatePurchase.item_id == item_id
            ).first()

            if not purchase:
                return False

            return purchase.is_active()

        except Exception as e:
            print(f" Ошибка проверки активной донат-покупки: {e}")
            return False

    @staticmethod
    def get_active_donate_purchases(db, user_id: int) -> List[int]:
        """Получает список ID активных донат-покупок пользователя"""
        try:
            purchases = db.query(models.DonatePurchase).filter(
                models.DonatePurchase.user_id == user_id
            ).all()

            return [p.item_id for p in purchases if p.is_active()]

        except Exception as e:
            print(f" Ошибка получения активных донат-покупок: {e}")
            return []


class TelegramUserRepository:
    @staticmethod
    def get_user_by_id(db, user_id: int):
        """Получает пользователя по ID"""
        return db.execute(
            "SELECT * FROM telegram_users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    @staticmethod
    def create_user(db, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Создает нового пользователя"""
        db.execute(
            "INSERT INTO telegram_users (user_id, username, first_name, last_name, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (user_id, username, first_name, last_name)
        )


class ModerationLogRepository:
    @staticmethod
    def add_log(
            db: Session,
            action: str,  # Измените на str вместо ModerationAction если нужно
            chat_id: int,
            user_id: int,
            admin_id: int,
            reason: str = "",
            duration_minutes: Optional[int] = None
    ) -> models.ModerationLog:
        """Добавляет запись в лог модерации"""
        try:
            log = models.ModerationLog(
                action=action,  # ОБЯЗАТЕЛЬНОЕ поле
                chat_id=chat_id,
                user_id=user_id,
                admin_id=admin_id,
                reason=reason,
                duration_minutes=duration_minutes
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка добавления лога модерации: {e}")
            raise

    @staticmethod
    def add_moderation_log(
            db: Session,
            user_id: int,
            admin_id: int,
            action_type: str,
            duration: Optional[int] = None,
            reason: Optional[str] = None,
            chat_id: Optional[int] = None
    ) -> models.ModerationLog:
        """Альтернативный метод для добавления лога модерации"""
        try:
            # Конвертируем action_type в action если нужно
            action = action_type  # или используйте маппинг

            log = models.ModerationLog(
                action=action,  # ОБЯЗАТЕЛЬНОЕ поле
                user_id=user_id,
                admin_id=admin_id,
                chat_id=chat_id,
                reason=reason,
                duration_minutes=duration // 60 if duration else None  # конвертируем секунды в минуты
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            logger.info(f"Лог модерации добавлен: {action} для {user_id} от {admin_id}")
            return log
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка добавления лога модерации: {e}")
            raise

    @staticmethod
    def get_logs_by_user(db: Session, user_id: int, limit: int = 50) -> List[models.ModerationLog]:
        """Получает логи для конкретного пользователя"""
        try:
            logs = db.query(models.ModerationLog).filter(
                models.ModerationLog.user_id == user_id
            ).order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()
            return logs
        except Exception as e:
            logger.error(f"Ошибка получения логов пользователя {user_id}: {e}")
            return []

    @staticmethod
    def get_logs_by_admin(db: Session, admin_id: int, limit: int = 50) -> List[models.ModerationLog]:
        """Получает логи действий конкретного администратора"""
        try:
            logs = db.query(models.ModerationLog).filter(
                models.ModerationLog.admin_id == admin_id
            ).order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()
            return logs
        except Exception as e:
            logger.error(f"Ошибка получения логов администратора {admin_id}: {e}")
            return []

    @staticmethod
    def get_chat_logs(db: Session, chat_id: int, limit: int = 50) -> List[models.ModerationLog]:
        """Получает логи для конкретного чата"""
        try:
            logs = db.query(models.ModerationLog).filter(
                models.ModerationLog.chat_id == chat_id
            ).order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()
            return logs
        except Exception as e:
            logger.error(f"Ошибка получения логов чата {chat_id}: {e}")
            return []

    @staticmethod
    def get_recent_logs(db: Session, limit: int = 100) -> List[models.ModerationLog]:
        """Получает последние логи"""
        try:
            logs = db.query(models.ModerationLog).order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()
            return logs
        except Exception as e:
            logger.error(f"Ошибка получения последних логов: {e}")
            return []

    @staticmethod
    def search_logs(
            db: Session,
            user_id: Optional[int] = None,
            admin_id: Optional[int] = None,
            action: Optional[str] = None,  # Измените на action вместо action_type
            chat_id: Optional[int] = None,
            days: Optional[int] = 7,
            limit: int = 100
    ) -> List[models.ModerationLog]:
        """Поиск логов с фильтрами"""
        try:
            query = db.query(models.ModerationLog)

            # Применяем фильтры
            if user_id:
                query = query.filter(models.ModerationLog.user_id == user_id)

            if admin_id:
                query = query.filter(models.ModerationLog.admin_id == admin_id)

            if action:
                query = query.filter(models.ModerationLog.action == action)

            if chat_id:
                query = query.filter(models.ModerationLog.chat_id == chat_id)

            if days:
                from_date = datetime.utcnow() - timedelta(days=days)
                query = query.filter(models.ModerationLog.created_at >= from_date)

            logs = query.order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()

            return logs
        except Exception as e:
            logger.error(f"Ошибка поиска логов: {e}")
            return []

    @staticmethod
    def add_moderation_log(
            db: Session,
            user_id: int,
            admin_id: int,
            action_type: str,
            duration: Optional[int] = None,
            reason: Optional[str] = None,
            chat_id: Optional[int] = None
    ) -> models.ModerationLog:
        """Добавляет запись в лог модерации"""
        try:
            # Создаем объект с правильными параметрами
            log = models.ModerationLog(
                action=action_type,  # Используем action_type как action
                user_id=user_id,
                admin_id=admin_id,
                chat_id=chat_id,
                reason=reason,
                duration_minutes=duration // 60 if duration else None,
                action_type=action_type  # Если в модели есть это поле
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            logger.info(f"Лог модерации добавлен: {action_type} для {user_id} от {admin_id}")
            return log
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка добавления лога модерации: {e}")
            raise

    @staticmethod
    def add_log(
            db: Session,
            action: str,
            chat_id: int,
            user_id: int,
            admin_id: int,
            reason: str = "",
            duration_minutes: Optional[int] = None
    ) -> models.ModerationLog:
        """Альтернативный метод для добавления лога"""
        try:
            log = models.ModerationLog(
                action=action,
                chat_id=chat_id,
                user_id=user_id,
                admin_id=admin_id,
                reason=reason,
                duration_minutes=duration_minutes
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка добавления лога модерации: {e}")
            raise

    @staticmethod
    def get_stats(db: Session, days: int = 30) -> Dict[str, Any]:
        """Статистика по действиям модерации"""
        try:
            from_date = datetime.utcnow() - timedelta(days=days)

            # Общее количество действий
            total = db.query(models.ModerationLog).filter(
                models.ModerationLog.created_at >= from_date
            ).count()

            # По типам действий
            by_type = {}
            logs = db.query(
                models.ModerationLog.action,
                models.ModerationLog.duration_minutes,
                models.ModerationLog.reason
            ).filter(
                models.ModerationLog.created_at >= from_date
            ).all()

            for action, duration_minutes, reason in logs:
                if action not in by_type:
                    by_type[action] = {
                        'count': 0,
                        'with_reason': 0,
                        'temporary': 0,
                        'permanent': 0
                    }

                by_type[action]['count'] += 1

                if reason:
                    by_type[action]['with_reason'] += 1

                if duration_minutes:
                    by_type[action]['temporary'] += 1
                else:
                    by_type[action]['permanent'] += 1

            # Топ админов по активности
            admin_stats = {}
            logs_for_admins = db.query(
                models.ModerationLog.admin_id,
                models.ModerationLog.action
            ).filter(
                models.ModerationLog.created_at >= from_date
            ).all()

            for admin_id, action in logs_for_admins:
                if admin_id not in admin_stats:
                    admin_stats[admin_id] = {'total': 0, 'actions': {}}

                admin_stats[admin_id]['total'] += 1
                admin_stats[admin_id]['actions'][action] = admin_stats[admin_id]['actions'].get(action, 0) + 1

            return {
                'total': total,
                'by_type': by_type,
                'top_admins': dict(sorted(admin_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:10]),
                'period_days': days
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}

class DailyStatsRepository:
    """Репозиторий для работы со статистикой сообщений"""

    @staticmethod
    def increment_message_count(db: Session, user_id: int, chat_id: int) -> models.DailyMessageStats:
        """Увеличивает счетчик сообщений пользователя в чате за сегодня"""
        today = date.today()

        # Находим существующую запись за сегодня
        stat = db.query(models.DailyMessageStats).filter(
            models.DailyMessageStats.user_id == user_id,
            models.DailyMessageStats.chat_id == chat_id,
            models.DailyMessageStats.stat_date == today
        ).first()

        if stat:
            # Увеличиваем счетчик
            stat.message_count += 1
            stat.updated_at = datetime.now()
        else:
            # Создаем новую запись
            stat = models.DailyMessageStats(
                user_id=user_id,
                chat_id=chat_id,
                message_count=1,
                stat_date=today
            )
            db.add(stat)

        db.commit()
        db.refresh(stat)
        return stat

    @staticmethod
    def get_user_stats_today(db: Session, user_id: int, chat_id: int) -> Optional[models.DailyMessageStats]:
        """Получает статистику пользователя за сегодня в конкретном чате"""
        today = date.today()
        return db.query(models.DailyMessageStats).filter(
            models.DailyMessageStats.user_id == user_id,
            models.DailyMessageStats.chat_id == chat_id,
            models.DailyMessageStats.stat_date == today
        ).first()

    @staticmethod
    def get_top_active_users(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, str, int]]:
        """Получает топ самых активных пользователей за сегодня в чате"""
        today = date.today()

        results = db.query(
            models.DailyMessageStats.user_id,
            models.TelegramUser.username,
            models.TelegramUser.first_name,
            models.DailyMessageStats.message_count
        ).join(
            models.TelegramUser,
            models.DailyMessageStats.user_id == models.TelegramUser.telegram_id
        ).filter(
            models.DailyMessageStats.chat_id == chat_id,
            models.DailyMessageStats.stat_date == today,
            models.DailyMessageStats.message_count > 0
        ).order_by(
            desc(models.DailyMessageStats.message_count)
        ).limit(limit).all()

        return [(user_id, username or "", first_name or "", message_count)
                for user_id, username, first_name, message_count in results]

    @staticmethod
    def get_user_rank_today(db: Session, chat_id: int, user_id: int) -> Optional[int]:
        """Получает позицию пользователя в топе активности за сегодня"""
        today = date.today()

        # Создаем подзапрос для ранжирования
        subquery = db.query(
            models.DailyMessageStats.user_id,
            func.row_number().over(
                order_by=desc(models.DailyMessageStats.message_count)
            ).label('position')
        ).filter(
            models.DailyMessageStats.chat_id == chat_id,
            models.DailyMessageStats.stat_date == today,
            models.DailyMessageStats.message_count > 0
        ).subquery()

        result = db.query(subquery.c.position).filter(
            subquery.c.user_id == user_id
        ).first()

        return result[0] if result else None

    @staticmethod
    def get_user_message_count_today(db: Session, chat_id: int, user_id: int) -> int:
        """Получает количество сообщений пользователя за сегодня"""
        today = date.today()
        stat = db.query(models.DailyMessageStats).filter(
            models.DailyMessageStats.user_id == user_id,
            models.DailyMessageStats.chat_id == chat_id,
            models.DailyMessageStats.stat_date == today
        ).first()

        return stat.message_count if stat else 0

    @staticmethod
    def cleanup_old_stats(db: Session, days_to_keep: int = 7) -> int:
        """Очищает старую статистику (оставляет только последние N дней)"""
        cutoff_date = date.today() - timedelta(days=days_to_keep)

        deleted_count = db.query(models.DailyMessageStats).filter(
            models.DailyMessageStats.stat_date < cutoff_date
        ).delete()

        db.commit()
        return deleted_count

    @staticmethod
    def reset_daily_stats(db: Session) -> int:
        """Сбрасывает ежедневную статистику (вызывать в 00:00)"""
        # Вместо удаления, можно обнулить счетчики или создать архив
        # Но проще начать новый день с пустой статистики
        return 0  # Для автоматического сброса через очистку старых данных

    @staticmethod
    def get_chat_stats_summary(db: Session, chat_id: int) -> dict:
        """Получает сводную статистику по чату за сегодня"""
        today = date.today()

        # Общее количество сообщений в чате сегодня
        total_messages = db.query(func.sum(models.DailyMessageStats.message_count)).filter(
            models.DailyMessageStats.chat_id == chat_id,
            models.DailyMessageStats.stat_date == today
        ).scalar() or 0

        # Количество активных пользователей сегодня
        active_users = db.query(models.DailyMessageStats.user_id).filter(
            models.DailyMessageStats.chat_id == chat_id,
            models.DailyMessageStats.stat_date == today,
            models.DailyMessageStats.message_count > 0
        ).distinct().count()

        return {
            'chat_id': chat_id,
            'date': today,
            'total_messages': total_messages,
            'active_users': active_users,
            'avg_messages_per_user': total_messages / active_users if active_users > 0 else 0
        }


class ModerationLogRepository:
    @staticmethod
    def add_moderation_log(
        db: Session,
        user_id: int,
        admin_id: int,
        action_type: str,
        duration: Optional[int] = None,
        reason: Optional[str] = None,
        chat_id: Optional[int] = None
    ) -> models.ModerationLog:
        """Добавляет запись в лог модерации"""
        try:
            # Создаем объект с правильными параметрами
            log = models.ModerationLog(
                action=action_type,  # Используем action_type как action
                user_id=user_id,
                admin_id=admin_id,
                chat_id=chat_id,
                reason=reason,
                duration_minutes=duration // 60 if duration else None,
                action_type=action_type  # Если в модели есть это поле
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            logger.info(f"Лог модерации добавлен: {action_type} для {user_id} от {admin_id}")
            return log
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка добавления лога модерации: {e}")
            raise

    @staticmethod
    def add_log(
        db: Session,
        action: str,
        chat_id: int,
        user_id: int,
        admin_id: int,
        reason: str = "",
        duration_minutes: Optional[int] = None
    ) -> models.ModerationLog:
        """Альтернативный метод для добавления лога"""
        try:
            log = models.ModerationLog(
                action=action,
                chat_id=chat_id,
                user_id=user_id,
                admin_id=admin_id,
                reason=reason,
                duration_minutes=duration_minutes
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return log
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка добавления лога модерации: {e}")
            raise

    @staticmethod
    def get_logs_by_user(db: Session, user_id: int, limit: int = 50) -> List[models.ModerationLog]:
        """Получает логи для конкретного пользователя"""
        try:
            logs = db.query(models.ModerationLog).filter(
                models.ModerationLog.user_id == user_id
            ).order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()
            return logs
        except Exception as e:
            logger.error(f"Ошибка получения логов пользователя {user_id}: {e}")
            return []

    @staticmethod
    def get_logs_by_admin(db: Session, admin_id: int, limit: int = 50) -> List[models.ModerationLog]:
        """Получает логи действий конкретного администратора"""
        try:
            logs = db.query(models.ModerationLog).filter(
                models.ModerationLog.admin_id == admin_id
            ).order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()
            return logs
        except Exception as e:
            logger.error(f"Ошибка получения логов администратора {admin_id}: {e}")
            return []

    @staticmethod
    def get_chat_logs(db: Session, chat_id: int, limit: int = 50) -> List[models.ModerationLog]:
        """Получает логи для конкретного чата"""
        try:
            logs = db.query(models.ModerationLog).filter(
                models.ModerationLog.chat_id == chat_id
            ).order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()
            return logs
        except Exception as e:
            logger.error(f"Ошибка получения логов чата {chat_id}: {e}")
            return []

    @staticmethod
    def get_recent_logs(db: Session, limit: int = 100) -> List[models.ModerationLog]:
        """Получает последние логи"""
        try:
            logs = db.query(models.ModerationLog).order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()
            return logs
        except Exception as e:
            logger.error(f"Ошибка получения последних логов: {e}")
            return []

    @staticmethod
    def search_logs(
        db: Session,
        user_id: Optional[int] = None,
        admin_id: Optional[int] = None,
        action: Optional[str] = None,
        chat_id: Optional[int] = None,
        days: Optional[int] = 7,
        limit: int = 100
    ) -> List[models.ModerationLog]:
        """Поиск логов с фильтрами"""
        try:
            query = db.query(models.ModerationLog)

            # Применяем фильтры
            if user_id:
                query = query.filter(models.ModerationLog.user_id == user_id)

            if admin_id:
                query = query.filter(models.ModerationLog.admin_id == admin_id)

            if action:
                query = query.filter(models.ModerationLog.action == action)

            if chat_id:
                query = query.filter(models.ModerationLog.chat_id == chat_id)

            if days:
                from_date = datetime.utcnow() - timedelta(days=days)
                query = query.filter(models.ModerationLog.created_at >= from_date)

            logs = query.order_by(
                desc(models.ModerationLog.created_at)
            ).limit(limit).all()

            return logs
        except Exception as e:
            logger.error(f"Ошибка поиска логов: {e}")
            return []

    @staticmethod
    def get_stats(db: Session, days: int = 30) -> Dict[str, Any]:
        """Статистика по действиям модерации"""
        try:
            from_date = datetime.utcnow() - timedelta(days=days)

            # Общее количество действий
            total = db.query(models.ModerationLog).filter(
                models.ModerationLog.created_at >= from_date
            ).count()

            # По типам действий
            by_type = {}
            logs = db.query(
                models.ModerationLog.action,
                models.ModerationLog.duration_minutes,
                models.ModerationLog.reason
            ).filter(
                models.ModerationLog.created_at >= from_date
            ).all()

            for action, duration_minutes, reason in logs:
                if action not in by_type:
                    by_type[action] = {
                        'count': 0,
                        'with_reason': 0,
                        'temporary': 0,
                        'permanent': 0
                    }

                by_type[action]['count'] += 1

                if reason:
                    by_type[action]['with_reason'] += 1

                if duration_minutes:
                    by_type[action]['temporary'] += 1
                else:
                    by_type[action]['permanent'] += 1

            # Топ админов по активности
            admin_stats = {}
            logs_for_admins = db.query(
                models.ModerationLog.admin_id,
                models.ModerationLog.action
            ).filter(
                models.ModerationLog.created_at >= from_date
            ).all()

            for admin_id, action in logs_for_admins:
                if admin_id not in admin_stats:
                    admin_stats[admin_id] = {'total': 0, 'actions': {}}

                admin_stats[admin_id]['total'] += 1
                admin_stats[admin_id]['actions'][action] = admin_stats[admin_id]['actions'].get(action, 0) + 1

            return {
                'total': total,
                'by_type': by_type,
                'top_admins': dict(sorted(admin_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:10]),
                'period_days': days
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}


class ActiveMuteRepository:
    """Репозиторий для работы с активными мутами"""

    @staticmethod
    def add_active_mute(db,
                        user_id: int,
                        chat_id: int,
                        admin_id: int,
                        muted_until: datetime,
                        reason: Optional[str] = None) -> ActiveMute:
        """Добавляет активный мут"""
        try:
            # Удаляем старый мут если есть
            db.query(ActiveMute).filter(
                and_(
                    ActiveMute.user_id == user_id,
                    ActiveMute.chat_id == chat_id
                )
            ).delete()

            # Добавляем новый
            mute = ActiveMute(
                user_id=user_id,
                chat_id=chat_id,
                admin_id=admin_id,
                muted_until=muted_until,
                reason=reason
            )
            db.add(mute)
            db.commit()
            logger.info(f"Активный мут добавлен: {user_id} в {chat_id} до {muted_until}")
            return mute
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка добавления активного мута: {e}")
            raise

    @staticmethod
    def remove_active_mute(db, user_id: int, chat_id: int) -> bool:
        """Удаляет активный мут"""
        try:
            deleted = db.query(ActiveMute).filter(
                and_(
                    ActiveMute.user_id == user_id,
                    ActiveMute.chat_id == chat_id
                )
            ).delete()
            db.commit()
            logger.info(f"Активный мут удален: {user_id} из {chat_id}")
            return deleted > 0
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка удаления активного мута: {e}")
            return False

    @staticmethod
    def get_active_mute(db, user_id: int, chat_id: int) -> Optional[ActiveMute]:
        """Получает активный мут пользователя в чате"""
        try:
            mute = db.query(ActiveMute).filter(
                and_(
                    ActiveMute.user_id == user_id,
                    ActiveMute.chat_id == chat_id
                )
            ).first()
            return mute
        except Exception as e:
            logger.error(f"Ошибка получения активного мута: {e}")
            return None

    @staticmethod
    def get_chat_active_mutes(db, chat_id: int = None) -> List[ActiveMute]:
        """Получает все активные муты в чате или все если chat_id=None"""
        try:
            query = db.query(ActiveMute)
            if chat_id is not None:
                query = query.filter(ActiveMute.chat_id == chat_id)
            mutes = query.all()
            return mutes
        except Exception as e:
            logger.error(f"Ошибка получения активных мутов чата {chat_id}: {e}")
            return []

    @staticmethod
    def get_user_active_mutes(db, user_id: int) -> List[ActiveMute]:
        """Получает все активные муты пользователя"""
        try:
            mutes = db.query(ActiveMute).filter(
                ActiveMute.user_id == user_id
            ).all()
            return mutes
        except Exception as e:
            logger.error(f"Ошибка получения активных мутов пользователя {user_id}: {e}")
            return []

    @staticmethod
    def cleanup_expired_mutes(db) -> int:
        """Очищает истекшие муты, возвращает количество удаленных"""
        try:
            current_time = datetime.utcnow()
            deleted = db.query(ActiveMute).filter(
                ActiveMute.muted_until < current_time
            ).delete()
            db.commit()
            if deleted > 0:
                logger.info(f"Очищено {deleted} истекших мутов")
            return deleted
        except Exception as e:
            db.rollback()
            logger.error(f"Ошибка очистки истекших мутов: {e}")
            return 0

    @staticmethod
    def get_expired_mutes(db) -> List[ActiveMute]:
        """Получает истекшие муты"""
        try:
            current_time = datetime.utcnow()
            mutes = db.query(ActiveMute).filter(
                ActiveMute.muted_until < current_time
            ).all()
            return mutes
        except Exception as e:
            logger.error(f"Ошибка получения истекших мутов: {e}")
            return []


class ThiefRepository:
    @staticmethod
    def record_steal_attempt(db, thief_id: int, victim_id: int, successful: bool, amount: int):
        """Записывает попытку кражи в таблицу StealAttempt"""
        try:
            # ВАЖНО: Сначала исправляем последовательность если нужно
            from sqlalchemy import text

            # Проверяем, не существует ли уже такой записи (дублирование за 1 минуту)
            existing = db.query(models.StealAttempt).filter(
                models.StealAttempt.thief_id == thief_id,
                models.StealAttempt.victim_id == victim_id,
                models.StealAttempt.successful == successful,
                models.StealAttempt.attempt_time >= datetime.now() - timedelta(minutes=1)
            ).first()

            if existing:
                return existing

            # Используем SQL запрос для избежания проблем с последовательностью
            from sqlalchemy import text

            try:
                # Способ 1: Используем nextval для получения следующего ID
                result = db.execute(
                    text("""
                         INSERT INTO steal_attempts (id, thief_id, victim_id, successful, amount, attempt_time)
                         VALUES (nextval('steal_attempts_id_seq'), :thief_id, :victim_id, :successful, :amount,
                                 :attempt_time) RETURNING id
                         """),
                    {
                        'thief_id': thief_id,
                        'victim_id': victim_id,
                        'successful': successful,
                        'amount': amount if successful else 0,
                        'attempt_time': datetime.now()
                    }
                )
                db.commit()
                record_id = result.fetchone()[0]
                print(
                    f"✅ Запись кражи добавлена: ID={record_id}, вор={thief_id}, жертва={victim_id}, сумма={amount}, успех={successful}")

            except Exception as e:
                # Способ 2: Если nextval не работает, используем max+1
                print(f"⚠️ Способ 1 не сработал: {e}")
                db.rollback()

                # Получаем максимальный ID
                max_id_result = db.execute(text("SELECT COALESCE(MAX(id), 0) FROM steal_attempts")).fetchone()
                next_id = max_id_result[0] + 1

                result = db.execute(
                    text("""
                         INSERT INTO steal_attempts (id, thief_id, victim_id, successful, amount, attempt_time)
                         VALUES (:id, :thief_id, :victim_id, :successful, :amount, :attempt_time)
                         """),
                    {
                        'id': next_id,
                        'thief_id': thief_id,
                        'victim_id': victim_id,
                        'successful': successful,
                        'amount': amount if successful else 0,
                        'attempt_time': datetime.now()
                    }
                )
                db.commit()
                print(
                    f"✅ Запись кражи добавлена: ID={next_id}, вор={thief_id}, жертва={victim_id}, сумма={amount}, успех={successful}")

            # Сразу обновляем статистику пользователя
            user = UserRepository.get_user_by_telegram_id(db, thief_id)
            if user:
                # Увеличиваем счетчик игр бандита
                user.bandit_games_count = (user.bandit_games_count or 0) + 1

                if successful:
                    # Успешная кража
                    user.bandit_total_wins = (user.bandit_total_wins or 0) + amount

                    if amount > (user.bandit_max_win or 0):
                        user.bandit_max_win = amount

                    # Общая статистика
                    user.win_coins = (user.win_coins or 0) + amount

                    if amount > (user.max_win_coins or 0):
                        user.max_win_coins = amount
                else:
                    # Неудачная попытка
                    user.bandit_total_losses = (user.bandit_total_losses or 0) + 1

                # Обновляем максимальную ставку (сумму кражи)
                if amount > (user.bandit_max_bet or 0):
                    user.bandit_max_bet = amount

                if amount > (user.max_bet or 0):
                    user.max_bet = amount

                print(f"✅ Статистика бандита обновлена для {thief_id}: успех={successful}, сумма={amount}")
                db.commit()

            return True

        except Exception as e:
            print(f"❌ Критическая ошибка записи попытки кражи: {e}")
            db.rollback()
            return None

    @staticmethod
    def get_last_steal_time(db, thief_id: int) -> Optional[datetime]:
        """Получает время последней кражи пользователя"""
        try:
            last_attempt = db.query(models.StealAttempt).filter(
                models.StealAttempt.thief_id == thief_id,
                models.StealAttempt.successful == True
            ).order_by(models.StealAttempt.attempt_time.desc()).first()

            return last_attempt.attempt_time if last_attempt else None

        except Exception as e:
            print(f" Ошибка получения времени последней кражи: {e}")
            return None

    @staticmethod
    def get_last_steal_time_by_victim(db, victim_id: int) -> Optional[datetime]:
        """Получает время последней кражи у жертвы"""
        try:
            last_attempt = db.query(models.StealAttempt).filter(
                models.StealAttempt.victim_id == victim_id,
                models.StealAttempt.successful == True
            ).order_by(models.StealAttempt.attempt_time.desc()).first()

            return last_attempt.attempt_time if last_attempt else None

        except Exception as e:
            print(f" Ошибка получения времени последней кражи жертвы: {e}")
            return None

    @staticmethod
    def get_user_thief_stats(db, user_id: int) -> Dict[str, Any]:
        """Получает статистику краж пользователя"""
        try:
            # Получаем пользователя
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                return {}

            # Получаем статистику из таблицы StealAttempt
            successful_count = db.query(func.count(models.StealAttempt.id)).filter(
                models.StealAttempt.thief_id == user_id,
                models.StealAttempt.successful == True
            ).scalar() or 0

            failed_count = db.query(func.count(models.StealAttempt.id)).filter(
                models.StealAttempt.thief_id == user_id,
                models.StealAttempt.successful == False
            ).scalar() or 0

            total_stolen = db.query(func.sum(models.StealAttempt.amount)).filter(
                models.StealAttempt.thief_id == user_id,
                models.StealAttempt.successful == True
            ).scalar() or 0

            # Получаем время последней кражи
            last_steal_time = ThiefRepository.get_last_steal_time(db, user_id)

            return {
                'successful_steals': successful_count,
                'failed_steals': failed_count,
                'total_stolen': int(total_stolen),
                'last_steal_time': last_steal_time,
                # Статистика из полей пользователя
                'bandit_games_count': user.bandit_games_count or 0,
                'bandit_total_wins': user.bandit_total_wins or 0,
                'bandit_total_losses': user.bandit_total_losses or 0,
                'bandit_max_win': user.bandit_max_win or 0,
                'bandit_max_loss': user.bandit_max_loss or 0,
                'bandit_max_bet': user.bandit_max_bet or 0
            }

        except Exception as e:
            print(f" Ошибка получения статистики вора: {e}")
            return {
                'successful_steals': 0,
                'failed_steals': 0,
                'total_stolen': 0,
                'last_steal_time': None,
                'bandit_games_count': 0,
                'bandit_total_wins': 0,
                'bandit_total_losses': 0,
                'bandit_max_win': 0,
                'bandit_max_loss': 0,
                'bandit_max_bet': 0
            }

    @staticmethod
    def get_top_thieves_by_stolen(db, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает топ воров по сумме украденного"""
        try:
            results = db.query(
                models.StealAttempt.thief_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                func.sum(models.StealAttempt.amount).label('total_stolen'),
                func.count(models.StealAttempt.id).label('successful_steals')
            ).join(
                models.TelegramUser,
                models.StealAttempt.thief_id == models.TelegramUser.telegram_id
            ).filter(
                models.StealAttempt.successful == True
            ).group_by(
                models.StealAttempt.thief_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name
            ).order_by(
                desc('total_stolen')
            ).limit(limit).all()

            return [
                {
                    'user_id': thief_id,
                    'username': username or "",
                    'first_name': first_name or "",
                    'total_stolen': int(total_stolen),
                    'successful_steals': successful_steals
                }
                for thief_id, username, first_name, total_stolen, successful_steals in results
            ]

        except Exception as e:
            print(f" Ошибка получения топа воров: {e}")
            return []

    @staticmethod
    def get_user_rank_by_stolen(db, user_id: int) -> Optional[int]:
        """Получает позицию пользователя в топе по сумме украденного"""
        try:
            # Создаем подзапрос для ранжирования
            subquery = db.query(
                models.StealAttempt.thief_id,
                func.sum(models.StealAttempt.amount).label('total_stolen'),
                func.row_number().over(
                    order_by=desc(func.sum(models.StealAttempt.amount))
                ).label('position')
            ).filter(
                models.StealAttempt.successful == True
            ).group_by(
                models.StealAttempt.thief_id
            ).subquery()

            result = db.query(subquery.c.position).filter(
                subquery.c.thief_id == user_id
            ).first()

            return result[0] if result else None

        except Exception as e:
            print(f" Ошибка получения ранга вора: {e}")
            return None

    @staticmethod
    def get_bandit_top_stats(db, stat_type: str, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Получает топ по статистике бандита"""
        try:
            field_mapping = {
                'games_count': 'bandit_games_count',
                'total_wins': 'bandit_total_wins',
                'max_win': 'bandit_max_win',
                'max_bet': 'bandit_max_bet',
                'total_losses': 'bandit_total_losses',
                'max_loss': 'bandit_max_loss'
            }

            if stat_type not in field_mapping:
                return []

            field_name = field_mapping[stat_type]
            field = getattr(models.TelegramUser, field_name)

            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                field
            ).filter(
                field > 0
            ).order_by(
                desc(field)
            ).limit(limit).all()

            return [
                (user_id, first_name or username or "ㅤ", int(value))
                for user_id, username, first_name, value in results
            ]

        except Exception as e:
            print(f" Ошибка получения топа бандита по {stat_type}: {e}")
            return []

    @staticmethod
    def get_bandit_stats_by_user(db, user_id: int, stat_type: str) -> Optional[int]:
        """Получает конкретную статистику бандита пользователя"""
        try:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                return None

            stat_mapping = {
                'games_count': user.bandit_games_count,
                'total_wins': user.bandit_total_wins,
                'max_win': user.bandit_max_win,
                'max_bet': user.bandit_max_bet,
                'total_losses': user.bandit_total_losses,
                'max_loss': user.bandit_max_loss
            }

            return stat_mapping.get(stat_type, 0) or 0

        except Exception as e:
            print(f" Ошибка получения статистики бандита пользователя: {e}")
            return None

    @staticmethod
    def get_bandit_user_rank(db, user_id: int, stat_type: str) -> Optional[int]:
        """Получает позицию пользователя в топе статистики бандита"""
        try:
            field_mapping = {
                'games_count': 'bandit_games_count',
                'total_wins': 'bandit_total_wins',
                'max_win': 'bandit_max_win',
                'max_bet': 'bandit_max_bet',
                'total_losses': 'bandit_total_losses',
                'max_loss': 'bandit_max_loss'
            }

            if stat_type not in field_mapping:
                return None

            field_name = field_mapping[stat_type]
            field = getattr(models.TelegramUser, field_name)

            # Получаем значение пользователя
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                return None

            user_value = getattr(user, field_name) or 0

            # Считаем, сколько пользователей имеют большее значение
            count = db.query(func.count(models.TelegramUser.telegram_id)).filter(
                field > user_value
            ).scalar()

            return count + 1 if count is not None else 1

        except Exception as e:
            print(f" Ошибка получения ранга статистики бандита: {e}")
            return None

    @staticmethod
    def cleanup_old_steal_attempts(db, days: int = 30) -> int:
        """Очищает старые записи о кражах"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted_count = db.query(models.StealAttempt).filter(
                models.StealAttempt.attempt_time < cutoff_date
            ).delete()
            return deleted_count
        except Exception as e:
            print(f" Ошибка очистки старых записей краж: {e}")
            return 0


class PoliceRepository:


    @staticmethod
    def get_user_arrest(db, user_id: int):
        """Получает информацию об аресте пользователя"""
        from database.models import UserArrest
        return db.query(UserArrest).filter(
            UserArrest.user_id == user_id,
            UserArrest.release_time > datetime.now()
        ).first()

    @staticmethod
    def unarrest_user(db, user_id: int) -> bool:
        """Снимает арест с пользователя"""
        from database.models import UserArrest
        deleted_count = db.query(UserArrest).filter(UserArrest.user_id == user_id).delete()
        return deleted_count > 0

    @staticmethod
    def get_all_active_arrests(db):
        """Получает все активные аресты"""
        from database.models import UserArrest
        return db.query(UserArrest).filter(
            UserArrest.release_time > datetime.now()
        ).all()

    @staticmethod
    def get_arrests_by_police(db, police_id: int):
        """Получает все аресты, выполненные конкретным полицейским"""
        from database.models import UserArrest
        return db.query(UserArrest).filter(
            UserArrest.arrested_by == police_id
        ).all()


    @staticmethod
    def get_last_arrest_by_police(db, police_id: int):
        """Получает последний арест, выполненный полицейским"""
        from database.models import UserArrest
        try:
            last_arrest = db.query(UserArrest)\
                .filter(UserArrest.arrested_by == police_id)\
                .order_by(UserArrest.release_time.desc())\
                .first()
            return last_arrest
        except Exception as e:
            print(f" Ошибка получения последнего ареста полицейского {police_id}: {e}")
            return None


    @staticmethod
    def cleanup_expired_arrests(db) -> int:
        """Очищает истекшие аресты и возвращает количество удаленных"""
        from database.models import UserArrest
        deleted_count = db.query(UserArrest).filter(
            UserArrest.release_time <= datetime.now()
        ).delete()
        return deleted_count

    @staticmethod
    def arrest_user(db, user_id: int, arrested_by: int, release_time: datetime):
        """Арестовывает пользователя с указанием кто арестовал"""
        from database.models import UserArrest

        # Сначала удаляем старую запись если есть
        db.query(UserArrest).filter(UserArrest.user_id == user_id).delete()

        # Создаем новый арест
        arrest = UserArrest(
            user_id=user_id,
            arrested_by=arrested_by,
            release_time=release_time
        )
        db.add(arrest)


class RouletteLimitRepository:
    """Репозиторий для работы с лимитами рулетки в группах"""

    @staticmethod
    def get_or_create_limit(db: Session, chat_id: int) -> models.GroupRouletteLimit:
        """Получает или создает запись лимита рулетки для группы"""
        limit = db.query(models.GroupRouletteLimit).filter(
            models.GroupRouletteLimit.chat_id == chat_id
        ).first()

        if not limit:
            limit = models.GroupRouletteLimit(
                chat_id=chat_id,
                free_used=False,
                limit_removed=False,
                donation_paid=False
            )
            db.add(limit)
            db.commit()
            db.refresh(limit)

        return limit

    @staticmethod
    def get_limit_status(db: Session, chat_id: int) -> Dict[str, Any]:
        """Получает статус лимита рулетки в группе"""
        limit = RouletteLimitRepository.get_or_create_limit(db, chat_id)

        return {
            'chat_id': chat_id,
            'free_used': limit.free_used,
            'limit_removed': limit.limit_removed,
            'donation_paid': limit.donation_paid,
            'removed_by': limit.removed_by,
            'removed_at': limit.removed_at,
            'removed_via': limit.removed_via,
            'is_new_group': not limit.limit_removed and not limit.free_used
        }

    @staticmethod
    def use_free_launch(db: Session, chat_id: int) -> bool:
        """Использует бесплатный запуск рулетки. Возвращает True если можно запускать"""
        limit = RouletteLimitRepository.get_or_create_limit(db, chat_id)

        # Если лимит уже снят - разрешаем
        if limit.limit_removed:
            return True

        # Если бесплатный запуск еще не использован - используем и разрешаем
        if not limit.free_used:
            limit.free_used = True
            db.commit()
            return True

        # Бесплатный запуск уже использован - блокируем
        return False

    @staticmethod
    def unlock_with_coins(db: Session, chat_id: int, user_id: int) -> bool:
        """Снимает лимит рулетки за 100,000,000 монет"""
        limit = RouletteLimitRepository.get_or_create_limit(db, chat_id)

        if limit.limit_removed:
            return False  # Лимит уже снят

        # Создаем транзакцию
        transaction = models.RouletteLimitTransaction(
            chat_id=chat_id,
            user_id=user_id,
            amount_paid=100_000_000,
            transaction_type='coins'
        )
        db.add(transaction)

        # Обновляем лимит
        limit.limit_removed = True
        limit.removed_by = user_id
        limit.removed_at = datetime.utcnow()
        limit.removed_via = 'coins'

        db.commit()
        return True

    @staticmethod
    def unlock_with_donation(db: Session, chat_id: int, user_id: int) -> bool:
        """Снимает лимит рулетки после подтверждения доната 500₽"""
        limit = RouletteLimitRepository.get_or_create_limit(db, chat_id)

        if limit.limit_removed:
            return False  # Лимит уже снят

        # Создаем транзакцию
        transaction = models.RouletteLimitTransaction(
            chat_id=chat_id,
            user_id=user_id,
            donation_amount=500,
            transaction_type='donate'
        )
        db.add(transaction)

        # Обновляем лимит
        limit.limit_removed = True
        limit.donation_paid = True
        limit.removed_by = user_id
        limit.removed_at = datetime.utcnow()
        limit.removed_via = 'donate'

        db.commit()
        return True

    @staticmethod
    def is_limit_removed(db: Session, chat_id: int) -> bool:
        """Проверяет, снят ли лимит рулетки"""
        limit = db.query(models.GroupRouletteLimit).filter(
            models.GroupRouletteLimit.chat_id == chat_id
        ).first()

        return limit.limit_removed if limit else False

    @staticmethod
    def lock_limit(db: Session, chat_id: int) -> bool:
        """Возвращает лимит рулетки (сбрасывает unlock)"""
        limit = RouletteLimitRepository.get_or_create_limit(db, chat_id)
        
        # Сбрасываем все флаги
        limit.limit_removed = False
        limit.donation_paid = False
        limit.free_used = False
        limit.removed_by = None
        limit.removed_at = None
        limit.removed_via = None
        
        db.commit()
        return True

    @staticmethod
    def can_launch_roulette(db: Session, chat_id: int) -> bool:
        """Проверяет, можно ли запускать рулетку в группе"""
        return RouletteLimitRepository.use_free_launch(db, chat_id)

    @staticmethod
    def get_transaction_history(db: Session, chat_id: int = None, user_id: int = None, limit: int = 10):
        """Получает историю транзакций по лимитам"""
        query = db.query(models.RouletteLimitTransaction)

        if chat_id:
            query = query.filter(models.RouletteLimitTransaction.chat_id == chat_id)

        if user_id:
            query = query.filter(models.RouletteLimitTransaction.user_id == user_id)

        return query.order_by(models.RouletteLimitTransaction.created_at.desc()).limit(limit).all()

    @staticmethod
    def cleanup_old_data(db: Session, days: int = 180):
        """Очищает старые данные"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Удаляем старые транзакции
        deleted_transactions = db.query(models.RouletteLimitTransaction).filter(
            models.RouletteLimitTransaction.created_at < cutoff_date
        ).delete()

        # Удаляем лимиты неактивных групп (где лимит не снят)
        deleted_limits = db.query(models.GroupRouletteLimit).filter(
            models.GroupRouletteLimit.created_at < cutoff_date,
            models.GroupRouletteLimit.limit_removed == False
        ).delete()

        db.commit()
        return {'transactions': deleted_transactions, 'limits': deleted_limits}