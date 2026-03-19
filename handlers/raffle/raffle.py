# handlers/raffle/raffle.py

import asyncio
import random
import logging
from decimal import Decimal
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from aiogram import types, Dispatcher, Bot
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.orm import Session

from database import SessionLocal
from database.crud import UserRepository, TransactionRepository

logger = logging.getLogger(__name__)

# ==========================
# НАСТРОЙКИ И КОНСТАНТЫ
# ==========================

MIN_RAFFLE_AMOUNT = 50000
MIN_PARTICIPANTS = 5
MAX_PARTICIPANTS = 150
WINNER_PERCENTAGE = 0.30
MIN_WINNERS = 1
DURATION_MINUTES = 3
VIRUS_BASE_INCREMENT = 0  # ИЗМЕНЕНО: в начале у всех 0 вирусов
VIRUS_TIME_INCREMENT = 1  # Увеличение вирусов за каждую секунду
MAX_VIRUS_COUNT = 50  # ИЗМЕНЕНО: максимум 50 вирусов вместо 150

# Активные розыгрыши
active_raffles: Dict[str, Dict] = {}


# ==========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================

def generate_raffle_id() -> str:
    """Генерирует уникальный ID розыгрыша"""
    return f"raffle_{datetime.now().timestamp()}_{random.randint(1000, 9999)}"


def calculate_winners(participants: List[Dict], total_amount: int) -> List[Dict]:
    """Рассчитывает победителей с бонусами за первые места"""
    if not participants:
        return []

    # Сортируем участников по количеству вирусов (убыванию)
    sorted_participants = sorted(participants, key=lambda x: x.get('virus_count', 0), reverse=True)

    # Рассчитываем количество победителей (30% от участников, но минимум 1)
    winner_count = max(MIN_WINNERS, int(len(sorted_participants) * WINNER_PERCENTAGE))
    winner_count = min(winner_count, len(sorted_participants))

    # Берём топ-N участников с наибольшим количеством вирусов
    top_winners = sorted_participants[:winner_count]

    # Система бонусов за места
    place_bonuses = {
        1: 4.0,  # 1-е место получает в 4 раза больше базовой доли
        2: 2.5,  # 2-е место получает в 2.5 раза больше
        3: 1.8,  # 3-е место получает в 1.8 раза больше
        4: 1.3,  # 4-е место получает в 1.3 раза больше
        5: 1.1  # 5-е место получает в 1.1 раза больше
    }

    # Распределение призового фонда
    total_weight = 0
    winners_data = []

    for i, winner in enumerate(top_winners):
        position = i + 1

        # Базовый вес по вирусам
        virus_weight = winner.get('virus_count', 0) or 1

        # Применяем бонус за место
        place_multiplier = place_bonuses.get(position, 1.0)

        # Итоговый вес
        total_weight += virus_weight * place_multiplier

        winners_data.append({
            'user_id': winner['user_id'],
            'username': winner['username'],
            'virus_count': winner.get('virus_count', 0),
            'position': position,
            'weight': virus_weight * place_multiplier,
            'place_multiplier': place_multiplier
        })

    # Распределяем призы
    winners = []
    remaining_amount = total_amount

    # Первый проход: распределение по весам
    for winner_info in winners_data:
        prize_share = winner_info['weight'] / total_weight
        prize = int(total_amount * prize_share)
        prize = max(1, prize)  # Минимум 1 монета

        winners.append({
            'user_id': winner_info['user_id'],
            'username': winner_info['username'],
            'prize': prize,
            'position': winner_info['position'],
            'virus_count': winner_info['virus_count']
        })
        remaining_amount -= prize

    # Распределяем оставшиеся средства
    if remaining_amount > 0:
        # Сначала даем первым местам
        for i in range(min(len(winners), 5)):
            if remaining_amount <= 0:
                break
            winners[i]['prize'] += 1
            remaining_amount -= 1

        # Если еще остались, распределяем поровну
        if remaining_amount > 0:
            bonus_per_winner = remaining_amount // len(winners)
            extra_bonus = remaining_amount % len(winners)

            for i, winner in enumerate(winners):
                winner['prize'] += bonus_per_winner
                if i < extra_bonus:
                    winner['prize'] += 1

    return winners


def update_virus_counts(participants: List[Dict], start_time: datetime = None):
    """Обновляет количество вирусов у всех участников с уникальными значениями"""
    if not participants or not start_time:
        return participants

    elapsed_seconds = max(0, int((datetime.now() - start_time).total_seconds()))

    # Максимальное количество вирусов за 3 минуты = 50 (ИЗМЕНЕНО)
    max_viruses = MAX_VIRUS_COUNT
    max_time_seconds = DURATION_MINUTES * 60

    # Процент прошедшего времени
    time_percentage = min(elapsed_seconds / max_time_seconds, 1.0)

    # Базовое количество вирусов (максимум 50)
    base_virus_count = int(time_percentage * max_viruses)

    # Создаем уникальные значения вирусов для каждого участника
    for i, participant in enumerate(participants):
        # У каждого участника своя скорость роста
        virus_speed = participant.get('virus_speed', random.uniform(0.8, 1.2))

        # Добавляем позиционный бонус (первые места получают немного больше)
        position_bonus = max(0, (len(participants) - i) / len(participants)) * 2  # Уменьшен бонус

        # Уникальное случайное отклонение для каждого участника
        unique_offset = (participant.get('user_id', 0) % 10) * 0.05  # Уменьшено отклонение

        # Итоговое количество вирусов
        virus_count = int(base_virus_count * virus_speed + position_bonus + unique_offset)

        # Гарантируем, что первые места имеют разные значения
        if i < 5:  # Для первых 5 мест
            # Увеличиваем разрыв между местами (меньше разрыв)
            place_bonus = (4 - i) * 1  # 1-е место: +4, 2-е: +3, 3-е: +2, 4-е: +1, 5-е: +0
            virus_count += place_bonus

        # Убедимся что вирусы не отрицательные и не превышают максимум (50)
        participant['virus_count'] = max(1, min(virus_count, max_viruses))

    # Дополнительно сортируем и корректируем, чтобы первые места были уникальными
    if len(participants) >= 5:
        # Берем топ-5 участников
        top_participants = sorted(participants, key=lambda x: x.get('virus_count', 0), reverse=True)[:5]

        # Гарантируем разницу минимум в 1 вирус между соседними местами
        for i in range(1, min(5, len(top_participants))):
            current_virus = top_participants[i].get('virus_count', 0)
            prev_virus = top_participants[i - 1].get('virus_count', 0)

            if current_virus >= prev_virus:
                # Уменьшаем текущее место на разницу + 1
                top_participants[i]['virus_count'] = max(1, prev_virus - 1)

    return participants


