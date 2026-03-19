import pytz
from datetime import datetime, date

from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, Float, Text, ForeignKey, Enum as SQLEnum, Date, \
    UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.sql.sqltypes import Numeric

from enum import Enum

from database import Base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, BigInteger, Text, Float, Index


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    reference_link = Column(Text)
    coins = Column(Numeric(30, 0), default=7500000)

    # Общая статистика
    win_coins = Column(Numeric(30, 0), default=0)
    defeat_coins = Column(Numeric(30, 0), default=0)
    max_win_coins = Column(Numeric(30, 0), default=0)
    min_win_coins = Column(Numeric(30, 0), default=0)
    max_bet = Column(Numeric(30, 0), default=0)

    # НОВЫЕ ПОЛЯ: Статистика по играм
    # Рулетка
    roulette_total_wins = Column(Numeric(30, 0), default=0)
    roulette_total_losses = Column(Numeric(30, 0), default=0)
    roulette_max_win = Column(Numeric(30, 0), default=0)
    roulette_max_loss = Column(Numeric(30, 0), default=0)
    roulette_max_bet = Column(Numeric(30, 0), default=0)
    roulette_games_count = Column(Numeric, default=0)

    # Бандит (однорукий бандит)
    bandit_total_wins = Column(Numeric(30, 0), default=0)
    bandit_total_losses = Column(Numeric(30, 0), default=0)
    bandit_max_win = Column(Numeric(30, 0), default=0)
    bandit_max_loss = Column(Numeric(30, 0), default=0)
    bandit_max_bet = Column(Numeric(30, 0), default=0)
    bandit_games_count = Column(Numeric, default=0)

    # Другие поля...
    is_admin = Column(Boolean, default=False)
    robberies_today = Column(Integer, default=0, nullable=False)
    last_robbery_reset = Column(DateTime(timezone=True), nullable=True)
    action = Column(String(50), nullable=True)
    duration_minutes = Column(Integer, default=0, nullable=False)

    # Связи
    references = relationship("ReferenceUser", back_populates="owner")
    transactions_from = relationship("Transaction", foreign_keys="Transaction.from_user_id", back_populates="from_user")
    transactions_to = relationship("Transaction", foreign_keys="Transaction.to_user_id", back_populates="to_user")
    chat_memberships = relationship("UserChat", back_populates="user")
    daily_records = relationship("DailyRecord", back_populates="user")
    roulette_transactions = relationship("RouletteTransaction", back_populates="user")
    purchases = relationship("UserPurchase", back_populates="user")
    transfer_limits = relationship("TransferLimit", back_populates="user")





class ReferenceUser(Base):
    __tablename__ = "reference_users"

    id = Column(Integer, primary_key=True)
    owner_telegram_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    reference_telegram_id = Column(BigInteger, nullable=False)

    # Связи
    owner = relationship("TelegramUser", back_populates="references")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    from_user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))  # Изменено на BigInteger
    to_user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))    # Изменено на BigInteger
    amount = Column(Numeric, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    description = Column(Text)

    # Связи
    from_user = relationship("TelegramUser", foreign_keys=[from_user_id], back_populates="transactions_from")
    to_user = relationship("TelegramUser", foreign_keys=[to_user_id], back_populates="transactions_to")

class UserChat(Base):
    __tablename__ = "user_chats"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    chat_id = Column(BigInteger, nullable=False)

    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser", back_populates="chat_memberships")


class DailyRecord(Base):
    __tablename__ = "daily_records"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    username = Column(Text, nullable=False)
    first_name = Column(Text)
    amount = Column(Numeric, nullable=False)
    record_date = Column(Date, nullable=False)
    chat_id = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser", back_populates="daily_records")

# database/models.py (добавить в конец файла)

class DailyLossRecord(Base):
    """Таблица для рекордов проигрышей за день"""
    __tablename__ = 'daily_loss_records'

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False)
    username = Column(Text, nullable=False)
    first_name = Column(Text)
    amount = Column(Numeric, nullable=False)  # Сумма проигрыша (положительное число)
    record_date = Column(Date, nullable=False)
    chat_id = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser")

    def __repr__(self):
        return f"<DailyLossRecord(user_id={self.user_id}, amount={self.amount}, date={self.record_date})>"


