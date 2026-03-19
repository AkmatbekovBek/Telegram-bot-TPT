import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Optional
import pytz
from aiogram import Bot
from .record_core import RecordCore, RecordErrors


class RecordService:
    """Сервис для работы с рекордами и балансами"""

    def __init__(self, record_core: RecordCore):
        self.core = record_core
        self.logger = logging.getLogger(__name__)
        self._reset_task = None
        self._start_daily_reset()

    def _start_daily_reset(self):
        """Запускает фоновую задачу для сброса рекордов дня в 00:00 МСК"""
        async def reset_loop():
            while True:
                try:
                    # Таймзона Москвы
                    msk_tz = pytz.timezone('Europe/Moscow')
                    now = datetime.now(msk_tz)
                    target_time = time(0, 0)  # 00:00 МСК
                    
                    # Вычисляем время до следующей полночи
                    if now.time() > target_time:
                        next_day = now.date() + timedelta(days=1)
                    else:
                        next_day = now.date()
                    
                    next_reset = msk_tz.localize(
                        datetime.combine(next_day, target_time)
                    )
                    
                    seconds_until_reset = (next_reset - now).total_seconds()
                    
                    self.logger.info(f"⏰ Следующий сброс РЕКОРДОВ ДНЯ через {seconds_until_reset:.0f} секунд")
                    await asyncio.sleep(seconds_until_reset)
                    
                    # Выполняем сброс ТОЛЬКО рекордов дня
                    await self.reset_daily_records()
                    
                except Exception as e:
                    self.logger.error(f"Ошибка в цикле сброса рекордов: {e}")
                    await asyncio.sleep(3600)  # Ждем час при ошибке
        
        # Запускаем фоновую задачу
        self._reset_task = asyncio.create_task(reset_loop())

    # handlers/record/services.py

    async def reset_daily_records(self, bot: Bot = None):
        """Сбрасывает только рекорды дня (выигрыши и проигрыши), НЕ данные профиля"""
        try:
            self.logger.info("🎯 Начинаем сброс ВСЕХ РЕКОРДОВ ДНЯ...")

            with self.core.db_session() as db:
                from database.models import DailyRecord, DailyLossRecord

                # 1. Удаляем ВСЕ записи DailyRecord (рекорды выигрышей за день)
                deleted_wins = db.query(DailyRecord).delete()

                # 2. Удаляем ВСЕ записи DailyLossRecord (рекорды проигрышей за день)
                deleted_losses = db.query(DailyLossRecord).delete()

                # 3. НЕ сбрасываем defeat_coins в профиле - это общая статистика!
                #    defeat_coins остается как общая сумма всех проигрышей пользователя

                db.commit()

                self.logger.info(
                    f"✅ Все рекорды дня сброшены! Удалено: {deleted_wins} выигрышей, {deleted_losses} проигрышей")

                # Уведомляем в консоль
                print("🔄 ВСЕ РЕКОРДЫ ДНЯ ОБНУЛЕНЫ! (00:00 МСК)")
                print(f"📊 Удалено записей выигрышей: {deleted_wins}")
                print(f"📊 Удалено записей проигрышей: {deleted_losses}")
                print("💰 Балансы пользователей сохранены")
                print("📈 Общая статистика проигрышей (defeat_coins) сохранена")

                return True

        except Exception as e:
            self.logger.error(f" Ошибка при сбросе рекордов дня: {e}")
            return False

    # ВСЕ ОСТАЛЬНЫЕ МЕТОДЫ ОСТАЮТСЯ БЕЗ ИЗМЕНЕНИЙreset_daily_records
    async def auto_register_user_in_top(self, user_id: int, chat_id: int, username: str = None,
                                        first_name: str = None) -> bool:
        """Автоматически регистрирует пользователя в топе чата при любом сообщении"""
        try:
            await self.core.ensure_user_registered(user_id, chat_id, username, first_name)

            with self.core.db_session() as db:
                from database.crud import ChatRepository

                user_position = ChatRepository.get_user_rank_in_chat(db, chat_id, user_id)
                if user_position is None:
                    self.logger.info(f"👤 Пользователь {user_id} автоматически зарегистрирован в топе чата {chat_id}")
                else:
                    self.logger.debug(f"👤 Пользователь {user_id} уже в топе на позиции {user_position}")

            return True

        except Exception as e:
            self.logger.error(f"Error in auto_register_user_in_top: {e}")
            return False

    async def add_win_record(self, user_id: int, amount: int, chat_id: int = None,
                             username: str = None, first_name: str = None) -> bool:
        """Добавляет или обновляет рекорд выигрыша (только если сумма больше текущего рекорда)"""
        try:
            if amount <= 0:
                self.logger.warning(f"Attempt to add non-positive win record: {amount}")
                return False

            if chat_id is None:
                chat_id = 0
            elif isinstance(chat_id, str):
                try:
                    chat_id = int(chat_id)
                except (ValueError, TypeError):
                    self.logger.warning(f"Invalid chat_id: {chat_id}, using 0")
                    chat_id = 0

            await self.core.ensure_user_registered(user_id, chat_id, username, first_name)

            with self.core.db_session() as db:
                from database.crud import DailyRecordRepository
                from datetime import date

                today = date.today()

                current_record = self.core._get_user_daily_record_global(user_id)

                if current_record and amount <= current_record.amount:
                    self.logger.info(
                        f"📊 Рекорд выигрыша не обновлен: текущий {current_record.amount} >= новый {amount}")
                    return True

                record = DailyRecordRepository.add_or_update_daily_record(
                    db=db,
                    user_id=user_id,
                    username=username or "",
                    first_name=first_name or "",
                    amount=amount,
                    chat_id=chat_id
                )

                if record:
                    if current_record:
                        self.logger.info(
                            f"🎯 Рекорд выигрыша УЛУЧШЕН для пользователя {user_id}: {current_record.amount} -> {amount} монет")
                    else:
                        self.logger.info(f"🎯 Новый рекорд выигрыша для пользователя {user_id}: {amount} монет")
                    return True
                else:
                    self.logger.error(f" Не удалось обновить рекорд для пользователя {user_id}")
                    return False

        except Exception as e:
            self.logger.error(f" Ошибка в add_win_record: {e}")
            return False

    # handlers/record/services.py

    async def add_loss_record(self, user_id: int, loss_amount: int, username: str = None,
                              first_name: str = None, chat_id: int = 0) -> bool:
        """Добавляет запись о проигрыше в DailyLossRecord (только если сумма больше текущего рекорда)"""
        try:
            if loss_amount <= 0:
                self.logger.warning(f"Attempt to add non-positive loss record: {loss_amount}")
                return False

            await self.core.ensure_user_registered(user_id, chat_id, username, first_name)

            with self.core.db_session() as db:
                from database.crud import DailyRecordRepository

                # Добавляем в таблицу рекордов проигрышей за день
                record = DailyRecordRepository.add_or_update_daily_loss_record(
                    db=db,
                    user_id=user_id,
                    username=username or "",
                    first_name=first_name or "",
                    loss_amount=loss_amount,
                    chat_id=chat_id
                )

                if record:
                    self.logger.info(f"💸 Рекорд проигрыша для пользователя {user_id}: {loss_amount} монет")
                    return True
                else:
                    self.logger.error(f" Не удалось обновить рекорд проигрыша для пользователя {user_id}")
                    return False

        except Exception as e:
            self.logger.error(f"Error in add_loss_record: {e}")
            return False

    async def update_user_balance(self, user_id: int, amount: int, username: str = None,
                                  first_name: str = None) -> bool:
        """Обновляет баланс пользователя (отдельно от рекордов)"""
        try:
            await self.core.ensure_user_registered(user_id, 0, username, first_name)

            with self.core.db_session() as db:
                from database.crud import UserRepository

                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if user:
                    new_balance = user.coins + amount
                    if new_balance < 0:
                        self.logger.warning(f"Negative balance prevented for user {user_id}")
                        return False

                    user.coins = new_balance
                    db.commit()
                    self.logger.info(f"Balance updated for user {user_id}: {amount} -> {new_balance} coins")
                    return True
                return False

        except Exception as e:
            self.logger.error(f"Error in update_user_balance: {e}")
            return False

    def get_daily_record_stats(self, user_id: int) -> dict:
        """Получает статистику рекордов пользователя за сегодня"""
        with self.core.db_session() as db:
            from database.crud import UserRepository

            user = UserRepository.get_user_by_telegram_id(db, user_id)
            win_record = self.core._get_user_daily_record_global(user_id)
            loss_record = self.core._get_user_loss_record(user_id)

            win_rank = self.core._get_user_global_rank_today(user_id)
            loss_rank = self.core._get_user_loss_rank_today(user_id)

            return {
                'win_amount': win_record.amount if win_record else 0,
                'win_rank': win_rank,
                'loss_amount': loss_record.defeat_coins if loss_record else 0,
                'loss_rank': loss_rank,
                'current_balance': user.coins if user else 0
            }

    def get_user_position_in_chat(self, user_id: int, chat_id: int) -> dict:
        """Получает позицию пользователя в топе чата"""
        with self.core.db_session() as db:
            from database.crud import ChatRepository, UserRepository

            user_position = ChatRepository.get_user_rank_in_chat(db, chat_id, user_id)
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            user_coins = user.coins if user else 0

            top_users = ChatRepository.get_top_rich_in_chat(db, chat_id, 5)

            return {
                'position': user_position,
                'coins': user_coins,
                'top_5': top_users
            }