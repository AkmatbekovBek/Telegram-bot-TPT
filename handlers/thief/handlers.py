import re
import random
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple

from aiogram import types

from database import db_session
from database.crud import ThiefRepository, UserRepository, PoliceRepository
from handlers.thief.service import ThiefService

logger = logging.getLogger(__name__)


def normalize_cmd(text: str) -> str:
    """Нормализует команду, убирает лишние пробелы и приводит к нижнему регистру"""
    if not text or not text.strip():
        return ""

    text = re.sub(r"^[/!]", "", text)
    text = re.sub(r"@[\w_]+$", "", text)

    parts = text.strip().lower().split()
    return parts[0] if parts else ""


def is_rob_cmd(msg: types.Message):
    """Проверяет, является ли сообщение командой кражи !граб или -сумма"""
    if not msg.text or not msg.text.strip():
        return False

    text = msg.text.strip()

    # Проверяем оба варианта
    return text.startswith('!граб') or (text.startswith('-') and text[1:].replace(',', '').replace(' ', '').isdigit())


def is_thief_stats_cmd(msg: types.Message):
    """Проверяет команды статистики краж"""
    if not msg.text or not msg.text.strip():
        return False

    normalized_cmd = normalize_cmd(msg.text)
    return normalized_cmd in ["кражи", "thief_stats", "статистика"]


async def rob_user(message: types.Message):
    """Основной обработчик кражи !граб и -сумма"""
    try:
        thief = message.from_user
        if not ThiefService.check_thief_permission(thief.id):
            await message.reply("🎭 Только <b>Воры в законе</b> могут красть!", parse_mode="HTML")
            return

        if not message.reply_to_message:
            await message.reply("❗ Ответь на сообщение жертвы.")
            return

        victim_user = message.reply_to_message.from_user
        if not victim_user:
            await message.reply("❓ Не удалось определить пользователя.")
            return

        victim_id = victim_user.id
        bot = await message.bot.get_me()

        if victim_id == bot.id:
            await message.reply("🤖 У бота нет денег.")
            return

        if thief.id == victim_id:
            await message.reply("🚫 Нельзя грабить себя")
            return

        # Проверяем, не является ли жертва вором
        if ThiefService.check_thief_permission(victim_id):
            await message.reply(f"🎭 Нельзя грабить другого вора в законе!")
            return

        # Парсим сумму из сообщения
        text = message.text.strip()

        # Если это команда с дефисом (например, -1000)
        if text.startswith('-') and text[1:].replace(',', '').replace(' ', '').isdigit():
            # Убираем минус и парсим сумму
            amount_text = text[1:].strip()
            try:
                steal_amount = int(amount_text.replace(',', '').replace(' ', ''))
            except ValueError:
                await message.reply(" Укажите корректную сумму!")
                return
        # Если это команда !граб
        elif text.lower().startswith('!граб'):
            amount_text = text[5:].strip()
            if not amount_text:
                await message.reply(" Укажите сумму для кражи: !граб [сумма] или просто -сумма (например, -1000)")
                return
            try:
                steal_amount = int(amount_text.replace(',', '').replace(' ', ''))
            except ValueError:
                await message.reply(" Укажите корректную сумму!")
                return
        else:
            await message.reply(" Используйте команду: !граб [сумма] или просто -сумма (например, -1000)")
            return

        # Проверяем сумму
        if steal_amount <= 0:
            await message.reply(" Сумма должна быть положительной!")
            return

        # Получаем баланс вора
        thief_balance = ThiefService.get_user_balance(thief.id)

        # Если у вора меньше 20 миллионов, он не может красть
        if thief_balance < 20_000_000:
            await message.reply(f" У вас {thief_balance:,} som. Для кражи нужно иметь минимум 20 миллионов som!")
            return

        # Если сумма больше 20 миллионов
        if steal_amount > 20_000_000:
            await message.reply(" Нельзя красть больше 20 миллионов за раз!")
            return

        if steal_amount < 1:
            await message.reply(" Минимальная сумма для кражи: 5 000 som!")
            return

        # Проверяем кулдаун
        can_steal, cooldown_info = ThiefService.check_steal_cooldown(thief.id)
        if not can_steal:
            await message.reply(f"⏳ До следующей кражи: {cooldown_info}")
            return

        # Выполняем кражу
        success, msg_text, stolen_amount = ThiefService.rob_user(thief.id, victim_id, steal_amount)

        if success:
            # Определяем имена
            thief_name = thief.username or thief.first_name or "Неизвестный вор"
            victim_name = victim_user.username or victim_user.first_name or "Неизвестная жертва"

            await message.reply(
                f"👤 {thief_name} незаметно украл у {victim_name} 💸 +{stolen_amount:,}"
            )
        else:
            await message.reply(f" {msg_text}")

    except Exception as e:
        logger.error(f"Error in rob_user: {e}")
        await message.reply("🚨 Внутренняя ошибка кражи.")


async def thief_stats(message: types.Message):
    """Показывает статистику по кражам"""
    try:
        user_id = message.from_user.id

        if not ThiefService.check_thief_permission(user_id):
            await message.reply("🎭 Только <b>Воры в законе</b> могут просматривать статистику!", parse_mode="HTML")
            return

        stats = ThiefService.get_thief_stats(user_id)

        result = f"📊 <b>Статистика кражей {message.from_user.full_name}</b>\n\n"
        result += f"✅ Успешных краж: {stats['successful_steals']}\n"
        result += f" Неудачных попыток: {stats['failed_steals']}\n"
        result += f"💰 Всего украдено: {stats['total_stolen']:,} som\n\n"

        if stats['last_steal_time']:
            last_steal = stats['last_steal_time'].strftime("%d.%m.%Y %H:%M")
            result += f"⏰ Последняя кража: {last_steal}\n"
        else:
            result += "⏰ Последняя кража: никогда\n"

        # Проверяем кулдаун
        can_steal, cooldown_info = ThiefService.check_steal_cooldown(user_id)
        if not can_steal and cooldown_info:
            result += f"⏳ До следующей кражи: {cooldown_info}\n"

        # Добавляем информацию о минимальном балансе для кражи
        balance = ThiefService.get_user_balance(user_id)
        result += f"💰 Ваш баланс: {balance:,} som\n"

        if balance < 20_000_000:
            result += f"⚠️ Для кражи нужно: 20,000,000 som (не хватает {20_000_000 - balance:,})"
        else:
            result += f"✅ Можете красть до 20,000,000 som"

        result += f"\n\n🎯 <i>Удачи в следующих кражах!</i>"

        await message.reply(result, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in thief_stats: {e}")
        await message.reply(" Ошибка при получении статистики.")


def register_thief_handlers(dp):
    """Регистрация обработчиков для вора"""
    dp.register_message_handler(rob_user, is_rob_cmd, state="*")
    dp.register_message_handler(thief_stats, is_thief_stats_cmd, state="*")
    logger.info("✅ Обработчики 'кража' зарегистрированы")