# handlers/transfer.py
import asyncio
import logging
import time
from typing import Tuple, Dict
from aiogram import Dispatcher, types
from aiogram.utils.markdown import escape_md
from config import bot
from database import get_db
from database.crud import UserRepository, TransactionRepository
from handlers.transfer_limit import transfer_limit


class TransferHandlers:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._db_session_cache = None
        # Словарь для хранения времени последнего перевода пользователя
        # {user_id: timestamp}
        self._last_transfer_time: Dict[int, float] = {}

    def _get_db_session(self):
        """Создает сессию БД с обработкой ошибок"""
        try:
            return next(get_db())
        except Exception as e:
            self.logger.error(f"Database connection error: {e}")
            raise

    def _sanitize_name(self, name: str) -> str:
        """Оптимизированная очистка имени от невидимых символов"""
        if not name:
            return "Аноним"

        # Быстрая очистка через фильтрацию
        cleaned = ''.join(c for c in name.strip()
                          if ord(c) >= 32 and c not in ['\u200B', '\u0000', '\x00'])[:100]

        return cleaned or "Аноним"

    def _get_user_display_name(self, user) -> str:
        """Оптимизированное получение отображаемого имени"""
        if not user:
            return "Аноним"

        if user.first_name:
            sanitized_name = self._sanitize_name(user.first_name)
            if sanitized_name != "Аноним":
                return sanitized_name

        if user.username:
            return f"@{user.username}"

        return "Аноним"

    async def _validate_transfer_conditions(self, message: types.Message, amount: int) -> Tuple[bool, str]:
        """Оптимизированная проверка условий перевода"""
        if not message.reply_to_message:
            return False, " Чтобы перевести деньги, ответьте на сообщение пользователя"

        reply_user = message.reply_to_message.from_user
        sender_id = message.from_user.id

        if reply_user.id == sender_id:
            return False, " Нельзя переводить деньги самому себе!"

        if reply_user.id == (await bot.get_me()).id:
            return False, " Нельзя переводить деньги боту!"

        if amount <= 0:
            return False, " Сумма перевода должна быть положительной!"

        # Проверка антифлуда
        last_time = self._last_transfer_time.get(sender_id)
        if last_time:
            time_passed = time.time() - last_time
            if time_passed < 30:
                remaining_time = int(30 - time_passed)
                return False, f"⏳ Следующий перевод можно будет сделать через {remaining_time} секунд"

        return True, ""

    async def _get_or_create_recipient(self, db, recipient_id: int, recipient_user: types.User):
        """Оптимизированное получение/создание получателя"""
        recipient = UserRepository.get_user_by_telegram_id(db, recipient_id)
        if recipient:
            return recipient, recipient.coins

        # Создаем нового пользователя
        clean_first_name = self._sanitize_name(recipient_user.first_name)
        clean_last_name = self._sanitize_name(recipient_user.last_name) if recipient_user.last_name else None

        recipient = UserRepository.get_or_create_user(
            db=db,
            telegram_id=recipient_id,
            username=recipient_user.username,
            first_name=clean_first_name,
            last_name=clean_last_name
        )
        return recipient, 0

    async def _execute_transfer(self, db, sender_id: int, recipient_id: int, amount: int) -> bool:
        """Оптимизированное выполнение перевода"""
        try:
            # Получаем оба пользователя
            sender = UserRepository.get_user_by_telegram_id(db, sender_id)
            if not sender or sender.coins < amount:
                return False

            recipient = UserRepository.get_user_by_telegram_id(db, recipient_id)
            if not recipient:
                return False

            # Обновляем балансы
            UserRepository.update_user_balance(db, sender_id, sender.coins - amount)
            UserRepository.update_user_balance(db, recipient_id, recipient.coins + amount)

            # Создаем транзакцию
            TransactionRepository.create_transaction(
                db=db,
                from_user_id=sender_id,
                to_user_id=recipient_id,
                amount=amount,
                description="Перевод в групповом чате"
            )

            # Обновляем лимиты
            transfer_limit.record_transfer(sender_id, amount)

            # Обновляем время последнего перевода
            self._last_transfer_time[sender_id] = time.time()

            return True
        except Exception as e:
            self.logger.error(f"Error executing transfer: {e}")
            return False

    async def _process_transfer(self, message: types.Message, amount: int) -> bool:
        """Оптимизированная основная логика перевода"""
        sender_id = message.from_user.id

        # Быстрая валидация
        is_valid, error_msg = await self._validate_transfer_conditions(message, amount)
        if not is_valid:
            await message.reply(error_msg)
            return False

        recipient_id = message.reply_to_message.from_user.id

        # Проверка лимитов
        can_transfer, error_msg, remaining, is_unlimited = transfer_limit.can_make_transfer(sender_id, amount)
        if not can_transfer:
            await message.reply(error_msg)
            return False

        db = self._get_db_session()
        try:
            # Проверяем отправителя
            sender = UserRepository.get_user_by_telegram_id(db, sender_id)
            if not sender:
                await message.reply(" Сначала зарегистрируйтесь через /start в ЛС с ботом!")
                return False

            # Получаем/создаем получателя
            recipient_user = message.reply_to_message.from_user
            recipient, _ = await self._get_or_create_recipient(db, recipient_id, recipient_user)

            # Выполняем перевод
            if not await self._execute_transfer(db, sender_id, recipient_id, amount):
                await message.reply(" Ошибка при выполнении перевода")
                return False

            # Формируем успешное сообщение
            sender_name = self._get_user_display_name(sender)
            recipient_name = self._sanitize_name(recipient_user.first_name) or (
                f"@{recipient_user.username}" if recipient_user.username else "Аноним")

            success_text = (
                f"{escape_md(sender_name)} передал(а) {amount} монет {escape_md(recipient_name)}"
            )

            # Отправляем сообщение без reply, чтобы убрать "пересланно"
            await message.answer(success_text, parse_mode=types.ParseMode.MARKDOWN)

            return True

        except Exception as e:
            self.logger.error(f"Database error in transfer: {e}")
            await message.reply(" Ошибка базы данных при выполнении перевода")
            return False
        finally:
            db.close()

    async def handle_group_transfer(self, message: types.Message):
        """Оптимизированный обработчик переводов через +"""
        if not message.text or not message.text.strip().startswith('+'):
            return

        text = message.text.strip()

        try:
            amount_str = text[1:].strip()
            if not amount_str:
                await message.reply(" Укажите сумму после +. Пример: +100")
                return

            amount = int(amount_str)
            await self._process_transfer(message, amount)
        except ValueError:
            await message.reply(" Неверный формат суммы! Используйте: +100")

    async def handle_dait_command(self, message: types.Message):
        """Оптимизированный обработчик команды 'дать'"""
        if not message.text:
            return

        text = message.text.strip()
        parts = text.split()

        if len(parts) < 2:
            await message.reply(" Неверный формат! Используйте: дать 100")
            return

        try:
            amount = int(parts[1])
            await self._process_transfer(message, amount)
        except ValueError:
            await message.reply(" Неверный формат суммы! Используйте: дать 100")

    async def show_balance(self, message: types.Message):
        """Оптимизированное отображение баланса"""
        user_id = message.from_user.id
        db = self._get_db_session()
        try:
            await asyncio.sleep(0.1)
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                await message.reply(" Сначала зарегистрируйтесь через /start в ЛС с ботом!")
                return

            coins = user.coins
            display_name = f"[{escape_md(self._get_user_display_name(user))}](tg://user?id={user_id})"

            # Быстрая проверка лимитов
            _, _, remaining, is_unlimited = transfer_limit.can_make_transfer(user_id, 1)

            balance_text = f"{display_name} \nМонет: {coins}"
            if not is_unlimited:
                balance_text += f"\n📊 Доступно для переводов сегодня: {remaining} Монет"
            else:
                balance_text += "\n♾️ Безлимитные переводы"

            await message.answer(balance_text, parse_mode=types.ParseMode.MARKDOWN)

        finally:
            db.close()

    async def show_limits(self, message: types.Message):
        """Отображение информации о лимитах"""
        user_id = message.from_user.id
        limit_info = transfer_limit.get_limit_info(user_id)
        await message.answer(limit_info)

    async def show_transaction_history(self, message: types.Message):
        """Оптимизированное отображение истории транзакций"""
        user_id = message.from_user.id
        db = self._get_db_session()
        try:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                await message.reply(" Сначала зарегистрируйтесь через /start в ЛС с ботом!")
                return

            transactions = TransactionRepository.get_user_transactions(db, user_id, limit=10)
            if not transactions:
                await message.answer("📊 История транзакций:\nПока нет операций")
                return

            history_text = "📊 *История ваших транзакций:*\n\n"

            # Оптимизированное форматирование транзакций
            for i, transaction in enumerate(transactions, 1):
                timestamp = transaction.timestamp.strftime("%d.%m %H:%M")
                history_text += self._format_transaction_line(i, transaction, user_id, db, timestamp)

            if len(history_text) > 4000:
                history_text = history_text[:4000] + "\n\n... (показаны последние операции)"

            await message.answer(history_text, parse_mode=types.ParseMode.MARKDOWN)

        finally:
            db.close()

    def _format_transaction_line(self, index: int, transaction, user_id: int, db, timestamp: str) -> str:
        """Оптимизированное форматирование одной строки транзакции"""
        if transaction.from_user_id == user_id:
            target_user = UserRepository.get_user_by_telegram_id(db, transaction.to_user_id)
            target_name = self._get_user_link(target_user) if target_user else "Аноним"
            return f"{index}. ➡️ Отправлено: -{transaction.amount} Монет для {target_name}\n   🕒 {timestamp}\n\n"
        else:
            source_user = UserRepository.get_user_by_telegram_id(db, transaction.from_user_id)
            source_name = self._get_user_link(source_user) if source_user else "Аноним"
            return f"{index}. ⬅️ Получено: +{transaction.amount} Монет от {source_name}\n   🕒 {timestamp}\n\n"

    def _get_user_link(self, user) -> str:
        """Быстрое создание ссылки на пользователя"""
        if not user:
            return "Аноним"
        return f"[{escape_md(self._get_user_display_name(user))}](tg://user?id={user.telegram_id})"


def register_transfer_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    handlers = TransferHandlers()

    # Команда лимитов
    dp.register_message_handler(
        handlers.show_limits,
        lambda message: message.text and message.text.lower() in ['лимиты', 'лимит', 'limits']
    )

    # История транзакций
    dp.register_message_handler(
        handlers.show_transaction_history,
        lambda message: message.text and message.text.lower() in ['транзакции', 'переводы']
    )

    # Обработчик переводов через +
    dp.register_message_handler(
        handlers.handle_group_transfer,
        lambda message: message.text and message.text.strip().startswith('+')
    )

    # Обработчик команды "дать"
    dp.register_message_handler(
        handlers.handle_dait_command,
        lambda message: message.text and message.text.strip().lower().startswith('дать ')
    )

    print("✅ Transfer handlers registered (gift functionality removed)")