from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from decouple import config

# Синхронный PostgreSQL
DATABASE_URL = config('DATABASE_URL')

# Синхронный движок
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Для обратной совместимости
def get_db():
    db = SessionLocal()
    try:
        db.expire_all()
        yield db
    finally:
        db.close()

# Импортируем утилиты
from .session_utils import db_session, async_db_session

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "db_session",
    "async_db_session"
]