def format_participants_list(participants: List[Dict]) -> str:
    """Форматирует список участников для отображения (просто как в примере)"""
    if not participants:
        return ""

    result_lines = []

    # Сортируем участников по количеству вирусов (убыванию)
    sorted_participants = sorted(participants, key=lambda x: x.get('virus_count', 0), reverse=True)

    for participant in sorted_participants:
        username = participant['username'] or "Аноним"
        virus_count = participant.get('virus_count', 0)

        # Просто: username: virus_count🦠
        result_lines.append(f"{username}: {virus_count}🦠")

    return "\n".join(result_lines)

def format_winners_list(winners: List[Dict]) -> str:
    """Форматирует список победителей"""
    if not winners:
        return "Победители не определены"

    result_lines = []
    for winner in winners:
        username = winner['username'] or "Аноним"
        prize = winner['prize']
        result_lines.append(f"{username} выиграл {prize:,} монет")

    return "\n".join(result_lines)


def create_raffle_keyboard(raffle_id: str, is_creator: bool = False) -> InlineKeyboardMarkup:
    """Создает клавиатуру для розыгрыша"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    # ВСЕГДА показываем кнопку "Присоединиться"
    keyboard.row(
        InlineKeyboardButton(text="Присоединиться", callback_data=f"join_raffle_{raffle_id}")
    )

    # Всегда показываем кнопки "Начать" и "Отмена" для pending розыгрышей
    # (колбэки start_raffle_callback и cancel_raffle_callback проверяют creator_id)
    keyboard.row(
        InlineKeyboardButton(text="Начать", callback_data=f"start_raffle_{raffle_id}"),
        InlineKeyboardButton(text="Отмена", callback_data=f"cancel_raffle_{raffle_id}")
    )

    return keyboard


def create_active_raffle_keyboard(raffle_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для активного розыгрыша (после старта)"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(text="Присоединиться", callback_data=f"join_raffle_{raffle_id}")
    )
    return keyboard


def create_final_message_no_keyboard() -> InlineKeyboardMarkup:
    """Создает пустую клавиатуру для финального сообщения"""
    return InlineKeyboardMarkup()


async def is_user_admin(user_id: int, chat_id: int, bot: Bot) -> bool:
    """Проверяет, является ли пользователь администратором бота или чата"""
    try:
        # Импортируем список админов из констант
        from handlers.admin.admin_constants import ADMIN_IDS
        
        # Проверка в списке главных админов
        if user_id in ADMIN_IDS:
            return True
        
        # Проверка флага is_admin в БД
        db = SessionLocal()
        user = UserRepository.get_user_by_telegram_id(db, user_id)
        db.close()

        if user and user.is_admin:
            return True

        # Проверка админа чата
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.is_chat_admin():
                return True
        except Exception:
            pass

        return False
    except Exception as e:
        logger.error(f"Ошибка проверки прав администратора: {e}")
        return False


async def pin_raffle_message(bot: Bot, chat_id: int, message_id: int):
    """Закрепляет сообщение розыгрыша"""
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True)
        logger.info(f"Сообщение розыгрыша закреплено: {message_id}")
    except Exception as e:
        logger.error(f"Ошибка закрепления сообщения: {e}")


async def unpin_raffle_message(bot: Bot, chat_id: int, message_id: Optional[int] = None):
    """Открепляет закрепленное сообщение розыгрыша"""
    try:
        await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Сообщение розыгрыша откреплено в чате: {chat_id}")
        return True
    except Exception as e:
        if "message to unpin not found" in str(e).lower():
            logger.info(f"Сообщение уже не закреплено в чате: {chat_id}")
            return True
        logger.error(f"Ошибка открепления сообщения: {e}")
        return False


async def auto_start_raffle_if_full(bot: Bot, raffle_id: str):
    """Автоматически запускает розыгрыш если достигнут лимит участников"""
    if raffle_id not in active_raffles:
        return

    raffle = active_raffles[raffle_id]

    # Проверяем, можно ли запустить автоматически
    if (raffle["status"] == "pending" and
            len(raffle['participants']) >= MAX_PARTICIPANTS):

        logger.info(f"Достигнут лимит участников {MAX_PARTICIPANTS}, запускаем розыгрыш автоматически")

        # Запускаем розыгрыш
        raffle['status'] = 'active'
        raffle['is_active'] = True
        raffle['start_time'] = datetime.now()
        raffle['end_time'] = datetime.now() + timedelta(minutes=DURATION_MINUTES)

        # УБЕДИТЕСЬ: при автостарте тоже сбрасываем вирусы на 0
        for participant in raffle['participants']:
            participant['virus_count'] = 0

        # Обновляем вирусы
        updated_participants = update_virus_counts(raffle['participants'], raffle['start_time'])
        raffle['participants'] = updated_participants
        participants_text = format_participants_list(updated_participants)

        started_text = (
            f"🏁 Розыгрыш начался!\n\n"
            f"{participants_text}\n\n"
            f"Всего: {len(raffle['participants'])}\n"
            f"⏰ Осталось: {DURATION_MINUTES:02d}:00"
        )

        try:
            await bot.edit_message_text(
                chat_id=raffle['chat_id'],
                message_id=raffle['message_id'],
                text=started_text,
                reply_markup=create_active_raffle_keyboard(raffle_id)
            )

            # Открепляем сообщение после старта
            if raffle.get('is_pinned', False):
                success = await unpin_raffle_message(bot, raffle['chat_id'], raffle['message_id'])
                if success:
                    raffle['is_pinned'] = False

        except Exception as e:
            logger.error(f"Ошибка обновления сообщения при автостарте: {e}")

        # Запускаем таймер завершения
        asyncio.create_task(raffle_timer(bot, raffle_id))

        # Запускаем обновление вирусов
        raffle['virus_updater'] = asyncio.create_task(start_virus_updater(bot, raffle_id))


async def update_raffle_virus_counter(bot: Bot, raffle_id: str):
    """Обновляет счетчик вирусов в активном розыгрыше"""
    if raffle_id not in active_raffles:
        return

    raffle = active_raffles[raffle_id]

    if raffle["status"] != "active":
        return

    # Обновляем количество вирусов у всех участников
    updated_participants = update_virus_counts(raffle['participants'], raffle['start_time'])
    raffle['participants'] = updated_participants

    # Формируем список участников с обновленными вирусами
    participants_text = format_participants_list(updated_participants)

    time_left = max(0, int((raffle['end_time'] - datetime.now()).total_seconds()))
    minutes = time_left // 60
    seconds = time_left % 60

    raffle_text = (
        f"Розыгрыш начался\n\n"
        f"{participants_text}\n\n"
        f"Всего: {len(raffle['participants'])}\n"
        f"⏰ Осталось: {minutes:02d}:{seconds:02d}"
    )

    try:
        await bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=raffle_text,
            reply_markup=create_active_raffle_keyboard(raffle_id)
        )
    except Exception as e:
        # Игнорируем ошибку если сообщение уже было изменено или удалено
        if "message is not modified" not in str(e):
            logger.debug(f"Ошибка обновления счетчика вирусов: {e}")


async def start_virus_updater(bot: Bot, raffle_id: str):
    """Запускает обновление счетчика вирусов каждую секунду"""
    while raffle_id in active_raffles and active_raffles[raffle_id]["status"] == "active":
        await update_raffle_virus_counter(bot, raffle_id)
        await asyncio.sleep(1)  # Обновляем каждую секунду


# ==========================
# ХЕНДЛЕРЫ
# ==========================

async def raffle_rules(message: types.Message):
    """Показать правила розыгрыша"""
    rules_text = (
        "<b>СИСТЕМА РОЗЫГРЫШЕЙ</b>\n\n"

        "<b>Основные правила:</b>\n"
        "• Минимальная сумма розыгрыша: 50,000 Монет\n"
        "• Минимум участников: 5 человек\n"
        "• Максимум участников: 150 человек\n"
        "• Победителей: 30% от числа участников\n"
        "• Длительность: 3 минуты\n"
        "• Максимум вирусов: 50 🦠\n\n"  # ИЗМЕНЕНО

        "<b>Как работает система вирусов:</b>\n"
        "• У каждого участника есть вирусы 🦠\n"
        "• Чем дольше участвуешь - тем больше вирусов\n"
        "• Чем больше вирусов - тем больше шанс на выигрыш\n"
        "• Вирусы растут каждую секунду\n"
        "• Максимальное количество вирусов: 50\n\n"  # ИЗМЕНЕНО

        "<b>Распределение призов:</b>\n"
        "• Победители с наибольшим количеством вирусов получают больше\n"
        "• Призовой фонд делится пропорционально вирусам\n"
        "• Первые места получают бонусы\n\n"

        "<b>Команды:</b>\n"
        "• !розыгрыш 50000 — создать розыгрыш\n"
        "• !раффл 100000 — создать розыгрыш\n"
        "• розыгрыш 50000 — создать розыгрыш\n"
        "• раффл 100000 — создать розыгрыш\n\n"

        "<b>Важно:</b>\n"
        "• Розыгрыши могут создавать только администраторы\n"
        "• Для старта розыгрыша нужно нажать кнопку 'Начать'\n"
        "• Минимум 5 участников для старта\n"
        "• При достижении 150 участников розыгрыш запустится автоматически\n\n"

        "<b>Удачи всем участникам!</b>"
    )

    await message.answer(rules_text, parse_mode="HTML")


async def raffle_start(message: types.Message, state: FSMContext):
    """Начать создание розыгрыша (только для админов)"""
    # Проверяем права админа
    if not await is_user_admin(message.from_user.id, message.chat.id, message.bot):
        await message.answer("❌ Только администраторы бота могут создавать розыгрыши")
        return

    # Проверяем, не в состоянии ли мы уже
    current_state = await state.get_state()
    if current_state:
        await message.answer("Вы уже участвуете в другом процессе. Закончите его сначала.")
        return

    text = message.text.lower().strip()

    # Проверяем команды розыгрыша
    if not (text.startswith('!розыгрыш ') or
            text.startswith('!раффл ') or
            text.startswith('розыгрыш ') or
            text.startswith('раффл ')):
        return

    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(f"Используйте: <code>!розыгрыш сумма</code>\nПример: <code>!розыгрыш {MIN_RAFFLE_AMOUNT}</code>")
        return

    amount = int(parts[1])

    if amount < MIN_RAFFLE_AMOUNT:
        await message.answer(f"Минимальная сумма розыгрыша: {MIN_RAFFLE_AMOUNT:,} Монет")
        return

    # Проверяем баланс создателя
    db: Optional[Session] = None
    try:
        db = SessionLocal()
        user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
        if not user:
            await message.answer("Пользователь не найден. Начните с команды /start")
            return

        if user.coins < amount:
            await message.answer(f"Недостаточно Монет для розыгрыша. Ваш баланс: {user.coins:,}")
            return

        # Проверяем, нет ли уже активного розыгрыша в чате
        for raffle_id, raffle in active_raffles.items():
            if raffle["chat_id"] == message.chat.id and raffle["status"] in ["pending", "active"]:
                await message.answer("В этом чате уже идет розыгрыш!")
                return

        # Создаем розыгрыш
        raffle_id = generate_raffle_id()

        admin_name = message.from_user.username or message.from_user.first_name

        # Списание средств у создателя
        user.coins -= Decimal(amount)

        # Записываем транзакцию
        TransactionRepository.create_transaction(
            db,
            from_user_id=message.from_user.id,
            to_user_id=None,  # В систему
            amount=amount,
            description=f"Создание розыгрыша #{raffle_id}"
        )

        db.commit()

        # ИМЕНЯЕМ: создатель НЕ участвует в своем розыгрыше
        active_raffles[raffle_id] = {
            'creator_id': message.from_user.id,
            'creator_name': admin_name,
            'amount': amount,
            'participants': [],  # Создатель НЕ в списке участников
            'status': 'pending',  # Ожидает запуска
            'chat_id': message.chat.id,
            'message_id': None,
            'start_time': None,
            'end_time': None,
            'winners': [],
            'is_active': False,  # Флаг, что розыгрыш еще не начался
            'is_pinned': False,
            'virus_updater': None  # Задача обновления вирусов
        }

        await state.update_data(raffle_id=raffle_id)

        # Создаем сообщение о розыгрыше
        raffle_text = (
            f"{admin_name} предлагает принять участие в розыгрыше {amount:,} монет, максимальное число участников - {MAX_PARTICIPANTS}\n\n"
            f"👤 Создатель: {admin_name} (не участвует)\n"
            f"👥 Участники: \n\n"
            f"Всего: 0"
        )

        # ВАЖНО: передаем is_creator=True чтобы показать кнопки "Начать" и "Отмена"
        keyboard = create_raffle_keyboard(raffle_id, is_creator=True)
        msg = await message.answer(raffle_text, reply_markup=keyboard)

        # Запоминаем ID сообщения
        active_raffles[raffle_id]['message_id'] = msg.message_id

        # Закрепляем сообщение
        await pin_raffle_message(message.bot, message.chat.id, msg.message_id)
        active_raffles[raffle_id]['is_pinned'] = True

        logger.info(f"Создан розыгрыш {raffle_id} на сумму {amount:,}")

    except Exception as e:
        logger.error(f"Ошибка при создании розыгрыша: {e}")
        await message.answer("Произошла ошибка при создании розыгрыша")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


async def join_raffle_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """Присоединиться к розыгрышу (можно до старта)"""
    raffle_id = callback_query.data.replace("join_raffle_", "")

    if raffle_id not in active_raffles:
        await callback_query.answer("Розыгрыш не найден или завершен")
        return

    raffle = active_raffles[raffle_id]

    # ПРОВЕРЯЕМ: создатель не может присоединиться к своему розыгрышу
    if callback_query.from_user.id == raffle['creator_id']:
        await callback_query.answer("Вы не можете участвовать в своем розыгрыше!")
        return

    if raffle["status"] == "finished":
        await callback_query.answer("Розыгрыш уже завершен")
        return

    if raffle["status"] == "cancelled":
        await callback_query.answer("Розыгрыш отменен")
        return

    # Проверяем, не участвует ли уже пользователь
    for participant in raffle['participants']:
        if participant['user_id'] == callback_query.from_user.id:
            await callback_query.answer("Вы уже участвуете в этом розыгрыше!")
            return

    # Проверяем лимит участников
    if len(raffle['participants']) >= MAX_PARTICIPANTS:
        await callback_query.answer(f"Достигнут лимит участников: {MAX_PARTICIPANTS}")
        return

    # Добавляем участника
    username = callback_query.from_user.username or callback_query.from_user.first_name or "Аноним"

    # Уникальная скорость роста для каждого участника
    user_id_hash = abs(callback_query.from_user.id) % 100
    virus_speed = 0.8 + (user_id_hash / 100) * 0.4  # От 0.8 до 1.2

    # Устанавливаем начальное количество вирусов в зависимости от статуса розыгрыша
    if raffle["status"] == "pending":
        # Если розыгрыш еще не начался - 0 вирусов
        initial_virus = 0
    else:
        # Если розыгрыш уже активен - рассчитываем вирусы с момента старта
        elapsed_seconds = max(0, int((datetime.now() - raffle['start_time']).total_seconds()))
        time_percentage = min(elapsed_seconds / (DURATION_MINUTES * 60), 1.0)
        initial_virus = int(time_percentage * MAX_VIRUS_COUNT * virus_speed)  # ИЗМЕНЕНО: MAX_VIRUS_COUNT

    raffle['participants'].append({
        'user_id': callback_query.from_user.id,
        'username': username,
        'joined_at': datetime.now(),
        'virus_count': initial_virus,
        'virus_speed': virus_speed,  # Уникальная скорость роста
        'is_fake': False,
        'user_hash': user_id_hash  # Для уникальности
    })

    # Определяем, какая клавиатура нужна
    if raffle["status"] == "pending":
        # До старта - определяем, является ли пользователь создателем
        is_creator = (callback_query.from_user.id == raffle['creator_id'])
        keyboard = create_raffle_keyboard(raffle_id, is_creator=is_creator)
    else:
        # После старта - стандартная клавиатура
        keyboard = create_active_raffle_keyboard(raffle_id)

    # Формируем текст участников
    participants_text = format_participants_list(raffle['participants'])

    # Обновляем сообщение
    if raffle["status"] == "pending":
        updated_text = (
            f"{raffle['creator_name']} предлагает принять участие в розыгрыше {raffle['amount']:,} монет, максимальное число участников - {MAX_PARTICIPANTS}\n\n"
            f"Участники: \n"
            f"{participants_text}\n\n"
            f"Всего: {len(raffle['participants'])}"
        )
    else:
        # Обновляем вирусы для всех участников
        updated_participants = update_virus_counts(raffle['participants'], raffle['start_time'])
        raffle['participants'] = updated_participants
        participants_text = format_participants_list(updated_participants)

        time_left = max(0, int((raffle['end_time'] - datetime.now()).total_seconds()))
        minutes = time_left // 60
        seconds = time_left % 60

        updated_text = (
            f"🏁 Розыгрыш начался!\n\n"
            f"{participants_text}\n\n"
            f"👥 Всего: {len(raffle['participants'])}\n"
            f"💰 Приз: {raffle['amount']:,} Монет\n"
            f"⏰ Осталось: {minutes:02d}:{seconds:02d}"
        )

    try:
        await callback_query.bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=updated_text,
            reply_markup=keyboard
        )

        # Проверяем, не достигли ли мы лимита участников для автостарта
        if raffle["status"] == "pending" and len(raffle['participants']) >= MAX_PARTICIPANTS:
            await auto_start_raffle_if_full(callback_query.bot, raffle_id)

    except Exception as e:
        logger.error(f"Ошибка обновления сообщения розыгрыша: {e}")

    await callback_query.answer(f"Вы присоединились к розыгрышу! Участников: {len(raffle['participants'])}")


def ensure_unique_viruses(participants: List[Dict]) -> List[Dict]:
    """Гарантирует, что у участников разные значения вирусов"""
    if len(participants) <= 1:
        return participants

    # Сортируем по вирусам
    sorted_participants = sorted(participants, key=lambda x: x.get('virus_count', 0), reverse=True)

    # Гарантируем разницу минимум в 1 вирус
    for i in range(1, len(sorted_participants)):
        current_virus = sorted_participants[i].get('virus_count', 0)
        prev_virus = sorted_participants[i - 1].get('virus_count', 0)

        if current_virus >= prev_virus:
            # Устанавливаем на 1 меньше, чем предыдущий
            sorted_participants[i]['virus_count'] = max(0, prev_virus - 1)

    return sorted_participants

async def start_raffle_callback(callback_query: types.CallbackQuery):
    """Запустить розыгрыш (только создатель)"""
    raffle_id = callback_query.data.replace("start_raffle_", "")

    if raffle_id not in active_raffles:
        await callback_query.answer("Розыгрыш не найден")
        return

    raffle = active_raffles[raffle_id]

    # Проверяем, что это создатель
    if callback_query.from_user.id != raffle['creator_id']:
        await callback_query.answer("Только создатель может начать розыгрыш")
        return

    if raffle["status"] != "pending":
        await callback_query.answer("Розыгрыш уже начат или завершен")
        return

    # Проверяем минимальное количество участников
    if len(raffle['participants']) < MIN_PARTICIPANTS:
        await callback_query.answer(f"Минимум участников: {MIN_PARTICIPANTS}")
        return

    # Запускаем розыгрыш
    raffle['status'] = 'active'
    raffle['is_active'] = True
    raffle['start_time'] = datetime.now()
    raffle['end_time'] = datetime.now() + timedelta(minutes=DURATION_MINUTES)

    # УБЕДИТЕСЬ ЧТО У ВСЕХ УЧАСТНИКОВ 0 ВИРУСОВ ПРИ СТАРТЕ
    for participant in raffle['participants']:
        participant['virus_count'] = 0

    # Формируем текст участников с вирусами (они все будут 0 в начале)
    updated_participants = update_virus_counts(raffle['participants'], raffle['start_time'])
    raffle['participants'] = updated_participants
    participants_text = format_participants_list(updated_participants)

    started_text = (
        f"🏁 Розыгрыш начался!\n\n"
        f"{participants_text}\n\n"
        f"Всего: {len(raffle['participants'])}\n"
        f"⏰ Осталось: {DURATION_MINUTES:02d}:00"
    )

    try:
        await callback_query.bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=started_text,
            reply_markup=create_active_raffle_keyboard(raffle_id)
        )

        # Открепляем сообщение после старта
        if raffle.get('is_pinned', False):
            success = await unpin_raffle_message(callback_query.bot, raffle['chat_id'], raffle['message_id'])
            if success:
                raffle['is_pinned'] = False

        # Запускаем обновление вирусов каждую секунду
        raffle['virus_updater'] = asyncio.create_task(start_virus_updater(callback_query.bot, raffle_id))

    except Exception as e:
        logger.error(f"Ошибка обновления сообщения о старте: {e}")

    # Запускаем таймер завершения
    asyncio.create_task(raffle_timer(callback_query.bot, raffle_id))
    await callback_query.answer("Розыгрыш начался!")


async def cancel_raffle_callback(callback_query: types.CallbackQuery):
    """Отменить розыгрыш (только создатель)"""
    raffle_id = callback_query.data.replace("cancel_raffle_", "")

    if raffle_id not in active_raffles:
        await callback_query.answer("Розыгрыш не найден")
        return

    raffle = active_raffles[raffle_id]

    # Проверяем, что это создатель
    if callback_query.from_user.id != raffle['creator_id']:
        await callback_query.answer("Только создатель может отменить розыгрыш")
        return

    if raffle["status"] == "finished":
        await callback_query.answer("Розыгрыш уже завершен")
        return

    # Останавливаем обновление вирусов если активно
    if raffle.get('virus_updater'):
        raffle['virus_updater'].cancel()
        raffle['virus_updater'] = None

    # Возвращаем средства создателю
    db: Optional[Session] = None
    try:
        db = SessionLocal()
        user = UserRepository.get_user_by_telegram_id(db, raffle['creator_id'])
        if user:
            user.coins += Decimal(raffle['amount'])
            TransactionRepository.create_transaction(
                db,
                from_user_id=None,  # От системы
                to_user_id=raffle['creator_id'],
                amount=raffle['amount'],
                description=f"Возврат средств за отмененный розыгрыш #{raffle_id}"
            )
            db.commit()
    except Exception as e:
        logger.error(f"Ошибка возврата средств: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()

    # Отменяем розыгрыш
    raffle['status'] = 'cancelled'

    cancellation_text = (
        f"{raffle['creator_name']} отменил розыгрыш\n\n"
        f"Сумма: {raffle['amount']:,} Монет\n"
        f"Участников было: {len(raffle['participants'])}\n\n"
        f"Средства возвращены создателю."
    )

    try:
        await callback_query.bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=cancellation_text
        )

        # Открепляем сообщение при отмене
        if raffle.get('is_pinned', False):
            await unpin_raffle_message(callback_query.bot, raffle['chat_id'], raffle['message_id'])

    except Exception as e:
        logger.error(f"Ошибка обновления сообщения об отмене: {e}")

    # Удаляем розыгрыш
    del active_raffles[raffle_id]
    await callback_query.answer("Розыгрыш отменен, средства возвращены")


async def raffle_timer(bot: Bot, raffle_id: str):
    """Таймер завершения розыгрыша"""
    if raffle_id not in active_raffles:
        return

    raffle = active_raffles[raffle_id]

    if not raffle.get('end_time'):
        return

    wait_seconds = (raffle['end_time'] - datetime.now()).total_seconds()

    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

    # Дополнительная проверка после сна
    if raffle_id not in active_raffles:
        return

    await finish_raffle(bot, raffle_id)


async def finish_raffle(bot: Bot, raffle_id: str):
    """Завершить розыгрыш и определить победителей"""
    if raffle_id not in active_raffles:
        return

    raffle = active_raffles[raffle_id]

    if raffle["status"] == "finished":
        return

    # Останавливаем обновление вирусов
    if raffle.get('virus_updater'):
        raffle['virus_updater'].cancel()
        raffle['virus_updater'] = None

    # Обновляем вирусы в последний раз
    updated_participants = update_virus_counts(raffle['participants'], raffle['start_time'])

    # ГАРАНТИРУЕМ уникальные значения вирусов
    updated_participants = ensure_unique_viruses(updated_participants)

    raffle['participants'] = updated_participants

    # Определяем победителей на основе вирусов
    raffle['winners'] = calculate_winners(raffle['participants'], raffle['amount'])
    raffle['status'] = 'finished'

    # Начисляем призы победителям
    db: Optional[Session] = None
    try:
        db = SessionLocal()
        for winner in raffle['winners']:
            user = UserRepository.get_user_by_telegram_id(db, winner['user_id'])
            if user:
                # Начисляем приз
                user.coins += Decimal(winner['prize'])

                # Записываем транзакцию
                TransactionRepository.create_transaction(
                    db,
                    from_user_id=None,  # От системы
                    to_user_id=winner['user_id'],
                    amount=winner['prize'],
                    description=f"Выигрыш в розыгрыше (место: {winner['position']})"
                )

        db.commit()

    except Exception as e:
        logger.error(f"Ошибка при начислении призов: {e}")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()

    # Формируем финальное сообщение (ОБЪЕДИНЕННОЕ)
    participants_text = format_participants_list(raffle['participants'])
    winners_text = format_winners_list(raffle['winners'])

    # ОБЪЕДИНЕННОЕ сообщение как в примере
    final_text = (
        f"Розыгрыш окончен\n\n"
        f"{participants_text}\n\n"
        f"{raffle['creator_name']} провёл розыгрыш\n\n"
        f"{winners_text}"
    )

    # Обновляем оригинальное сообщение
    try:
        await bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=final_text,
            reply_markup=create_final_message_no_keyboard()
        )

        # Открепляем сообщение при завершении если еще закреплено
        if raffle.get('is_pinned', False):
            try:
                await unpin_raffle_message(bot, raffle['chat_id'], raffle['message_id'])
                raffle['is_pinned'] = False
            except Exception as e:
                logger.warning(f"Не удалось открепить сообщение при завершении: {e}")
                raffle['is_pinned'] = False

    except Exception as e:
        logger.error(f"Ошибка обновления финального сообщения: {e}")

    # Удаляем розыгрыш из активных
    if raffle_id in active_raffles:
        del active_raffles[raffle_id]


# ==========================
# АДМИН КОМАНДЫ ДЛЯ ТЕСТИРОВАНИЯ
# ==========================

async def create_test_raffle(message: types.Message):
    """Создать тестовый розыгрыш (админ команда)"""
    if not await is_user_admin(message.from_user.id, message.chat.id, message.bot):
        await message.answer("Эта команда доступна только администраторам")
        return

    # Создаем тестовый розыгрыш
    db: Optional[Session] = None
    try:
        db = SessionLocal()
        user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
        if not user:
            await message.answer("Пользователь не найден")
            return

        # Добавляем тестовые средства
        test_amount = 100000
        user.coins += Decimal(test_amount)
        db.commit()

        raffle_id = generate_raffle_id()
        admin_name = message.from_user.username or message.from_user.first_name

        active_raffles[raffle_id] = {
            'creator_id': message.from_user.id,
            'creator_name': admin_name,
            'amount': test_amount,
            'participants': [],
            'status': 'pending',
            'chat_id': message.chat.id,
            'message_id': None,
            'start_time': None,
            'end_time': None,
            'winners': [],
            'is_active': False,
            'is_pinned': False,
            'virus_updater': None
        }

        raffle_text = (
            f"{admin_name} предлагает принять участие в розыгрыше {test_amount:,} монет, максимальное число участников - {MAX_PARTICIPANTS}\n\n"
            f"Участники: \n\n"
            f"Всего: 0"
        )

        keyboard = create_raffle_keyboard(raffle_id, is_creator=True)
        msg = await message.answer(raffle_text, reply_markup=keyboard)

        active_raffles[raffle_id]['message_id'] = msg.message_id

        # Закрепляем тестовое сообщение
        await pin_raffle_message(message.bot, message.chat.id, msg.message_id)
        active_raffles[raffle_id]['is_pinned'] = True

        await message.answer(f"✅ Создан тестовый розыгрыш на {test_amount:,} Монет\n"
                             f"ID: {raffle_id}\n"
                             f"На ваш баланс добавлено {test_amount:,} Монет для тестирования")

    except Exception as e:
        logger.error(f"Ошибка при создании тестового розыгрыша: {e}")
        await message.answer("Ошибка при создании тестового розыгрыша")
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


async def force_start_raffle(message: types.Message):
    """Принудительно стартовать розыгрыш без проверки минимального количества участников"""
    if not await is_user_admin(message.from_user.id, message.chat.id, message.bot):
        await message.answer("Эта команда доступна только администраторам")
        return

    # Ищем активный ожидающий розыгрыш в чате
    found_raffle = None
    for raffle_id, raffle in active_raffles.items():
        if raffle["chat_id"] == message.chat.id and raffle["status"] == "pending":
            found_raffle = raffle_id
            break

    if not found_raffle:
        await message.answer("В этом чате нет ожидающих розыгрышей")
        return

    raffle = active_raffles[found_raffle]

    # Проверяем, что это админ или создатель
    if message.from_user.id != raffle['creator_id'] and not await is_user_admin(message.from_user.id, message.chat.id,
                                                                                message.bot):
        await message.answer("Только создатель или администратор может стартовать розыгрыш")
        return

    # Создаем фейковый callback для запуска
    from aiogram.types import CallbackQuery
    fake_callback = types.CallbackQuery(
        id="force_start",
        from_user=message.from_user,
        chat_instance="force_start",
        message=message,
        data=f"start_raffle_{found_raffle}"
    )

    # Временно отключаем проверку минимального количества участников
    original_min_participants = MIN_PARTICIPANTS
    try:
        # Глобально меняем значение
        import handlers.raffle.raffle as raffle_module
        raffle_module.MIN_PARTICIPANTS = 1

        await start_raffle_callback(fake_callback)
        await message.answer("✅ Розыгрыш принудительно запущен (тестовый режим)")
    finally:
        # Восстанавливаем оригинальное значение
        raffle_module.MIN_PARTICIPANTS = original_min_participants


async def add_fake_users(message: types.Message):
    """Добавить тестовых участников в розыгрыш"""
    if not await is_user_admin(message.from_user.id, message.chat.id, message.bot):
        await message.answer("Эта команда доступна только администраторам")
        return

    # Ищем активный ожидающий розыгрыш в чате
    found_raffle = None
    for raffle_id, raffle in active_raffles.items():
        if raffle["chat_id"] == message.chat.id and raffle["status"] == "pending":
            found_raffle = raffle_id
            break

    if not found_raffle:
        await message.answer("В этом чате нет ожидающих розыгрышей")
        return

    raffle = active_raffles[found_raffle]

    # Определяем сколько нужно добавить участников
    needed_participants = MAX_PARTICIPANTS - len(raffle['participants'])
    if needed_participants <= 0:
        await message.answer(
            f"Уже максимальное количество участников: {len(raffle['participants'])}/{MAX_PARTICIPANTS}")
        return

    # Ограничиваем количество добавляемых участников
    add_count = min(needed_participants, 50)  # Добавляем максимум 50 за раз

    # Добавляем тестовых участников с 0 вирусов
    start_index = len(raffle['participants']) + 1
    for i in range(start_index, start_index + add_count):
        if len(raffle['participants']) >= MAX_PARTICIPANTS:
            break

        fake_user_id = -i  # Отрицательные ID для тестовых пользователей
        raffle['participants'].append({
            'user_id': fake_user_id,
            'username': f"Тестовый_Участник_{i}",
            'joined_at': datetime.now(),
            'virus_count': 0,  # ВСЕГДА 0 при добавлении
            'virus_speed': random.uniform(0.8, 1.2),
            'is_fake': True  # Флаг, что это тестовый пользователь
        })

    # Формируем текст участников
    participants_text = format_participants_list(raffle['participants'])

    # Обновляем сообщение
    updated_text = (
        f"{raffle['creator_name']} предлагает принять участие в розыгрыше {raffle['amount']:,} монет, максимальное число участников - {MAX_PARTICIPANTS}\n\n"
        f"Участники: \n"
        f"{participants_text}\n\n"
        f"Всего: {len(raffle['participants'])}"
    )

    try:
        # Определяем, какая клавиатура нужна
        if raffle["status"] == "pending":
            # Определяем, является ли текущий пользователь создателем
            is_creator = (message.from_user.id == raffle['creator_id'])
            keyboard = create_raffle_keyboard(found_raffle, is_creator=is_creator)
        else:
            keyboard = create_active_raffle_keyboard(found_raffle)

        await message.bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=updated_text,
            reply_markup=keyboard
        )

        # Проверяем, не достигли ли мы лимита для автостарта
        if len(raffle['participants']) >= MAX_PARTICIPANTS:
            await auto_start_raffle_if_full(message.bot, found_raffle)

        await message.answer(f"✅ Добавлено {add_count} тестовых участников\n"
                             f"Теперь участников: {len(raffle['participants'])}\n"
                             f"Лимит для автостарта: {MAX_PARTICIPANTS}")
    except Exception as e:
        logger.error(f"Ошибка обновления сообщения: {e}")
        await message.answer("Ошибка при добавлении тестовых участников")


async def clear_fake_users(message: types.Message):
    """Удалить тестовых участников из розыгрыша"""
    if not await is_user_admin(message.from_user.id, message.chat.id, message.bot):
        await message.answer("Эта команда доступна только администраторам")
        return

    # Ищем активный розыгрыш в чате
    found_raffle = None
    for raffle_id, raffle in active_raffles.items():
        if raffle["chat_id"] == message.chat.id and raffle["status"] in ["pending", "active"]:
            found_raffle = raffle_id
            break

    if not found_raffle:
        await message.answer("В этом чате нет активных розыгрышей")
        return

    raffle = active_raffles[found_raffle]

    # Удаляем тестовых участников
    original_count = len(raffle['participants'])
    raffle['participants'] = [p for p in raffle['participants'] if not p.get('is_fake', False)]
    removed_count = original_count - len(raffle['participants'])

    # Перенумеровываем базовые вирусы
    for i, participant in enumerate(raffle['participants']):
        participant['base_virus'] = i + 1
        if raffle["status"] == "pending":
            participant['virus_count'] = i + 1

    # Формируем текст участников
    participants_text = ""
    if raffle["status"] == "active" and raffle.get('start_time'):
        updated_participants = update_virus_counts(raffle['participants'], raffle['start_time'])
        raffle['participants'] = updated_participants
        participants_text = format_participants_list(updated_participants)
    else:
        participants_text = format_participants_list(raffle['participants'])

    # Обновляем сообщение
    if raffle["status"] == "pending":
        updated_text = (
            f"{raffle['creator_name']} предлагает принять участие в розыгрыше {raffle['amount']:,} монет, максимальное число участников - {MAX_PARTICIPANTS}\n\n"
            f"Участники: \n"
            f"{participants_text}\n\n"
            f"Всего: {len(raffle['participants'])}"
        )
    else:
        time_left = max(0, int((raffle['end_time'] - datetime.now()).total_seconds()))
        minutes = time_left // 60
        seconds = time_left % 60

        updated_text = (
            f"Розыгрыш начался\n\n"
            f"{participants_text}\n\n"
            f"Всего: {len(raffle['participants'])}\n"
            f"⏰ Осталось: {minutes:02d}:{seconds:02d}"
        )

    try:
        # Определяем, какая клавиатура нужна
        if raffle["status"] == "pending":
            # Определяем, является ли текущий пользователь создателем
            is_creator = (message.from_user.id == raffle['creator_id'])
            keyboard = create_raffle_keyboard(found_raffle, is_creator=is_creator)
        else:
            keyboard = create_active_raffle_keyboard(found_raffle)

        await message.bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=updated_text,
            reply_markup=keyboard
        )

        await message.answer(f"✅ Удалено {removed_count} тестовых участников\n"
                             f"Осталось участников: {len(raffle['participants'])}")
    except Exception as e:
        logger.error(f"Ошибка обновления сообщения: {e}")
        await message.answer("Ошибка при удалении тестовых участников")


async def test_raffle_complete(message: types.Message):
    """Тестовое завершение розыгрыша (админ команда)"""
    if not await is_user_admin(message.from_user.id, message.chat.id, message.bot):
        await message.answer("Эта команда доступна только администраторам")
        return

    # Ищем активный розыгрыш в чате
    found_raffle = None
    for raffle_id, raffle in active_raffles.items():
        if raffle["chat_id"] == message.chat.id and raffle["status"] == "active":
            found_raffle = raffle_id
            break

    if not found_raffle:
        await message.answer("В этом чате нет активных розыгрышей")
        return

    # Немедленно завершаем розыгрыш
    await finish_raffle(message.bot, found_raffle)
    await message.answer("✅ Розыгрыш завершен (тестовый режим)")


async def raffle_status(message: types.Message):
    """Показать статус всех активных розыгрышей"""
    if not await is_user_admin(message.from_user.id, message.chat.id, message.bot):
        return

    if not active_raffles:
        await message.answer("Активных розыгрышей нет")
        return

    status_text = "<b>Статус активных розыгрышей:</b>\n\n"
    for raffle_id, raffle in active_raffles.items():
        status_emoji = "🟢" if raffle["status"] == "active" else "🟡" if raffle["status"] == "pending" else "🔴"
        pinned_status = "📌" if raffle.get('is_pinned', False) else ""
        status_text += (
            f"{status_emoji} {pinned_status} <b>{raffle['creator_name']}</b>\n"
            f"Статус: {raffle['status']}\n"
            f"Сумма: {raffle['amount']:,} Монет\n"
            f"Участников: {len(raffle['participants'])}/{MAX_PARTICIPANTS}\n"
            f"Чат: {raffle['chat_id']}\n"
            f"ID: <code>{raffle_id}</code>\n\n"
        )

    await message.answer(status_text, parse_mode="HTML")


# ==========================
# КОМАНДЫ АДМИНИСТРАТОРОВ
# ==========================

async def cancel_raffle_command(message: types.Message):
    """Отмена розыгрыша через команду"""
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Ищем активный ожидающий розыгрыш созданный пользователем
    found_raffle = None
    for raffle_id, raffle in active_raffles.items():
        if (raffle["creator_id"] == user_id and
                raffle["chat_id"] == chat_id and
                raffle["status"] in ["pending", "active"]):  # Разрешаем отмену активных тоже
            found_raffle = raffle_id
            break

    if not found_raffle:
        await message.answer("❌ У вас нет активных розыгрышей в этом чате")
        return

    # Проверяем, что розыгрыш еще не завершен
    raffle = active_raffles[found_raffle]
    if raffle["status"] == "finished":
        await message.answer("❌ Этот розыгрыш уже завершен")
        return

    # Останавливаем обновление вирусов если активно
    if raffle.get('virus_updater'):
        raffle['virus_updater'].cancel()
        raffle['virus_updater'] = None

    # Возвращаем средства создателю
    db: Optional[Session] = None
    try:
        db = SessionLocal()
        user = UserRepository.get_user_by_telegram_id(db, raffle['creator_id'])
        if user:
            user.coins += Decimal(raffle['amount'])
            TransactionRepository.create_transaction(
                db,
                from_user_id=None,  # От системы
                to_user_id=raffle['creator_id'],
                amount=raffle['amount'],
                description=f"Возврат средств за отмененный розыгрыш #{found_raffle}"
            )
            db.commit()
    except Exception as e:
        logger.error(f"Ошибка возврата средств: {e}")
        if db:
            db.rollback()
        await message.answer("❌ Ошибка возврата средств")
        return
    finally:
        if db:
            db.close()

    # Отменяем розыгрыш
    raffle['status'] = 'cancelled'

    cancellation_text = (
        f"{raffle['creator_name']} отменил розыгрыш\n\n"
        f"Сумма: {raffle['amount']:,} Монет\n"
        f"Участников было: {len(raffle['participants'])}\n\n"
        f"Средства возвращены создателю."
    )

    try:
        await message.bot.edit_message_text(
            chat_id=raffle['chat_id'],
            message_id=raffle['message_id'],
            text=cancellation_text
        )

        # Открепляем сообщение при отмене
        if raffle.get('is_pinned', False):
            await unpin_raffle_message(message.bot, raffle['chat_id'], raffle['message_id'])

    except Exception as e:
        logger.error(f"Ошибка обновления сообщения об отмене: {e}")

    # Удаляем розыгрыш
    del active_raffles[found_raffle]
    await message.answer("✅ Розыгрыш отменен, средства возвращены")


async def force_finish_raffle(message: types.Message):
    """Принудительное завершение розыгрыша (для админов)"""
    if not await is_user_admin(message.from_user.id, message.chat.id, message.bot):
        await message.answer("Эта команда доступна только администраторам")
        return

    # Ищем активный розыгрыш в чате
    found_raffle = None
    for raffle_id, raffle in active_raffles.items():
        if raffle["chat_id"] == message.chat.id and raffle["status"] == "active":
            found_raffle = raffle_id
            break

    if not found_raffle:
        await message.answer("В этом чате нет активных розыгрышей")
        return

    # Завершаем розыгрыш
    await finish_raffle(message.bot, found_raffle)
    await message.answer("Розыгрыш принудительно завершен")


# ==========================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ==========================

def register_raffle_handlers(dp: Dispatcher):
    """Регистрация обработчиков розыгрышей"""

    # Правила розыгрыша
    dp.register_message_handler(
        raffle_rules,
        lambda m: m.text and m.text.lower() in [
            "розыгрыш", "раффл", "!розыгрыш", "!раффл",
            "розыгрыши", "раффлы", "/розыгрыш", "/раффл",
            "правила розыгрыша", "правила раффла"
        ],
        state="*"
    )

    # Создание розыгрыша (только для админов)
    dp.register_message_handler(
        raffle_start,
        lambda m: m.text and (
                m.text.lower().startswith('!розыгрыш ') or
                m.text.lower().startswith('!раффл ') or
                m.text.lower().startswith('розыгрыш ') or
                m.text.lower().startswith('раффл ')
        ),
        state=None
    )

    # Колбэки для участия
    dp.register_callback_query_handler(
        join_raffle_callback,
        lambda c: c.data.startswith("join_raffle_"),
        state="*"
    )

    dp.register_callback_query_handler(
        start_raffle_callback,
        lambda c: c.data.startswith("start_raffle_"),
        state="*"
    )

    dp.register_callback_query_handler(
        cancel_raffle_callback,
        lambda c: c.data.startswith("cancel_raffle_"),
        state="*"
    )

    # Отмена розыгрыша через команду (для создателя)
    dp.register_message_handler(
        cancel_raffle_command,
        lambda m: m.text and any(cmd in m.text.lower() for cmd in [
            "отмена розыгрыша",
            "отменить розыгрыш",
            "!отмена",
            "/отмена",
            "отмена",
            "отменить",
            "cancel raffle",
            "отмена раффла",
            "отменить раффл"
        ]),
        state="*"
    )

    # Принудительное завершение (админы)
    dp.register_message_handler(
        force_finish_raffle,
        commands=["завершить_розыгрыш", "force_finish"],
        state="*"
    )

    # Админ команды для тестирования
    dp.register_message_handler(
        create_test_raffle,
        commands=["test_raffle", "тест_розыгрыш"],
        state="*"
    )

    dp.register_message_handler(
        force_start_raffle,
        commands=["force_start", "принудительно_старт"],
        state="*"
    )

    dp.register_message_handler(
        add_fake_users,
        commands=["add_fake_users", "добавить_тест_участников"],
        state="*"
    )

    dp.register_message_handler(
        clear_fake_users,
        commands=["clear_fake_users", "удалить_тест_участников"],
        state="*"
    )

    dp.register_message_handler(
        test_raffle_complete,
        commands=["test_complete", "тест_завершить"],
        state="*"
    )

    dp.register_message_handler(
        raffle_status,
        commands=["raffle_status", "статус_розыгрышей"],
        state="*"
    )

    logger.info("✅ Обработчики розыгрышей зарегистрированы")