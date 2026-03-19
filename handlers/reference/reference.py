# handlers/reference.py
import binascii
import os
import asyncio
from typing import List, Dict
from contextlib import contextmanager
from dataclasses import dataclass

from aiogram import types, Dispatcher
from aiogram.utils.deep_linking import get_start_link
from config import bot
from database import SessionLocal, get_db
from database.crud import UserRepository, ReferenceRepository
from const import REFERENCE_MENU_TEXT, REFERENCE_LINK_TEXT
from keyboards.reference_keyboard import reference_menu_keyboard
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# КОНФИГУРАЦИЯ
# =============================================================================

@dataclass(frozen=True)
class ReferralConfig:
    """Конфигурация реферальной системы"""
    REFERRER_BONUS: int = 1000000  # 1 000 000 Монет для пригласившего


# =============================================================================
# УТИЛИТЫ
# =============================================================================

class DatabaseManager:
    """Менеджер для работы с базой данных"""

    __slots__ = ()

    @staticmethod
    @contextmanager
    def db_session():
        """Контекстный менеджер для БД"""
        db = SessionLocal()
        try:
            db.expire_all()
            yield db
        finally:
            db.close()


# =============================================================================
# СЕРВИС РЕФЕРАЛЬНОЙ СИСТЕМЫ
# =============================================================================

class ReferralService:
    """Сервис для работы с реферальной системой"""

    __slots__ = ('_config',)

    def __init__(self):
        self._config = ReferralConfig()

    async def process_referral(self, message: types.Message, payload: str) -> bool:
        """Обработка реферальной ссылки. Возвращает True если реферал обработан"""
        # Проверяем, является ли payload реферальной ссылкой в новом формате
        if payload and payload.startswith("ref_"):
            try:
                # Извлекаем ID пригласившего
                referrer_id = int(payload.replace("ref_", ""))
                return await self._process_new_referral(message, referrer_id)
            except (ValueError, TypeError) as e:
                logger.error(f" Ошибка извлечения ID из реферальной ссылки: {e}")
                return False
        else:
            # Старый формат ссылки (для обратной совместимости)
            return await self._process_old_referral(message, payload)

    async def _process_new_referral(self, message: types.Message, referrer_id: int) -> bool:
        """Обработка реферального перехода в новом формате ref_<user_id>"""
        with DatabaseManager.db_session() as db:
            try:
                # Проверяем, не пытается ли пользователь пригласить сам себя
                if referrer_id == message.from_user.id:
                    return False

                # Проверяем, не заходил ли уже этот пользователь по реферальной ссылке
                if ReferenceRepository.check_reference_exists(db, message.from_user.id):
                    return False

                # Проверяем, существует ли пригласивший
                referrer = UserRepository.get_user_by_telegram_id(db, referrer_id)
                if not referrer:
                    logger.warning(f" Приглашающий {referrer_id} не найден в базе")
                    return False

                # Сохраняем реферала в базу
                ReferenceRepository.add_reference(db, referrer_id, message.from_user.id)

                # Начисляем бонус пригласившему (1 000 000 Монет)
                referrer.coins += self._config.REFERRER_BONUS

                # Обновляем общий заработок от рефералов
                if hasattr(referrer, 'referral_earnings'):
                    referrer.referral_earnings = (referrer.referral_earnings or 0) + self._config.REFERRER_BONUS

                # Уведомляем пригласившего
                asyncio.create_task(
                    self._send_referral_notification(referrer_id, message.from_user.id)
                )

                # Уведомляем нового пользователя
                asyncio.create_task(
                    self._send_welcome_notification(message.from_user.id, referrer_id)
                )

                db.commit()
                logger.info(f"✅ Реферал обработан: {message.from_user.id} приглашен {referrer_id}")
                return True

            except Exception as e:
                logger.error(f" Ошибка обработки реферала: {e}")
                db.rollback()
                return False

    async def _process_old_referral(self, message: types.Message, payload: str) -> bool:
        """Обработка реферального перехода в старом формате (для обратной совместимости)"""
        with DatabaseManager.db_session() as db:
            try:
                if ReferenceRepository.check_reference_exists(db, message.from_user.id):
                    return False

                link = await get_start_link(payload=payload)
                owner = UserRepository.get_user_by_link(db, link)
                if not owner:
                    return False

                ReferenceRepository.add_reference(db, owner.telegram_id, message.from_user.id)

                # Начисляем бонус пригласившему
                owner.coins += self._config.REFERRER_BONUS

                # Обновляем общий заработок от рефералов
                if hasattr(owner, 'referral_earnings'):
                    owner.referral_earnings = (owner.referral_earnings or 0) + self._config.REFERRER_BONUS

                # Уведомляем участников
                asyncio.create_task(
                    self._send_referral_notification(owner.telegram_id, message.from_user.id)
                )
                asyncio.create_task(
                    self._send_welcome_notification(message.from_user.id, owner.telegram_id)
                )

                db.commit()
                return True

            except Exception as e:
                logger.error(f" Ошибка обработки старой реферальной ссылки: {e}")
                db.rollback()
                return False

    async def _send_referral_notification(self, referrer_id: int, referred_user_id: int):
        """Отправляет уведомление пригласившему"""
        try:
            # Получаем информацию о пользователях
            referred_user = await bot.get_chat(referred_user_id)
            referrer_user = await bot.get_chat(referrer_id)

            referred_name = referred_user.username or referred_user.first_name or "новый пользователь"
            referrer_name = referrer_user.username or referrer_user.first_name or "пользователь"

            # Уведомление для пригласившего
            notification_text = (
                f"🎉 @{referred_name} зашёл по твоей ссылке!\n"
                f"+{self._config.REFERRER_BONUS:,} Монет начислено."
            ).replace(",", " ")

            await bot.send_message(
                chat_id=referrer_id,
                text=notification_text
            )

            logger.info(f"✅ Уведомление отправлено пригласившему {referrer_id}")

        except Exception as e:
            logger.error(f" Ошибка отправки уведомления пригласившему: {e}")

    async def _send_welcome_notification(self, referred_user_id: int, referrer_id: int):
        """Отправляет приветственное сообщение рефералу"""
        try:
            # Получаем информацию о пригласившем
            referrer_user = await bot.get_chat(referrer_id)
            referrer_name = referrer_user.username or referrer_user.first_name or "пользователь"

            # Приветствие для нового пользователя
            welcome_text = f"👋 Вы вошли в бот по ссылке от @{referrer_name}!"

            await bot.send_message(
                chat_id=referred_user_id,
                text=welcome_text
            )

            logger.info(f"✅ Приветствие отправлено новому пользователю {referred_user_id}")

        except Exception as e:
            logger.error(f" Ошибка отправки приветствия рефералу: {e}")


