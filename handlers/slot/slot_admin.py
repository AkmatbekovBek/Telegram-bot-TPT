import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Command
from database import SessionLocal

logger = logging.getLogger(__name__)


class SlotAdminHandler:
    """Административные команды для игры в слот"""

    async def slot_stats_command(self, message: types.Message):
        """Команда !slotstats - статистика по игре"""
        if not await self._check_admin(message):
            await message.reply(" Только администраторы могут просматривать статистику")
            return

        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Статистика по чатам
            chat_stats = db.execute(
                text("""
                     SELECT COUNT(*)                                   as total_chats,
                            SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active_chats
                     FROM chats
                     WHERE chat_type IN ('group', 'supergroup')
                     """)
            ).fetchone()

            stats_text = (
                f"📊 <b>Статистика игры 'Слот'</b>\n\n"
                f"<b>Чаты:</b>\n"
                f"• Всего: {chat_stats[0] or 0}\n"
                f"• Активных: {chat_stats[1] or 0}\n\n"
                f"<b>Использование:</b>\n"
                f"Команда: <code>!слот [ставка]</code>\n"
                f"Пример: <code>!слот 1000</code>\n\n"
                f"<b>Управление:</b>\n"
                f"<code>!slon</code> - включить в чате\n"
                f"<code>!sloff</code> - выключить в чате"
            )

            await message.reply(stats_text, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Error getting slot stats: {e}")
            await message.reply(" Ошибка при получении статистики")
        finally:
            db.close()

    async def _check_admin(self, message: types.Message) -> bool:
        """Проверяет, является ли пользователь администратором бота"""
        from handlers.admin.admin_helpers import check_admin_async
        return await check_admin_async(message)


def register_slot_admin_handlers(dp: Dispatcher):
    """Регистрация админ-обработчиков"""
    handler = SlotAdminHandler()

    dp.register_message_handler(
        handler.slot_stats_command,
        commands=['slotstats'],
        prefix='!',
        state="*"
    )

    logger.info("✅ Админ-обработчики игры 'Слот' зарегистрированы")