# main_admin_handler.py

import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher import FSMContext

from database.models import ModerationLog
from handlers.admin.mute_ban import MuteBanManager
from .admin_constants import ADMIN_IDS, HIDDEN_ADMIN_IDS, BROADCAST_BATCH_SIZE, BROADCAST_DELAY, PRIVILEGES, SHOP_ITEMS
from .admin_helpers import (db_session, check_admin_async, get_all_admins_from_db, format_number,
                            get_broadcast_cancel_keyboard, )
from .admin_notifications import send_admin_action_notification
from database.crud import UserRepository, TransactionRepository, ShopRepository, ModerationLogRepository
from handlers.cleanup_scheduler import CleanupScheduler

# ДОБАВЛЯЕМ ИМПОРТЫ ДЛЯ РЕКОРДОВ
from handlers.record.record_core import RecordCore
from handlers.record.services import RecordService

logger = logging.getLogger(__name__)


class AdminHandler:
    """Основной класс для обработки административных команд"""

    def __init__(self):
        self.logger = logger
        self.broadcast_cancelled = False
        self.cleanup_scheduler = None
        self.mute_ban_manager = MuteBanManager()
        # ДОБАВЛЯЕМ ИНИЦИАЛИЗАЦИЮ ДЛЯ РЕКОРДОВ
        self.core = RecordCore()
        self.record_service = RecordService(self.core)

    # ========== КОМАНДА ПОМОЩИ ==========
    async def admin_help(self, message: types.Message):
        """Показывает список админ-команд"""
        if not await check_admin_async(message):
            return

        all_admins = get_all_admins_from_db()
        total_admins = len(all_admins) + len(ADMIN_IDS)

        help_text = (
            "<b>АДМИН-ПАНЕЛЬ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "<b>МОДЕРАЦИЯ</b>\n"
            "├ <code>/mute [время] [причина]</code> - Мут пользователя (ответом)\n"
            "├ <code>/unmute</code> - Снять мут (ответом)\n"
            "├ <code>/ban [время] [причина]</code> - Бан пользователя (ответом)\n"
            "├ <code>/unban [ID]</code> - Разбан пользователя\n"
            "└ <code>/kick [причина]</code> - Кик пользователя (ответом)\n\n"

            "<b>УПРАВЛЕНИЕ СОМАМИ</b>\n"
            "├ <code>/add [ID] [сумма]</code> - Добавить Монеты пользователю\n"
            "├ <code>/remove [ID] [сумма]</code> - Забрать Монеты у пользователя\n"
            "└ <code>/set [ID] [сумма]</code> - Установить точное количество\n\n"

            "<b>УПРАВЛЕНИЕ ПРИВИЛЕГИЯМИ</b>\n"
            "├ <code>/give [ID] [привилегия] [дни]</code> - Выдать привилегию\n"
            "├ <code>/take [ID] [привилегия]</code> - Отобрать привилегию\n"
            "├ <code>/privileges [ID]</code> - Показать привилегии пользователя\n"
            "└ <code>/extend [ID] [привилегия] [дни]</code> - Продлить привилегию\n\n"

            "<b>ЛОГИРОВАНИЕ</b>\n"
            "├ <code>/logs</code> - Просмотр логов модерации\n"
            "├ <code>/logs [ID]</code> - Логи конкретного пользователя\n"
            "└ <code>/modlog</code> - Альтернативная команда\n\n"

            "<b>УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ</b>\n"
            "├ <code>/info [ID]</code> - Информация о пользователе\n"
            "├ <code>/find [username/имя]</code> - Поиск пользователя\n"
            "├ <code>/chats [ID]</code> - Чаты пользователя\n"
            "├ <code>/unlimit [ID]</code> - Снять лимит переводов\n"
            "├ <code>/limit [ID]</code> - Установить лимит переводов\n"
            "├ <code>/radd [ID]</code> - Добавить администратора\n"
            "├ <code>/rremove [ID]</code> - Удалить администратора\n"
            "├ <code>/radminlist</code> - Список администраторов\n"
            "└ <code>/reward [ID] [сумма] [привилегия]</code> - Выдать награду\n\n"

            "<b>СТАТИСТИКА</b>\n"
            "├ <code>/stats</code> - Общая статистика бота\n"
            "├ <code>/chatstats</code> - Статистика по чатам\n"
            "├ <code>/broadcast [текст]</code> - Рассылка пользователям\n"
            "├ <code>/broadcast_chats [текст]</code> - Рассылка в чаты\n"
            "└ <code>/broadcast_all [текст]</code> - Общая рассылка\n\n"

            "<b>ИГРЫ И РЕКОРДЫ</b>\n"
            "├ <code>/сбросить_рекорды</code> - Принудительный сброс рекордов\n"
            "└ <code>/ртоп</code> - Компактный топ пользователей\n\n"

            "<b>ДОСТУПНЫЕ ПРИВИЛЕГИИ</b>\n"
            "├ <code></code> - Вор в законе\n"
            "├ <code></code> - Полицейский\n"
            "└ <code>unlimit</code> - Снятие лимита перевода\n\n"

            "<b>ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ</b>\n"
            "├ <code>/add 123456 5000000</code> - Добавить 5M Монет\n"
            "├ <code>/give 123456  30</code> - Выдать привилегию на 30 дней\n"
            "├ <code>/give 123456 unlimit</code> - Снять лимит переводов\n"
            "├ <code>/mute 30м спам</code> - Мут на 30 минут\n"
            "├ <code>/ban 1d оскорбления</code> - Бан на 1 день\n"
            "├ <code>/kick нарушение правил</code> - Кик пользователя\n"
            "└ <code>/reward 123456 10000000 </code> - Награда 10M + привилегия\n\n"

            "<b>ОЧИСТКА И УПРАВЛЕНИЕ БД</b>\n"
            "├ <code>очистить базу</code> - Меню управления базой данных\n"
            "└ <code>/очистить</code> - Очистка, сброс балансов, статистика\n\n"

            f"<b>ВСЕГО АДМИНОВ:</b> <code>{total_admins}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await message.answer(help_text, parse_mode="HTML")

    # ========== УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ ==========
    async def add_admin(self, message: types.Message):
        """Добавляет нового администратора"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) != 1:
                await message.answer(" Использование: <code>/radd [ID пользователя]</code>", parse_mode="HTML")
                return
            new_admin_id = int(args[0])
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, new_admin_id)
                if not user:
                    await message.answer(" Пользователь не найден в базе данных")
                    return
                if user.is_admin:
                    await message.answer("ℹ️ Этот пользователь уже является администратором")
                    return
                UserRepository.update_admin_status(db, new_admin_id, True)
                db.commit()
                self.logger.info(f"Admin {message.from_user.id} added new admin {new_admin_id}")
                response = (
                    f"<b>Пользователь добавлен в администраторы!</b>\n"
                    f"ID: <code>{new_admin_id}</code>\n"
                    f"Имя: {user.first_name or 'Не указано'}\n"
                    f"Username: @{user.username or 'нет'}\n"
                    f"Теперь у пользователя есть доступ к админ-панели"
                )
                await message.answer(response, parse_mode="HTML")
        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in add_admin: {e}")
            await message.answer(" Произошла ошибка при добавлении администратора")

    async def remove_admin(self, message: types.Message):
        """Удаляет администратора"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) != 1:
                await message.answer(" Использование: <code>/rremove [ID администратора]</code>",
                                     parse_mode="HTML")
                return
            admin_id_to_remove = int(args[0])
            if admin_id_to_remove in ADMIN_IDS:
                await message.answer(" Нельзя удалить администратора из основного списка")
                return
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, admin_id_to_remove)
                if not user:
                    await message.answer(" Пользователь не найден")
                    return
                if not user.is_admin:
                    await message.answer(" Этот пользователь не является администратором")
                    return
                UserRepository.update_admin_status(db, admin_id_to_remove, False)
                db.commit()
                self.logger.info(f"Admin {message.from_user.id} removed admin {admin_id_to_remove}")
                response = (
                    f"<b>Администратор удален!</b>\n"
                    f"ID: <code>{admin_id_to_remove}</code>\n"
                    f"Имя: {user.first_name or 'Не указано'}\n"
                    f"Username: @{user.username or 'нет'}\n"
                    f"Пользователь больше не имеет доступа к админ-панели"
                )
                await message.answer(response, parse_mode="HTML")
        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in remove_admin: {e}")
            await message.answer(" Произошла ошибка при удалении администратора")

    async def list_admins(self, message: types.Message):
        """Показывает список всех администраторов"""
        if not await check_admin_async(message):
            return
        try:
            with db_session() as db:
                admin_users = UserRepository.get_admin_users(db)
                admins_text = "<b>Список администраторов</b>\n"
                # Основные администраторы (без скрытых)
                visible_admin_ids = [aid for aid in ADMIN_IDS if aid not in HIDDEN_ADMIN_IDS]
                admins_text += "<b>Основные администраторы:</b>\n"
                for admin_id in visible_admin_ids:
                    user = UserRepository.get_user_by_telegram_id(db, admin_id)
                    if user:
                        admins_text += f"ID: {admin_id} | {user.first_name or 'Без имени'} | @{user.username or 'нет'}"
                        if admin_id == message.from_user.id:
                            admins_text += " <b>(Вы)</b>"
                        admins_text += "\n"
                admins_text += "\n"
                # Дополнительные администраторы
                other_admins = [user for user in admin_users if user.telegram_id not in ADMIN_IDS and user.telegram_id not in HIDDEN_ADMIN_IDS]
                if other_admins:
                    admins_text += "<b>Дополнительные администраторы:</b>\n"
                    for i, user in enumerate(other_admins, 1):
                        admins_text += f"{i}. ID: {user.telegram_id} | {user.first_name or 'Без имени'} | @{user.username or 'нет'}\n"
                else:
                    admins_text += "<b>Дополнительные администраторы:</b>\nНет дополнительных админов\n"
                total_admins = len(admin_users) + len(visible_admin_ids)
                admins_text += f"\nВсего администраторов: {total_admins}"
                await message.answer(admins_text, parse_mode="HTML")
        except Exception as e:
            self.logger.error(f"Error in list_admins: {e}")
            await message.answer(" Произошла ошибка при получении списка администраторов")

    # ========== УПРАВЛЕНИЕ СомАМИ ==========
    async def _manage_coins(self, message: types.Message, operation: str):
        """Общий метод для управления Сомами"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) != 2:
                commands = {
                    "add": "/add [ID] [amount]",
                    "remove": "/remove [ID] [amount]",
                    "set": "/set [ID] [amount]"
                }
                await message.answer(f" Использование: <code>{commands[operation]}</code>", parse_mode="HTML")
                return
            user_id = int(args[0])
            amount = int(args[1])
            if amount <= 0:
                await message.answer(" Сумма должна быть положительной")
                return
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                # Если пользователя нет - создаем его
                if not user:
                    try:
                        # Пытаемся получить информацию о пользователе через Telegram API
                        chat_member = await message.bot.get_chat(user_id)
                        username = chat_member.username
                        first_name = chat_member.first_name or "Пользователь"
                        user = UserRepository.create_user_safe(
                            db, user_id,
                            first_name=first_name,
                            username=username
                        )
                        self.logger.info(f"✅ Создан новый пользователь {user_id} для операции с Сомами")
                    except Exception as user_info_error:
                        self.logger.warning(
                            f"Не удалось получить информацию о пользователе {user_id}: {user_info_error}")
                        user = UserRepository.create_user_safe(
                            db, user_id,
                            first_name="Пользователь",
                            username=None
                        )
                    # Обновляем текущие Монеты после создания пользователя
                    user = UserRepository.get_user_by_telegram_id(db, user_id)

                current_coins = user.coins
                if operation == "add":
                    new_coins = current_coins + amount
                    transaction_desc = "админ пополнение"
                    from_user, to_user = None, user_id
                elif operation == "remove":
                    if amount > current_coins:
                        await message.answer(f" У пользователя только {format_number(current_coins)} Монет")
                        return
                    new_coins = current_coins - amount
                    transaction_desc = "админ снятие"
                    from_user, to_user = user_id, None
                else:  # set
                    new_coins = amount
                    difference = amount - current_coins
                    if difference == 0:
                        await message.answer("ℹ️ Баланс пользователя уже установлен на эту сумму")
                        return
                    transaction_desc = "админ установка баланса"
                    from_user, to_user = (None, user_id) if difference > 0 else (user_id, None)
                    amount = abs(difference)

                UserRepository.update_user_balance(db, user_id, new_coins)
                if operation != "set" or amount != 0:
                    TransactionRepository.create_transaction(
                        db=db,
                        from_user_id=from_user,
                        to_user_id=to_user,
                        amount=amount,
                        description=transaction_desc
                    )
                db.commit()
                self.logger.info(f"Admin {message.from_user.id} {operation} {amount} coins for user {user_id}")

                # Отправляем уведомление пользователю
                if operation == "add":
                    await send_admin_action_notification(
                        message.bot,
                        user_id,
                        "add_coins",
                        amount=amount,
                        new_balance=new_coins
                    )

                operation_names = {
                    "add": "добавлено",
                    "remove": "забрано",
                    "set": "установлено"
                }
                response = (
                    f"<b>Операция выполнена успешно!</b>\n"
                    f"Пользователь: <code>{user_id}</code>\n"
                    f"Было: {format_number(current_coins)} | Стало: {format_number(new_coins)}\n"
                    f"{operation_names[operation].title()}: {format_number(amount)} Монет"
                )
                await message.answer(response, parse_mode="HTML")
        except ValueError:
            await message.answer(" Неверный формат. ID и сумма должны быть числами")
        except Exception as e:
            self.logger.error(f"Error in {operation}: {e}")
            await message.answer(" Произошла ошибка при выполнении операции")

    async def add_coins(self, message: types.Message):
        """Добавить Монеты пользователю"""
        await self._manage_coins(message, "add")

    async def remove_coins(self, message: types.Message):
        """Забрать Монеты у пользователя"""
        await self._manage_coins(message, "remove")

    async def set_coins(self, message: types.Message):
        """Установить точное количество Монет"""
        await self._manage_coins(message, "set")

    # ========== УПРАВЛЕНИЕ ПРИВИЛЕГИЯМИ ==========
    async def give_privilege(self, message: types.Message):
        """Выдать привилегию пользователю"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) < 2:
                await self._show_privilege_help(message, "give")
                return
            user_id = int(args[0])
            privilege_type = args[1].lower()
            days = int(args[2]) if len(args) > 2 else PRIVILEGES.get(privilege_type, {}).get("default_days", 30)
            if privilege_type not in PRIVILEGES:
                await message.answer(" Неизвестный тип привилегии")
                return
            privilege = PRIVILEGES[privilege_type]
            if days < 0:
                await message.answer(" Количество дней не может быть отрицательным")
                return
            # ИСПРАВЛЕНИЕ: Для unlimit устанавливаем days = 0
            if privilege_type == "unlimit":
                days = 0  # Для снятия лимита всегда навсегда
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                # Если пользователя нет - создаем его
                if not user:
                    try:
                        chat_member = await message.bot.get_chat(user_id)
                        username = chat_member.username
                        first_name = chat_member.first_name or "Пользователь"
                        user = UserRepository.create_user_safe(db, user_id, first_name, username)
                        self.logger.info(f"✅ Создан новый пользователь {user_id} для выдачи привилегии")
                    except Exception as user_info_error:
                        self.logger.warning(
                            f"Не удалось получить информацию о пользователе {user_id}: {user_info_error}")
                        user = UserRepository.create_user_safe(db, user_id, "Пользователь", None)
                    user = UserRepository.get_user_by_telegram_id(db, user_id)

                user_purchases = ShopRepository.get_user_purchases(db, user_id)
                # ИСПРАВЛЕНИЕ: Проверяем по правильному ID привилегии
                if privilege["id"] in user_purchases:
                    await message.answer(f"ℹ️ У пользователя уже есть привилегия '{privilege['name']}'")
                    return

                # ИСПРАВЛЕНИЕ: Сохраняем с правильным ID
                ShopRepository.add_user_purchase(
                    db,
                    user_id,
                    privilege["id"],  # Теперь для unlimit это 3, для  - 1
                    privilege["name"],
                    days if privilege["extendable"] else 0  # Для unlimit сохраняем 0
                )
                db.commit()

                # ИСПРАВЛЕНИЕ: Создаем копию privilege с реальным количеством дней
                privilege_with_days = privilege.copy()
                privilege_with_days['actual_days'] = days

                # Отправляем уведомление пользователю
                await send_admin_action_notification(
                    message.bot,
                    user_id,
                    "privilege",
                    privilege_info=privilege_with_days  # ← ПЕРЕДАЕМ С РЕАЛЬНЫМИ ДНЯМИ
                )

                self.logger.info(f"Admin {message.from_user.id} gave {privilege['name']} to user {user_id}")
                duration_text = f"{days} дней" if days > 0 else "навсегда"
                response = (
                    f"<b>Привилегия успешно выдана!</b>\n"
                    f"Пользователь: {user.first_name or 'Без имени'}\n"
                    f"ID: <code>{user_id}</code>\n"
                    f"Привилегия: {privilege['name']}\n"
                    f"Срок: {duration_text}\n"
                    f"Выдал: {message.from_user.first_name}"
                )
                await message.answer(response, parse_mode="HTML")
        except ValueError:
            await message.answer(" Неверный формат. ID и дни должны быть числами")
        except Exception as e:
            self.logger.error(f"Error in give_privilege: {e}")
            await message.answer(" Произошла ошибка при выдаче привилегии")

    async def remove_privilege(self, message: types.Message):
        """Отобрать привилегию у пользователя"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) != 2:
                await self._show_privilege_help(message, "take")
                return
            user_id = int(args[0])
            privilege_type = args[1].lower()
            if privilege_type not in PRIVILEGES:
                await message.answer(" Неизвестный тип привилегии")
                return
            privilege = PRIVILEGES[privilege_type]
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await message.answer(" Пользователь не найден")
                    return
                user_purchases = ShopRepository.get_user_purchases(db, user_id)
                if privilege["id"] not in user_purchases:
                    await message.answer(f"ℹ️ У пользователя нет привилегии '{privilege['name']}'")
                    return
                ShopRepository.remove_user_purchase(db, user_id, privilege["id"])
                db.commit()
                self.logger.info(f"Admin {message.from_user.id} removed {privilege['name']} from user {user_id}")
                response = (
                    f"<b>Привилегия успешно отобрана!</b>\n"
                    f"Пользователь: {user.first_name or 'Без имени'}\n"
                    f"ID: <code>{user_id}</code>\n"
                    f"Привилегия: {privilege['name']}\n"
                    f"Отобрал: {message.from_user.first_name}"
                )
                await message.answer(response, parse_mode="HTML")
        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in remove_privilege: {e}")
            await message.answer(" Произошла ошибка при отборе привилегии")

    async def list_privileges(self, message: types.Message):
        """Показать привилегии пользователя"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) != 1:
                await message.answer(" Использование: <code>/privileges [ID пользователя]</code>",
                                     parse_mode="HTML")
                return
            user_id = int(args[0])
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await message.answer(" Пользователь не найден")
                    return
                user_purchases_ids = ShopRepository.get_user_purchases(db, user_id)
                if not user_purchases_ids:
                    await message.answer(f"ℹ️ У пользователя {user_id} нет привилегий")
                    return
                privileges_text = f"<b>Привилегии пользователя</b> {user_id}\n"
                privileges_text += f"Имя: {user.first_name or 'Не указано'}\n"
                privileges_text += f"Username: @{user.username or 'нет'}\n"
                # Получаем детали привилегий
                from sqlalchemy import text
                result = db.execute(
                    text("SELECT item_id, item_name FROM user_purchases WHERE user_id = :user_id"),
                    {"user_id": user_id}
                ).fetchall()
                for item_id, item_name in result:
                    privileges_text += f"• {item_name}\n"
                privileges_text += f"\nВсего привилегий: {len(user_purchases_ids)}"
                await message.answer(privileges_text, parse_mode="HTML")
        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in list_privileges: {e}")
            await message.answer(" Произошла ошибка при получении привилегий")

    async def extend_privilege(self, message: types.Message):
        """Продлить привилегию пользователю"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) != 3:
                await self._show_privilege_help(message, "extend")
                return
            user_id = int(args[0])
            privilege_type = args[1].lower()
            days = int(args[2])
            if privilege_type not in PRIVILEGES:
                await message.answer(" Неизвестный тип привилегии")
                return
            privilege = PRIVILEGES[privilege_type]
            if not privilege["extendable"]:
                await message.answer(f" Привилегию '{privilege['name']}' нельзя продлить")
                return
            if days <= 0:
                await message.answer(" Количество дней должно быть положительным")
                return
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await message.answer(" Пользователь не найден")
                    return
                success = ShopRepository.extend_user_purchase(db, user_id, privilege["id"], days)
                if success:
                    db.commit()
                    self.logger.info(
                        f"Admin {message.from_user.id} extended {privilege['name']} for user {user_id} by {days} days")
                    # Отправляем уведомление пользователю
                    # ИСПРАВЛЕНИЕ: Создаем копию privilege с реальным количеством дней
                    privilege_with_days = privilege.copy()
                    privilege_with_days['actual_days'] = days

                    # Отправляем уведомление пользователю
                    await send_admin_action_notification(
                        message.bot,
                        user_id,
                        "privilege",
                        privilege_info=privilege_with_days
                    )
                    response = (
                        f"<b>Привилегия успешно продлена!</b>\n"
                        f"Пользователь: {user.first_name or 'Без имени'}\n"
                        f"ID: <code>{user_id}</code>\n"
                        f"Привилегия: {privilege['name']}\n"
                        f"Продлено на: {days} дней\n"
                        f"Продлил: {message.from_user.first_name}"
                    )
                    await message.answer(response, parse_mode="HTML")
                else:
                    await message.answer(f" У пользователя нет привилегии '{privilege['name']}' или произошла ошибка")
        except ValueError:
            await message.answer(" Неверный формат. ID и дни должны быть числами")
        except Exception as e:
            self.logger.error(f"Error in extend_privilege: {e}")
            await message.answer(" Произошла ошибка при продлении привилегии")

    async def _show_privilege_help(self, message: types.Message, command: str):
        """Показывает справку по командам привилегий"""
        help_texts = {
            "give": " Использование: <code>/give [ID] [привилегия] [дни]</code>\n",
            "take": " Использование: <code>/take [ID] [привилегия]</code>\n",
            "extend": " Использование: <code>/extend [ID] [привилегия] [дни]</code>\n"
        }
        help_text = help_texts[command] + "<b>Доступные привилегии:</b>\n"
        for priv_type, priv_info in PRIVILEGES.items():
            help_text += f"• <code>{priv_type}</code> - {priv_info['name']}"
            if command == "extend" and not priv_info['extendable']:
                help_text += " (не продлевается)"
            help_text += "\n"
        help_text += "\n<b>Примеры:</b>\n"
        if command == "give":
            help_text += (
                "<code>/give 123456 </code>\n"
                "<code>/give 123456  60</code>\n"
                "<code>/give 123456 unlimit</code>"
            )
        elif command == "take":
            help_text += (
                "<code>/take 123456 </code>\n"
                "<code>/take 123456 unlimit</code>"
            )
        else:  # extend
            help_text += (
                "<code>/extend 123456  30</code>\n"
                "<code>/extend 123456  60</code>"
            )
        await message.answer(help_text, parse_mode="HTML")

    # ========== СТАТИСТИКА И ИНФОРМАЦИЯ ==========
    async def user_info(self, message: types.Message):
        """Информация о пользователе"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) != 1:
                await message.answer(" Использование: <code>/info [ID]</code>", parse_mode="HTML")
                return
            user_id = int(args[0])
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await message.answer(" Пользователь не найден")
                    return

                # Получаем дополнительную информацию о чатах
                user_chats = UserRepository.get_user_chats(db, user_id)
                user_purchases = ShopRepository.get_user_purchases(db, user_id)
                has_unlimited = PRIVILEGES["unlimit"]["id"] in user_purchases

                info_text = (
                    f"<b>Информация о пользователе</b> #{user_id}\n"
                    f"Имя: {user.first_name or 'Не указано'}\n"
                    f"Username: @{user.username or 'Не указан'}\n"
                    f"Баланс: {format_number(user.coins)} Монет\n"
                    f"Выиграно: {format_number(user.win_coins or 0)} Монет\n"
                    f"Проиграно: {format_number(user.defeat_coins or 0)} Монет\n"
                    f"Макс. выигрыш: {format_number(user.max_win_coins or 0)} Монет\n"
                    f"Безлимитные переводы: {'Да' if has_unlimited else ' Нет'}\n"
                    f"Найден в чатах: {len(user_chats)}\n"
                    f"Админ: {'Да' if user.is_admin else ' Нет'}\n"
                )
                if hasattr(user, 'created_at') and user.created_at:
                    info_text += f"Зарегистрирован: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"

                # Добавляем кнопку для просмотра чатов
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton(
                    "Показать чаты пользователя",
                    callback_data=f"admin_show_chats_{user_id}"
                ))

                await message.answer(info_text, parse_mode="HTML", reply_markup=keyboard)
        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in user_info: {e}")
            await message.answer(" Произошла ошибка")

    # Добавить обработчик callback для кнопки
    async def handle_show_user_chats(self, callback: types.CallbackQuery):
        """Обработчик кнопки показа чатов пользователя"""
        try:
            user_id = int(callback.data.split('_')[-1])

            with db_session() as db:
                user_chats = UserRepository.get_user_chats(db, user_id)
                user = UserRepository.get_user_by_telegram_id(db, user_id)

                if not user_chats:
                    await callback.message.edit_text(
                        f" Пользователь {user_id} не найден ни в одном чате",
                        parse_mode="HTML"
                    )
                    return

                response = [
                    f"<b>Чаты пользователя</b>",
                    f"{user.first_name or 'Без имени'} (ID: <code>{user_id}</code>)",
                    f"@{user.username or 'нет'}",
                    f"",
                    f"<b>Найден в {len(user_chats)} чатах:</b>"
                ]

                for i, (chat_id, chat_title) in enumerate(user_chats[:10], 1):
                    response.append(f"{i}. {self._escape_html(chat_title)} (ID: <code>{chat_id}</code>)")

                if len(user_chats) > 10:
                    response.append(f"\n<i>... и еще {len(user_chats) - 10} чатов</i>")

                await callback.message.edit_text("\n".join(response), parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error in handle_show_user_chats: {e}")
            await callback.answer(" Ошибка при загрузке чатов")
        finally:
            await callback.answer()

    async def bot_stats(self, message: types.Message):
        """Общая статистика бота"""
        if not await check_admin_async(message):
            return

        try:
            with db_session() as db:
                total_users = UserRepository.get_total_users_count(db)
                total_coins = UserRepository.get_total_coins_sum(db)
                admin_users = UserRepository.get_admin_users(db)
                all_users = UserRepository.get_all_users(db)

                # Получаем топ-5 и топ-100
                rich_users_top5 = sorted(all_users, key=lambda u: u.coins, reverse=True)[:5]
                rich_users_top100 = sorted(all_users, key=lambda u: u.coins, reverse=True)[:100]

                # Формируем основную статистику
                stats_text = "<b>Статистика бота</b>\n"
                stats_text += f"Всего пользователей: {format_number(total_users)}\n"
                stats_text += f"Всего Монет в системе: {format_number(total_coins)}\n"
                stats_text += f"Администраторов: {len(admin_users)}\n"

                if rich_users_top5:
                    stats_text += "\n<b>Топ-5 по балансу:</b>\n"
                    for i, user in enumerate(rich_users_top5, 1):
                        display_name = user.first_name or user.username or f"Пользователь {user.telegram_id}"
                        admin_status = " " if user.is_admin else ""
                        stats_text += f"{i}. {display_name} - {format_number(user.coins)} Монет{admin_status}\n"
                else:
                    stats_text += "\nПока нет данных о пользователях\n"

                # Добавляем кнопку для просмотра топ-100
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton(
                    "Показать топ-100 по балансу",
                    callback_data=f"admin_show_top100_{message.message_id}"
                ))

                await message.answer(stats_text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            self.logger.error(f"Error in bot_stats: {e}")
            await message.answer(" Произошла ошибка при получении статистики")

    async def handle_show_top100(self, callback: types.CallbackQuery):
        """Показывает топ-100 пользователей по балансу"""
        if not await self.check_admin_callback_async(callback):
            await callback.answer(" У вас нет прав администратора", show_alert=True)
            return

        try:
            message_id = int(callback.data.split('_')[-1])

            with db_session() as db:
                all_users = UserRepository.get_all_users(db)
                rich_users_top100 = sorted(all_users, key=lambda u: u.coins, reverse=True)[:100]

                if not rich_users_top100:
                    await callback.message.edit_text(
                        "<b>Топ-100 по балансу</b>\n\n"
                        " Нет данных о пользователях",
                        parse_mode="HTML"
                    )
                    await callback.answer()
                    return

                # Формируем текст
                header = "<b>Топ-100 по балансу</b>\n\n"
                text = header

                for i, user in enumerate(rich_users_top100, 1):
                    # Обрезаем длинные имена
                    display_name = user.first_name or user.username or f"User {user.telegram_id}"
                    if len(display_name) > 20:
                        display_name = display_name[:17] + "..."

                    admin_status = " " if user.is_admin else ""
                    user_text = f"{i}. <code>{user.telegram_id}</code> | {self._escape_html(display_name)}"
                    user_text += f" - {format_number(user.coins)} Монет{admin_status}\n"
                    text += user_text

                    # Разбиваем на несколько сообщений если текст слишком длинный
                    if len(text) > 3800 and i < len(rich_users_top100):
                        # Отправляем первую часть
                        await callback.message.edit_text(
                            text + "\n\n<i>Продолжение в следующем сообщении...</i>",
                            parse_mode="HTML"
                        )

                        # Ждем немного
                        await asyncio.sleep(0.5)

                        # Начинаем второе сообщение
                        text = "🏆 <b>Топ-100 по балансу (продолжение)</b>\n\n"
                        continue

                # Добавляем кнопку возврата
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton(
                    "⬅️ Назад к статистике",
                    callback_data=f"admin_back_to_stats_{message_id}"
                ))

                await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            self.logger.error(f"Error in handle_show_top100: {e}")
            await callback.message.edit_text(" Ошибка при загрузке топ-100")
        finally:
            await callback.answer()

    async def handle_top100_navigation(self, callback: types.CallbackQuery):
        """Навигация по страницам топ-100"""
        if not await check_admin_async(callback.message):
            await callback.answer(" У вас нет прав", show_alert=True)
            return

        try:
            # Пример callback_data: admin_top100_next_2_123456
            parts = callback.data.split('_')
            action = parts[3]  # next
            page_num = int(parts[4])  # номер страницы
            message_id = int(parts[5])  # ID исходного сообщения

            with db_session() as db:
                all_users = UserRepository.get_all_users(db)
                rich_users_top100 = sorted(all_users, key=lambda u: u.coins, reverse=True)[:100]

                if not rich_users_top100:
                    await callback.message.edit_text(" Нет данных о пользователях")
                    return

                # Разбиваем на фрагменты по 20 пользователей на страницу (для удобства навигации)
                users_per_page = 20
                total_pages = (len(rich_users_top100) + users_per_page - 1) // users_per_page

                # Корректируем номер страницы
                if action == "next":
                    page_num += 1
                elif action == "prev":
                    page_num -= 1

                # Проверяем границы
                if page_num < 1:
                    page_num = 1
                elif page_num > total_pages:
                    page_num = total_pages

                # Получаем пользователей для текущей страницы
                start_idx = (page_num - 1) * users_per_page
                end_idx = start_idx + users_per_page
                page_users = rich_users_top100[start_idx:end_idx]

                # Формируем текст страницы
                header = f"🏆 <b>Топ-100 по балансу</b>\n"
                header += f"📄 Страница {page_num}/{total_pages}\n\n"

                page_text = header
                for i, user in enumerate(page_users, start_idx + 1):
                    display_name = user.first_name or user.username or f"Пользователь {user.telegram_id}"
                    admin_status = " 👑" if user.is_admin else ""
                    user_text = f"{i}. <code>{user.telegram_id}</code> | {self._escape_html(display_name)}"
                    user_text += f" - {format_number(user.coins)} Монет{admin_status}\n"
                    page_text += user_text

                # Создаем клавиатуру навигации
                keyboard = types.InlineKeyboardMarkup(row_width=3)

                buttons = []
                if page_num > 1:
                    buttons.append(types.InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data=f"admin_top100_prev_{page_num - 1}_{message_id}"
                    ))

                buttons.append(types.InlineKeyboardButton(
                    "📊 Назад к статистике",
                    callback_data=f"admin_back_to_stats_{message_id}"
                ))

                if page_num < total_pages:
                    buttons.append(types.InlineKeyboardButton(
                        "Далее ➡️",
                        callback_data=f"admin_top100_next_{page_num + 1}_{message_id}"
                    ))

                keyboard.row(*buttons)

                await callback.message.edit_text(page_text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            self.logger.error(f"Error in handle_top100_navigation: {e}")
            await callback.message.edit_text(" Ошибка навигации")
        finally:
            await callback.answer()

    async def handle_back_to_stats(self, callback: types.CallbackQuery):
        """Возврат к основной статистике"""
        if not await self.check_admin_callback_async(callback):
            await callback.answer(" У вас нет прав администратора", show_alert=True)
            return

        try:
            # Показываем загрузку
            await callback.message.edit_text("🔄 Загрузка статистики...")

            with db_session() as db:
                total_users = UserRepository.get_total_users_count(db)
                total_coins = UserRepository.get_total_coins_sum(db)
                admin_users = UserRepository.get_admin_users(db)
                all_users = UserRepository.get_all_users(db)

                # Получаем топ-5 и топ-100
                rich_users_top5 = sorted(all_users, key=lambda u: u.coins, reverse=True)[:5]

                # Формируем основную статистику
                stats_text = "📊 <b>Статистика бота</b>\n"
                stats_text += f"👥 Всего пользователей: {format_number(total_users)}\n"
                stats_text += f"💰 Всего Монет в системе: {format_number(total_coins)}\n"
                stats_text += f"👑 Администраторов: {len(admin_users)}\n"

                if rich_users_top5:
                    stats_text += "\n🏆 <b>Топ-5 по балансу:</b>\n"
                    for i, user in enumerate(rich_users_top5, 1):
                        display_name = user.first_name or user.username or f"Пользователь {user.telegram_id}"
                        admin_status = " 👑" if user.is_admin else ""
                        stats_text += f"{i}. {display_name} - {format_number(user.coins)} Монет{admin_status}\n"
                else:
                    stats_text += "\n🏆 Пока нет данных о пользователях\n"

                # Добавляем кнопку для просмотра топ-100
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton(
                    "📈 Показать топ-100 по балансу",
                    callback_data=f"admin_show_top100_{callback.message.message_id}"
                ))

                await callback.message.edit_text(stats_text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            self.logger.error(f"Error in handle_back_to_stats: {e}")
            await callback.message.edit_text(" Ошибка возврата к статистике")
        finally:
            await callback.answer()

    async def get_chats_stats(self, message: types.Message):
        """Статистика по чатам"""
        if not await check_admin_async(message):
            return
        with db_session() as db:
            all_chats = UserRepository.get_all_chats(db)
            active_chats = UserRepository.get_active_chats(db, days_active=7)
            stats_text = "📊 <b>Статистика чатов</b>\n"
            stats_text += f"👥 Всего чатов в базе: {len(all_chats)}\n"
            stats_text += f"🔔 Активных чатов: {len(active_chats)}\n"
            if all_chats:
                chat_stats = []
                for chat_id in all_chats[:15]:
                    info = UserRepository.get_chat_info(db, chat_id)
                    chat_stats.append((chat_id, info['members_count'], info['is_active'], info['title']))
                chat_stats.sort(key=lambda x: x[1], reverse=True)
                stats_text += "🏆 <b>Топ чатов по участникам:</b>\n"
                for i, (chat_id, members_count, is_active, title) in enumerate(chat_stats[:10], 1):
                    status = "🟢" if is_active else "🔴"
                    chat_title = title if title != 'Неизвестно' else f"Чат {chat_id}"
                    stats_text += f"{i}. {chat_title} | 👥 {members_count} {status}\n"
            await message.answer(stats_text, parse_mode="HTML")

    # ========== РАССЫЛКИ ==========
    async def _broadcast_message(self, message: types.Message, target_type: str):
        """Общий метод для рассылки сообщений"""
        if not await check_admin_async(message):
            return
        text = message.get_args()
        if not text:
            usage_commands = {
                "users": "/broadcast [текст]",
                "chats": "/broadcast_chats [текст]",
                "all": "/broadcast_all [текст]"
            }
            await message.answer(f" Использование: <code>{usage_commands[target_type]}</code>", parse_mode="HTML")
            return
        try:
            with db_session() as db:
                if target_type == "users":
                    recipients = UserRepository.get_all_users(db)
                    recipient_ids = [user.telegram_id for user in recipients]
                    recipient_type = "пользователей"
                    broadcast_type = ""
                elif target_type == "chats":
                    recipient_ids = UserRepository.get_all_chats(db)
                    recipient_type = "чатов"
                    broadcast_type = "_chats"
                else:  # all
                    users = UserRepository.get_all_users(db)
                    chats = UserRepository.get_all_chats(db)
                    recipient_ids = [user.telegram_id for user in users] + chats
                    recipient_type = "получателей"
                    broadcast_type = "_all"
                total = len(recipient_ids)
                if total == 0:
                    await message.answer(f" Нет {recipient_type} для рассылки")
                    return
                status_msg = await message.answer(
                    f"📢 Начинаю рассылку для {format_number(total)} {recipient_type}...\n"
                    f"⏳ Обработано: 0/{format_number(total)}\n"
                    f"✅ Успешно: 0\n"
                    f" Ошибок: 0",
                    reply_markup=get_broadcast_cancel_keyboard(broadcast_type)
                )
                success_count = 0
                failed_count = 0
                self.broadcast_cancelled = False
                for i, recipient_id in enumerate(recipient_ids, 1):
                    if self.broadcast_cancelled:
                        break
                    try:
                        await message.bot.send_message(
                            chat_id=recipient_id,
                            text=f"\n{text}"
                        )
                        success_count += 1
                        await asyncio.sleep(BROADCAST_DELAY)
                    except Exception as e:
                        self.logger.warning(f"Не удалось отправить сообщение {recipient_id}: {e}")
                        failed_count += 1
                    # Обновляем статус каждые N получателей
                    if i % BROADCAST_BATCH_SIZE == 0 or i == total:
                        try:
                            await status_msg.edit_text(
                                f"📢 Рассылка для {format_number(total)} {recipient_type}...\n"
                                f"⏳ Обработано: {format_number(i)}/{format_number(total)}\n"
                                f"✅ Успешно: {format_number(success_count)}\n"
                                f" Ошибок: {format_number(failed_count)}",
                                reply_markup=get_broadcast_cancel_keyboard(broadcast_type)
                            )
                        except Exception as e:
                            self.logger.error(f"Ошибка при обновлении статуса: {e}")
                if self.broadcast_cancelled:
                    result_text = (
                        f" Рассылка отменена!\n"
                        f"📊 Итоги:\n"
                        f"👥 Всего {recipient_type}: {format_number(total)}\n"
                        f"⏳ Обработано: {format_number(i)}\n"
                        f"✅ Успешно: {format_number(success_count)}\n"
                        f" Ошибок: {format_number(failed_count)}"
                    )
                else:
                    delivery_rate = (success_count / total) * 100 if total > 0 else 0
                    result_text = (
                        f"✅ Рассылка завершена!\n"
                        f"📊 Итоги:\n"
                        f"👥 Всего {recipient_type}: {format_number(total)}\n"
                        f"✅ Успешно: {format_number(success_count)}\n"
                        f" Не удалось: {format_number(failed_count)}\n"
                        f"📈 Процент доставки: {delivery_rate:.1f}%"
                    )
                await status_msg.edit_text(result_text)
        except Exception as e:
            self.logger.error(f"Error in broadcast {target_type}: {e}")
            await message.answer(f" Произошла ошибка при рассылке: {e}")

    async def broadcast_message(self, message: types.Message):
        """Рассылка пользователям"""
        await self._broadcast_message(message, "users")

    async def broadcast_to_chats(self, message: types.Message):
        """Рассылка в чаты"""
        await self._broadcast_message(message, "chats")

    async def broadcast_to_all(self, message: types.Message):
        """Общая рассылка"""
        await self._broadcast_message(message, "all")

    # ========== ПОИСК И ОЧИСТКА ==========
    async def find_user(self, message: types.Message):
        """Поиск пользователя по имени или username"""
        if not await check_admin_async(message):
            return
        search_term = message.get_args()
        if not search_term:
            await message.answer(" Использование: <code>/find [имя/username]</code>", parse_mode="HTML")
            return
        with db_session() as db:
            found_users = UserRepository.search_users(db, search_term)
            if not found_users:
                await message.answer(" Пользователи не найдены")
                return
            result_text = f"🔍 <b>Результаты поиска по '{search_term}':</b>\n"
            for user in found_users[:10]:
                user_id = user.telegram_id
                name = user.first_name or 'Не указано'
                username = f"@{user.username}" if user.username else "Нет username"
                coins = format_number(user.coins)
                admin_status = " 👑" if user.is_admin else ""
                result_text += f"🆔 {user_id} | {name} | {username} | {coins} Монет{admin_status}\n"
            if len(found_users) > 10:
                result_text += f"\n... и еще {len(found_users) - 10} пользователей"
            await message.answer(result_text, parse_mode="HTML")

    async def remove_transfer_limit(self, message: types.Message):
        """Снимает лимит переводов для пользователя"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) != 1:
                await message.answer(" Использование: <code>/unlimit [ID пользователя]</code>",
                                     parse_mode="HTML")
                return
            user_id = int(args[0])
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await message.answer(" Пользователь не найден")
                    return
                user_purchases = ShopRepository.get_user_purchases(db, user_id)
                if SHOP_ITEMS["unlimited_transfers"] in user_purchases:
                    await message.answer("ℹ️ У пользователя уже снят лимит переводов")
                    return
                # ИСПРАВЛЕНИЕ: Используем правильный ID и название
                ShopRepository.add_user_purchase(
                    db,
                    user_id,
                    SHOP_ITEMS["unlimited_transfers"],  # Теперь это 3
                    PRIVILEGES["unlimit"]["name"],  # "🔐 Снятие лимита перевода"
                    0
                )
                db.commit()
                self.logger.info(f"Admin {message.from_user.id} removed transfer limit for user {user_id}")
                # Отправляем уведомление пользователю ТОЛЬКО о снятии лимита
                await send_admin_action_notification(
                    message.bot,
                    user_id,
                    "unlimit",
                    privilege_info=PRIVILEGES["unlimit"]
                )
                response = (
                    f"✅ <b>Лимит переводов успешно снят!</b>\n"
                    f"👤 Пользователь: {user.first_name or 'Без имени'}\n"
                    f"📱 Username: @{user.username or 'нет'}\n"
                    f"💰 Текущий баланс: {format_number(user.coins)} Монет\n"
                    f"♾️ Теперь пользователь может переводить неограниченные суммы"
                )
                await message.answer(response, parse_mode="HTML")
        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in remove_transfer_limit: {e}")
            await message.answer(" Произошла ошибка при снятии лимита")

    async def manual_cleanup(self, message: types.Message):
        """Ручная очистка данных"""
        if not await check_admin_async(message):
            return
        if self.cleanup_scheduler is None:
            self.cleanup_scheduler = CleanupScheduler()
        try:
            result = await self.cleanup_scheduler.run_manual_cleanup()
            await message.answer(result)
        except Exception as e:
            self.logger.error(f"Error in manual_cleanup: {e}")
            await message.answer(f" Ошибка при очистке: {e}")

    # ========== CALLBACK ОБРАБОТЧИКИ ==========

    async def handle_broadcast_cancel(self, callback: types.CallbackQuery):
        """Обработчик отмены рассылки"""
        if not await check_admin_async(callback.message):
            await callback.answer(" У вас нет прав для отмены рассылки", show_alert=True)
            return
        self.broadcast_cancelled = True
        await callback.answer(" Рассылка будет отменена", show_alert=True)

    async def add_transfer_limit(self, message: types.Message):
        """Устанавливает лимит переводов для пользователя"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) != 1:
                await message.answer(" Использование: <code>/limit [ID пользователя]</code>",
                                     parse_mode="HTML")
                return
            user_id = int(args[0])
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await message.answer(" Пользователь не найден")
                    return
                user_purchases = ShopRepository.get_user_purchases(db, user_id)
                # ИСПРАВЛЕНИЕ: Проверяем по правильному ID
                if SHOP_ITEMS["unlimited_transfers"] not in user_purchases:
                    await message.answer("ℹ️ У пользователя уже установлен лимит переводов")
                    return
                # ИСПРАВЛЕНИЕ: Удаляем по правильному ID
                ShopRepository.remove_user_purchase(db, user_id, SHOP_ITEMS["unlimited_transfers"])
                db.commit()
                self.logger.info(f"Admin {message.from_user.id} added transfer limit for user {user_id}")
                response = (
                    f"✅ <b>Лимит переводов успешно установлен!</b>\n"
                    f"👤 Пользователь: {user.first_name or 'Без имени'}\n"
                    f"📱 Username: @{user.username or 'нет'}\n"
                    f"💰 Текущий баланс: {format_number(user.coins)} Монет\n"
                    f"📏 Теперь пользователь ограничен в переводах стандартными лимитами"
                )
                await message.answer(response, parse_mode="HTML")
        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in add_transfer_limit: {e}")
            await message.answer(" Произошла ошибка при установке лимита")

    async def admin_give_reward(self, message: types.Message):
        """Выдать Монеты и привилегию одновременно"""
        if not await check_admin_async(message):
            return
        try:
            args = message.get_args().split()
            if len(args) < 3:
                await message.answer(
                    " Использование: <code>/reward [ID] [сумма] [привилегия]</code>\n"
                    "📋 Доступные привилегии:\n"
                    "• <code></code> - 👑 Вор в законе\n"
                    "• <code></code> - 👮‍♂️ Полицейский\n"
                    "• <code>unlimit</code> - 🔐 Снятие лимита\n"
                    "📝 Примеры:\n"
                    "<code>/reward 123456 5000000 </code>\n"
                    "<code>/reward 123456 10000000 unlimit</code>",
                    parse_mode="HTML"
                )
                return
            user_id = int(args[0])
            amount = int(args[1])
            privilege_type = args[2].lower()
            if amount <= 0:
                await message.answer(" Сумма должна быть положительной")
                return
            if privilege_type not in PRIVILEGES:
                await message.answer(" Неизвестный тип привилегии")
                return
            privilege = PRIVILEGES[privilege_type]
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await message.answer(" Пользователь не найден")
                    return
                # Добавляем Монеты
                current_coins = user.coins
                new_coins = current_coins + amount
                UserRepository.update_user_balance(db, user_id, new_coins)
                # Создаем транзакцию
                TransactionRepository.create_transaction(
                    db=db,
                    from_user_id=None,
                    to_user_id=user_id,
                    amount=amount,
                    description="админ награда"
                )
                # Выдаем привилегию
                user_purchases = ShopRepository.get_user_purchases(db, user_id)
                privilege_given = False
                if privilege["id"] not in user_purchases:
                    ShopRepository.add_user_purchase(
                        db,
                        user_id,
                        privilege["id"],
                        privilege["name"],
                        privilege["default_days"] if privilege["extendable"] else 0
                    )
                    privilege_given = True
                else:
                    # Если привилегия уже есть - продлеваем если можно
                    if privilege["extendable"]:
                        ShopRepository.extend_user_purchase(
                            db,
                            user_id,
                            privilege["id"],
                            privilege["default_days"]
                        )
                        privilege_given = True

                db.commit()
                # Отправляем уведомление админу
                admin_response = (
                    f"✅ <b>Награда успешно выдана!</b>\n"
                    f"👤 Пользователь: {user.first_name or 'Без имени'}\n"
                    f"🆔 ID: <code>{user_id}</code>\n"
                    f"💰 Сумма: {format_number(amount)} Монет\n"
                    f"🎁 Привилегия: {privilege['name']}"
                )
                await message.answer(admin_response, parse_mode="HTML")
                # Отправляем красивое уведомление в ЛС пользователю
                await send_admin_action_notification(
                    message.bot,
                    user_id,
                    "coins_and_privilege",
                    amount=amount,
                    new_balance=new_coins,
                    privilege_info=privilege
                )
                self.logger.info(f"Admin {message.from_user.id} gave reward to user {user_id}")
        except ValueError:
            await message.answer(" Неверный формат. ID и сумма должны быть числами")
        except Exception as e:
            self.logger.error(f"Error in admin_give_reward: {e}")
            await message.answer(" Произошла ошибка при выдаче награды")

    async def _ensure_user_exists(self, db, user_id: int, bot=None) -> bool:
        """Гарантирует что пользователь существует в базе"""
        user = UserRepository.get_user_by_telegram_id(db, user_id)
        if user:
            return True
        try:
            # Пытаемся получить информацию о пользователе
            first_name = "Пользователь"
            username = None
            if bot:
                try:
                    chat_member = await bot.get_chat(user_id)
                    first_name = chat_member.first_name or "Пользователь"
                    username = chat_member.username
                except Exception as chat_error:
                    self.logger.warning(f"Could not get chat info for {user_id}: {chat_error}")
            UserRepository.create_user_safe(db, user_id, first_name, username)
            self.logger.info(f"✅ Создан новый пользователь {user_id}")
            return True
        except Exception as e:
            self.logger.error(f" Ошибка создания пользователя {user_id}: {e}")
            return False

    async def admin_user_chats(self, message: types.Message):
        """Показывает в каких чатах находится пользователь"""
        if not await check_admin_async(message):
            return

        try:
            args = message.get_args().split()
            if len(args) != 1:
                await message.answer(
                    " Использование: <code>/chats [ID пользователя]</code>\n\n"
                    "📝 <b>Пример:</b>\n"
                    "<code>/chats 123456789</code>",
                    parse_mode="HTML"
                )
                return

            user_id = int(args[0])

            with db_session() as db:
                # Получаем основную информацию о пользователе
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    await message.answer(" Пользователь не найден в базе данных")
                    return

                # Получаем чаты пользователя
                user_chats = UserRepository.get_user_chats(db, user_id)

                # Формируем ответ
                response = [
                    f"🔍 <b>Чаты пользователя</b>",
                    f"👤 <b>{user.first_name or 'Без имени'}</b> (ID: <code>{user_id}</code>)",
                    f"📱 Username: @{user.username or 'нет'}",
                    ""
                ]

                if user_chats:
                    response.append(f"💬 <b>Найден в {len(user_chats)} чатах:</b>")

                    for i, (chat_id, chat_title) in enumerate(user_chats[:15], 1):
                        # Пытаемся получить актуальную информацию о чате
                        try:
                            chat_info = await message.bot.get_chat(chat_id)
                            members_count = await message.bot.get_chat_members_count(chat_id)

                            chat_type = "👥 Группа"
                            if chat_info.type == "supergroup":
                                chat_type = "👑 Супергруппа"
                            elif chat_info.type == "channel":
                                chat_type = "📢 Канал"
                            elif chat_info.type == "private":
                                chat_type = "💬 ЛС"

                            response.append(
                                f"{i}. <b>{self._escape_html(chat_info.title)}</b>\n"
                                f"   🆔 <code>{chat_id}</code> | {chat_type}\n"
                                f"   👥 Участников: {members_count}"
                            )
                        except Exception as e:
                            # Если не удалось получить актуальную информацию, используем сохраненную
                            response.append(
                                f"{i}. <b>{self._escape_html(chat_title)}</b>\n"
                                f"   🆔 <code>{chat_id}</code>\n"
                                f"   ℹ️ <i>Информация устарела</i>"
                            )

                    if len(user_chats) > 15:
                        response.append(f"\n📋 <i>... и еще {len(user_chats) - 15} чатов</i>")

                    # Добавляем статистику
                    response.extend([
                        "",
                        "📊 <b>Статистика:</b>",
                        f"• Всего чатов в базе: {len(user_chats)}",
                        f"• Первый сбор данных: {user_chats[-1][1] if user_chats else 'неизвестно'}",
                        f"• Последнее обновление: {user_chats[0][1] if user_chats else 'неизвестно'}"
                    ])

                else:
                    response.extend([
                        "💬 <b>Чаты пользователя:</b>",
                        " Пользователь не найден ни в одном чате",
                        "",
                        "💡 <i>Данные собираются когда пользователь использует команды бота в чатах</i>"
                    ])

                await message.answer("\n".join(response), parse_mode="HTML")

        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in admin_user_chats: {e}")
            await message.answer(" Произошла ошибка при поиске чатов пользователя")

    async def check_admin_callback_async(self, callback: types.CallbackQuery) -> bool:
        """Проверяет права администратора для callback"""
        try:
            user_id = callback.from_user.id

            # Проверяем встроенных админов
            if user_id in ADMIN_IDS:
                return True

            # Проверяем в базе данных
            with db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if user and user.is_admin:
                    return True

            return False
        except Exception as e:
            self.logger.error(f"Error in check_admin_callback_async: {e}")
            return False

    def _escape_html(self, text: str) -> str:
        """Экранирование HTML-символов"""
        if not text:
            return ""
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    async def force_reset_records(self, message: types.Message):
        """Принудительный сброс рекордов дня (только для админов)"""
        try:
            # Проверяем права администратора
            if not await self.core._check_admin_rights(message):
                await message.reply(" Эта команда доступна только администраторам!")
                return

            self.logger.info(f"🔄 Принудительный сброс рекордов инициирован пользователем {message.from_user.id}")

            # Выполняем сброс
            success = await self.record_service.reset_daily_records()

            if success:
                await message.reply(
                    "✅ <b>Рекорды дня принудительно сброшены!</b>\n\n"
                    "📊 Все ежедневные рекорды обнулены\n"
                    "🕐 Следующий автоматический сброс в 00:00 МСК",
                    parse_mode=types.ParseMode.HTML
                )
                self.logger.info("✅ Принудительный сброс рекордов выполнен успешно")
            else:
                await message.reply(" Ошибка при сбросе рекордов")

        except Exception as e:
            self.logger.error(f" Ошибка в force_reset_records: {e}")
            await message.reply(" Ошибка при принудительном сбросе рекордов")

    async def bot_stats_command(self, message: types.Message):
        """Команда /stats - показывает статистику бота"""
        if not await check_admin_async(message):
            return

        try:
            with db_session() as db:
                total_users = UserRepository.get_total_users_count(db)
                total_coins = UserRepository.get_total_coins_sum(db)
                admin_users = UserRepository.get_admin_users(db)
                all_users = UserRepository.get_all_users(db)

                # Получаем топ-5 пользователей
                rich_users_top5 = sorted(all_users, key=lambda u: u.coins, reverse=True)[:5]

                # Формируем статистику
                stats_text = "📊 <b>СТАТИСТИКА БОТА</b>\n\n"
                stats_text += f"👥 <b>Всего пользователей:</b> {format_number(total_users)}\n"
                stats_text += f"💰 <b>Всего Монет в системе:</b> {format_number(total_coins)}\n"
                stats_text += f"👑 <b>Администраторов:</b> {len(admin_users)}\n"

                if rich_users_top5:
                    stats_text += "\n🏆 <b>ТОП-5 по балансу (всего в системе):</b>\n"
                    for i, user in enumerate(rich_users_top5, 1):
                        display_name = user.first_name or user.username or f"User {user.telegram_id}"
                        if len(display_name) > 20:
                            display_name = display_name[:17] + "..."

                        admin_status = " 👑" if user.is_admin else ""
                        stats_text += f"{i}. <code>{user.telegram_id}</code> | {display_name} - {format_number(user.coins)} Монет{admin_status}\n"

                # Добавляем кнопку для просмотра топ-100
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton(
                        "📈 Показать топ-100 по балансу",
                        callback_data=f"admin_show_top100_{message.message_id}"
                    )
                )

                await message.answer(stats_text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            self.logger.error(f"Error in bot_stats_command: {e}")
            await message.answer(" Произошла ошибка при получении статистики")

    async def show_compact_top(self, message: types.Message):
        """Компактный топ с полными никами (только для админов)"""
        # Проверяем права администратора
        if not await check_admin_async(message):
            return

        try:
            with db_session() as db:
                all_users = UserRepository.get_all_users(db)
                top_users = sorted(all_users, key=lambda u: u.coins, reverse=True)[:10]  # 10 пользователей

                if not top_users:
                    await message.reply("🏆 Топ пользователей\n\n📭 Пока нет данных")
                    return

                # Форматируем как на скриншоте
                top_text = "🏆 <b>Топ богатеев в боте</b>\n\n"

                for i, user in enumerate(top_users, 1):
                    # Полное имя пользователя (без обрезки)
                    name = user.first_name or user.username or "Аноним"

                    # Форматируем баланс
                    coins = user.coins
                    if coins >= 1000000:
                        coins_str = f"{coins:,}".replace(",", " ")
                    else:
                        coins_str = str(coins)

                    # ID пользователя
                    user_id = str(user.telegram_id)

                    # Формируем строку
                    line = f"{i}. <b>{name}</b> - {coins_str} ({user_id})\n"
                    top_text += line

                # Создаем клавиатуру с кнопкой
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton(
                        "📈 Показать топ-100",
                        callback_data=f"show_more_top_{message.from_user.id}"
                    )
                )

                await message.reply(top_text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            self.logger.error(f"Error in show_compact_top: {e}")
            await message.reply(" Ошибка при получении топа")

    async def handle_show_more_top(self, callback: types.CallbackQuery):
        """Показывает топ-100 пользователей (только для админов)"""
        # Проверяем права администратора
        if not await self.check_admin_callback_async(callback):
            await callback.answer(" У вас нет прав администратора", show_alert=True)
            return

        try:
            with db_session() as db:
                all_users = UserRepository.get_all_users(db)
                top_users = sorted(all_users, key=lambda u: u.coins, reverse=True)[:100]

                if not top_users:
                    await callback.message.edit_text(" Нет данных о пользователях")
                    await callback.answer()
                    return

                # Формируем текст
                top_text = "🏆 <b>Топ богатеев в боте</b>\n\n"

                for i, user in enumerate(top_users, 1):
                    # Полное имя
                    name = user.first_name or user.username or "Аноним"

                    # Форматируем баланс
                    coins = user.coins
                    if coins >= 1000000:
                        coins_str = f"{coins:,}".replace(",", " ")
                    else:
                        coins_str = str(coins)

                    # ID пользователя
                    user_id = str(user.telegram_id)

                    # Формируем строку
                    line = f"{i}. <b>{name}</b> - {coins_str} ({user_id})\n"
                    top_text += line

                # Добавляем кнопку возврата к топ-10
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton(
                        "⬅️ Назад к топ-10",
                        callback_data=f"back_to_top10_{callback.message.message_id}"
                    )
                )

                await callback.message.edit_text(top_text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            self.logger.error(f"Error in handle_show_more_top: {e}")
            await callback.message.edit_text(" Ошибка при загрузке топ-100")
        finally:
            await callback.answer()

    async def handle_back_to_top10(self, callback: types.CallbackQuery):
        """Возврат к топ-10"""
        # Проверяем права администратора
        if not await self.check_admin_callback_async(callback):
            await callback.answer(" У вас нет прав администратора", show_alert=True)
            return

        try:
            message_id = int(callback.data.split('_')[-1])

            # Просто вызываем show_compact_top для текущего сообщения
            # Создаем фиктивное сообщение для вызова метода
            fake_message = types.Message(
                message_id=message_id,
                chat=callback.message.chat,
                from_user=callback.from_user,
                text="!ртоп",
                date=callback.message.date,
                bot=callback.bot
            )

            await self.show_compact_top(fake_message)

        except Exception as e:
            self.logger.error(f"Error in handle_back_to_top10: {e}")
            await callback.message.edit_text(" Ошибка возврата к топ-10")
        finally:
            await callback.answer()

    async def show_moderation_logs(self, message: types.Message):
        """Показывает логи модерации"""
        if not await check_admin_async(message):
            return

        try:
            args = message.get_args().split()

            if args:
                # Если указан ID пользователя
                try:
                    user_id = int(args[0])
                    await self._show_user_moderation_logs(message, user_id)
                    return
                except ValueError:
                    # Если не число, показываем обычные логи
                    pass

            # Показываем первую страницу
            await self._show_moderation_logs_page(message, 0)

        except Exception as e:
            self.logger.error(f"Error in show_moderation_logs: {e}")
            await message.answer(" Произошла ошибка при получении логов")

    async def _show_moderation_logs_page(self, message: types.Message, page: int = 0):
        """Показывает страницу логов модерации"""
        try:
            with db_session() as db:
                from database.models import ModerationLog

                logs_per_page = 10
                offset = page * logs_per_page

                # Используем created_at для сортировки (так как timestamp может быть NULL)
                logs = db.query(ModerationLog).order_by(
                    ModerationLog.created_at.desc()
                ).offset(offset).limit(logs_per_page + 1).all()

                if not logs:
                    await message.answer("📭 Логов модерации не найдено")
                    return

                has_next = len(logs) > logs_per_page
                if has_next:
                    logs = logs[:logs_per_page]

                logs_text = f"📋 <b>Логи модерации (страница {page + 1})</b>\n\n"

                action_icons = {
                    'mute': '🔇',
                    'unmute': '🔊',
                    'ban': '🚫',
                    'unban': '✅',
                    'kick': '👢',
                    'botban': '🤖🚫',
                    'botunban': '🤖✅'
                }

                for i, log in enumerate(logs, 1):
                    # Используем свойства для совместимости
                    action = log.effective_action
                    icon = action_icons.get(action, '📝')

                    # Форматируем длительность
                    duration_text = ""
                    if log.duration_minutes:
                        duration_text = f"{log.duration_minutes}м"
                    elif log.duration:
                        minutes = log.duration // 60
                        duration_text = f"{minutes}м"

                    # Форматируем причину
                    reason = log.reason or "не указана"
                    if len(reason) > 30:
                        reason = reason[:27] + "..."

                    # Форматируем время
                    time_str = log.effective_timestamp.strftime('%d.%m.%Y %H:%M')

                    logs_text += (
                        f"{i}. {icon} <b>{action.upper()}</b>\n"
                        f"   👤 Цель: <code>{log.user_id}</code>\n"
                        f"   👮‍♂️ Админ: <code>{log.admin_id}</code>\n"
                    )

                    if duration_text:
                        logs_text += f"   ⏰ Длит: {duration_text}\n"

                    logs_text += (
                        f"   📝 Причина: {reason}\n"
                    )

                    if log.chat_id:
                        logs_text += f"   💬 Чат: <code>{log.chat_id}</code>\n"

                    logs_text += f"   📅 Время: {time_str}\n"
                    logs_text += "   ─────────────────────\n"

                # Создаем клавиатуру пагинации
                keyboard = types.InlineKeyboardMarkup(row_width=3)
                buttons = []

                if page > 0:
                    buttons.append(
                        types.InlineKeyboardButton(
                            "◀️ Назад",
                            callback_data=f"modlogs_page_{page - 1}"
                        )
                    )

                buttons.append(
                    types.InlineKeyboardButton(
                        f"📄 {page + 1}",
                        callback_data="modlogs_current"
                    )
                )

                if has_next:
                    buttons.append(
                        types.InlineKeyboardButton(
                            "Вперёд ▶️",
                            callback_data=f"modlogs_page_{page + 1}"
                        )
                    )

                if buttons:
                    keyboard.row(*buttons)

                # Кнопки фильтров
                keyboard.row(
                    types.InlineKeyboardButton("🔍 Поиск по ID", callback_data="modlogs_search_user"),
                    types.InlineKeyboardButton("📊 Статистика", callback_data="modlogs_stats")
                )

                await message.answer(logs_text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            self.logger.error(f"Error in _show_moderation_logs_page: {e}")
            await message.answer(" Ошибка при формировании логов")

    async def _show_user_moderation_logs(self, message: types.Message, user_id: int):
        """Показывает логи модерации для конкретного пользователя"""
        try:
            with db_session() as db:
                logs = ModerationLogRepository.get_user_logs(db, user_id, limit=20)

                if not logs:
                    await message.answer(f"📭 Логов модерации для пользователя <code>{user_id}</code> не найдено")
                    return

                logs_text = f"📋 <b>Логи модерации пользователя</b> <code>{user_id}</code>\n\n"

                for i, log in enumerate(logs, 1):
                    time_str = log.timestamp.strftime('%d.%m.%Y %H:%M')

                    logs_text += (
                        f"{i}. <b>{log.action_type.upper()}</b>\n"
                        f"   👮‍♂️ Админ: <code>{log.admin_id}</code>\n"
                        f"   📝 Причина: {log.reason or 'не указана'}\n"
                        f"   📅 Время: {time_str}\n"
                        f"   ─────────────────────\n"
                    )

                # Добавляем статистику
                total = len(logs)
                actions = {}
                for log in logs:
                    actions[log.action_type] = actions.get(log.action_type, 0) + 1

                stats_text = "\n📊 <b>Статистика:</b>\n"
                stats_text += f"• Всего действий: {total}\n"
                for action_type, count in actions.items():
                    stats_text += f"• {action_type}: {count}\n"

                logs_text += stats_text

                await message.answer(logs_text, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error in _show_user_moderation_logs: {e}")
            await message.answer(" Ошибка при получении логов пользователя")

    async def handle_modlogs_page(self, callback: types.CallbackQuery):
        """Обработчик пагинации логов"""
        if not await self.check_admin_callback_async(callback):
            await callback.answer(" У вас нет прав администратора", show_alert=True)
            return

        try:
            page = int(callback.data.split('_')[-1])
            await self._show_moderation_logs_page(callback.message, page)
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_modlogs_page: {e}")
            await callback.answer(" Ошибка пагинации")

    async def handle_modlogs_stats(self, callback: types.CallbackQuery):
        """Показывает статистику модерации"""
        if not await self.check_admin_callback_async(callback):
            await callback.answer(" У вас нет прав администратора", show_alert=True)
            return

        try:
            with db_session() as db:
                stats = ModerationLogRepository.get_stats(db, days=30)

                if not stats:
                    await callback.message.answer("📭 Статистика недоступна")
                    await callback.answer()
                    return

                stats_text = "📊 <b>Статистика модерации (30 дней)</b>\n\n"
                stats_text += f"📈 Всего действий: <b>{stats['total']}</b>\n\n"

                if stats['by_type']:
                    stats_text += "📋 <b>По типам действий:</b>\n"
                    for action_type, data in stats['by_type'].items():
                        stats_text += (
                            f"• <b>{action_type}</b>: {data['count']}\n"
                            f"  └ с причиной: {data['with_reason']}\n"
                        )

                if stats['top_admins']:
                    stats_text += "\n👑 <b>Топ администраторов:</b>\n"
                    for admin_id, admin_data in list(stats['top_admins'].items())[:5]:
                        stats_text += f"• <code>{admin_id}</code>: {admin_data['total']} действий\n"

                await callback.message.answer(stats_text, parse_mode="HTML")
                await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_modlogs_stats: {e}")
            await callback.answer(" Ошибка получения статистики")

    async def handle_modlogs_search(self, callback: types.CallbackQuery):
        """Запрос ID пользователя для поиска логов"""
        if not await self.check_admin_callback_async(callback):
            await callback.answer(" У вас нет прав администратора", show_alert=True)
            return

        try:
            await callback.message.answer(
                "🔍 <b>Поиск логов по ID пользователя</b>\n\n"
                "Введите ID пользователя:\n"
                "<code>/logs 123456789</code>\n\n"
                "Или используйте команду:\n"
                "<code>/modlog 123456789</code>",
                parse_mode="HTML"
            )
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Error in handle_modlogs_search: {e}")
            await callback.answer(" Ошибка")

    async def handle_modlogs_current(self, callback: types.CallbackQuery):
        """Обработчик текущей страницы"""
        await callback.answer("📋 Текущая страница")


def register_admin_handlers(dp: Dispatcher):
    """Регистрирует все админ-обработчики"""
    handler = AdminHandler()

    # Команды сброса рекордов
    dp.register_message_handler(
        handler.force_reset_records,
        commands=['сбросить_рекорды', 'reset_records', 'обнулить_рекорды']
    )
    dp.register_message_handler(
        handler.force_reset_records,
        lambda m: m.text and m.text.lower().strip() in ['сбросить рекорды', 'обнулить рекорды', 'reset records']
    )
    dp.register_message_handler(handler.bot_stats_command, commands=['stats', 'статс', 'статистика'])

    # Основные команды
    dp.register_message_handler(handler.admin_help, commands=['admin_help', 'admin', 'help_admin'])

    # Управление Сомами - ОБНОВЛЕННЫЕ КОМАНДЫ
    dp.register_message_handler(handler.add_coins, commands=['add'])
    dp.register_message_handler(handler.remove_coins, commands=['remove'])
    dp.register_message_handler(handler.set_coins, commands=['set'])

    # Управление пользователями - ОБНОВЛЕННЫЕ КОМАНДЫ
    dp.register_message_handler(handler.user_info, commands=['info'])
    dp.register_message_handler(handler.find_user, commands=['find'])
    dp.register_message_handler(handler.remove_transfer_limit, commands=['unlimit'])
    dp.register_message_handler(handler.add_transfer_limit, commands=['limit'])
    dp.register_message_handler(handler.add_admin, commands=['radd'])
    dp.register_message_handler(handler.remove_admin, commands=['rremove'])
    dp.register_message_handler(handler.list_admins, commands=['radminlist'])
    dp.register_message_handler(handler.admin_user_chats, commands=['chats'])

    # Статистика - ОБНОВЛЕННЫЕ КОМАНДЫ
    dp.register_message_handler(handler.bot_stats, commands=['stats', 'статистика'])
    dp.register_message_handler(handler.get_chats_stats, commands=['chatstats'])

    # Рассылки - ОБНОВЛЕННЫЕ КОМАНДЫ
    dp.register_message_handler(handler.broadcast_message, commands=['broadcast'])
    dp.register_message_handler(handler.broadcast_to_chats, commands=['broadcast_chats'])
    dp.register_message_handler(handler.broadcast_to_all, commands=['broadcast_all'])

    # Управление привилегиями - ОБНОВЛЕННЫЕ КОМАНДЫ
    dp.register_message_handler(handler.give_privilege, commands=['give'])
    dp.register_message_handler(handler.remove_privilege, commands=['take'])
    dp.register_message_handler(handler.list_privileges, commands=['privileges'])
    dp.register_message_handler(handler.extend_privilege, commands=['extend'])

    # Комбинированные действия
    dp.register_message_handler(handler.admin_give_reward, commands=['reward'])

    # Очистка
    dp.register_message_handler(
        handler.manual_cleanup,
        lambda m: m.text and m.text.lower().strip() in ["очистить базу", "cleanup", "очистка"]
    )

    # Callback обработчики
    dp.register_callback_query_handler(
        handler.handle_show_user_chats,
        lambda c: c.data.startswith("admin_show_chats_")
    )
    dp.register_callback_query_handler(
        handler.handle_broadcast_cancel,
        lambda c: c.data in ["cancel_broadcast", "cancel_broadcast_chats", "cancel_broadcast_all"]
    )
    dp.register_callback_query_handler(
        handler.handle_show_top100,
        lambda c: c.data.startswith("admin_show_top100_")
    )
    dp.register_callback_query_handler(
        handler.handle_top100_navigation,
        lambda c: c.data.startswith("admin_top100_")
    )
    dp.register_callback_query_handler(
        handler.handle_back_to_stats,
        lambda c: c.data.startswith("admin_back_to_stats_")
    )
    # Топ пользователей
    dp.register_message_handler(
        handler.show_compact_top,
        lambda m: m.text and m.text.lower() in ['!ртоп', '/ртоп']
    )

    dp.register_callback_query_handler(
        handler.handle_show_more_top,
        lambda c: c.data.startswith("show_more_top_")
    )

    dp.register_callback_query_handler(
        handler.handle_back_to_top10,
        lambda c: c.data.startswith("back_to_top10_")
    )

    # ========== ЛОГИ МОДЕРАЦИИ ==========
    dp.register_message_handler(
        handler.show_moderation_logs,
        commands=['модлог', 'modlog', 'логи', 'logs']
    )

    dp.register_message_handler(
        handler.show_moderation_logs,
        lambda m: m.text and m.text.startswith('/logs')
    )

    # Callback обработчики для логов
    dp.register_callback_query_handler(
        handler.handle_modlogs_page,
        lambda c: c.data.startswith("modlogs_page_")
    )

    dp.register_callback_query_handler(
        handler.handle_modlogs_stats,
        lambda c: c.data == "modlogs_stats"
    )

    dp.register_callback_query_handler(
        handler.handle_modlogs_search,
        lambda c: c.data == "modlogs_search_user"
    )

    dp.register_callback_query_handler(
        handler.handle_modlogs_current,
        lambda c: c.data == "modlogs_current"
    )

    print("✅ Админ обработчики зарегистрированы")
    return handler