# =============================================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР СЕРВИСА
# =============================================================================

referral_service = ReferralService()


# =============================================================================
# ОБРАБОТЧИКИ CALLBACK КНОПОК
# =============================================================================

async def reference_menu_call(call: types.CallbackQuery):
    """Меню реферальной системы с обновленной статистикой"""
    db = next(get_db())
    try:
        # Получаем статистику рефералов
        referrer_id = call.from_user.id
        referrals_count = ReferenceRepository.get_referrals_count(db, referrer_id)

        # Получаем сумму бонусов
        user = UserRepository.get_user_by_telegram_id(db, referrer_id)
        if user:
            # Если у пользователя нет поля referral_earnings, вычисляем из бонусов
            if hasattr(user, 'referral_earnings'):
                referral_earnings = user.referral_earnings or 0
            else:
                # Вычисляем как referrals_count * REFERRER_BONUS
                referral_earnings = referrals_count * referral_service._config.REFERRER_BONUS
        else:
            referral_earnings = 0

        # Формируем текст с статистикой
        stats_text = f"""
📊 <b>Реферальная система</b>

👥 <b>Количество приглашенных:</b> {referrals_count}
💰 <b>Сумма полученных бонусов:</b> {referral_earnings:,} Монет
        """.strip()

        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=stats_text + "\n\n" + REFERENCE_MENU_TEXT,
            reply_markup=reference_menu_keyboard(),
            parse_mode=types.ParseMode.HTML
        )
    except Exception as e:
        logger.error(f" Ошибка отображения реферального меню: {e}")
    finally:
        db.close()


