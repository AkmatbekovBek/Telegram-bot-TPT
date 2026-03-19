from contextlib import contextmanager, asynccontextmanager
from . import SessionLocal

@contextmanager
def db_session():
    """Синхронный контекстный менеджер для работы с БД"""
    db = SessionLocal()
    try:
        db.expire_all()
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

@asynccontextmanager
async def async_db_session():
    """Асинхронный контекстный менеджер для работы с БД (для асинхронных хендлеров)"""
    db = SessionLocal()
    try:
        db.expire_all()
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()