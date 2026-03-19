import logging
from typing import Dict
from contextlib import contextmanager

from aiogram import Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import func

from database import get_db, models
from database.crud import UserRepository, ShopRepository

# Конфигурация магазина ТОЧНО по вашему заданию
SHOP_ITEMS = [
    {
        "id": 3,
        "name": "защита от !бот стоп",
        "price": 15000000,
        "price_display": "15 лям",
        "description": "защита от !бот стоп — 15 лям",
        "benefit": "Защита от команды !бот стоп"
    },
    {
        "id": 4,
        "name": "защита от !бот стоп !!мут !!помолчи",
        "price": 25000000,
        "price_display": "25 лям",
        "description": "защита от !бот стоп !!мут !!помолчи - 25 лям",
        "benefit": "Полная защита от мьюта и команды бот стоп"
    },
    {
        "id": 5,
        "name": "защита от !граб",
        "price": 15000000,
        "price_display": "15 лям",
        "description": "защита от !граб - 15 лям",
        "benefit": "Защита от грабежа другими игроками"
    },
    {
        "id": 6,
        "name": "Лицензия на свадьбу",
        "price": 500000,
        "price_display": "500к",
        "description": "Лицензия на свадьбу — 500к",
        "benefit": "Позволяет заключить брак в чате"
    }
]

# ID товаров для быстрого доступа
ITEM_IDS = {item["id"]: item for item in SHOP_ITEMS}


