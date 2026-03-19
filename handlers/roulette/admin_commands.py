# handlers/roulette/admin_commands.py
import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext

from .state_manager import state_manager
from .config import CONFIG

logger = logging.getLogger(__name__)


async def roulette_on_command(message: types.Message):
    """Включить рулетку в этом чате (!ron)"""

    # Проверяем права администратора
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await state_manager.check_admin_permissions(user_id, chat_id, message.bot):
        await message.answer(" Эта команда доступна только администраторам группы или бота")
        return

    # Если рулетка уже включена в этом чате
    if state_manager.is_roulette_enabled(chat_id):
        await message.answer("ℹ️ Рулетка уже включена в этом чате")
        return

    # Включаем рулетку в этом чате
    state_manager.enable_roulette(chat_id)

    # Очищаем кэш для текущего пользователя
    state_manager.clear_cache(user_id, chat_id)

    chat_name = message.chat.title if hasattr(message.chat, 'title') else "этом чате"
    logger.info(f"Рулетка включена пользователем {user_id} в чате {chat_id} ({chat_name})")

    await message.answer(
        f"✅ <b>Рулетка включена в {chat_name}!</b>\n\n"
        "🎰 Теперь все команды рулетки доступны для использования.\n"
        "Участники могут делать ставки и играть в рулетку.",
        parse_mode="HTML"
    )


async def roulette_off_command(message: types.Message):
    """Отключить рулетку в этом чате (!roff)"""

    # Проверяем права администратора
    user_id = message.from_user.id
    chat_id = message.chat.id

    if not await state_manager.check_admin_permissions(user_id, chat_id, message.bot):
        await message.answer(" Эта команда доступна только администраторам группы или бота")
        return

    # Если рулетка уже отключена в этом чате
    if not state_manager.is_roulette_enabled(chat_id):
        await message.answer("ℹ️ Рулетка уже отключена в этом чате")
        return

    # Отключаем рулетку в этом чате
    state_manager.disable_roulette(chat_id)

    # Очищаем кэш для текущего пользователя
    state_manager.clear_cache(user_id, chat_id)

    chat_name = message.chat.title if hasattr(message.chat, 'title') else "этом чате"
    logger.info(f"Рулетка отключена пользователем {user_id} в чате {chat_id} ({chat_name})")

    await message.answer(
        f"🚫 <b>Рулетка отключена в {chat_name}!</b>\n\n"
        "🎰 Все команды рулетки временно недоступны.\n"
        "Для включения используйте команду <code>!ron</code>.",
        parse_mode="HTML"
    )


async def roulette_status_command(message: types.Message):
    """Показать статус рулетки в этом чате (!rstatus)"""

    # Проверяем права администратора
    user_id = message.from_user.id
    chat_id = message.chat.id

    is_admin = await state_manager.check_admin_permissions(user_id, chat_id, message.bot)

    status = "🟢 <b>Включена и работает</b>" if state_manager.is_roulette_enabled(chat_id) else "🔴 <b>Отключена</b>"
    chat_name = message.chat.title if hasattr(message.chat, 'title') else "этом чате"

    response = (
        f"🎰 <b>Статус рулетки в {chat_name}</b>\n\n"
        f"Состояние: {status}\n"
        f"ID чата: <code>{chat_id}</code>\n"
    )

    if is_admin:
        response += (
            f"\n<b>Команды управления:</b>\n"
            f"• <code>!ron</code> - включить рулетку в этом чате\n"
            f"• <code>!roff</code> - отключить рулетку в этом чате\n"
            f"• <code>!rstatus</code> - показать статус"
        )
    else:
        response += f"\n<i>Только администраторы могут управлять рулеткой</i>"

    await message.answer(response, parse_mode="HTML")





