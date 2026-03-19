import logging
from datetime import datetime
from pathlib import Path

from aiogram import Dispatcher, types
from aiogram.types import InputFile

from database import SessionLocal
from database import models
from database.crud import UserRepository, ShopRepository

from .constants import WEDDING_LICENSE_ITEM_ID, WEDDING_LICENSE_ITEM_NAME, WEDDING_LICENSE_PRICE, MAX_GUESTS
from .keyboards import wedding_keyboard, divorce_keyboard
from .service import WeddingState, get_wedding, set_wedding, clear_wedding, \
    DivorceState, get_divorce, set_divorce, clear_divorce
from .texts import build_wedding_message, build_cancel_text, build_success_text, \
    build_divorce_message, build_divorce_quote
from .utils import display_name_from_user, user_link, is_chat_admin_or_owner

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
WEDDING_PHOTO_PATH = ASSETS_DIR / "wedding.png"


class MarriageHandlers:
    async def start_wedding(self, message: types.Message):
        """Команда !свадьба"""
        logger.info(f"💍 start_wedding called for {message.chat.id}")
        if message.chat.type not in ("group", "supergroup"):
            await message.reply("Команда !свадьба доступна только в группах.")
            return

        chat_id = message.chat.id
        user_id = message.from_user.id

        # Только одна свадьба на чат
        if get_wedding(chat_id):
            await message.reply("💍 В этом чате уже идёт свадьба. Сначала завершите или отмените текущую.")
            return

        # Резервируем лицензию
        db = SessionLocal()
        reserved = None
        try:
            # гарантируем, что пользователь есть в БД
            UserRepository.get_or_create_user(
                db,
                telegram_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )

            reserved = self._reserve_wedding_license(db, user_id)
            if not reserved:
                await message.reply(
                    "Перед запуском необходимо купить лицензию на свадьбу в магазине за 500000 монет.\n"
                    "Откройте магазин в ЛС бота: /shop или /магазин.\n"
                    "После покупки снова используйте команду !свадьба."
                )
                return

            # Создаём состояние
            state = WeddingState(chat_id=chat_id, initiator_id=user_id, message_id=0)
            state.reserved_license = reserved

            initiator_name = display_name_from_user(message.from_user)
            state.display_names[user_id] = user_link(user_id, initiator_name)

            sent = await message.answer(build_wedding_message(state), reply_markup=wedding_keyboard())
            state.message_id = sent.message_id
            set_wedding(state)

        except Exception as e:
            logger.exception("start_wedding error: %s", e)
            # если не получилось стартануть — возвращаем лицензию
            if reserved:
                try:
                    self._return_wedding_license(SessionLocal(), reserved)
                except Exception:
                    pass
            await message.reply("Произошла ошибка при запуске свадьбы. Попробуйте позже.")
        finally:
            try:
                db.close()
            except Exception:
                pass

    async def callback_handler(self, callback: types.CallbackQuery):
        data = callback.data or ""
        if not data.startswith("marriage:"):
            return

        chat_id = callback.message.chat.id
        state = get_wedding(chat_id)
        if not state or callback.message.message_id != state.message_id:
            await callback.answer("Эта свадьба уже неактуальна.", show_alert=True)
            return

        # Кэшируем имя пользователя
        if callback.from_user and callback.from_user.id not in state.display_names:
            state.display_names[callback.from_user.id] = user_link(
                callback.from_user.id,
                display_name_from_user(callback.from_user)
            )

        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "role" and len(parts) == 3:
            await self._handle_role(callback, state, parts[2])
            return
        if action == "guest":
            await self._handle_guest(callback, state)
            return
        if action == "sign":
            await self._handle_sign(callback, state)
            return
        if action == "marry":
            await self._handle_marry(callback, state)
            return
        if action == "cancel":
            await self._handle_cancel(callback, state)
            return

        await callback.answer("Неизвестное действие", show_alert=True)

    # -------------------------
    # ЛОГИКА КНОПОК
    # -------------------------

    async def _handle_role(self, callback: types.CallbackQuery, state: WeddingState, role_key: str):
        uid = callback.from_user.id

        # нельзя занимать несколько ролей/быть гостем
        if state.is_user_taken(uid):
            await callback.answer("Вы уже участвуете в этой свадьбе.", show_alert=True)
            return

        # нельзя занять уже занятую роль
        if role_key == "registrar":
            if state.registrar_id:
                await callback.answer("Регистратор уже выбран.", show_alert=True)
                return
            state.registrar_id = uid

        elif role_key == "groom":
            if state.groom_id:
                await callback.answer("Жених уже выбран.", show_alert=True)
                return
            state.groom_id = uid

        elif role_key == "bride":
            if state.bride_id:
                await callback.answer("Невеста уже выбрана.", show_alert=True)
                return
            state.bride_id = uid

        elif role_key == "witness":
            if state.witness_id:
                await callback.answer("Свидетель уже выбран.", show_alert=True)
                return
            state.witness_id = uid

        elif role_key == "witnessess":
            if state.witnessess_id:
                await callback.answer("Свидетельница уже выбрана.", show_alert=True)
                return
            state.witnessess_id = uid

        else:
            await callback.answer("Неизвестная роль", show_alert=True)
            return

        await self._refresh_message(callback, state)
        await callback.answer("✅")

    async def _handle_guest(self, callback: types.CallbackQuery, state: WeddingState):
        uid = callback.from_user.id
        if state.is_user_taken(uid):
            await callback.answer("Вы уже участвуете в этой свадьбе.", show_alert=True)
            return

        if len(state.guests) >= MAX_GUESTS:
            await callback.answer("Достигнут лимит гостей.", show_alert=True)
            return

        state.guests.append(uid)
        await self._refresh_message(callback, state)
        await callback.answer("✅ Вы добавлены в гости")

    async def _handle_sign(self, callback: types.CallbackQuery, state: WeddingState):
        uid = callback.from_user.id

        if uid == state.groom_id:
            state.groom_signed = True
            await self._refresh_message(callback, state)
            await callback.answer("✅ Жених поставил подпись")
            return
        if uid == state.bride_id:
            state.bride_signed = True
            await self._refresh_message(callback, state)
            await callback.answer("✅ Невеста поставила подпись")
            return

        await callback.answer("Подпись могут поставить только жених или невеста.", show_alert=True)

    async def _handle_marry(self, callback: types.CallbackQuery, state: WeddingState):
        uid = callback.from_user.id
        if uid != state.registrar_id:
            await callback.answer("Поженить может только регистратор.", show_alert=True)
            return

        if not state.are_roles_filled():
            await callback.answer("Заполните все роли.", show_alert=True)
            return

        if not state.are_signatures_ready():
            await callback.answer("Нужны подписи жениха и невесты.", show_alert=True)
            return

        # Запись в БД
        db = SessionLocal()
        try:
            # Проверка: оба не должны уже быть в браке
            if self._user_has_marriage(db, state.groom_id) or self._user_has_marriage(db, state.bride_id):
                await callback.answer("Один из пользователей уже состоит в браке.", show_alert=True)
                return

            marriage = models.Marriage(
                groom_id=state.groom_id,
                bride_id=state.bride_id,
                chat_id=state.chat_id,
                created_at=datetime.utcnow(),
            )
            db.add(marriage)
            db.commit()

            # Сообщение + фото
            groom_txt = state.display_names.get(state.groom_id, "")
            bride_txt = state.display_names.get(state.bride_id, "")
            caption = build_success_text(groom_txt, bride_txt)

            if WEDDING_PHOTO_PATH.exists():
                await callback.message.bot.send_photo(
                    chat_id=state.chat_id,
                    photo=InputFile(str(WEDDING_PHOTO_PATH)),
                    caption=caption,
                    parse_mode="HTML",
                )
            else:
                await callback.message.bot.send_message(state.chat_id, caption, parse_mode="HTML")

            # Убираем клавиатуру и закрываем состояние
            try:
                await callback.message.edit_text(build_wedding_message(state) + "\n\n✅ Брак зарегистрирован.", reply_markup=None)
            except Exception:
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass

            clear_wedding(state.chat_id)
            await callback.answer("✅")

        except Exception as e:
            db.rollback()
            logger.exception("marry error: %s", e)
            await callback.answer("Ошибка регистрации брака", show_alert=True)
        finally:
            db.close()

    async def _handle_cancel(self, callback: types.CallbackQuery, state: WeddingState):
        uid = callback.from_user.id

        allowed = uid == state.registrar_id or uid == state.initiator_id
        if not allowed:
            allowed = await is_chat_admin_or_owner(callback.message.bot, state.chat_id, uid)

        if not allowed:
            await callback.answer("Отменить свадьбу может регистратор/создатель или админ чата.", show_alert=True)
            return

        # Возврат лицензии
        if state.reserved_license:
            try:
                db = SessionLocal()
                self._return_wedding_license(db, state.reserved_license)
                db.close()
            except Exception:
                logger.exception("Failed to return wedding license")

        clear_wedding(state.chat_id)

        try:
            await callback.message.edit_text(build_cancel_text(), reply_markup=None)
        except Exception:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

        await callback.answer("✅")

    async def _refresh_message(self, callback: types.CallbackQuery, state: WeddingState):
        try:
            await callback.message.edit_text(
                build_wedding_message(state),
                reply_markup=wedding_keyboard(),
                parse_mode="HTML"
            )
        except Exception:
            # если сообщение не получилось обновить — ничего страшного
            pass

    # -------------------------
    # ЛИЦЕНЗИЯ
    # -------------------------

    def _reserve_wedding_license(self, db, user_id: int):
        """Снимаем 1 лицензию из user_purchases и держим её в памяти до финала."""
        q = db.query(models.UserPurchase).filter(
            models.UserPurchase.user_id == user_id,
            models.UserPurchase.item_id == WEDDING_LICENSE_ITEM_ID,
        ).order_by(models.UserPurchase.purchased_at.asc())

        purchase = q.first()
        if not purchase:
            return None

        data = {
            "user_id": purchase.user_id,
            "item_id": purchase.item_id,
            "item_name": purchase.item_name,
            "price": int(purchase.price) if purchase.price is not None else WEDDING_LICENSE_PRICE,
            "chat_id": int(purchase.chat_id) if purchase.chat_id is not None else 0,
        }

        db.delete(purchase)
        db.commit()
        return data

    def _return_wedding_license(self, db, reserved: dict):
        ShopRepository.add_user_purchase(
            db,
            user_id=reserved.get("user_id"),
            item_id=reserved.get("item_id", WEDDING_LICENSE_ITEM_ID),
            item_name=reserved.get("item_name", WEDDING_LICENSE_ITEM_NAME),
            price=reserved.get("price", WEDDING_LICENSE_PRICE),
            chat_id=reserved.get("chat_id", 0),
        )

    def _user_has_marriage(self, db, user_id: int) -> bool:
        if not user_id:
            return False
        return db.query(models.Marriage).filter(
            (models.Marriage.groom_id == user_id) | (models.Marriage.bride_id == user_id)
        ).first() is not None


    # -------------------------
    # РАЗВОД
    # -------------------------

    async def start_divorce(self, message: types.Message):
        """Команда !развод"""
        logger.info(f"💔 start_divorce called for {message.chat.id}")
        if message.chat.type not in ("group", "supergroup"):
            await message.reply("Команда !развод доступна только в группах.")
            return

        chat_id = message.chat.id
        user_id = message.from_user.id

        if get_divorce(chat_id):
            await message.reply("В этом чате уже идёт процесс развода.")
            return

        db = SessionLocal()
        try:
            # Ищем брак пользователя
            marriage = db.query(models.Marriage).filter(
                (models.Marriage.groom_id == user_id) | (models.Marriage.bride_id == user_id)
            ).first()

            if not marriage:
                await message.reply("Вы не состоите в браке.")
                return

            # Создаем состояние развода
            state = DivorceState(
                chat_id=chat_id,
                initiator_id=user_id,
                groom_id=marriage.groom_id,
                bride_id=marriage.bride_id,
                message_id=0
            )

            # Кэшируем имена супругов
            # Получаем имена из user purchases или last name если повезет
            # но лучше просто линки сформировать
            initiator_name = display_name_from_user(message.from_user)
            state.display_names[user_id] = user_link(user_id, initiator_name)

            # Для второго супруга попробуем найти имя в БД или использовать ID
            partner_id = marriage.bride_id if user_id == marriage.groom_id else marriage.groom_id
            partner_user = UserRepository.get_user_by_telegram_id(db, partner_id)
            if partner_user:
                p_name = partner_user.first_name
                state.display_names[partner_id] = user_link(partner_id, p_name)

            sent = await message.answer(
                build_divorce_message(state),
                reply_markup=divorce_keyboard(),
                parse_mode="HTML"
            )
            state.message_id = sent.message_id
            set_divorce(state)

        except Exception as e:
            logger.exception("start_divorce error: %s", e)
            await message.reply("Ошибка при запуске развода.")
        finally:
            db.close()

    async def divorce_callback_handler(self, callback: types.CallbackQuery):
        data = callback.data or ""
        if not data.startswith("divorce:"):
            return

        chat_id = callback.message.chat.id
        state = get_divorce(chat_id)
        if not state or callback.message.message_id != state.message_id:
            await callback.answer("Этот процесс развода уже неактуален.", show_alert=True)
            return

        # Кэшируем имя
        if callback.from_user and callback.from_user.id not in state.display_names:
            state.display_names[callback.from_user.id] = user_link(
                callback.from_user.id,
                display_name_from_user(callback.from_user)
            )

        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "role" and len(parts) == 3:
            await self._handle_divorce_role(callback, state, parts[2])
            return
        if action == "sign":
            await self._handle_divorce_sign(callback, state)
            return
        if action == "process":
            await self._handle_divorce_process(callback, state)
            return
        if action == "cancel":
            await self._handle_divorce_cancel(callback, state)
            return

        await callback.answer("Неизвестное действие")

    async def _handle_divorce_role(self, callback: types.CallbackQuery, state: DivorceState, role_key: str):
        uid = callback.from_user.id

        if role_key == "judge":
            if not state.can_be_judge(uid):
                await callback.answer("Вы не можете быть судьёй (или судья уже есть).", show_alert=True)
                return
            state.judge_id = uid
            await callback.answer("Вы назначены судьёй.")

        elif role_key == "juror":
            if not state.can_be_juror(uid):
                 # Если уже присяжный - молча игнорим или алерт
                if uid in state.jurors:
                    await callback.answer("Вы уже присяжный.", show_alert=True)
                    return
                await callback.answer("Вы не можете быть присяжным.", show_alert=True)
                return
            
            if len(state.jurors) >= 20:
                await callback.answer("Лимит присяжных достигнут.", show_alert=True)
                return
            
            state.jurors.append(uid)
            await callback.answer("Вы стали присяжным.")
        
        await self._refresh_divorce_message(callback, state)

    async def _handle_divorce_sign(self, callback: types.CallbackQuery, state: DivorceState):
        uid = callback.from_user.id
        if uid == state.groom_id:
            state.groom_signed = True
            await callback.answer("Муж подписал.")
        elif uid == state.bride_id:
            state.bride_signed = True
            await callback.answer("Жена подписала.")
        else:
            await callback.answer("Только супруги могут подписывать.", show_alert=True)
            return

        await self._refresh_divorce_message(callback, state)

    async def _handle_divorce_process(self, callback: types.CallbackQuery, state: DivorceState):
        uid = callback.from_user.id
        if uid != state.judge_id:
            await callback.answer("Развести может только судья.", show_alert=True)
            return

        if not state.are_signatures_ready():
            await callback.answer("Нужны подписи обоих супругов.", show_alert=True)
            return

        # Разводим
        db = SessionLocal()
        try:
            db.query(models.Marriage).filter(
                (models.Marriage.groom_id == state.groom_id) & (models.Marriage.bride_id == state.bride_id)
            ).delete()
            db.commit()

            # Отправляем цитату
            quote = build_divorce_quote()
            await callback.message.bot.send_message(state.chat_id, quote)

            # Удаляем сообщение с кнопками или меняем текст
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except:
                pass
            
            clear_divorce(state.chat_id)
            await callback.answer("Развод завершен.")

        except Exception as e:
            logger.exception("Divorce process error: %s", e)
            db.rollback()
            await callback.answer("Ошибка при разводе.", show_alert=True)
        finally:
            db.close()

    async def _handle_divorce_cancel(self, callback: types.CallbackQuery, state: DivorceState):
        uid = callback.from_user.id
        # Отменить могут супруги или судья?
        # В ТЗ: "Может быть нажата супругами."
        if uid not in (state.groom_id, state.bride_id):
             await callback.answer("Отменить могут только супруги.", show_alert=True)
             return

        clear_divorce(state.chat_id)
        try:
            await callback.message.edit_text("Развод отменен.", reply_markup=None)
        except:
            pass
        await callback.answer("Отменено")

    async def _refresh_divorce_message(self, callback: types.CallbackQuery, state: DivorceState):
        try:
            await callback.message.edit_text(
                build_divorce_message(state),
                reply_markup=divorce_keyboard(),
                parse_mode="HTML"
            )
        except:
            pass


def register_marriage_handlers(dp: Dispatcher):
    handler = MarriageHandlers()

    dp.register_message_handler(
        handler.start_wedding,
        lambda m: m.text and m.text.lower().strip() == "!свадьба",
        state="*"
    )

    dp.register_message_handler(
        handler.start_divorce,
        lambda m: m.text and m.text.lower().strip() == "!развод",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.callback_handler,
        lambda c: c.data and c.data.startswith("marriage:"),
        state="*"
    )

    dp.register_callback_query_handler(
        handler.divorce_callback_handler,
        lambda c: c.data and c.data.startswith("divorce:"),
        state="*"
    )

    logging.getLogger(__name__).info("✅ Marriage handlers registered")