async def reference_link_call(call: types.CallbackQuery):
    """Генерация уникальной реферальной ссылки в новом формате"""
    db = next(get_db())
    try:
        user_id = call.from_user.id

        # Создаем ссылку в формате: https://t.me/ИмяБота?start=ref_<user_id>
        bot_username = (await bot.get_me()).username
        link = f"https://t.me/{bot_username}?start=ref_{user_id}"

        # Сохраняем ссылку в базе данных
        UserRepository.update_reference_link(db, user_id, link)

        # Получаем статистику для отображения
        referrals_count = ReferenceRepository.get_referrals_count(db, user_id)
        user = UserRepository.get_user_by_telegram_id(db, user_id)

        # Вычисляем общий заработок
        if user and hasattr(user, 'referral_earnings'):
            referral_earnings = user.referral_earnings or 0
        else:
            referral_earnings = referrals_count * referral_service._config.REFERRER_BONUS

        # Формируем сообщение со ссылкой и статистикой
        message_text = f"""
🔗 <b>Ваша реферальная ссылка:</b>

<code>{link}</code>

📊 <b>Статистика:</b>
👥 Приглашено: {referrals_count} человек
💰 Заработано: {referral_earnings:,} Монет

💎 <b>Как это работает:</b>
1. Поделитесь этой ссылкой с друзьями
2. Когда друг перейдет по ссылке и начнет использовать бота:
   • Вам начисляется {referral_service._config.REFERRER_BONUS:,} Монет
   • Другу показывается, кто его пригласил
   • Вы получаете уведомление о новом реферале
        """.strip()

        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=message_text,
            parse_mode=types.ParseMode.HTML
        )
    except Exception as e:
        logger.error(f" Ошибка создания реферальной ссылки: {e}")
    finally:
        db.close()


async def reference_list_call(call: types.CallbackQuery):
    """Показ списка приглашенных пользователей с новым форматированием"""
    db = next(get_db())
    try:
        referrer_id = call.from_user.id
        references = ReferenceRepository.get_user_references(db, referrer_id)

        if references:
            # Получаем информацию о каждом реферале
            referral_list = []
            for i, ref in enumerate(references[:50], 1):  # Ограничиваем 50 рефералов
                try:
                    # Получаем данные пользователя
                    user_data = UserRepository.get_user_by_telegram_id(db, ref.reference_telegram_id)
                    if user_data:
                        username = user_data.username
                        if not username and user_data.first_name:
                            username = user_data.first_name

                        if username:
                            referral_list.append(f"{i}. @{username}")
                        else:
                            referral_list.append(f"{i}. Пользователь #{ref.reference_telegram_id}")
                    else:
                        referral_list.append(f"{i}. Пользователь #{ref.reference_telegram_id}")
                except Exception as e:
                    logger.error(f"Ошибка получения данных реферала: {e}")
                    referral_list.append(f"{i}. Неизвестный пользователь")

            referral_text = '\n'.join(referral_list)

            # Добавляем статистику в начало
            referrals_count = len(references)
            user = UserRepository.get_user_by_telegram_id(db, referrer_id)

            if user and hasattr(user, 'referral_earnings'):
                referral_earnings = user.referral_earnings or 0
            else:
                referral_earnings = referrals_count * referral_service._config.REFERRER_BONUS

            stats_text = f"""
📊 <b>Статистика приглашений:</b>
👥 Всего приглашено: {referrals_count} человек
💰 Заработано: {referral_earnings:,} Монет

<b>Приглашенные:</b>
            """.strip()

            full_text = f"{stats_text}\n{referral_text}"

            # Проверяем длину сообщения (ограничение Telegram)
            if len(full_text) > 4000:
                full_text = f"{stats_text}\n\n⚠️ Список слишком длинный. Показаны первые 50 пользователей."

            await bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=full_text,
                parse_mode=types.ParseMode.HTML
            )
        else:
            await bot.answer_callback_query(
                callback_query_id=call.id,
                text=" У вас пока нет приглашенных пользователей",
                show_alert=True
            )

    except Exception as e:
        logger.error(f" Ошибка получения списка рефералов: {e}")
        await bot.answer_callback_query(
            callback_query_id=call.id,
            text=" Ошибка при получении списка рефералов",
            show_alert=True
        )
    finally:
        db.close()


# =============================================================================
# РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# =============================================================================

def register_reference_handlers(dp: Dispatcher):
    """Регистрация обработчиков реферальной системы"""
    dp.register_callback_query_handler(reference_menu_call, lambda call: call.data == "reference_menu")
    dp.register_callback_query_handler(reference_link_call, lambda call: call.data == "reference_link")
    dp.register_callback_query_handler(reference_list_call, lambda call: call.data == "referral_list")

    # Экспортируем сервис для использования в других модулях
    return referral_service