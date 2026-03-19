import logging
from aiogram import types, Dispatcher
from sqlalchemy import text
from database import SessionLocal

logger = logging.getLogger(__name__)


class BasketAdminHandler:
    """Административные команды для игры 'Basket Win'"""

    async def basket_stats_command(self, message: types.Message):
        """Команда !basstats - статистика по игре"""
        if not await self._check_admin(message):
            await message.reply(" Только администраторы могут просматривать статистику")
            return

        db = SessionLocal()
        try:
            # Статистика по чатам
            chat_stats = db.execute(
                text("""
                     SELECT COUNT(*) as total_chats,
                            SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active_chats
                     FROM chats
                     WHERE chat_type IN ('group', 'supergroup')
                     """)
            ).fetchone()

            stats_text = (
                f"📊 <b>Статистика игры 'Basket Win'</b>\n\n"
                f"<b>Чаты:</b>\n"
                f"• Всего: {chat_stats[0] or 0}\n"
                f"• Активных: {chat_stats[1] or 0}\n\n"
                f"<b>Использование:</b>\n"
                f"Команда: <code>бас [ставка]</code>\n"
                f"Пример: <code>бас 50</code>\n\n"
                f"<b>Управление:</b>\n"
                f"<code>!bason</code> - включить в чате\n"
                f"<code>!basoff</code> - выключить в чате\n\n"
                f"<b>Проверка баланса:</b>\n"
                f"<code>баланс</code> или <code>б</code>"
            )

            await message.reply(stats_text, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Error getting basket stats: {e}")
            await message.reply(" Ошибка при получении статистики")
        finally:
            db.close()

    async def _check_admin(self, message: types.Message) -> bool:
        """Проверяет, является ли пользователь администратором бота"""
        from handlers.admin.admin_helpers import check_admin_async
        return await check_admin_async(message)


def register_basket_admin_handlers(dp: Dispatcher):
    """Регистрация админ-обработчиков"""
    handler = BasketAdminHandler()

    dp.register_message_handler(
        handler.basket_stats_command,
        commands=['basstats'],
        prefix='!',
        state="*"
    )

    logger.info("✅ Админ-обработчики игры 'Basket Win' зарегистрированы")