class RouletteTransaction(Base):
    __tablename__ = "roulette_transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    amount = Column(Numeric, nullable=False)
    is_win = Column(Boolean, nullable=False)
    bet_type = Column(Text)
    bet_value = Column(Text)
    result_number = Column(BigInteger)
    profit = Column(Numeric)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser", back_populates="roulette_transactions")


class RouletteGameLog(Base):
    __tablename__ = "roulette_game_logs"

    id = Column(BigInteger, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    result = Column(BigInteger, nullable=False)
    color_emoji = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserPurchase(Base):
    __tablename__ = "user_purchases"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    item_id = Column(BigInteger, nullable=False)
    item_name = Column(Text, nullable=False)
    price = Column(BigInteger, nullable=False)
    chat_id = Column(Numeric, nullable=False, default=-1)
    purchased_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_user_item', 'user_id', 'item_id'),
    )
    # Связи
    user = relationship("TelegramUser", back_populates="purchases")


class TransferLimit(Base):
    __tablename__ = "transfer_limits"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("telegram_users.telegram_id"))
    amount = Column(BigInteger, nullable=False)
    transfer_time = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser", back_populates="transfer_limits")



class RouletteLimit(Base):
    __tablename__ = "roulette_limits"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)  # ID чата/группы
    date = Column(Date, nullable=False)
    spin_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    user = relationship("TelegramUser")

    # Уникальный индекс на user_id, chat_id и date
    __table_args__ = (UniqueConstraint('user_id', 'chat_id', 'date', name='_user_chat_date_uc'),)


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=True)
    chat_type = Column(String(50), nullable=True)  # 'group', 'supergroup', 'channel'
    is_active = Column(Boolean, default=True)
    slots_enabled = Column(Boolean, default=True)
    basketball_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BotStop(Base):
    __tablename__ = 'bot_stop_users'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    blocked_user_id = Column(BigInteger, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

    # Уникальный индекс, чтобы нельзя было заблокировать одного пользователя несколько раз
    __table_args__ = (
        UniqueConstraint('user_id', 'blocked_user_id', name='unique_user_block'),
    )

    def __repr__(self):
        return f"<BotStop(user_id={self.user_id}, blocked_user_id={self.blocked_user_id})>"


# database/models.py (с другими именами таблиц)
class UserChatSearch(Base):
    __tablename__ = 'user_chats_search'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    chat_title = Column(String(255), nullable=True)  # ИЗМЕНИТЕ НА nullable=True
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('user_id', 'chat_id', name='unique_user_chat_search'),
    )


class UserNickSearch(Base):
    __tablename__ = 'user_nicks_search'  # ← ИЗМЕНИТЕ ИМЯ

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    nick = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('user_id', 'nick', name='unique_user_nick_search'),
    )

# database/models.py (добавьте в конец файла)
class Arrest(Base):
    __tablename__ = '_arrests'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    release_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<Arrest(user_id={self.user_id}, release_time={self.release_time})>"


class StealAttempt(Base):
    __tablename__ = 'steal_attempts'

    id = Column(BigInteger, primary_key=True, autoincrement=True)  # Добавьте autoincrement=True
    thief_id = Column(BigInteger, nullable=False, index=True)  # Исправлено: thief_id вместо _id
    victim_id = Column(BigInteger, nullable=False, index=True)
    successful = Column(Boolean, nullable=False)
    amount = Column(BigInteger, default=0)
    attempt_time = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<StealAttempt(thief_id={self.thief_id}, victim_id={self.victim_id}, successful={self.successful}, amount={self.amount})>"


# database/models.py (добавьте в конец файла)
class DonatePurchase(Base):
    __tablename__ = 'donate_purchases'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    item_id = Column(Integer, nullable=False)  # 1 - Вор в законе, 2 - Полицейский, 3 - Снятие лимита
    item_name = Column(String(255), nullable=False)
    purchase_date = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=True)  # null = навсегда

    __table_args__ = (
        UniqueConstraint('user_id', 'item_id', name='unique_user_item'),
    )

    def is_active(self):
        """Проверяет, активна ли покупка"""
        if self.expires_at is None:  # Навсегда
            return True
        return datetime.now() < self.expires_at

    def __repr__(self):
        return f"<DonatePurchase(user_id={self.user_id}, item='{self.item_name}')>"