async def roulette_unlock_coins_command(message: types.Message):
    """Снять лимит рулетки за 100,000,000 монет (команда !rul_unlock)"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    # Проверка что команда в группе
    if message.chat.type not in ['group', 'supergroup']:
        await message.reply("❌ Эта команда работает только в группах")
        return

    # Получаем статус лимита рулетки
    limit_info = state_manager.get_roulette_limit_info(chat_id)

    # Если лимит уже снят
    if limit_info.get('limit_removed', False):
        await message.reply("✅ Лимит рулетки уже снят в этой группе")
        return

    # Проверка баланса
    from database import SessionLocal
    from database.crud import UserRepository

    db = SessionLocal()
    try:
        user = UserRepository.get_user_by_telegram_id(db, user_id)
        if not user or user.coins < 100_000_000:
            await message.reply(
                f"❌ Недостаточно средств. Нужно 100,000,000 монет\n"
                f"Ваш баланс: {user.coins if user else 0} монет"
            )
            return

        # Списание монет
        UserRepository.update_user_balance(db, user_id, user.coins - 100_000_000)

        # Снятие лимита рулетки
        state_manager.unlock_roulette_with_coins(chat_id, user_id)

        # Форматируем имя пользователя
        user_link = f"[{username}](tg://user?id={user_id})"

        await message.reply(
            f"✅ {user_link} снял лимит рулетки за 100,000,000 монет!\n"
            f"Теперь рулетка доступна без ограничений для всех участников группы.",
            parse_mode="Markdown"
        )

        # Логирование
        logger.info(f"Лимит рулетки снят в группе {chat_id} пользователем {user_id} за монеты")

    except Exception as e:
        logger.error(f"Ошибка снятия лимита рулетки: {e}")
        await message.reply("❌ Ошибка при снятии лимита")
    finally:
        db.close()


async def roulette_unlock_donate_command(message: types.Message):
    """Снять лимит рулетки после подтверждения доната 500₽ (команда !rul_unlock_donate)"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Только для администраторов
    if not await state_manager.check_admin_permissions(user_id, chat_id, message.bot):
        await message.reply("❌ Только администраторы могут использовать эту команду")
        return

    # Получаем статус лимита рулетки
    limit_info = state_manager.get_roulette_limit_info(chat_id)

    # Если лимит уже снят
    if limit_info.get('limit_removed', False):
        await message.reply("✅ Лимит рулетки уже снят в этой группе")
        return

    # Снимаем лимит рулетки
    state_manager.unlock_roulette_with_donation(chat_id)

    await message.reply(
        "✅ Лимит рулетки снят (донат 500₽ подтверждён)\n"
        "Теперь рулетка доступна без ограничений для всех участников группы."
    )

    # Логирование
    logger.info(f"Лимит рулетки снят в группе {chat_id} пользователем {user_id} через донат")


async def roulette_limit_status_command(message: types.Message):
    """Показать статус лимита рулетки в группе (!rul_status)"""
    chat_id = message.chat.id

    # Только для групп
    if message.chat.type not in ['group', 'supergroup']:
        await message.reply("ℹ️ Эта команда работает только в группах")
        return

    limit_info = state_manager.get_roulette_limit_info(chat_id)
    chat_title = message.chat.title or "Эта группа"

    status = "✅ СНЯТ" if limit_info.get('limit_removed') else "⚠️ АКТИВЕН"
    free_used = "Да" if limit_info.get('free_used') else "Нет"
    is_new = "Да" if limit_info.get('is_new_group') else "Нет"

    removed_info = ""
    if limit_info.get('removed_by'):
        removed_info = f"\n👤 Снял: <code>{limit_info['removed_by']}</code>"
        if limit_info.get('removed_at'):
            removed_info += f"\n📅 Когда: {limit_info['removed_at'].strftime('%d.%m.%Y %H:%M')}"
        if limit_info.get('removed_via'):
            removed_info += f"\n💰 Способ: {'монеты' if limit_info['removed_via'] == 'coins' else 'донат 500₽'}"

    response = (
        f"🎰 <b>Статус лимита рулетки</b>\n\n"
        f"🏷️ <b>Группа:</b> {chat_title}\n"
        f"🆔 <b>ID:</b> <code>{chat_id}</code>\n"
        f"🆕 <b>Новая группа:</b> {is_new}\n"
        f"🔒 <b>Лимит рулетки:</b> {status}\n"
        f"🎁 <b>Бесплатный запуск использован:</b> {free_used}\n"
        f"{removed_info}\n\n"
        f"<b>Для снятия лимита:</b>\n"
        f"• Донат 500₽ через /донат\n"
        f"• Укажите ID группы при оплате"
    )

    await message.reply(response, parse_mode="HTML")