class ShopHandler:
    """Класс для обработки операций магазина"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @contextmanager
    def _db_session(self):
        """Контекстный менеджер для работы с БД"""
        session = None
        try:
            session = next(get_db())
            yield session
        except Exception as e:
            self.logger.error(f"Database connection error: {e}")
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()

    def _format_number(self, number: int) -> str:
        """Форматирует числа с разделителями тысяч"""
        return f"{number:,}".replace(",", " ")

    def _create_shop_keyboard(self, user_id: int = None, chat_id: int = None) -> InlineKeyboardMarkup:
        """Создает клавиатуру магазина с учетом активных покупок"""
        keyboard = InlineKeyboardMarkup(row_width=1)

        try:
            with self._db_session() as db:
                # Получаем количество покупок для лицензий
                license_counts = {}
                if user_id:
                    # Считаем количество покупок обычных лицензий (item_id = 2)
                    regular_count = db.query(func.count(models.UserPurchase.id)).filter(
                        models.UserPurchase.user_id == user_id,
                        models.UserPurchase.item_id == 2  # обычная лицензия
                    ).scalar() or 0

                    # Считаем количество покупок VIP лицензий (item_id = 1)
                    vip_count = db.query(func.count(models.UserPurchase.id)).filter(
                        models.UserPurchase.user_id == user_id,
                        models.UserPurchase.item_id == 1  # VIP лицензия
                    ).scalar() or 0

                    # Считаем количество лицензий на свадьбу (item_id = 6)
                    wedding_license_count = db.query(func.count(models.UserPurchase.id)).filter(
                        models.UserPurchase.user_id == user_id,
                        models.UserPurchase.item_id == 6  # лицензия на свадьбу
                    ).scalar() or 0

                    license_counts = {
                        2: regular_count,  # обычная лицензия
                        1: vip_count,  # VIP-ЛИЦЕНЗИЯ
                        6: wedding_license_count  # лицензия на свадьбу
                    }

                # Добавляем кнопки товаров по новому формату
                # Используем текстовые цены, а не из SHOP_ITEMS
                items_with_prices = [
                    {"id": 3, "name": "защита от !бот стоп", "price": "4.000.000"},
                    {"id": 4, "name": "защита от !!мут !бот стоп", "price": "8.000.000"},
                    {"id": 5, "name": "защита от !граб", "price": "10.000.000"},
                    {"id": 6, "name": "лицензия на свадьбу", "price": "500.000"}
                ]

                for item in items_with_prices:
                    # Для свадебной лицензии добавляем количество
                    if item["id"] == 6:
                        count = license_counts.get(6, 0)
                        if count > 0:
                            button_text = f"{item['name']} - {item['price']} монет (у вас {count})"
                        else:
                            button_text = f"{item['name']} - {item['price']} монет"
                    else:
                        button_text = f"{item['name']} - {item['price']} монет"

                    callback_data = f"shop_buy_{item['id']}"

                    keyboard.add(InlineKeyboardButton(
                        text=button_text,
                        callback_data=callback_data
                    ))

        except Exception as e:
            self.logger.error(f"Error creating shop keyboard: {e}")
            # Возвращаем клавиатуру без подсчета в случае ошибки
            items_with_prices = [
                {"id": 3, "name": "защита от !бот стоп", "price": "4.000.000"},
                {"id": 4, "name": "защита от !!мут !бот стоп", "price": "8.000.000"},
                {"id": 5, "name": "защита от !граб", "price": "10.000.000"},
                {"id": 6, "name": "лицензия на свадьбу", "price": "500.000"}
            ]

            for item in items_with_prices:
                button_text = f"{item['name']} - {item['price']} монет"
                keyboard.add(InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"shop_buy_{item['id']}"
                ))

        return keyboard

    def _get_shop_message_text(self, user_id: int = None, chat_id: int = None) -> str:
        """Формирует текст сообщения для магазина"""
        try:
            text = "<b>Магазин</b>\n\n"

            # Добавляем описания товаров
            text += "Защита от !бот стоп - 4.000.000 монет\n"
            text += "Защита от !!мут !бот стоп - 8.000.000 монет\n"
            text += "Невидимка от !бот ищи - 10.000.000 монет\n"
            text += "Лицензия на свадьбу - 500.000 монет\n\n"

            # Информация о количестве лицензий
            if user_id:
                try:
                    with self._db_session() as db:
                        wedding_count = db.query(func.count(models.UserPurchase.id)).filter(
                            models.UserPurchase.user_id == user_id,
                            models.UserPurchase.item_id == 6
                        ).scalar() or 0

                        if wedding_count > 0:
                            text += "<b>Ваши лицензии:</b>\n"
                            text += f"Лицензий на свадьбу: {wedding_count}\n"
                            text += "\n"
                except Exception as e:
                    self.logger.error(f"Error getting license counts for shop text: {e}")

            return text

        except Exception as e:
            self.logger.error(f"Error in _get_shop_message_text: {e}")
            return "🛒 <b>Магазин</b>\n\n"

    async def shop_command(self, message: types.Message):
        """Обработчик команды магазина"""
        # Проверяем, что команда вызвана в личных сообщениях
        if message.chat.type != "private":
            bot_username = (await message.bot.get_me()).username
            await message.reply(
                f"🏪<b>Магазин</b>\n"
                f"Покупки выполняются только в <a href='https://t.me/{bot_username}'>личном чате с ботом</a>.",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return

        user_id = message.from_user.id
        chat_id = message.chat.id

        try:
            # Используем упрощенный текст
            text = "<b>Магазин</b>\n\n"
            text += "Защита от !бот стоп - 4.000.000 монет\n"
            text += "Защита от !!мут !бот стоп - 8.000.000 монет\n"
            text += "Невидимка от !бот ищи - 10.000.000 монет\n"
            text += "Лицензия на свадьбу - 500.000 монет\n\n"

            # Получаем количество лицензий
            try:
                with self._db_session() as db:
                    wedding_count = db.query(func.count(models.UserPurchase.id)).filter(
                        models.UserPurchase.user_id == user_id,
                        models.UserPurchase.item_id == 6  # лицензия на свадьбу
                    ).scalar() or 0

                    if wedding_count > 0:
                        text += "<b>Ваши лицензии:</b>\n"
                        text += f"Лицензий на свадьбу: {wedding_count}\n"
                        text += "\n"
            except Exception as e:
                self.logger.error(f"Error getting license counts: {e}")

            keyboard = self._create_shop_keyboard(user_id, chat_id)

            await message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            self.logger.error(f"Error in shop_command: {e}")
            try:
                keyboard = self._create_shop_keyboard(user_id, chat_id)
                await message.answer(
                    "🛒 <b>Магазин</b>\n\n",
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as inner_e:
                self.logger.error(f"Error sending fallback shop message: {inner_e}")

    async def shop_callback_handler(self, callback: types.CallbackQuery):
        """Обработчик нажатий на кнопки магазина"""
        action = callback.data
        user_id = callback.from_user.id
        chat_id = callback.message.chat.id

        try:
            if action.startswith("shop_buy_"):
                await self._handle_purchase(callback, user_id, chat_id)
            elif action == "back_to_shop":
                await self._handle_back_to_shop(callback, user_id, chat_id)

        except Exception as e:
            self.logger.error(f"Error in shop callback handler: {e}")
            await self._handle_error(callback)

    async def _handle_purchase(self, callback: types.CallbackQuery, user_id: int, chat_id: int):
        """Обрабатывает попытку покупки товара"""
        item_id = int(callback.data.split("_")[2])
        item = ITEM_IDS.get(item_id)

        if not item:
            await callback.answer(" Товар не найден", show_alert=True)
            return

        with self._db_session() as db:
            try:
                # Получаем пользователя и проверяем баланс
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await callback.message.edit_text(
                        " Ошибка! Пользователь не найден.",
                        reply_markup=self._get_back_keyboard(),
                        parse_mode="HTML"
                    )
                    return

                user_balance = user.coins

                # Проверяем достаточно ли средств
                if user_balance >= item["price"]:
                    # Совершаем покупку
                    user.coins -= item["price"]

                    # Для всех товаров используем глобальный подход (chat_id = 0)
                    purchase_chat_id = 0

                    ShopRepository.add_user_purchase(
                        db, user_id, item_id, item["name"], item["price"], purchase_chat_id
                    )

                    db.commit()

                    # Получаем новое количество лицензий (если это лицензия)
                    new_count = None
                    if item["id"] in [1, 2]:
                        new_count = db.query(func.count(models.UserPurchase.id)).filter(
                            models.UserPurchase.user_id == user_id,
                            models.UserPurchase.item_id == item["id"]
                        ).scalar() or 0

                    # Формируем сообщение об успехе
                    price_formatted = self._format_number(item["price"])
                    new_balance_formatted = self._format_number(user.coins)

                    success_text = ""
                    
                    # Специальное сообщение для лицензий
                    # Специальное сообщение для лицензий
                    if item["id"] in [1, 2]:
                         success_text = (
                            f"<b>Вы успешно приобрели {item['name']}!</b>\n\n"
                            f"Стоимость: {price_formatted} монет\n"
                        )
                    else:
                        success_text = (
                            f"<b>Покупка успешна!</b>\n\n"
                            f"Товар: {item['name']}\n"
                            f"Стоимость: {price_formatted} монет\n"
                            f"Списано: {price_formatted} монет\n\n"
                        )

                    # Добавляем информацию о количестве лицензий
                    if new_count is not None:
                        if item["id"] == 1:
                            success_text += f"Теперь у вас {new_count} обычных лицензий\n\n"
                        elif item["id"] == 2:
                            success_text += f"Теперь у вас {new_count} VIP лицензий\n\n"

                    success_text += (
                        f"<b>Преимущество:</b>\n"
                        f"{item['benefit']}"
                    )

                    # Добавляем информацию о глобальности для защиты
                    if item["id"] in [3, 4, 5]:
                        success_text += "\n\n<b>Эта защита действует во всех чатах!</b>"

                    await callback.message.edit_text(
                        success_text,
                        reply_markup=self._get_back_keyboard(),
                        parse_mode="HTML"
                    )

                    self.logger.info(f"User {user_id} purchased item {item_id}")

                else:
                    # Недостаточно средств
                    missing_money = item["price"] - user_balance
                    await self._handle_insufficient_funds(callback, item, missing_money, user_id)

            except Exception as e:
                db.rollback()
                self.logger.error(f"Purchase error: {e}")
                await callback.message.edit_text(
                    " Произошла ошибка при покупке!\n\n"
                    "Пожалуйста, попробуйте позже.",
                    reply_markup=self._get_back_keyboard(),
                    parse_mode="HTML"
                )

    async def _handle_insufficient_funds(self, callback: types.CallbackQuery, item: Dict,
                                         missing_money: int, user_id: int):
        """Обрабатывает случай недостатка средств"""
        missing_formatted = self._format_number(missing_money)

        try:
            # Пытаемся отправить уведомление в ЛС
            await callback.message.bot.send_message(
                user_id,
                f" <b>Недостаточно средств</b>\n\n"
                f"📦 Товар: {item['name']}\n"
                f"💷 Не хватает: {missing_formatted} монет\n\n"  # Изменил Сом на монет
                f"💡 Пополните баланс и попробуйте снова!",
                parse_mode="HTML"
            )

            await callback.message.edit_text(
                " <b>Недостаточно средств</b>\n\n"
                f"Информация отправлена в личные сообщения.",
                reply_markup=self._get_back_keyboard(),
                parse_mode="HTML"
            )

        except Exception as e:
            # Если не удалось отправить в ЛС
            self.logger.warning(f"Could not send DM to user {user_id}: {e}")
            await callback.message.edit_text(
                f" <b>Недостаточно средств!</b>\n\n"
                f"📦 Товар: {item['name']}\n"
                f"💷 Не хватает: {missing_formatted} монет\n\n"  # Изменил Сом на монет
                f"💡 <b>Разблокируйте бота в ЛС для получения уведомлений!</b>",
                reply_markup=self._get_back_keyboard(),
                parse_mode="HTML"
            )

    async def _handle_back_to_shop(self, callback: types.CallbackQuery, user_id: int, chat_id: int):
        """Возвращает в главное меню магазина"""
        try:
            # Используем тот же текст, что и в shop_command
            text = "<b>Магазин</b>\n\n"
            text += "Защита от !бот стоп - 4.000.000 монет\n"
            text += "Защита от !!мут !бот стоп - 8.000.000 монет\n"
            text += "Невидимка от !бот ищи - 10.000.000 монет\n"
            text += "Лицензия на свадьбу - 500.000 монет\n\n"

            # Получаем количество лицензий
            try:
                with self._db_session() as db:
                    wedding_count = db.query(func.count(models.UserPurchase.id)).filter(
                        models.UserPurchase.user_id == user_id,
                        models.UserPurchase.item_id == 6  # лицензия на свадьбу
                    ).scalar() or 0

                    if wedding_count > 0:
                        text += "<b>Ваши лицензии:</b>\n"
                        text += f"Лицензий на свадьбу: {wedding_count}\n"
                        text += "\n"
            except Exception as e:
                self.logger.error(f"Error getting license counts: {e}")

            # Получаем клавиатуру
            keyboard = self._create_shop_keyboard(user_id, chat_id)

            # Редактируем сообщение
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

            # Подтверждаем callback
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in _handle_back_to_shop: {e}", exc_info=True)

            # Если не удалось отредактировать, отправляем новое сообщение
            try:
                keyboard = self._create_shop_keyboard(user_id, chat_id)
                await callback.message.answer(
                    "🛒 <b>Магазин</b>\n\n",
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                await callback.answer()
            except Exception as send_error:
                self.logger.error(f"Error sending new message: {send_error}")
                await callback.answer(" Ошибка загрузки магазина", show_alert=True)

    async def _handle_error(self, callback: types.CallbackQuery):
        """Обрабатывает общие ошибки"""
        try:
            await callback.message.edit_text(
                " <b>Произошла ошибка!</b>\n\n"
                "Пожалуйста, попробуйте позже или обратитесь к администратору.",
                reply_markup=self._get_back_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            self.logger.error(f"Error in _handle_error: {e}")
            await callback.answer(" Произошла ошибка", show_alert=True)

    def _get_back_keyboard(self) -> InlineKeyboardMarkup:
        """Создает клавиатуру с кнопкой возврата"""
        return InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅️ Назад в магазин", callback_data="back_to_shop")
        )


def register_shop_handlers(dp: Dispatcher):
    """Регистрация обработчиков магазина"""
    handler = ShopHandler()

    # Регистрация команд
    dp.register_message_handler(
        handler.shop_command,
        commands=["магазин", "shop"],
        state="*"
    )
    dp.register_message_handler(
        handler.shop_command,
        lambda m: m.text and m.text.lower().strip() in ["магазин", "shop"],
        state="*"
    )

    # Регистрация callback обработчиков
    dp.register_callback_query_handler(
        handler.shop_callback_handler,
        lambda c: c.data.startswith("shop_buy_") or c.data == "back_to_shop",
        state="*"
    )

    logging.info("✅ Магазин обработчики зарегистрированы")