class UserArrest(Base):
    __tablename__ = 'user_arrests'

    user_id = Column(BigInteger, primary_key=True)
    arrested_by = Column(BigInteger, nullable=False)
    release_time = Column(DateTime, nullable=False)
    arrested_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<UserArrest(user_id={self.user_id}, arrested_by={self.arrested_by}, release_time={self.release_time})>"







class ModerationAction(str, Enum):
    MUTE = "mute"
    BAN = "ban"
    KICK = "kick"


class ModerationLog(Base):
    __tablename__ = "moderation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    admin_id = Column(BigInteger, nullable=False)

    # Основные поля (должны быть в БД)
    action = Column(String(50), nullable=False)
    chat_id = Column(BigInteger, nullable=True)
    reason = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Новые поля для ТЗ (могут быть NULL пока не добавим в БД)
    duration = Column(Integer, nullable=True)  # В секундах
    action_type = Column(String(20), nullable=True)  # Дублирует action для совместимости
    timestamp = Column(DateTime(timezone=True), nullable=True)  # Дублирует created_at

    # Свойства для совместимости
    @property
    def effective_action(self):
        """Возвращает action_type если есть, иначе action"""
        return self.action_type or self.action

    @property
    def effective_timestamp(self):
        """Возвращает timestamp если есть, иначе created_at"""
        return self.timestamp or self.created_at

    @property
    def effective_duration(self):
        """Возвращает duration если есть, иначе duration_minutes * 60"""
        if self.duration is not None:
            return self.duration
        elif self.duration_minutes is not None:
            return self.duration_minutes * 60
        return None

    __table_args__ = (
        Index('idx_modlogs_user', 'user_id'),
        Index('idx_modlogs_admin', 'admin_id'),
        Index('idx_modlogs_chat', 'chat_id'),
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'},
    )

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, index=True)
    chat_id = Column(BigInteger, index=True)
    username = Column(String)
    coins = Column(Integer, default=0)
    win_coins = Column(BigInteger, default=0)
    defeat_coins = Column(BigInteger, default=0)
    max_win_coins = Column(BigInteger, default=0)
    min_win_coins = Column(BigInteger, default=0)
    max_bet_coins = Column(BigInteger, default=0)



class DailyMessageStats(Base):
    """Таблица для ежедневной статистики сообщений по чатам"""
    __tablename__ = 'daily_message_stats'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False)
    chat_id = Column(BigInteger, nullable=False, index=True)
    message_count = Column(Integer, default=0, nullable=False)
    stat_date = Column(Date, nullable=False, default=date.today)  # Дата статистики
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Индексы для быстрого поиска
    __table_args__ = (
        UniqueConstraint('user_id', 'chat_id', 'stat_date', name='unique_user_chat_date'),
        Index('idx_daily_stats_chat_date', 'chat_id', 'stat_date'),
        Index('idx_daily_stats_message_count', 'chat_id', 'stat_date', 'message_count'),
    )

    # Связи
    user = relationship("TelegramUser")

    def __repr__(self):
        return f"<DailyMessageStats(user_id={self.user_id}, chat_id={self.chat_id}, date={self.stat_date}, messages={self.message_count})>"


class UserStatus(Base):
    """Модель для хранения статусов пользователей"""
    __tablename__ = 'user_statuses'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False,
                     index=True)  # ← Добавьте ForeignKey
    status_id = Column(Integer, nullable=False)
    status_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    link_url = Column(String(500), nullable=True)
    link_text = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("TelegramUser")

    __table_args__ = (
        Index('idx_user_status_active', 'user_id', 'is_active'),
        Index('idx_status_expires', 'expires_at'),
        Index('idx_user_status_current', 'user_id', 'status_id', 'is_active'),
    )


