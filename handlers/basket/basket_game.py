import logging
from aiogram import types, Dispatcher
from aiogram.utils.exceptions import RetryAfter
import asyncio
from database.models import Chat
from handlers.game_lock import game_lock

logger = logging.getLogger(__name__)


class BasketGameHandler:
    """Обработчик игры 'Basket Win'"""

    def __init__(self):
        self.active_chats = set()  # Чаты где игра включена
        self.active_games = {}  # Активные игры по пользователям

    async def basket_command(self, message: types.Message):
        """Команда 'бас <ставка>'"""
        # Проверяем сообщение
        text = message.text or ''
        text_lower = text.lower().strip()

        # Проверяем, что сообщение команда "бас" (с пробелом или без)
        if text_lower not in ['бас'] and not text_lower.startswith('бас '):
            return

        # Если просто "бас" или "б" без аргументов - показываем справку
        if text_lower in ['бас']:
            await self._show_help(message)
            return

        # Проверяем, не активна ли уже игра у пользователя
        user_id = message.from_user.id
        # Проверяем, не активна ли уже игра у пользователя
        user_id = message.from_user.id
        if not game_lock.lock(user_id):
            await message.reply("⏳ У вас уже запущена игра! Дождитесь результата.")
            return

        # Устанавливаем флаг активной игры
        self.active_games[user_id] = True

        try:
            # Проверяем, что игра включена в чате
            chat_id = message.chat.id
            if not await self._is_game_enabled(chat_id):
                await message.reply(
                    "🏀 Игра 'Basket Win' отключена в этом чате\n"
                    "Включить можно командой !bason"
                )
                self.active_games.pop(user_id, None)
                return

            # Парсим ставку
            try:
                parts = text_lower.split()
                if len(parts) < 2:
                    await self._show_help(message)
                    self.active_games.pop(user_id, None)
                    return

                bet_str = parts[1]
                bet = self._parse_bet(bet_str)

                # Проверяем ставку
                if not self._is_valid_bet(bet):
                    await message.reply(
                        " Недопустимая ставка!\n"
                        "Минимальная ставка: 5 000 Монет\n"
                        "Пример: бас 5000"
                    )
                    self.active_games.pop(user_id, None)
                    return

            except ValueError as e:
                logger.error(f"Error parsing bet: {e}")
                await self._show_help(message)
                self.active_games.pop(user_id, None)
                return

            # Проверяем баланс
            balance = await self._get_user_balance(user_id)

            if balance < bet:
                await message.reply(
                    f"🏀 У тебя не хватает Монет\n"
                    f"Твой баланс: {balance:,} Монет"
                )
                self.active_games.pop(user_id, None)
                return

            # Снимаем ставку БЕЗ записи в историю транзакций
            if not await self._update_user_balance_without_history(user_id, -bet):
                await message.reply(" Ошибка при списании средств")
                self.active_games.pop(user_id, None)
                return

            # Отправляем анимированный бросок
            try:
                loading_msg = await message.reply(
                    f"🏀 <b>Игрок:</b> {message.from_user.first_name}\n"
                    f"💰 <b>Ставка:</b> {bet:,} Монет\n\n"
                    f"<i>Бросаем мяч...</i>",
                    parse_mode="HTML"
                )

                # Задержка перед броском
                await asyncio.sleep(1)

                # Отправляем анимацию баскетбольного мяча
                dice_msg = await message.answer_dice(emoji="🏀")

                # Ждем завершения анимации (4-5 секунд)
                await asyncio.sleep(5)

            except RetryAfter as e:
                # Ждем если flood control
                await asyncio.sleep(e.timeout)
                dice_msg = await message.answer_dice(emoji="🏀")
                await asyncio.sleep(5)

            # Получаем результат броска
            dice_value = dice_msg.dice.value

            # ОПРЕДЕЛЯЕМ РЕЗУЛЬТАТ ПО ТЗ:
            # Значения 1, 2, 3 = ПРОМАХ (проигрыш)
            # Значения 4, 5 = ПОПАДАНИЕ (×6)

            if dice_value in [1, 2, 3]:  # ПРОМАХ - проигрыш
                win_multiplier = 0
                result_message = "❌ Мимо! Ты проиграл"
                win_amount = 0
                result_type = "Промах"

            elif dice_value in [4, 5]:  # ПОПАДАНИЕ
                win_multiplier = 6
                result_message = "🎯 Вау! Прямое попадание!"
                win_amount = bet * win_multiplier
                result_type = "Прямое попадание"

            else:  # На всякий случай для других значений (если появятся)
                win_multiplier = 0
                result_message = "❌ Неизвестный результат"
                win_amount = 0
                result_type = "Проигрыш"

            # Начисляем выигрыш если есть или записываем проигрыш в историю
            if win_amount > 0:
                win_description = f"{result_type} (×{win_multiplier})"
                await self._update_user_balance_with_result(user_id, win_amount, win_description, original_bet=bet)
            else:
                # Записываем проигрыш в историю
                await self._update_user_balance_with_result(user_id, 0, result_type, original_bet=bet)

            # Получаем новый баланс
            new_balance = await self._get_user_balance(user_id)

            # Формируем результат
            result_text = (
                f"🏀 <b>BASKET</b>\n"
                f"<b>Игрок:</b> {message.from_user.first_name}\n"
                f"<b>Ставка:</b> {bet:,} Монет\n"
                f"<b>Результат:</b> {result_message}\n"
            )

            if win_amount > 0:
                net_win = win_amount - bet  # Чистый выигрыш
                result_text += (
                    f"<b>Множитель:</b> ×{win_multiplier}\n"
                    f"💰 <b>Чистый выигрыш:</b> +{net_win:,} Монет\n"
                )
            else:
                result_text += (
                    f"<b>Потеряно:</b> -{bet:,} Монет\n"
                )

            # Обновляем сообщение с результатом
            try:
                await loading_msg.edit_text(result_text, parse_mode="HTML")
            except RetryAfter as e:
                await asyncio.sleep(e.timeout)
                await loading_msg.edit_text(result_text, parse_mode="HTML")
            except Exception:
                # Если не удалось отредактировать, отправляем новое
                await message.answer(result_text, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Error in basket command: {e}", exc_info=True)
            try:
                await message.answer(" Произошла ошибка при запуске игры")
            except:
                pass
        finally:
            # Снимаем флаг активной игры и блокировку
            self.active_games.pop(user_id, None)
            game_lock.unlock(user_id)

    async def _show_help(self, message: types.Message):
        """Показывает справку по игре"""
        help_text = (
            f"🏀 <b>Игра 'Basket Win'</b>\n\n"
            f"<b>Команда:</b> <code>бас [ставка]</code> или <code>б [ставка]</code>\n"
            f"<b>Пример:</b> <code>бас 50</code>\n\n"
            f"<b>Правила:</b>\n"
            f"• Бросаем баскетбольный мяч 🏀\n"
            f"• Значение 1, 2 или 3: ❌ Промах → проигрыш\n"
            f"• Значение 4 или 5: 🎯 Попадание → ×6\n\n"
            f"<b>Команды управления (админы):</b>\n"
            f"<code>!bason</code> - включить игру в чате\n"
            f"<code>!basoff</code> - выключить игру в чате\n\n"
        )

        await message.reply(help_text, parse_mode="HTML")

    async def _is_game_enabled(self, chat_id: int) -> bool:
        """Проверяет, включена ли игра в чате"""
        from database import SessionLocal
        db = SessionLocal()
        try:
            chat = db.query(Chat).filter(Chat.chat_id == chat_id).first()
            return chat.basketball_enabled if chat else True  # По умолчанию включено
        except:
            return True
        finally:
            db.close()

    # ... (skipping constants or helpers if any)

    async def basket_on_command(self, message: types.Message):
        """Команда !bason - включить игру в чате"""
        if not await self._check_admin(message):
            await message.reply(" Только администраторы могут управлять игрой")
            return

        chat_id = message.chat.id
        from database import SessionLocal
        db = SessionLocal()
        try:
            chat = db.query(Chat).filter(Chat.chat_id == chat_id).first()
            if chat:
                chat.basketball_enabled = True
            else:
                # Создаем запись о чате
                chat = Chat(
                    chat_id=chat_id,
                    title=message.chat.title,
                    chat_type=message.chat.type,
                    is_active=True,
                    slots_enabled=True,
                    basketball_enabled=True
                )
                db.add(chat)

            db.commit()
            self.active_chats.add(chat_id)
            await message.reply("✅ Игра 'Basket Win' включена в этом чате!")
        except Exception as e:
            logger.error(f"Error enabling basket game: {e}")
            await message.reply(" Ошибка при включении игры")
        finally:
            db.close()

    async def basket_off_command(self, message: types.Message):
        """Команда !basoff - выключить игру в чате"""
        if not await self._check_admin(message):
            await message.reply(" Только администраторы могут управлять игрой")
            return

        chat_id = message.chat.id
        from database import SessionLocal
        db = SessionLocal()
        try:
            chat = db.query(Chat).filter(Chat.chat_id == chat_id).first()
            if chat:
                chat.basketball_enabled = False
                db.commit()
                self.active_chats.discard(chat_id)
                await message.reply(" Игра 'Basket Win' выключена в этом чате")
            else:
                await message.reply("ℹ️ Игра еще не была активирована в этом чате")
        except Exception as e:
            logger.error(f"Error disabling basket game: {e}")
            await message.reply(" Ошибка при выключении игры")
        finally:
            db.close()


    async def _check_admin(self, message: types.Message) -> bool:
        """Проверяет, является ли пользователь администратором чата"""
        try:
            chat_member = await message.bot.get_chat_member(
                message.chat.id,
                message.from_user.id
            )
            return chat_member.is_chat_admin()
        except:
            return False

    def _parse_bet(self, bet_str: str) -> int:
        """Парсит строку ставки в число"""
        bet_str = bet_str.lower().strip()
        
        # Обрабатываем сокращения k/к (тысячи) и m/м (миллионы)
        multiplier = 1
        if bet_str.endswith('k') or bet_str.endswith('к'):
            multiplier = 1000
            bet_str = bet_str[:-1]
        elif bet_str.endswith('m') or bet_str.endswith('м'):
            multiplier = 1_000_000
            bet_str = bet_str[:-1]
        elif bet_str.endswith('kk') or bet_str.endswith('кк'):
            multiplier = 1_000_000
            bet_str = bet_str[:-2]
        
        # Убираем пробелы и запятые
        bet_str = bet_str.replace(' ', '').replace(',', '').replace('.', '')
        
        return int(bet_str) * multiplier

    def _is_valid_bet(self, bet: int) -> bool:
        """Проверяет валидность ставки"""
        return bet >= 5000 and bet <= 10_000_000_000  # От 5к до 10 млрд

    async def _get_user_balance(self, user_id: int) -> int:
        """Получает баланс пользователя"""
        from database import SessionLocal
        from database.crud import UserRepository
        
        db = SessionLocal()
        try:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            return int(user.coins) if user else 0
        finally:
            db.close()

    async def _update_user_balance_without_history(self, user_id: int, amount: int) -> bool:
        """Обновляет баланс пользователя без записи в историю"""
        from database import SessionLocal
        from database.crud import UserRepository
        
        db = SessionLocal()
        try:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if user:
                new_balance = int(user.coins) + amount
                if new_balance < 0:
                    return False
                UserRepository.update_user_balance(db, user_id, new_balance)
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating balance: {e}")
            return False
        finally:
            db.close()

    async def _update_user_balance_with_result(self, user_id: int, win_amount: int, description: str, original_bet: int = 0) -> bool:
        """Обновляет баланс с записью результата игры"""
        from database import SessionLocal
        from database.crud import UserRepository
        
        db = SessionLocal()
        try:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if user:
                if win_amount > 0:
                    # Выигрыш
                    new_balance = int(user.coins) + win_amount
                    UserRepository.update_user_balance(db, user_id, new_balance)
                    
                    # Обновляем статистику выигрышей
                    user.win_coins = (user.win_coins or 0) + win_amount
                    net_win = win_amount - original_bet
                    if net_win > (user.max_win_coins or 0):
                        user.max_win_coins = net_win
                else:
                    # Проигрыш - уже списали при ставке
                    user.defeat_coins = (user.defeat_coins or 0) + original_bet
                
                # Обновляем максимальную ставку
                if original_bet > (user.max_bet or 0):
                    user.max_bet = original_bet
                
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating balance with result: {e}")
            db.rollback()
            return False
        finally:
            db.close()


def register_basket_handlers(dp: Dispatcher):
    """Регистрация обработчиков игры 'Basket Win'"""
    handler = BasketGameHandler()

    # Команда запуска игры
    dp.register_message_handler(
        handler.basket_command,
        lambda m: m.text and m.text.strip().lower() in ['бас'] or
                  m.text and (m.text.lower().startswith('бас ')),
        state="*"
    )

    # Команды управления
    dp.register_message_handler(
        handler.basket_on_command,
        lambda m: m.text and m.text.lower().startswith('!bason'),
        state="*"
    )
    dp.register_message_handler(
        handler.basket_off_command,
        lambda m: m.text and m.text.lower().startswith('!basoff'),
        state="*"
    )

    logger.info("✅ Обработчики игры 'Basket Win' зарегистрированы")