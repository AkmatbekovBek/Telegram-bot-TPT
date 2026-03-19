"""
Модели для системы проверки чеков
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Boolean, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import json

Base = declarative_base()


class Check(Base):
    """Модель для хранения информации о чеках"""
    __tablename__ = 'donate_checks'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    username = Column(String(255))
    first_name = Column(String(255))
    chat_id = Column(BigInteger, nullable=False)
    check_photo_id = Column(String(500))  # file_id фото
    status = Column(String(50), default='pending')  # pending, approved, rejected, banned
    amount = Column(Float, nullable=True)  # Сумма доната
    coins_given = Column(BigInteger, nullable=True)  # Количество выданных монет
    admin_id = Column(BigInteger, nullable=True)  # ID админа, который обработал
    admin_username = Column(String(255))
    created_at = Column(DateTime, default=datetime.now)
    processed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)  # Дополнительные заметки
    additional_data = Column(JSON, nullable=True)  # Дополнительные данные в JSON формате

    def get_additional_data(self):
        """Безопасно получает дополнительные данные"""
        if self.additional_data:
            if isinstance(self.additional_data, str):
                try:
                    return json.loads(self.additional_data)
                except:
                    return {}
            return self.additional_data or {}
        return {}


class BanList(Base):
    """Модель для бан-листа"""
    __tablename__ = 'ban_list'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, unique=True, index=True)
    username = Column(String(255))
    reason = Column(String(500))
    admin_id = Column(BigInteger, nullable=False)
    banned_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=True)  # Если бан временный


class CheckLog(Base):
    """Лог действий с чеками"""
    __tablename__ = 'check_logs'

    id = Column(Integer, primary_key=True)
    check_id = Column(Integer, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)
    action = Column(String(100), nullable=False)  # approve, ban, remove_limit
    amount = Column(Float, nullable=True)
    admin_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    notes = Column(Text, nullable=True)