class StatusTransaction(Base):
    """Транзакции статусов"""
    __tablename__ = 'status_transactions'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    status_id = Column(Integer, nullable=False)
    status_name = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)  # 'admin_give', 'purchase', 'remove', 'extend'
    amount_rub = Column(Integer, nullable=True)
    amount_tenge = Column(Integer, nullable=True)
    days = Column(Integer, nullable=True)
    admin_id = Column(BigInteger, nullable=True)
    link_url = Column(Text, nullable=True)
    link_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_status_transactions_status_id', 'status_id'),
        Index('idx_status_transactions_created', 'created_at'),
    )

    def __repr__(self):
        return f"<StatusTransaction(user_id={self.user_id}, action={self.action})>"


class UserBonus(Base):
    """Статистика бонусов пользователя"""
    __tablename__ = 'user_bonuses'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    last_bonus_time = Column(DateTime, nullable=True)
    bonus_count = Column(Integer, default=0)
    total_bonus_amount = Column(BigInteger, default=0)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<UserBonus(user_id={self.user_id}, count={self.bonus_count})>"


class DailyBonusLog(Base):
    """Лог ежедневных бонусов"""
    __tablename__ = 'daily_bonus_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    status_id = Column(Integer, nullable=True)
    status_name = Column(String(50), nullable=True)
    bonus_amount = Column(BigInteger, nullable=False, default=0)
    total_bonus_amount = Column(BigInteger, nullable=False, default=0)
    is_automatic = Column(Boolean, default=True)  # True - автоматическое, False - ручное
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index('idx_daily_bonus_logs_created', 'created_at'),
        Index('idx_daily_bonus_logs_automatic', 'is_automatic'),
    )

    def __repr__(self):
        return f"<DailyBonusLog(user_id={self.user_id}, amount={self.bonus_amount})>"


from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, Index
from sqlalchemy.sql import func



from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, Index
from sqlalchemy.sql import func


class ActiveMute(Base):
    __tablename__ = "active_mutes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    admin_id = Column(BigInteger, nullable=False)
    muted_until = Column(DateTime(timezone=True), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_active_mutes_user_chat', 'user_id', 'chat_id'),
        Index('idx_active_mutes_until', 'muted_until'),
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci'},
    )

    def __repr__(self):
        return f"<ActiveMute(user_id={self.user_id}, chat_id={self.chat_id}, until={self.muted_until})>"


class ThiefArrest(Base):
    __tablename__ = 'thief_arrests'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    release_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<ThiefArrest(user_id={self.user_id}, release_time={self.release_time})>"


class GroupRouletteLimit(Base):
    """Таблица для хранения лимитов рулетки в группах"""
    __tablename__ = "group_roulette_limits"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    free_used = Column(Boolean, default=False, nullable=False)  # Использован ли бесплатный запуск
    limit_removed = Column(Boolean, default=False, nullable=False)  # Снят ли лимит
    removed_by = Column(BigInteger, nullable=True)  # Кто снял (ID пользователя)
    removed_at = Column(DateTime, nullable=True)  # Когда снял
    removed_via = Column(String(20), nullable=True)  # Способ снятия: 'coins' или 'donate'
    donation_paid = Column(Boolean, default=False, nullable=False)  # Оплачен ли донат (500₽)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<GroupRouletteLimit(chat_id={self.chat_id}, free_used={self.free_used}, limit_removed={self.limit_removed})>"


class RouletteLimitTransaction(Base):
    """Транзакции по снятию лимитов рулетки"""
    __tablename__ = "roulette_limit_transactions"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)  # Кто снял лимит
    amount_paid = Column(BigInteger, nullable=True)  # Сумма в монетах (100 млн)
    donation_amount = Column(Integer, nullable=True)  # Сумма в рублях (500)
    transaction_type = Column(String(20), nullable=False)  # 'coins' или 'donate'
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<RouletteLimitTransaction(chat_id={self.chat_id}, user_id={self.user_id}, type={self.transaction_type})>"


class Marriage(Base):
    """Модель браков"""
    __tablename__ = 'marriages'

    id = Column(Integer, primary_key=True)
    groom_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False)
    bride_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    groom = relationship("TelegramUser", foreign_keys=[groom_id])
    bride = relationship("TelegramUser", foreign_keys=[bride_id])

    __table_args__ = (
        Index('idx_marriage_groom', 'groom_id'),
        Index('idx_marriage_bride', 'bride_id'),
    )

    def __repr__(self):
        return f"<Marriage(groom={self.groom_id}, bride={self.bride_id})>"