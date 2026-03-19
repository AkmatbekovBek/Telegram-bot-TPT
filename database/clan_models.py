from sqlalchemy import Column, Integer, String, Text, BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Clan(Base):
    __tablename__ = 'clans'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    tag = Column(String(20), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    avatar = Column(String(500), nullable=True)
    total_coins = Column(BigInteger, default=0, nullable=False)
    last_updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    auto_accept_requests = Column(Boolean, default=False)  # Автоматическое принятие заявок
    join_type = Column(String(10), default='manual')  # 'auto' или 'manual'
    notification_chat_id = Column(BigInteger, nullable=True)  # Чат для уведомлений
    allow_public_join = Column(Boolean, default=False)  # Публичное вступление

    # Связи
    members = relationship("ClanMember", back_populates="clan", cascade="all, delete-orphan", lazy="dynamic")
    invitations = relationship("ClanInvitation", back_populates="clan", cascade="all, delete-orphan", lazy="dynamic")
    join_requests = relationship("ClanJoinRequest", back_populates="clan", cascade="all, delete-orphan", lazy="dynamic")
    invite_codes = relationship("ClanInviteCode", back_populates="clan", cascade="all, delete-orphan", lazy="dynamic")


class ClanMember(Base):
    __tablename__ = 'clan_members'

    id = Column(Integer, primary_key=True)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(BigInteger, nullable=False)
    role = Column(String(20), default='member')  # leader, deputy, member
    coins_contributed = Column(BigInteger, default=0)
    joined_at = Column(DateTime, default=datetime.now)

    # Связь с кланом
    clan = relationship("Clan", back_populates="members")


class ClanInvitation(Base):
    __tablename__ = 'clan_invitations'

    id = Column(Integer, primary_key=True)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='CASCADE'), nullable=False)
    from_user_id = Column(BigInteger, nullable=False)
    to_user_id = Column(BigInteger, nullable=False)
    status = Column(String(20), default='pending')  # pending, accepted, rejected
    created_at = Column(DateTime, default=datetime.now)

    # Связь с кланом
    clan = relationship("Clan", back_populates="invitations")


class ClanJoinRequest(Base):
    __tablename__ = 'clan_join_requests'

    id = Column(Integer, primary_key=True)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(BigInteger, nullable=False)
    message = Column(Text, nullable=True)
    status = Column(String(20), default='pending')  # pending, approved, rejected
    created_at = Column(DateTime, default=datetime.now)

    # Связь с кланом
    clan = relationship("Clan", back_populates="join_requests")


class ClanInviteCode(Base):
    __tablename__ = 'clan_invite_codes'

    id = Column(Integer, primary_key=True)
    clan_id = Column(Integer, ForeignKey('clans.id', ondelete='CASCADE'), nullable=False)
    creator_id = Column(BigInteger, nullable=False)
    code = Column(String(20), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    used_by_id = Column(BigInteger, nullable=True)

    # Связь с кланом
    clan = relationship("Clan", back_populates="invite_codes")


class ClanSettings(Base):
    __tablename__ = 'clan_settings'

    id = Column(Integer, primary_key=True)
    clan_creation_price = Column(BigInteger, default=100000)  # Стоимость создания клана
    max_members = Column(Integer, default=50)  # Максимальное количество участников
    min_level_for_creation = Column(Integer, default=10)  # Минимальный уровень для создания
    daily_bonus_coins = Column(BigInteger, default=1000)  # Ежедневный бонус
    invite_code_expiry_hours = Column(Integer, default=24)  # Срок действия кода
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)