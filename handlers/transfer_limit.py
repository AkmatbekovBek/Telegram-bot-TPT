from datetime import datetime, timedelta
from database import get_db
from database.crud import ShopRepository, TransferLimitRepository


class TransferLimit:
    def __init__(self):
        # Конфигурация лимитов
        self.LIMIT_PERIOD_HOURS = 6
        self.MAX_LIMIT = 10000

        # ID товара "Снятие лимита рулетки в группе" из магазина
        self.UNLIMITED_TRANSFERS_ITEM_ID = 3

    def has_unlimited_transfers(self, user_id: int) -> bool:
        """Проверяет, купил ли пользователь снятие лимита"""
        db = next(get_db())
        try:
            user_purchases = ShopRepository.get_user_purchases(db, user_id)
            print(f"🔍 ДЕТАЛЬНАЯ ПРОВЕРКА БЕЗЛИМИТА:")
            print(f"   👤 Пользователь: {user_id}")
            print(f"   🛍️ Все покупки: {user_purchases}")
            print(f"   🔎 Ищем ID: {self.UNLIMITED_TRANSFERS_ITEM_ID}")
            print(f"   📊 Тип данных: {type(user_purchases)}")

            result = self.UNLIMITED_TRANSFERS_ITEM_ID in user_purchases
            print(f"   ✅ Результат: {result}")

            return result
        except Exception as e:
            print(f" Ошибка проверки безлимитного статуса: {e}")
            return False
        finally:
            db.close()

    def get_user_transfer_stats(self, user_id: int) -> tuple:
        """
        Получает статистику переводов пользователя за последний период из БД
        Возвращает: (total_sent, remaining_limit, is_unlimited)
        """
        db = next(get_db())
        try:
            print(f"🔍 НАЧАЛО ПРОВЕРКИ СТАТИСТИКИ ДЛЯ {user_id}")

            # Если пользователь купил снятие лимита - возвращаем безлимитный доступ
            is_unlimited = self.has_unlimited_transfers(user_id)
            print(f"   ♾️ Безлимитный статус: {is_unlimited}")

            if is_unlimited:
                print(f"   ✅ Пользователь {user_id} имеет безлимитный доступ")
                return 0, float('inf'), True

            # Получаем переводы за последние 6 часов из БД
            transfers = TransferLimitRepository.get_user_transfers_last_6h(db, user_id)
            print(f"   📊 Найдено транзакций: {len(transfers)}")

            total_sent = 0
            for transfer in transfers:
                total_sent += transfer.amount

            remaining_limit = max(0, self.MAX_LIMIT - total_sent)

            print(f"   💰 Итого переведено: {total_sent}")
            print(f"   📈 Осталось лимита: {remaining_limit}")
            return total_sent, remaining_limit, False

        except Exception as e:
            print(f" Ошибка получения статистики переводов: {e}")
            return 0, self.MAX_LIMIT, False
        finally:
            db.close()

    def record_transfer(self, user_id: int, amount: int):
        """Записывает перевод в БД для системы лимитов"""
        db = next(get_db())
        try:
            # Если пользователь с безлимитным доступом - не записываем
            if self.has_unlimited_transfers(user_id):
                print(f"♾️ Пользователь {user_id} имеет безлимитный доступ, перевод не записывается")
                return

            # Записываем перевод в БД
            transfer = TransferLimitRepository.add_transfer_limit(db, user_id, amount, datetime.now())
            if transfer:
                print(f"✅ Перевод записан в БД: {user_id} -> {amount}")
            else:
                print(f" Ошибка записи перевода в БД: {user_id} -> {amount}")

        except Exception as e:
            print(f" Ошибка записи перевода: {e}")
            db.rollback()
        finally:
            db.close()

    def can_make_transfer(self, user_id: int, amount: int) -> tuple:
        """
        Проверяет, может ли пользователь сделать перевод
        Возвращает: (can_transfer, error_message, remaining_limit, is_unlimited)
        """
        try:
            print(f"🎯 ПРОВЕРКА ВОЗМОЖНОСТИ ПЕРЕВОДА:")
            print(f"   👤 Пользователь: {user_id}")
            print(f"   💰 Сумма: {amount}")

            total_sent, remaining_limit, is_unlimited = self.get_user_transfer_stats(user_id)

            if is_unlimited:
                print(f"   ✅ БЕЗЛИМИТНЫЙ ДОСТУП - перевод разрешен")
                return True, "", float('inf'), True

            print(f"   📊 Проверка лимита: {total_sent} + {amount} <= {self.MAX_LIMIT}")

            if total_sent + amount > self.MAX_LIMIT:
                error_msg = f" Лимит на передачу {self.MAX_LIMIT} Монет за {self.LIMIT_PERIOD_HOURS} часов. Вы еще можете передать: {remaining_limit}"
                print(f"   🚫 ПРЕВЫШЕНИЕ ЛИМИТА: {total_sent} + {amount} > {self.MAX_LIMIT}")
                return False, error_msg, remaining_limit, False

            print(f"   ✅ ЛИМИТ В ПОРЯДКЕ: {total_sent} + {amount} <= {self.MAX_LIMIT}")
            return True, "", remaining_limit, False

        except Exception as e:
            print(f" Ошибка проверки лимита: {e}")
            return True, "", self.MAX_LIMIT, False

    def get_limit_info(self, user_id: int) -> str:
        """Возвращает информацию о лимитах пользователя"""
        total_sent, remaining_limit, is_unlimited = self.get_user_transfer_stats(user_id)

        if is_unlimited:
            return "♾️ У вас безлимитные переводы (куплено в <a href='https://t.me/'>донате</a>)"
        else:
            return (f"📊 Лимиты переводов:\n"
                    f"• Период: {self.LIMIT_PERIOD_HOURS} часов\n"
                    f"• Максимум: {self.MAX_LIMIT} Монет\n"
                    f"• Уже переведено: {total_sent} Монет\n"
                    f"• Доступно: {remaining_limit} Монет\n\n"
                    f"💡 Чтобы снять лимит: купите в <a href='https://t.me/'>донате</a>")

    def cleanup_old_data(self):
        """Очищает старые данные о переводах"""
        db = next(get_db())
        try:
            deleted_count = TransferLimitRepository.clean_old_transfers(db)
            print(f"🗑️ Очищено {deleted_count} старых записей о переводах")
        except Exception as e:
            print(f" Ошибка очистки старых данных: {e}")
        finally:
            db.close()


# Создаем глобальный экземпляр
transfer_limit = TransferLimit()