async def roulette_lock_command(message: types.Message):
    """Вернуть лимит рулетки (команда !rul_lock) - только для админов бота"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Проверяем права администратора БОТА
    from handlers.admin.admin_constants import ADMIN_IDS
    if user_id not in ADMIN_IDS:
        await message.reply("❌ Только главные администраторы бота могут использовать эту команду")
        return

    # Парсим аргументы (можно указать ID группы)
    args = message.text.split()
    target_chat_id = chat_id
    
    if len(args) > 1:
        try:
            target_chat_id = int(args[1])
        except ValueError:
            await message.reply("❌ Неверный формат ID группы")
            return

    # Получаем текущий статус лимита
    limit_info = state_manager.get_roulette_limit_info(target_chat_id)
    
    # Если лимит уже активен
    if not limit_info.get('limit_removed', False):
        await message.reply(f"ℹ️ Лимит рулетки уже активен для группы {target_chat_id}")
        return

    # Возвращаем лимит
    state_manager.lock_roulette_limit(target_chat_id)

    await message.reply(
        f"✅ Лимит рулетки возвращен для группы <code>{target_chat_id}</code>\n"
        f"Теперь рулетка снова имеет ограничения.",
        parse_mode="HTML"
    )

    logger.info(f"Лимит рулетки возвращен для группы {target_chat_id} пользователем {user_id}")


async def admin_free_unlock_command(message: types.Message):
    """Снять лимит рулетки бесплатно (только главные админы бота).

    Команда: !rul_free [chat_id]
    Если chat_id не указан — снимает в текущей группе.
    """
    user_id = message.from_user.id

    from handlers.admin.admin_constants import ADMIN_IDS
    if user_id not in ADMIN_IDS:
        await message.reply("❌ Только главные администраторы бота могут использовать эту команду")
        return

    args = message.text.split()
    if len(args) > 1:
        try:
            target_chat_id = int(args[1])
        except ValueError:
            await message.reply("❌ Неверный формат ID группы")
            return
    else:
        target_chat_id = message.chat.id

    # Проверяем текущий статус
    limit_info = state_manager.get_roulette_limit_info(target_chat_id)
    if limit_info.get('limit_removed', False):
        await message.reply(f"✅ Лимит рулетки уже снят для группы {target_chat_id}")
        return

    # Снимаем лимит через оба метода для надёжности
    state_manager.unlock_group_limit_paid(target_chat_id)
    state_manager.unlock_roulette_with_coins(target_chat_id, user_id)

    await message.reply(
        f"✅ Лимит рулетки снят для группы <code>{target_chat_id}</code>\n"
        f"Бесплатно (админ-команда). Монеты не списаны.",
        parse_mode="HTML"
    )
    logger.info(f"Лимит рулетки снят БЕСПЛАТНО для группы {target_chat_id} админом {user_id}")


async def admin_roulette_limit_status(message: types.Message):
    """Команда для админов: посмотреть статус лимита рулетки в любой группе (/rul_status -100123456789)"""
    # Проверка прав администратора
    user_id = message.from_user.id
    if not await state_manager.check_admin_permissions(user_id, message.chat.id, message.bot):
        await message.reply("❌ Только администраторы могут использовать эту команду")
        return

    # Парсим аргументы
    args = message.get_args().split()
    if not args:
        await message.reply(
            "Использование: /rul_status [ID_группы]\n"
            "Пример: /rul_status -100123456789\n\n"
            "Получить ID группы:\n"
            "1. Добавить бота в группу и написать /id\n"
            "2. Попросить другого бота показать ID\n"
            "3. Посмотреть при блокировке рулетки"
        )
        return

    try:
        group_id = int(args[0])

        # Получаем информацию о лимите рулетки
        limit_info = state_manager.get_roulette_limit_info(group_id)

        # Формируем ответ
        status = "✅ СНЯТ" if limit_info.get('limit_removed') else "⚠️ АКТИВЕН"
        free_used = "Да" if limit_info.get('free_used') else "Нет"
        is_new = "Да" if limit_info.get('is_new_group') else "Нет"

        removed_info = ""
        if limit_info.get('removed_by'):
            removed_info = f"\n👤 Снял: <code>{limit_info['removed_by']}</code>"
            if limit_info.get('removed_at'):
                removed_info += f"\n📅 Когда: {limit_info['removed_at'].strftime('%d.%m.%Y %H:%M')}"
            if limit_info.get('removed_via'):
                removed_info += f"\n💰 Способ: {'монеты (100 млн)' if limit_info['removed_via'] == 'coins' else 'донат (500₽)'}"

        response = (
            f"🎰 <b>Статус лимита рулетки</b>\n\n"
            f"🆔 <b>ID группы:</b> <code>{group_id}</code>\n"
            f"🆕 <b>Новая группа:</b> {is_new}\n"
            f"🔒 <b>Лимит рулетки:</b> {status}\n"
            f"🎁 <b>Бесплатный запуск использован:</b> {free_used}\n"
            f"💳 <b>Донат 500₽ оплачен:</b> {'Да' if limit_info.get('donation_paid') else 'Нет'}\n"
            f"{removed_info}"
        )

        await message.reply(response, parse_mode="HTML")

    except ValueError:
        await message.reply("❌ Неверный формат ID группы. Введите число (например: -100123456789)")
    except Exception as e:
        logger.error(f"Ошибка получения статуса лимита рулетки: {e}")
        await message.reply("❌ Ошибка при получении статуса лимита")


def register_roulette_admin_commands(dp: Dispatcher):
    """Регистрирует команды управления рулеткой"""

    # Команды с восклицательным знаком
    dp.register_message_handler(
        roulette_on_command,
        lambda m: m.text and m.text.lower().strip() == '!ron'
    )

    dp.register_message_handler(
        roulette_off_command,
        lambda m: m.text and m.text.lower().strip() == '!roff'
    )

    dp.register_message_handler(
        roulette_status_command,
        lambda m: m.text and m.text.lower().strip() == '!rstatus'
    )

    # Команды для лимитов рулетки
    dp.register_message_handler(
        roulette_unlock_donate_command,
        lambda m: m.text and m.text.lower().strip().startswith('!rul_unlock_donate'),
        chat_type=['group', 'supergroup']
    )

    dp.register_message_handler(
        roulette_unlock_donate_command,
        lambda m: m.text and m.text.lower().strip().startswith('!rul_unlock_donate'),
        chat_type=['group', 'supergroup']
    )

    dp.register_message_handler(
        roulette_limit_status_command,
        lambda m: m.text and m.text.lower().strip() == '!rul_status',
        chat_type=['group', 'supergroup']
    )

    # Команда для возврата лимита рулетки (только для главных админов)
    dp.register_message_handler(
        roulette_lock_command,
        lambda m: m.text and m.text.lower().strip().startswith('!rul_lock'),
        state="*"
    )

    # Бесплатное снятие лимита (только главные админы бота)
    dp.register_message_handler(
        admin_free_unlock_command,
        lambda m: m.text and m.text.lower().strip().startswith('!rul_free'),
        state="*"
    )

    # Админ-команда для проверки статуса любой группы
    dp.register_message_handler(
        admin_roulette_limit_status,
        commands=["rul_status"],
        state="*"
    )

    # Альтернативные варианты команд
    dp.register_message_handler(
        roulette_on_command,
        lambda m: m.text and m.text.lower().strip() in ['/ron', 'ron', 'рулетка вкл']
    )

    dp.register_message_handler(
        roulette_off_command,
        lambda m: m.text and m.text.lower().strip() in ['/roff', 'roff', 'рулетка выкл']
    )

    dp.register_message_handler(
        roulette_status_command,
        lambda m: m.text and m.text.lower().strip() in ['/rstatus', 'rstatus', 'статус рулетки']
    )

    logger.info("✅ Команды управления рулеткой (по чатам) зарегистрированы")