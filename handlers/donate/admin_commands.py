import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command

from .status_repository import StatusRepository
from .config import STATUSES
from handlers.admin.admin_helpers import check_admin_async

logger = logging.getLogger(__name__)


class DonateAdminCommands:
    """Команды администрирования для системы статусов"""

    def __init__(self):
        self.logger = logger
        self.status_repo = StatusRepository()

    async def status_command(self, message: types.Message):
        """Команда /status <ID> <статус> <ссылка> <текст>"""
        if not await check_admin_async(message):
            return

        try:
            args = message.get_args().split()
            if len(args) < 2:
                await self._show_status_help(message)
                return

            user_id = int(args[0])
            status_name = args[1].lower()
            days = 30  # По умолчанию 30 дней

            # Парсим ссылку и текст если есть
            link_url = None
            link_text = None

            if len(args) > 2:
                # Проверяем, является ли третий аргумент ссылкой
                if args[2].startswith(('http://', 'https://', 't.me/')):
                    link_url = args[2]
                    if len(args) > 3:
                        link_text = ' '.join(args[3:])
                else:
                    # Если не ссылка, то это текст ссылки
                    link_text = ' '.join(args[2:])

            # Находим статус по имени
            status = None
            for s in STATUSES:
                if s["name"].lower() == status_name:
                    status = s
                    break

            if not status:
                await message.answer(f" Неизвестный статус: {status_name}\n"
                                     f"Доступные статусы: {', '.join([s['name'] for s in STATUSES[1:]])}")
                return

            # Выдаем статус
            success, result_msg = self.status_repo.set_user_status(
                user_id=user_id,
                status_id=status["id"],
                days=days,
                admin_id=message.from_user.id,
                link_url=link_url,
                link_text=link_text
            )

            if success:
                response = (
                    f"✅ <b>Статус успешно выдан!</b>\n\n"
                    f"👤 Пользователь: <code>{user_id}</code>\n"
                    f"🎖️ Статус: {status['icon']} {status['name'].title()}\n"
                    f"⏰ Срок: {days} дней\n"
                    f"💰 Ежедневный бонус: {status['bonus_amount']:,} Монет"
                )

                if link_url:
                    response += f"\n🔗 Ссылка: <a href='{link_url}'>{link_text or link_url}</a>"

                await message.answer(response, parse_mode="HTML")

                # Логируем действие
                self.logger.info(f"Admin {message.from_user.id} gave status {status['name']} to user {user_id}")

            else:
                await message.answer(f" Ошибка: {result_msg}")

        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in status command: {e}")
            await message.answer(f" Произошла ошибка: {e}")

    async def dellstatus_command(self, message: types.Message):
        """Команда /dellstatus <ID>"""
        if not await check_admin_async(message):
            return

        try:
            args = message.get_args().split()
            if len(args) != 1:
                await message.answer(" Использование: <code>/dellstatus [ID пользователя]</code>",
                                     parse_mode="HTML")
                return

            user_id = int(args[0])

            # Удаляем статус
            success, result_msg = self.status_repo.remove_user_status(user_id)

            if success:
                await message.answer(
                    f"✅ <b>Статус успешно удален!</b>\n\n"
                    f"👤 Пользователь: <code>{user_id}</code>\n"
                    f"📛 Все активные статусы деактивированы\n"
                    f"👤 Теперь пользователь имеет обычный статус",
                    parse_mode="HTML"
                )

                # Логируем действие
                self.logger.info(f"Admin {message.from_user.id} removed status from user {user_id}")

            else:
                await message.answer(f" {result_msg}")

        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in dellstatus command: {e}")
            await message.answer(f" Произошла ошибка: {e}")

    async def extend_status_command(self, message: types.Message):
        """Команда для продления статуса"""
        if not await check_admin_async(message):
            return

        try:
            args = message.get_args().split()
            if len(args) < 2:
                await message.answer(" Использование: <code>/extend_status [ID] [дни] [статус]</code>\n"
                                     "📝 Пример: <code>/extend_status 123456 30</code>",
                                     parse_mode="HTML")
                return

            user_id = int(args[0])
            days = int(args[1])
            status_id = int(args[2]) if len(args) > 2 else None

            if days <= 0:
                await message.answer(" Количество дней должно быть положительным")
                return

            success, result_msg = self.status_repo.extend_user_status(user_id, days, status_id)

            if success:
                await message.answer(f"✅ {result_msg}", parse_mode="HTML")
                self.logger.info(f"Admin {message.from_user.id} extended status for user {user_id} by {days} days")
            else:
                await message.answer(f" {result_msg}")

        except ValueError:
            await message.answer(" Неверный формат. ID и дни должны быть числами")
        except Exception as e:
            self.logger.error(f"Error in extend_status command: {e}")
            await message.answer(f" Произошла ошибка: {e}")

    async def status_info_command(self, message: types.Message):
        """Команда для информации о статусе пользователя"""
        if not await check_admin_async(message):
            return

        try:
            args = message.get_args().split()
            if len(args) != 1:
                await message.answer(" Использование: <code>/status_info [ID пользователя]</code>",
                                     parse_mode="HTML")
                return

            user_id = int(args[0])

            # Получаем информацию о статусе
            user_info = self.status_repo.get_user_info_for_profile(user_id)

            if "error" in user_info:
                await message.answer(f" {user_info['error']}")
                return

            active_status = user_info["active_status"]
            bonus_stats = user_info["bonus_stats"]

            # ИСПРАВЛЕНИЕ: Используем переменную для следующего бонуса
            next_bonus_text = "доступен сейчас" if user_info[
                'can_receive_bonus'] else f'через {user_info["next_bonus_time"]}'

            if active_status:
                response = (
                    f"👤 <b>Информация о статусе пользователя</b>\n\n"
                    f"🆔 ID: <code>{user_id}</code>\n"
                    f"📛 Имя: {user_info['first_name'] or 'Не указано'}\n"
                    f"📱 Username: @{user_info['username'] or 'нет'}\n\n"
                    f"🎖️ <b>Статус:</b> {active_status['status_icon']} {active_status['status_name'].title()}\n"
                    f"⏰ Истекает: {active_status['expires_at'].strftime('%d.%m.%Y %H:%M') if active_status['expires_at'] else 'бессрочно'}\n"
                    f"📅 Осталось дней: {active_status['days_left'] or '∞'}\n\n"
                    f"💰 <b>Ежедневный бонус:</b> {user_info['daily_bonus_amount']:,} Монет\n"
                    f"🎁 Всего бонусов получено: {bonus_stats['bonus_count']}\n"
                    f"💸 Общая сумма бонусов: {bonus_stats['total_bonus_amount']:,} Монет\n\n"
                    f"🕐 <b>Следующий бонус:</b> {next_bonus_text}"
                )

                if active_status.get('link_url'):
                    response += f"\n🔗 <b>Ссылка в профиле:</b> <a href='{active_status['link_url']}'>{active_status['link_text'] or active_status['link_url']}</a>"
            else:
                response = (
                    f"👤 <b>Информация о статусе пользователя</b>\n\n"
                    f"🆔 ID: <code>{user_id}</code>\n"
                    f"📛 Имя: {user_info['first_name'] or 'Не указано'}\n"
                    f"📱 Username: @{user_info['username'] or 'нет'}\n\n"
                    f"🎖️ <b>Статус:</b> 👤 Обычный\n"
                    f"💰 <b>Ежедневный бонус:</b> 1.000.000 Монет\n"
                    f"🎁 Всего бонусов получено: {bonus_stats['bonus_count']}\n"
                    f"💸 Общая сумма бонусов: {bonus_stats['total_bonus_amount']:,} Монет\n\n"
                    f"🕐 <b>Следующий бонус:</b> {next_bonus_text}"
                )

            await message.answer(response, parse_mode="HTML", disable_web_page_preview=True)

        except ValueError:
            await message.answer(" Неверный формат. ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Error in status_info command: {e}")
            await message.answer(f" Произошла ошибка: {e}")

    async def status_list_command(self, message: types.Message):
        """Команда для списка пользователей с определенным статусом"""
        if not await check_admin_async(message):
            return

        try:
            args = message.get_args().split()
            status_arg = args[0] if args else None

            # Преобразуем название статуса в ID если нужно
            status_id = None
            if status_arg:
                # Проверяем, является ли аргумент числом
                if status_arg.isdigit():
                    status_id = int(status_arg)
                else:
                    # Преобразуем название статуса в ID
                    status_name_map = {
                        'обычный': 1,
                        'бронза': 2,
                        'платина': 3,
                        'золото': 4,
                        'бриллиант': 5,
                        'platin': 3,
                        'gold': 4,
                        'silver': 2,
                        'diamond': 5
                    }
                    status_lower = status_arg.lower()
                    if status_lower in status_name_map:
                        status_id = status_name_map[status_lower]
                    else:
                        # Ищем частичное совпадение
                        for s in STATUSES:
                            if status_lower in s["name"].lower():
                                status_id = s["id"]
                                break

                        if not status_id:
                            await message.answer(
                                f" Неизвестный статус: {status_arg}\n"
                                f"Доступные статусы: {', '.join([s['name'] for s in STATUSES])}"
                            )
                            return

            users = self.status_repo.search_users_by_status(status_id=status_id, limit=50)

            if not users:
                status_name = next((s["name"] for s in STATUSES if s["id"] == status_id),
                                   "любым статусом") if status_id else "активными статусами"
                await message.answer(f"ℹ️ Нет пользователей с {status_name}")
                return

            response = f"👥 <b>Пользователи с активными статусами</b>\n\n"

            for i, user in enumerate(users[:20], 1):
                status_info = next((s for s in STATUSES if s["id"] == user["status_id"]), None)
                status_icon = status_info["icon"] if status_info else "👤"

                response += f"{i}. {status_icon} <code>{user['user_id']}</code> | {user['first_name'] or user['username'] or 'Без имени'}\n"

                if user.get('days_left'):
                    response += f"   ⏳ Осталось дней: {user['days_left']}\n"
                else:
                    response += f"   ⏳ Бессрочно\n"

            if len(users) > 20:
                response += f"\n📋 ... и еще {len(users) - 20} пользователей"

            await message.answer(response, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error in status_list command: {e}")
            await message.answer(f" Произошла ошибка: {e}")

    async def _show_status_help(self, message: types.Message):
        """Показывает справку по командам статусов"""
        help_text = (
            "👑 <b>Команды управления статусами</b>\n\n"
            "📋 <b>Доступные команды:</b>\n"
            "• <code>/status [ID] [статус] [ссылка] [текст]</code> - Выдать статус\n"
            "• <code>/dellstatus [ID]</code> - Удалить статус\n"
            "• <code>/extend_status [ID] [дни] [статус]</code> - Продлить статус\n"
            "• <code>/status_info [ID]</code> - Информация о статусе\n"
            "• <code>/status_list [ID_статуса]</code> - Список пользователей\n\n"
            "🎖️ <b>Доступные статусы:</b>\n"
        )

        for status in STATUSES[1:]:  # Пропускаем обычный статус
            help_text += f"• <code>{status['name']}</code> - {status['icon']} {status['name'].title()} ({status['bonus_amount']:,} Монет/день)\n"

        help_text += "\n📝 <b>Примеры:</b>\n"
        help_text += "<code>/status 123456 бронза</code>\n"
        help_text += "<code>/status 123456 платина https://t.me/example Ваш канал</code>\n"
        help_text += "<code>/dellstatus 123456</code>\n"
        help_text += "<code>/extend_status 123456 30</code>\n"
        help_text += "<code>/status_info 123456</code>"

        await message.answer(help_text, parse_mode="HTML")


def register_donate_admin_commands(dp: Dispatcher):
    """Регистрация админ-команд для системы статусов"""
    handler = DonateAdminCommands()

    # Регистрация команд
    dp.register_message_handler(handler.status_command, commands=['status'], state="*")
    dp.register_message_handler(handler.dellstatus_command, commands=['dellstatus'], state="*")
    dp.register_message_handler(handler.extend_status_command, commands=['extend_status'], state="*")
    dp.register_message_handler(handler.status_info_command, commands=['status_info'], state="*")
    dp.register_message_handler(handler.status_list_command, commands=['status_list'], state="*")

    logger.info("✅ Админ-команды системы статусов зарегистрированы")