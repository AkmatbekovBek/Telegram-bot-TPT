# safe_cleanup.py
from database import SessionLocal
from database.models import *


def safe_cleanup():
    db = SessionLocal()
    try:
        print("🧹 Полная очистка всех данных...")

        # Очищаем в правильном порядке чтобы не нарушить foreign keys
        tables_to_clean = [
            # Сначала таблицы без зависимостей или с минимальными зависимостями
            StealAttempt, Arrest, UserArrest,
            DonatePurchase, UserNickSearch,
            UserChatSearch, BotStop, ModerationLog, RouletteLimit,
            TransferLimit, UserPurchase, RouletteTransaction, DailyRecord,
            Transaction, ReferenceUser, UserChat, RouletteGameLog,

            # Потом таблицы с зависимостями
            User,  # зависит от TelegramUser
            Chat,  # могут иметь связи с другими таблицами

            # И наконец основная таблица пользователей
            TelegramUser
        ]

        for table in tables_to_clean:
            try:
                count = db.query(table).count()
                if count > 0:
                    db.query(table).delete()
                    db.commit()
                    print(f"✅ Очищена {table.__tablename__}: {count} записей")
                else:
                    print(f"ℹ️  {table.__tablename__}: уже пустая")
            except Exception as e:
                db.rollback()
                print(f" Ошибка в {table.__tablename__}: {e}")

        print("🎯 Полная очистка завершена! Все данные удалены.")

    except Exception as e:
        print(f" Критическая ошибка: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    # Подтверждение для безопасности
    confirm = input("⚠️  Вы уверены, что хотите очистить ВСЕ данные? Это действие нельзя отменить! (y/N): ")
    if confirm.lower() in ['y', 'yes', 'д', 'да']:
        safe_cleanup()
    else:
        print(" Очистка отменена.")