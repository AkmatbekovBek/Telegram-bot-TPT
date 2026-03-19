import logging
from datetime import datetime, timedelta
import asyncio
from .status_repository import StatusRepository
from .texts_simple import donate_texts
from .config import SUPPORT_USERNAME
from database.crud import UserRepository

logger = logging.getLogger(__name__)


class DonateScheduler:
    """Планировщик для автоматических задач системы статусов"""

    def __init__(self, bot):
        self.bot = bot
        self.is_running = False
        self.status_repo = StatusRepository()
        logger.info("💰 Инициализация DonateScheduler (система статусов)")

    async def start_scheduler(self):
        """Запускает планировщик"""
        self.is_running = True
        logger.info("🚀 Запуск планировщика системы статусов")

        # Запускаем сразу первые проверки
        await self.deactivate_expired_statuses()
        await self.check_expiring_soon()
        await self.award_automatic_bonuses()  # Немедленно начисляем бонусы

        # Запускаем цикл проверок
        while self.is_running:
            try:
                current_time = datetime.now()
                current_hour = current_time.hour

                # Проверяем каждый час
                await asyncio.sleep(3600)

                # Каждый час проверяем истекшие статусы
                await self.deactivate_expired_statuses()

                # В 00:00 и 12:00 проверяем статусы, которые скоро истекут
                if current_hour == 0 or current_hour == 12:
                    await self.check_expiring_soon()

                # В 00:00 начисляем ежедневные бонусы (как в ТЗ)
                if current_hour == 0:
                    await self.award_automatic_bonuses()

            except Exception as e:
                logger.error(f" Ошибка в планировщике: {e}")
                await asyncio.sleep(60)  # Подождать минуту при ошибке

    async def deactivate_expired_statuses(self):
        """Деактивирует истекшие статусы"""
        try:
            logger.info("🧹 Проверка истекших статусов...")

            deactivated_count = self.status_repo.deactivate_expired_statuses()

            if deactivated_count > 0:
                logger.info(f"✅ Деактивировано {deactivated_count} истекших статусов")

                # Получаем список деактивированных пользователей для уведомлений
                expired_statuses = self.status_repo.get_expired_statuses()

                for status_info in expired_statuses:
                    try:
                        await self.send_status_expired_notification(status_info)
                    except Exception as e:
                        logger.error(f" Ошибка отправки уведомления пользователю {status_info['user_id']}: {e}")

        except Exception as e:
            logger.error(f" Ошибка деактивации истекших статусов: {e}")

    async def award_automatic_bonuses(self):
        """Автоматически начисляет бонусы всем пользователям каждые 24 часа"""
        try:
            logger.info("🎁 Начало автоматического начисления бонусов...")

            # Получаем всех пользователей, которым нужно начислить бонус
            user_ids = self.status_repo.get_users_for_automatic_bonus()

            if not user_ids:
                logger.info("ℹ️ Нет пользователей для начисления бонусов")
                return

            total_bonuses = 0
            total_amount = 0

            for user_id in user_ids:
                try:
                    # Начисляем бонус
                    success, message, bonus_amount = self.status_repo.award_automatic_bonus(user_id)

                    if success:
                        total_bonuses += 1
                        total_amount += bonus_amount

                        # Отправляем уведомление пользователю
                        await self.send_bonus_notification(user_id, bonus_amount)

                        logger.info(f"✅ Начислен бонус пользователю {user_id}: {bonus_amount:,} Монет")
                    else:
                        logger.warning(f"⚠️ Не удалось начислить бонус пользователю {user_id}: {message}")

                except Exception as e:
                    logger.error(f" Ошибка начисления бонуса пользователю {user_id}: {e}")
                    continue

            logger.info(f"✅ Автоматическое начисление завершено: {total_bonuses} пользователей, {total_amount:,} Монет")

        except Exception as e:
            logger.error(f" Ошибка автоматического начисления бонусов: {e}")

    async def check_expiring_soon(self):
        """Проверяет статусы, которые скоро истекут (завтра)"""
        try:
            logger.info("🔔 Проверка статусов, которые скоро истекут...")

            # Получаем статусы, которые истекают завтра
            expiring_statuses = self.status_repo.get_expiring_statuses(days_before=1)

            notification_count = 0
            for status_info in expiring_statuses:
                try:
                    if await self.send_expiration_notification(status_info):
                        notification_count += 1
                except Exception as e:
                    logger.error(
                        f" Ошибка отправки уведомления для статуса пользователя {status_info['user_id']}: {e}")

            if notification_count > 0:
                logger.info(f"📢 Отправлено {notification_count} уведомлений об истечении")

        except Exception as e:
            logger.error(f" Ошибка проверки истекающих статусов: {e}")

    async def send_expiration_notification(self, status_info: dict):
        """Отправляет уведомление об истечении статуса"""
        try:
            user_id = status_info['user_id']

            message = donate_texts.get("status_expiring").format(
                status_name=status_info['status_name'].title(),
                support_username=SUPPORT_USERNAME
            )

            await self.bot.send_message(user_id, message, parse_mode="HTML")
            logger.info(f"📢 Отправлено уведомление об истечении пользователю {user_id}")
            return True

        except Exception as e:
            logger.error(f" Ошибка отправки уведомления пользователю {status_info['user_id']}: {e}")
            return False

    async def send_status_expired_notification(self, status_info: dict):
        """Отправляет уведомление об истечении статуса"""
        try:
            user_id = status_info['user_id']

            message = donate_texts.get("status_expired").format(
                status_name=status_info['status_name'].title(),
                support_username=SUPPORT_USERNAME
            )

            await self.bot.send_message(user_id, message, parse_mode="HTML")
            logger.info(f"📢 Отправлено уведомление об истечении статуса пользователю {user_id}")
            return True

        except Exception as e:
            logger.error(f" Ошибка отправки уведомления пользователю {status_info['user_id']}: {e}")
            return False

    async def send_bonus_notification(self, user_id: int, bonus_amount: int):
        """Отправляет уведомление о начислении бонуса"""
        try:
            # Получаем информацию о статусе пользователя
            status = self.status_repo.get_user_active_status(user_id)
            status_name = status.get('status_name').title() if status else "Обычный"
            status_icon = status.get('status_icon') if status else "🐾"

            message = (
                f"<b>Ежедневный бонус начислен!</b>\n"
                f"<b>Ваш статус:</b> {status_name}{status_icon}\n"
                f"<b>Сумма бонуса:</b> {bonus_amount:,} Монет\n\n"
                f"<b>Следующий бонус через 24 часа</b>"
            )

            await self.bot.send_message(user_id, message, parse_mode="HTML")
            return True

        except Exception as e:
            logger.error(f" Ошибка отправки уведомления о бонусе пользователю {user_id}: {e}")
            return False

    async def stop_scheduler(self):
        """Останавливает планировщик"""
        self.is_running = False
        logger.info("🛑 Остановка планировщика системы статусов")