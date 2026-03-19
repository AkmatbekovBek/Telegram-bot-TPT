import logging
from datetime import datetime
from urllib.parse import quote

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import desc

from database import SessionLocal
from database.clan_models import Clan, ClanJoinRequest
from .clan_balance_updater import ClanBalanceUpdater
from .clan_database import ClanDatabase
from .clan_keyboards import (
    get_main_clan_keyboard, get_clan_profile_keyboard, get_clan_management_keyboard,
    get_clan_list_keyboard, get_clan_members_keyboard, get_invitations_keyboard,
    get_invitation_actions_keyboard, get_join_requests_keyboard, get_request_actions_keyboard,
    get_confirmation_keyboard, get_back_button, clan_cb, get_user_requests_keyboard
)
from .clan_utils import format_clan_info, format_member_info, format_clan_top

logger = logging.getLogger(__name__)

# Константы
CLANS_PER_PAGE = 10
MEMBERS_PER_PAGE = 10
REQUESTS_PER_PAGE = 10


class ClanHandler:
    """Обработчик системы кланов"""

    def __init__(self, bot_username: str = None):
        self.bot_username = bot_username

    def _get_db_session(self):
        from database import SessionLocal
        return SessionLocal()

    def generate_invite_link(self, clan_id: int) -> str:
        """Генерация пригласительной ссылки"""
        if self.bot_username:
            return f"https://t.me/{self.bot_username}?start=clan_invite_{clan_id}"
        return f"clan_invite_{clan_id}"

    def parse_invite_token(self, text: str) -> int:
        """Парсинг токена приглашения"""
        if text.startswith('clan_invite_'):
            try:
                return int(text.replace('clan_invite_', ''))
            except ValueError:
                return 0
        return 0

    # === Команды ===

    async def clans_command(self, message: types.Message):
        """Команда /clans - главное меню кланов"""
        user_id = message.from_user.id

        welcome_text = (
            "🏰 <b>Система кланов</b>\n\n"
            "Здесь вы можете создавать кланы, приглашать друзей "
            "и соревноваться с другими игроками!\n\n"
            "<b>Доступные действия:</b>\n"
            "• Создать свой клан\n"
            "• Присоединиться к существующему\n"
            "• Управлять своим кланом\n"
            "• Смотреть топ кланов\n"
            "• И многое другое!"
        )

        await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_clan_keyboard())

    async def clan_start_handler(self, message: types.Message):
        """Обработчик start с пригласительной ссылкой"""
        args = message.get_args()
        if not args:
            return

        clan_id = self.parse_invite_token(args)
        if clan_id == 0:
            return

        db = self._get_db_session()
        clan_db = ClanDatabase(db)

        try:
            clan = clan_db.get_clan_by_id(clan_id)
            if not clan:
                await message.answer(" Приглашение недействительно: клан не найден")
                return

            user_id = message.from_user.id

            # Проверяем, не состоит ли уже в клане
            user_clan = clan_db.get_user_clan(user_id)
            if user_clan:
                if user_clan.id == clan_id:
                    await message.answer(f"✅ Вы уже состоите в этом клане: {clan.name}")
                else:
                    await message.answer(f" Вы уже состоите в другом клане: {user_clan.name}")
                return

            # Создаем приглашение
            success = clan_db.create_invitation(
                clan_id=clan_id,
                from_user_id=0,  # 0 = приглашение по ссылке
                to_user_id=user_id
            )

            if success:
                await message.answer(
                    f"📨 <b>Приглашение в клан получено!</b>\n\n"
                    f"🏰 <b>Клан:</b> {clan.name} [{clan.tag}]\n"
                    f"📝 <b>Описание:</b> {clan.description[:100] if clan.description else 'Нет описания'}...\n\n"
                    f"Используйте команду /clans → 'Мои приглашения' для принятия приглашения.",
                    parse_mode="HTML",
                    reply_markup=get_main_clan_keyboard()
                )
            else:
                await message.answer(
                    " Не удалось создать приглашение. Возможно, приглашение уже отправлено.",
                    reply_markup=get_main_clan_keyboard()
                )

        finally:
            db.close()

    # === Callback обработчики ===

    async def clan_callback_handler(self, callback: CallbackQuery, callback_data: dict, state: FSMContext):
        """Обработчик callback'ов кланов"""
        action = callback_data['action']
        clan_id = int(callback_data['clan_id'])
        user_id = int(callback_data['user_id']) or callback.from_user.id
        request_id = int(callback_data['request_id'])
        page = int(callback_data['page'])

        db = self._get_db_session()
        from .clan_database import ClanDatabase
        clan_db = ClanDatabase(db)

        try:
            # Главное меню
            if action == 'main':
                await self._show_main_menu(callback)

            # Создание клана
            elif action == 'create':
                await self._start_clan_creation(callback, state)

            # Список кланов
            elif action == 'list':
                await self._show_clan_list(callback, clan_db, page)

            # Топ кланов
            elif action == 'top':
                await self._show_clan_top(callback, clan_db, page)

            # Поиск клана
            elif action == 'search':
                await self._start_clan_search(callback, state)

            # Мои приглашения
            elif action == 'invitations':
                await self._show_invitations(callback, clan_db, user_id)

            # Мои заявки
            elif action == 'my_requests':
                await self._show_my_requests(callback, clan_db, user_id)

            # Отозвать заявку
            elif action == 'withdraw_req':
                await self._handle_withdraw_request(callback, clan_db, request_id, user_id)

            # Мой клан
            elif action == 'my':
                await self._show_my_clan(callback, clan_db, user_id)

            # Просмотр клана
            elif action == 'view':
                await self._view_clan(callback, clan_db, clan_id, user_id)

            # Профиль клана
            elif action == 'profile':
                await self._show_clan_profile(callback, clan_db, clan_id, user_id)

            # Участники клана
            elif action == 'members':
                await self._show_clan_members(callback, clan_db, clan_id, user_id, page)

            # Управление кланом
            elif action == 'manage':
                await self._show_clan_management(callback, clan_db, clan_id, user_id)

            # Заявки на вступление
            elif action == 'requests':
                await self._show_join_requests(callback, clan_db, clan_id, user_id, page)

            # Подать заявку
            elif action == 'apply':
                await self._apply_to_clan(callback, clan_db, clan_id, user_id, state)

            # Принять/отклонить приглашение
            elif action in ['accept_invite', 'reject_invite']:
                await self._handle_invitation(callback, clan_db, action, request_id)

            # Просмотр приглашения
            elif action == 'view_invite':
                await self._view_invitation(callback, clan_db, request_id, clan_id)

            # Просмотр заявки
            elif action == 'view_request':
                await self._view_join_request(callback, clan_db, request_id, clan_id, user_id)

            # Принять/отклонить заявку
            elif action in ['approve_request', 'reject_request']:
                await self._handle_join_request(callback, clan_db, action, request_id, user_id, clan_id)

            # Передать лидерство
            elif action == 'transfer_leadership':
                await self._start_transfer_leadership(callback, clan_db, clan_id, user_id, state)

            # Покинуть клан
            elif action == 'leave':
                await self._confirm_leave_clan(callback, clan_db, clan_id, user_id)

            # Распустить клан
            elif action == 'disband':
                await self._confirm_disband_clan(callback, clan_db, clan_id, user_id)

            # Пригласить участника
            elif action == 'invite':
                await self._show_invite_options(callback, clan_db, clan_id, user_id)

            # Удалить участника
            elif action == 'remove_member':
                await self._start_remove_member(callback, clan_db, clan_id, user_id, state)

            # Назначить заместителя
            elif action == 'set_deputy':
                await self._start_set_deputy(callback, clan_db, clan_id, user_id, state)

            # Изменить описание
            elif action == 'edit_desc':
                await self._start_edit_description(callback, clan_db, clan_id, user_id, state)

            # Изменить аватар
            elif action == 'edit_avatar':
                await self._start_edit_avatar(callback, clan_db, clan_id, user_id, state)

            # Получить ссылку приглашения
            elif action == 'get_invite_link':
                await self._show_invite_link(callback, clan_db, clan_id, user_id)

            # Подтверждения действий
            elif action.startswith('confirm_'):
                confirm_action = action.replace('confirm_', '')
                await self._handle_confirmation(callback, clan_db, confirm_action, clan_id, user_id, request_id)

            elif action == 'stats':
                await self._show_clan_stats(callback, clan_db, clan_id, user_id)

            elif action == 'settings':
                await self._show_clan_settings(callback, clan_db, clan_id, user_id)

            elif action == 'set_join_auto':
                await self._set_join_type_auto(callback, clan_db, clan_id, user_id)

            elif action == 'set_join_manual':
                await self._set_join_type_manual(callback, clan_db, clan_id, user_id)

            elif action == 'toggle_auto_accept':
                await self._toggle_auto_accept(callback, clan_db, clan_id, user_id)

            elif action in ['approve_request_from_notification', 'reject_request_from_notification']:
                is_approve = (action == 'approve_request_from_notification')
                await self._handle_join_request_from_notification(
                    callback, clan_db, is_approve, request_id, user_id, clan_id
                )

            # Отмена действия
            elif action == 'cancel':
                await callback.answer(" Действие отменено")
                clan = clan_db.get_clan_by_id(clan_id)
                if clan:
                    await self._show_clan_profile(callback, clan_db, clan_id, user_id)
                else:
                    await self._show_main_menu(callback)

            await callback.answer()

        except Exception as e:
            logger.error(f"Error in clan callback: {e}", exc_info=True)
            await callback.answer(" Произошла ошибка", show_alert=True)
        finally:
            db.close()

    # === Новые методы для улучшений ===
    async def _show_my_requests(self, callback: CallbackQuery, clan_db: ClanDatabase, user_id: int):
        """Показать мои заявки на вступление"""
        requests = clan_db.get_user_pending_requests(user_id)

        if not requests:
            await callback.message.edit_text(
                f"📝 <b>Мои заявки</b>\n\n"
                "У вас нет активных заявок на вступление в кланы.",
                parse_mode="HTML",
                reply_markup=get_back_button('main')
            )
            return

        requests_text = f"📝 <b>Мои заявки ({len(requests)})</b>\n\n"
        requests_text += "Вы можете отозвать заявку, нажав на кнопку ниже."

        await callback.message.edit_text(
            requests_text,
            parse_mode="HTML",
            reply_markup=get_user_requests_keyboard(requests)
        )

    async def _handle_withdraw_request(self, callback: CallbackQuery, clan_db: ClanDatabase, request_id: int, user_id: int):
        """Обработка отзыва заявки"""
        success = clan_db.delete_join_request(request_id, user_id)

        if success:
            await callback.answer("✅ Заявка отозвана", show_alert=True)
            # Обновляем список
            await self._show_my_requests(callback, clan_db, user_id)
        else:
            await callback.answer("❌ Не удалось отозвать заявку (возможно, она уже обработана)", show_alert=True)
            await self._show_my_requests(callback, clan_db, user_id)

    async def _show_invite_options(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Показать опции приглашения"""
        clan = clan_db.get_clan_by_id(clan_id)
        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🔗 Пригласительная ссылка", callback_data=clan_cb.new(
                action='get_invite_link', clan_id=clan_id, user_id=user_id, request_id=0, page=0
            )),
            InlineKeyboardButton("📨 Пригласить по ID", callback_data=clan_cb.new(
                action='invite_by_id', clan_id=clan_id, user_id=user_id, request_id=0, page=0
            ))
        )
        keyboard.add(
            InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
                action='manage', clan_id=clan_id, user_id=user_id, request_id=0, page=0
            ))
        )

        await callback.message.edit_text(
            f"📨 <b>Пригласить в клан {clan.name}</b>\n\n"
            "Выберите способ приглашения:",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    async def _show_invite_link(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Показать пригласительную ссылку"""
        clan = clan_db.get_clan_by_id(clan_id)
        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            return

        invite_link = self.generate_invite_link(clan_id)

        await callback.message.edit_text(
            f"🔗 <b>Пригласительная ссылка для клана {clan.name}</b>\n\n"
            f"<code>{invite_link}</code>\n\n"
            "Отправьте эту ссылку друзьям, чтобы они могли присоединиться к вашему клану.",
            parse_mode="HTML",
            reply_markup=get_back_button('invite', clan_id)
        )

    async def _start_edit_description(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int,
                                      state: FSMContext):
        """Начать изменение описания"""
        clan = clan_db.get_clan_by_id(clan_id)
        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)
        if user_role not in ['leader', 'deputy']:
            await callback.answer(" У вас нет прав для изменения описания", show_alert=True)
            return

        await state.set_state("clan_edit_description")
        await state.update_data(clan_id=clan_id)

        await callback.message.edit_text(
            f"✏️ <b>Изменение описания клана {clan.name}</b>\n\n"
            f"Текущее описание:\n{clan.description or 'Нет описания'}\n\n"
            "Введите новое описание (до 500 символов):",
            parse_mode="HTML",
            reply_markup=get_back_button('manage', clan_id)
        )

    async def _start_edit_avatar(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int,
                                 state: FSMContext):
        """Начать изменение аватара"""
        clan = clan_db.get_clan_by_id(clan_id)
        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)
        if user_role not in ['leader', 'deputy']:
            await callback.answer(" У вас нет прав для изменения аватара", show_alert=True)
            return

        await state.set_state("clan_edit_avatar")
        await state.update_data(clan_id=clan_id)

        await callback.message.edit_text(
            f"🖼️ <b>Изменение аватара клана {clan.name}</b>\n\n"
            "Отправьте новое фото для аватара клана:",
            parse_mode="HTML",
            reply_markup=get_back_button('manage', clan_id)
        )

    # === Методы для главного меню ===

    async def _show_main_menu(self, callback: CallbackQuery):
        """Показать главное меню кланов"""
        await callback.message.edit_text(
            "🏰 <b>Система кланов</b>\n\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=get_main_clan_keyboard()
        )

    async def _start_clan_creation(self, callback: CallbackQuery, state: FSMContext):
        """Начать создание клана"""
        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            # Проверяем, не состоит ли пользователь уже в клане
            user_clan = clan_db.get_user_clan(callback.from_user.id)
            if user_clan:
                await callback.answer(f" Вы уже состоите в клане: {user_clan.name}", show_alert=True)
                return

            # Проверяем баланс
            from database.crud import UserRepository
            user = UserRepository.get_user_by_telegram_id(db, callback.from_user.id)
            settings = clan_db.get_clan_settings()

            if user.coins < settings.clan_creation_price:
                await callback.answer(
                    f" Недостаточно Монет!\n"
                    f"Нужно: {settings.clan_creation_price:,}\n"
                    f"У вас: {user.coins:,}",
                    show_alert=True
                )
                return

            await state.set_state("clan_create_name")
            await state.update_data(creation_price=settings.clan_creation_price)

            await callback.message.edit_text(
                f"🏰 <b>Создание клана</b>\n\n"
                f"Стоимость создания: {settings.clan_creation_price:,} Монет\n"
                f"Ваш баланс: {user.coins:,} Монет\n\n"
                f"Введите название клана (3-20 символов):",
                parse_mode="HTML",
                reply_markup=get_back_button('main')
            )

        finally:
            db.close()

    async def _show_clan_list(self, callback: CallbackQuery, clan_db: ClanDatabase, page: int):
        """Показать список кланов"""
        clans = clan_db.get_all_clans(limit=CLANS_PER_PAGE * page)

        if not clans:
            await callback.message.edit_text(
                "📋 <b>Список кланов</b>\n\n"
                "Пока не создано ни одного клана.\n"
                "Вы можете стать первым!",
                parse_mode="HTML",
                reply_markup=get_back_button('main')
            )
            return

        # Пагинация
        total_clans = len(clans)
        total_pages = (total_clans + CLANS_PER_PAGE - 1) // CLANS_PER_PAGE
        start_idx = (page - 1) * CLANS_PER_PAGE
        end_idx = start_idx + CLANS_PER_PAGE
        page_clans = clans[start_idx:end_idx]

        clans_text = "📋 <b>Список кланов</b>\n\n"
        for idx, clan in enumerate(page_clans, start=start_idx + 1):
            members_count = len(clan_db.get_clan_members(clan.id))
            clans_text += f"{idx}. <b>{clan.name}</b> [{clan.tag}]\n"
            clans_text += f"   👥 Участников: {members_count}\n"
            clans_text += f"   💰 Монет: {clan.total_coins:,}\n\n"

        clans_text += f"📄 Страница {page}/{total_pages}"

        await callback.message.edit_text(
            clans_text,
            parse_mode="HTML",
            reply_markup=get_clan_list_keyboard(page_clans, page, total_pages)
        )

    async def _show_clan_top(self, callback: CallbackQuery, clan_db: ClanDatabase, page: int):
        """Показать топ кланов"""
        clans = clan_db.get_top_clans(limit=CLANS_PER_PAGE * page)

        if not clans:
            await callback.message.edit_text(
                "🏆 <b>Топ кланов</b>\n\n"
                "Пока не создано ни одного клана.",
                parse_mode="HTML",
                reply_markup=get_back_button('main')
            )
            return

        # Пагинация
        total_pages = (len(clans) + CLANS_PER_PAGE - 1) // CLANS_PER_PAGE
        start_idx = (page - 1) * CLANS_PER_PAGE
        end_idx = start_idx + CLANS_PER_PAGE
        page_clans = clans[start_idx:end_idx]

        top_text = format_clan_top(page_clans, start_idx + 1)
        top_text += f"\n📄 Страница {page}/{total_pages}"

        await callback.message.edit_text(
            top_text,
            parse_mode="HTML",
            reply_markup=get_clan_list_keyboard(page_clans, page, total_pages)
        )

    async def _start_clan_search(self, callback: CallbackQuery, state: FSMContext):
        """Начать поиск клана"""
        await state.set_state("clan_search")

        await callback.message.edit_text(
            "🔍 <b>Поиск клана</b>\n\n"
            "Введите название или тег клана для поиска:",
            parse_mode="HTML",
            reply_markup=get_back_button('main')
        )

    async def _show_invitations(self, callback: CallbackQuery, clan_db: ClanDatabase, user_id: int):
        """Показать приглашения пользователя"""
        invitations = clan_db.get_user_invitations(user_id)

        if not invitations:
            await callback.message.edit_text(
                "📨 <b>Мои приглашения</b>\n\n"
                "У вас нет новых приглашений в кланы.",
                parse_mode="HTML",
                reply_markup=get_back_button('main')
            )
            return

        invites_text = "📨 <b>Мои приглашения</b>\n\n"
        for invite in invitations:
            clan = invite.clan
            invites_text += f"🏰 <b>{clan.name}</b> [{clan.tag}]\n"
            invites_text += f"📝 {clan.description[:50]}...\n"
            invites_text += f"👥 Участников: {len(clan.members)}\n\n"

        await callback.message.edit_text(
            invites_text,
            parse_mode="HTML",
            reply_markup=get_invitations_keyboard(invitations)
        )

    async def _show_my_clan(self, callback: CallbackQuery, clan_db: ClanDatabase, user_id: int):
        """Показать клан пользователя"""
        clan = clan_db.get_user_clan(user_id)

        if not clan:
            await callback.message.edit_text(
                "👤 <b>Мой клан</b>\n\n"
                "Вы не состоите ни в одном клане.\n"
                "Создайте свой или присоединитесь к существующему!",
                parse_mode="HTML",
                reply_markup=get_back_button('main')
            )
            return

        user_role = clan_db.get_user_role(clan.id, user_id)
        clan_info = format_clan_info(clan, user_role)

        await callback.message.edit_text(
            clan_info,
            parse_mode="HTML",
            reply_markup=get_clan_profile_keyboard(clan.id, user_role)
        )

    # === Методы для работы с кланами ===

    async def _view_clan(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Просмотр информации о клане"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        # Проверяем, состоит ли пользователь в этом клане
        user_role = clan_db.get_user_role(clan_id, user_id)

        clan_info = format_clan_info(clan, user_role)

        await callback.message.edit_text(
            clan_info,
            parse_mode="HTML",
            reply_markup=get_clan_profile_keyboard(clan.id, user_role)
        )

    async def _show_clan_profile(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Показать профиль клана"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)
        clan_info = format_clan_info(clan, user_role)

        await callback.message.edit_text(
            clan_info,
            parse_mode="HTML",
            reply_markup=get_clan_profile_keyboard(clan.id, user_role)
        )

    async def _show_clan_members(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int,
                                 page: int):
        """Показать участников клана"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        members = clan_db.get_clan_members(clan_id)
        user_role = clan_db.get_user_role(clan_id, user_id)

        if not members:
            await callback.message.edit_text(
                f"👥 <b>Участники клана {clan.name}</b>\n\n"
                "В клане пока нет участников.",
                parse_mode="HTML",
                reply_markup=get_back_button('profile', clan_id)
            )
            return

        # Пагинация
        total_members = len(members)
        total_pages = (total_members + MEMBERS_PER_PAGE - 1) // MEMBERS_PER_PAGE
        start_idx = (page - 1) * MEMBERS_PER_PAGE
        end_idx = start_idx + MEMBERS_PER_PAGE
        page_members = members[start_idx:end_idx]

        members_text = f"👥 <b>Участники клана {clan.name}</b>\n\n"

        for idx, member in enumerate(page_members, start=start_idx + 1):
            # Получаем информацию о пользователе
            from database.crud import UserRepository
            db = SessionLocal()
            user_info = UserRepository.get_user_by_telegram_id(db, member.user_id)
            db.close()

            if user_info:
                username = user_info.username or f"ID: {user_info.telegram_id}"
                role_icon = "👑" if member.role == 'leader' else "⭐" if member.role == 'deputy' else "👤"
                members_text += f"{idx}. {role_icon} <b>{username}</b>\n"
                members_text += f"   🎭 Роль: {member.role}\n"
                members_text += f"   💰 Вклад: {member.coins_contributed:,} Монет\n\n"

        members_text += f"📄 Страница {page}/{total_pages}\n"
        members_text += f"👥 Всего участников: {total_members}"

        await callback.message.edit_text(
            members_text,
            parse_mode="HTML",
            reply_markup=get_clan_members_keyboard(clan_id, page_members, user_role, page, total_pages)
        )

    async def _show_clan_management(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Показать меню управления кланом"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)

        if user_role not in ['leader', 'deputy']:
            await callback.answer(" У вас нет прав для управления кланом", show_alert=True)
            await self._show_clan_profile(callback, clan_db, clan_id, user_id)
            return

        await callback.message.edit_text(
            f"⚙️ <b>Управление кланом {clan.name}</b>\n\n"
            "Выберите действие для управления кланом:",
            parse_mode="HTML",
            reply_markup=get_clan_management_keyboard(clan.id, user_role)
        )

    async def _show_join_requests(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int,
                                  page: int):
        """Показать заявки на вступление"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)

        if user_role not in ['leader', 'deputy']:
            await callback.answer(" У вас нет прав для просмотра заявок", show_alert=True)
            await self._show_clan_profile(callback, clan_db, clan_id, user_id)
            return

        requests = clan_db.get_clan_join_requests(clan_id)

        if not requests:
            await callback.message.edit_text(
                f"📝 <b>Заявки на вступление в {clan.name}</b>\n\n"
                "Нет новых заявок на вступление.",
                parse_mode="HTML",
                reply_markup=get_back_button('profile', clan_id)
            )
            return

        # Пагинация
        total_requests = len(requests)
        total_pages = (total_requests + REQUESTS_PER_PAGE - 1) // REQUESTS_PER_PAGE
        start_idx = (page - 1) * REQUESTS_PER_PAGE
        end_idx = start_idx + REQUESTS_PER_PAGE
        page_requests = requests[start_idx:end_idx]

        requests_text = f"📝 <b>Заявки на вступление в {clan.name}</b>\n\n"

        for req in page_requests:
            # Получаем информацию о пользователе
            from database.crud import UserRepository
            db = SessionLocal()
            user_info = UserRepository.get_user_by_telegram_id(db, req.user_id)
            db.close()

            if user_info:
                username = user_info.username or f"ID: {user_info.telegram_id}"
                requests_text += f"👤 <b>{username}</b>\n"
                if req.message:
                    requests_text += f"📝 Сообщение: {req.message}\n"
                requests_text += f"📅 Дата: {req.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"

        requests_text += f"📄 Страница {page}/{total_pages}\n"
        requests_text += f"📝 Всего заявок: {total_requests}"

        await callback.message.edit_text(
            requests_text,
            parse_mode="HTML",
            reply_markup=get_join_requests_keyboard(page_requests, clan_id, page, total_pages)
        )

    async def _apply_to_clan(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int,
                             state: FSMContext):
        """Подать заявку на вступление в клан"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        # Проверяем, не состоит ли уже пользователь в клане
        user_clan = clan_db.get_user_clan(user_id)
        if user_clan:
            await callback.answer(f" Вы уже состоите в клане: {user_clan.name}", show_alert=True)
            return

        await state.set_state("clan_apply_message")
        await state.update_data(clan_id=clan_id)

        await callback.message.edit_text(
            f"📝 <b>Подача заявки в клан {clan.name}</b>\n\n"
            "Напишите сообщение для лидера клана (не обязательно):",
            parse_mode="HTML",
            reply_markup=get_back_button('profile', clan_id)
        )

    async def _view_invitation(self, callback: CallbackQuery, clan_db: ClanDatabase, invitation_id: int, clan_id: int):
        """Просмотр приглашения"""
        invitation = clan_db.db.query(clan_db.invitation_model).filter(
            clan_db.invitation_model.id == invitation_id
        ).first()

        if not invitation:
            await callback.answer(" Приглашение не найдено", show_alert=True)
            await self._show_invitations(callback, clan_db, callback.from_user.id)
            return

        clan = invitation.clan

        invite_text = (
            f"📨 <b>Приглашение в клан</b>\n\n"
            f"🏰 <b>Клан:</b> {clan.name} [{clan.tag}]\n"
            f"📝 <b>Описание:</b> {clan.description or 'Нет описания'}\n"
            f"👥 <b>Участников:</b> {len(clan.members)}\n"
            f"💰 <b>Монет:</b> {clan.total_coins:,}\n"
            f"📅 <b>Создан:</b> {clan.created_at.strftime('%d.%m.%Y')}\n\n"
            f"Выберите действие:"
        )

        await callback.message.edit_text(
            invite_text,
            parse_mode="HTML",
            reply_markup=get_invitation_actions_keyboard(invitation_id, clan_id)
        )

    async def _handle_invitation(self, callback: CallbackQuery, clan_db: ClanDatabase, action: str, invitation_id: int):
        """Обработать приглашение"""
        if action == 'accept_invite':
            success = clan_db.accept_invitation(invitation_id)
            if success:
                await callback.answer("✅ Вы присоединились к клану!", show_alert=True)
                # Обновляем меню
                await self._show_my_clan(callback, clan_db, callback.from_user.id)
            else:
                await callback.answer(" Ошибка при принятии приглашения", show_alert=True)
        else:  # reject_invite
            success = clan_db.reject_invitation(invitation_id)
            if success:
                await callback.answer(" Приглашение отклонено", show_alert=True)
                await self._show_invitations(callback, clan_db, callback.from_user.id)
            else:
                await callback.answer(" Ошибка при отклонении приглашения", show_alert=True)

    async def _view_join_request(self, callback: CallbackQuery, clan_db: ClanDatabase, request_id: int, clan_id: int,
                                 user_id: int):
        """Просмотр заявки на вступление"""
        request = clan_db.db.query(clan_db.request_model).filter(
            clan_db.request_model.id == request_id
        ).first()

        if not request:
            await callback.answer(" Заявка не найдена", show_alert=True)
            await self._show_join_requests(callback, clan_db, clan_id, callback.from_user.id, 1)
            return

        # Получаем информацию о пользователе
        from database.crud import UserRepository
        db = SessionLocal()
        user_info = UserRepository.get_user_by_telegram_id(db, user_id)
        db.close()

        if not user_info:
            await callback.answer(" Пользователь не найден", show_alert=True)
            return

        clan = clan_db.get_clan_by_id(clan_id)

        request_text = (
            f"📝 <b>Заявка на вступление</b>\n\n"
            f"👤 <b>Пользователь:</b> {user_info.username or f'ID: {user_id}'}\n"
            f"🏰 <b>Клан:</b> {clan.name}\n\n"
        )

        if request.message:
            request_text += f"📝 <b>Сообщение:</b> {request.message}\n\n"

        request_text += f"📅 <b>Дата заявки:</b> {request.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        request_text += "Выберите действие:"

        await callback.message.edit_text(
            request_text,
            parse_mode="HTML",
            reply_markup=get_request_actions_keyboard(request_id, clan_id, user_id)
        )

    async def _handle_join_request(self, callback: CallbackQuery, clan_db: ClanDatabase, action: str, request_id: int,
                                   user_id: int, clan_id: int):
        """Обработать заявку на вступление"""
        approve = (action == 'approve_request')

        # Получаем информацию о заявке
        request = clan_db.db.query(ClanJoinRequest).filter(
            ClanJoinRequest.id == request_id
        ).first()

        if not request:
            await callback.answer(" Заявка не найдена", show_alert=True)
            return

        if approve:
            # Добавляем пользователя в клан
            success = clan_db.add_member(clan_id, request.user_id)
            if success:
                request.status = 'approved'
                clan_db.db.commit()

                # Уведомляем пользователя
                try:
                    clan = clan_db.get_clan_by_id(clan_id)
                    await callback.bot.send_message(
                        request.user_id,
                        f"✅ <b>Ваша заявка в клан {clan.name} одобрена!</b>\n\n"
                        f"Добро пожаловать в клан!",
                        parse_mode="HTML"
                    )
                except:
                    pass

                await callback.answer("✅ Заявка одобрена!", show_alert=True)
            else:
                await callback.answer(" Ошибка при одобрении заявки", show_alert=True)
        else:
            request.status = 'rejected'
            clan_db.db.commit()

            # Уведомляем пользователя об отказе
            try:
                clan = clan_db.get_clan_by_id(clan_id)
                await callback.bot.send_message(
                    request.user_id,
                    f"❌ <b>Ваша заявка в клан {clan.name} отклонена.</b>",
                    parse_mode="HTML"
                )
            except:
                pass

            await callback.answer(" Заявка отклонена", show_alert=True)

        # Показываем обновленный список заявок
        await self._show_join_requests(callback, clan_db, clan_id, callback.from_user.id, 1)

    async def _start_transfer_leadership(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int,
                                         user_id: int, state: FSMContext):
        """Начать передачу лидерства"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)

        if user_role != 'leader':
            await callback.answer(" Только лидер может передать лидерство", show_alert=True)
            await self._show_clan_profile(callback, clan_db, clan_id, user_id)
            return

        # Получаем участников для передачи лидерства
        members = clan_db.get_clan_members(clan_id)

        if len(members) < 2:
            await callback.answer(" В клане должен быть хотя бы еще один участник", show_alert=True)
            return

        await state.set_state("clan_transfer_leadership")
        await state.update_data(clan_id=clan_id)

        await callback.message.edit_text(
            f"👑 <b>Передача лидерства в клане {clan.name}</b>\n\n"
            "Введите ID пользователя, которому хотите передать лидерство:",
            parse_mode="HTML",
            reply_markup=get_back_button('profile', clan_id)
        )

    async def _confirm_leave_clan(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Подтверждение выхода из клана"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)

        if user_role == 'leader':
            await callback.message.edit_text(
                f"⚠️ <b>Внимание!</b>\n\n"
                f"Вы являетесь лидером клана <b>{clan.name}</b>.\n"
                f"Если вы выйдете из клана, он будет распущен!\n\n"
                f"Вы уверены, что хотите покинуть клан?",
                parse_mode="HTML",
                reply_markup=get_confirmation_keyboard('leave', clan_id, user_id)
            )
        else:
            await callback.message.edit_text(
                f"🚪 <b>Выход из клана</b>\n\n"
                f"Вы уверены, что хотите покинуть клан <b>{clan.name}</b>?",
                parse_mode="HTML",
                reply_markup=get_confirmation_keyboard('leave', clan_id, user_id)
            )

    async def _confirm_disband_clan(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Подтверждение роспуска клана"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)

        if user_role != 'leader':
            await callback.answer(" Только лидер может распустить клан", show_alert=True)
            await self._show_clan_profile(callback, clan_db, clan_id, user_id)
            return

        await callback.message.edit_text(
            f"⚠️ <b>Роспуск клана</b>\n\n"
            f"Вы уверены, что хотите распустить клан <b>{clan.name}</b>?\n"
            f"Это действие необратимо! Все участники будут исключены.",
            parse_mode="HTML",
            reply_markup=get_confirmation_keyboard('disband', clan_id, user_id)
        )

    async def _start_invite_member(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int,
                                   state: FSMContext):
        """Начать приглашение участника по ID"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)

        if user_role not in ['leader', 'deputy']:
            await callback.answer(" У вас нет прав для приглашения", show_alert=True)
            await self._show_clan_profile(callback, clan_db, clan_id, user_id)
            return

        await state.set_state("clan_invite_by_id")
        await state.update_data(clan_id=clan_id)

        await callback.message.edit_text(
            f"📨 <b>Приглашение в клан {clan.name}</b>\n\n"
            "Введите ID пользователя, которого хотите пригласить:\n\n"
            "<i>Можно указать ID, @username или отправить контакт</i>",
            parse_mode="HTML",
            reply_markup=get_back_button('invite', clan_id)
        )

    async def process_invite_by_id(self, message: types.Message, state: FSMContext):
        """Обработка приглашения по ID/username"""
        identifier = message.text.strip()

        if not identifier:
            await message.answer(
                " Введите ID, @username или отправьте контакт",
                reply_markup=get_back_button('main')
            )
            return

        data = await state.get_data()
        clan_id = data.get('clan_id')

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            # Пытаемся определить пользователя
            user_to_invite = await self._resolve_user_identifier(db, identifier, message)

            if not user_to_invite:
                await message.answer(
                    " Пользователь не найден.\n"
                    "Убедитесь, что пользователь начал диалог с ботом.",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            # Проверяем, не состоит ли уже в клане
            user_clan = clan_db.get_user_clan(user_to_invite.telegram_id)
            if user_clan:
                await message.answer(
                    f" Пользователь уже состоит в клане: {user_clan.name}",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            # Создаем приглашение
            clan = clan_db.get_clan_by_id(clan_id)
            success = clan_db.create_invitation(
                clan_id=clan_id,
                from_user_id=message.from_user.id,
                to_user_id=user_to_invite.telegram_id
            )

            if success:
                # Отправляем уведомление приглашенному
                try:
                    await message.bot.send_message(
                        user_to_invite.telegram_id,
                        f"📨 Вы получили приглашение в клан!\n\n"
                        f"🏰 <b>Клан:</b> {clan.name} [{clan.tag}]\n"
                        f"📝 <b>Описание:</b> {clan.description[:100] if clan.description else 'Нет описания'}...\n"
                        f"👤 <b>Пригласил:</b> {message.from_user.first_name}\n\n"
                        f"Используйте команду /clans для просмотра приглашений.",
                        parse_mode="HTML"
                    )
                except:
                    pass  # Игнорируем ошибки отправки

                await message.answer(
                    f"✅ Приглашение отправлено пользователю @{user_to_invite.username or user_to_invite.telegram_id}",
                    reply_markup=get_back_button('manage', clan_id)
                )
            else:
                await message.answer(
                    " Не удалось отправить приглашение.\n"
                    "Возможно, приглашение уже отправлено.",
                    reply_markup=get_back_button('main')
                )

            await state.finish()

        finally:
            db.close()

    async def process_edit_description(self, message: types.Message, state: FSMContext):
        """Обработка изменения описания"""
        new_description = message.text.strip()

        if len(new_description) > 500:
            await message.answer(
                " Описание не должно превышать 500 символов.\n"
                "Сократите описание:",
                reply_markup=get_back_button('main')
            )
            return

        data = await state.get_data()
        clan_id = data.get('clan_id')

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            success = clan_db.update_clan(clan_id, description=new_description)

            if success:
                clan = clan_db.get_clan_by_id(clan_id)
                await message.answer(
                    f"✅ Описание клана {clan.name} успешно обновлено!",
                    reply_markup=get_back_button('profile', clan_id)
                )
            else:
                await message.answer(
                    " Ошибка при обновлении описания",
                    reply_markup=get_back_button('main')
                )

            await state.finish()

        finally:
            db.close()

    async def process_edit_avatar(self, message: types.Message, state: FSMContext):
        """Обработка изменения аватара"""
        if not message.photo:
            await message.answer(
                " Пожалуйста, отправьте фото",
                reply_markup=get_back_button('main')
            )
            return

        # Берем самое большое фото
        photo = message.photo[-1]
        file_id = photo.file_id

        data = await state.get_data()
        clan_id = data.get('clan_id')

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            success = clan_db.update_clan(clan_id, avatar=file_id)

            if success:
                clan = clan_db.get_clan_by_id(clan_id)
                await message.bot.send_photo(
                    chat_id=message.chat.id,
                    photo=file_id,
                    caption=f"✅ Аватар клана {clan.name} успешно обновлен!",
                    reply_markup=get_back_button('profile', clan_id)
                )
            else:
                await message.answer(
                    " Ошибка при обновлении аватара",
                    reply_markup=get_back_button('main')
                )

            await state.finish()

        finally:
            db.close()

    async def _start_remove_member(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int,
                                   state: FSMContext):
        """Начать исключение участника"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)

        if user_role not in ['leader', 'deputy']:
            await callback.answer(" У вас нет прав для исключения", show_alert=True)
            await self._show_clan_profile(callback, clan_db, clan_id, user_id)
            return

        await state.set_state("clan_remove_member")
        await state.update_data(clan_id=clan_id)

        await callback.message.edit_text(
            f"🗑️ <b>Исключение из клана {clan.name}</b>\n\n"
            "Введите ID пользователя, которого хотите исключить:",
            parse_mode="HTML",
            reply_markup=get_back_button('members', clan_id, 1)
        )

    async def _start_set_deputy(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int,
                                state: FSMContext):
        """Начать назначение заместителя"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)

        if user_role != 'leader':
            await callback.answer(" Только лидер может назначать заместителя", show_alert=True)
            await self._show_clan_profile(callback, clan_db, clan_id, user_id)
            return

        await state.set_state("clan_set_deputy")
        await state.update_data(clan_id=clan_id)

        await callback.message.edit_text(
            f"⭐ <b>Назначение заместителя в клане {clan.name}</b>\n\n"
            "Введите ID пользователя, которого хотите назначить заместителем:",
            parse_mode="HTML",
            reply_markup=get_back_button('members', clan_id, 1)
        )

    async def _handle_confirmation(self, callback: CallbackQuery, clan_db: ClanDatabase, action: str, clan_id: int,
                                   user_id: int, request_id: int):
        """Обработка подтверждений"""
        if action == 'leave':
            # Выход из клана
            success = clan_db.remove_member(clan_id, user_id)

            if success:
                await callback.answer("✅ Вы покинули клан", show_alert=True)
                await self._show_main_menu(callback)
            else:
                await callback.answer(" Ошибка при выходе из клана", show_alert=True)

        elif action == 'disband':
            # Роспуск клана
            success = clan_db.delete_clan(clan_id)

            if success:
                await callback.answer("✅ Клан распущен", show_alert=True)
                await self._show_main_menu(callback)
            else:
                await callback.answer(" Ошибка при роспуске клана", show_alert=True)

        elif action == 'remove_member':
            # Исключение участника
            success = clan_db.remove_member(clan_id, user_id)

            if success:
                await callback.answer(f"✅ Участник исключен", show_alert=True)
                await self._show_clan_members(callback, clan_db, clan_id, callback.from_user.id, 1)
            else:
                await callback.answer(" Ошибка при исключении участника", show_alert=True)

    # === Обработчики состояний (FSM) ===

    async def process_clan_name(self, message: types.Message, state: FSMContext):
        """Обработка названия клана"""
        name = message.text.strip()

        if len(name) < 3 or len(name) > 20:
            await message.answer(
                " Название должно быть от 3 до 20 символов.\n"
                "Попробуйте еще раз:",
                reply_markup=get_back_button('main')
            )
            return

        await state.update_data(clan_name=name)
        await state.set_state("clan_create_tag")

        await message.answer(
            "🏷️ Введите тег клана (2-10 символов, латиница):\n"
            "Пример: PEREC, BEST, WINNERS",
            reply_markup=get_back_button('main')
        )

    async def process_clan_tag(self, message: types.Message, state: FSMContext):
        """Обработка тега клана"""
        tag = message.text.strip().upper()

        if len(tag) < 2 or len(tag) > 10:
            await message.answer(
                " Тег должен быть от 2 до 10 символов.\n"
                "Попробуйте еще раз:",
                reply_markup=get_back_button('main')
            )
            return

        # Проверяем, что тег состоит только из латинских букв и цифр
        if not all(c.isalnum() and c.isascii() for c in tag):
            await message.answer(
                " Тег может содержать только латинские буквы и цифры.\n"
                "Попробуйте еще раз:",
                reply_markup=get_back_button('main')
            )
            return

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            # Проверяем уникальность тега
            existing = clan_db.get_clan_by_tag(tag)
            if existing:
                await message.answer(
                    f" Клан с тегом {tag} уже существует.\n"
                    "Придумайте другой тег:",
                    reply_markup=get_back_button('main')
                )
                return

            await state.update_data(clan_tag=tag)
            await state.set_state("clan_create_desc")

            await message.answer(
                "📝 Введите описание клана (до 500 символов):",
                reply_markup=get_back_button('main')
            )

        finally:
            db.close()

    async def process_clan_description(self, message: types.Message, state: FSMContext):
        """Обработка описания клана"""
        description = message.text.strip()

        if len(description) > 500:
            await message.answer(
                " Описание не должно превышать 500 символов.\n"
                "Сократите описание:",
                reply_markup=get_back_button('main')
            )
            return

        data = await state.get_data()

        # Создаем клан
        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            # Списываем Монеты за создание
            from database.crud import UserRepository
            user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
            settings = clan_db.get_clan_settings()

            if user.coins < settings.clan_creation_price:
                await message.answer(
                    f" Недостаточно Монет!\n"
                    f"Нужно: {settings.clan_creation_price:,}\n"
                    f"У вас: {user.coins:,}",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            user.coins -= settings.clan_creation_price
            db.commit()

            # Создаем клан
            clan = clan_db.create_clan(
                name=data['clan_name'],
                tag=data['clan_tag'],
                description=description,
                creator_id=message.from_user.id
            )

            if clan:
                await message.answer(
                    f"✅ <b>Клан создан успешно!</b>\n\n"
                    f"🏰 <b>Название:</b> {clan.name}\n"
                    f"🏷️ <b>Тег:</b> {clan.tag}\n"
                    f"📝 <b>Описание:</b> {clan.description}\n"
                    f"💰 <b>Стоимость создания:</b> {settings.clan_creation_price:,} Монет\n"
                    f"👑 <b>Вы стали лидером клана!</b>",
                    parse_mode="HTML",
                    reply_markup=get_clan_profile_keyboard(clan.id, 'leader')
                )
            else:
                await message.answer(
                    " Ошибка при создании клана",
                    reply_markup=get_back_button('main')
                )

            await state.finish()

        except Exception as e:
            logger.error(f"Error creating clan: {e}")
            await message.answer(
                " Ошибка при создании клана",
                reply_markup=get_back_button('main')
            )
            await state.finish()

        finally:
            db.close()

    async def process_clan_search(self, message: types.Message, state: FSMContext):
        """Обработка поиска клана"""
        query = message.text.strip()

        if len(query) < 2:
            await message.answer(
                " Запрос должен быть не менее 2 символов.\n"
                "Попробуйте еще раз:",
                reply_markup=get_back_button('main')
            )
            return

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            clans = clan_db.search_clans(query, limit=10)

            if not clans:
                await message.answer(
                    f"🔍 <b>Результаты поиска: '{query}'</b>\n\n"
                    "Кланы не найдены.",
                    parse_mode="HTML",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            clans_text = f"🔍 <b>Результаты поиска: '{query}'</b>\n\n"

            for idx, clan in enumerate(clans, 1):
                members_count = len(clan_db.get_clan_members(clan.id))
                clans_text += f"{idx}. <b>{clan.name}</b> [{clan.tag}]\n"
                clans_text += f"   📝 {clan.description[:50]}...\n"
                clans_text += f"   👥 Участников: {members_count}\n"
                clans_text += f"   💰 Монет: {clan.total_coins:,}\n\n"

            keyboard = InlineKeyboardMarkup(row_width=2)
            for clan in clans:
                keyboard.add(
                    InlineKeyboardButton(
                        f"🏰 {clan.name} [{clan.tag}]",
                        callback_data=clan_cb.new(
                            action='view', clan_id=clan.id, user_id=0, request_id=0, page=0
                        )
                    )
                )

            keyboard.add(
                InlineKeyboardButton("🔙 Главное меню", callback_data=clan_cb.new(
                    action='main', clan_id=0, user_id=0, request_id=0, page=0
                ))
            )

            await message.answer(
                clans_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

            await state.finish()

        finally:
            db.close()

    async def process_apply_message(self, message: types.Message, state: FSMContext):
        """Обработка сообщения при подаче заявки"""
        data = await state.get_data()
        clan_id = data.get('clan_id')

        if not clan_id:
            await message.answer(" Ошибка: клан не найден", reply_markup=get_back_button('main'))
            await state.finish()
            return

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            # Получаем настройки клана
            settings = clan_db.get_clan_join_settings(clan_id)

            # Создаем заявку
            success = clan_db.create_join_request(
                clan_id=clan_id,
                user_id=message.from_user.id,
                message=message.text.strip()
            )

            if success:
                clan = clan_db.get_clan_by_id(clan_id)

                # Получаем актуальную заявку
                request = clan_db.db.query(ClanJoinRequest).filter(
                    ClanJoinRequest.clan_id == clan_id,
                    ClanJoinRequest.user_id == message.from_user.id,
                    ClanJoinRequest.status == 'pending'
                ).order_by(ClanJoinRequest.created_at.desc()).first()

                if request:
                    # Если авто-принятие включено
                    if settings.get('auto_accept_requests', False):
                        # Автоматически добавляем в клан
                        join_success = clan_db.add_member(clan_id, message.from_user.id)

                        if join_success:
                            request.status = 'approved'
                            db.commit()

                            # Уведомляем пользователя
                            await message.answer(
                                f"✅ <b>Вы автоматически присоединились к клану {clan.name}!</b>\n\n"
                                f"Добро пожаловать в клан!",
                                parse_mode="HTML",
                                reply_markup=get_clan_profile_keyboard(clan.id, 'member')
                            )

                            # Уведомляем лидера
                            await self._send_auto_join_notification(message.bot, clan.id, message.from_user.id, clan_db)
                        else:
                            await message.answer(
                                "❌ Ошибка при присоединении к клану",
                                reply_markup=get_back_button('main')
                            )
                    else:
                        # Требуется подтверждение
                        request.status = 'pending'
                        db.commit()

                        # Отправляем уведомления лидерам
                        await self._send_request_notification(message.bot, clan_id, request.id, clan_db)

                        await message.answer(
                            f"✅ <b>Заявка отправлена!</b>\n\n"
                            f"Заявка на вступление в клан <b>{clan.name}</b> отправлена лидеру и заместителю.\n"
                            f"Ожидайте подтверждения.",
                            parse_mode="HTML",
                            reply_markup=get_back_button('main')
                        )
                else:
                    await message.answer(
                        "❌ Ошибка при создании заявки",
                        reply_markup=get_back_button('main')
                    )
            else:
                await message.answer(
                    "❌ Не удалось отправить заявку.\n"
                    "Возможно, вы уже подали заявку или состоите в клане.",
                    reply_markup=get_back_button('main')
                )

            await state.finish()

        except Exception as e:
            logger.error(f"Error processing apply message: {e}")
            await message.answer(
                "❌ Ошибка при отправке заявки",
                reply_markup=get_back_button('main')
            )
            await state.finish()
        finally:
            db.close()

    async def process_invite_member(self, message: types.Message, state: FSMContext):
        """Обработка приглашения участника"""
        try:
            invite_user_id = int(message.text.strip())
        except ValueError:
            await message.answer(
                " Некорректный ID пользователя.\n"
                "Введите числовой ID:",
                reply_markup=get_back_button('main')
            )
            return

        data = await state.get_data()
        clan_id = data.get('clan_id')

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            # Проверяем существование пользователя
            from database.crud import UserRepository
            user_to_invite = UserRepository.get_user_by_telegram_id(db, invite_user_id)

            if not user_to_invite:
                await message.answer(
                    " Пользователь не найден.\n"
                    "Убедитесь, что пользователь начал диалог с ботом.",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            # Проверяем, не состоит ли уже в клане
            user_clan = clan_db.get_user_clan(invite_user_id)
            if user_clan:
                await message.answer(
                    f" Пользователь уже состоит в клане: {user_clan.name}",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            # Создаем приглашение
            clan = clan_db.get_clan_by_id(clan_id)
            success = clan_db.create_invitation(
                clan_id=clan_id,
                from_user_id=message.from_user.id,
                to_user_id=invite_user_id
            )

            if success:
                # Отправляем уведомление приглашенному
                try:
                    await message.bot.send_message(
                        invite_user_id,
                        f"📨 Вы получили приглашение в клан!\n\n"
                        f"🏰 <b>Клан:</b> {clan.name} [{clan.tag}]\n"
                        f"📝 <b>Описание:</b> {clan.description or 'Нет описания'}\n"
                        f"👤 <b>Пригласил:</b> {message.from_user.first_name}\n\n"
                        f"Используйте команду /clans для просмотра приглашений.",
                        parse_mode="HTML"
                    )
                except:
                    pass  # Игнорируем ошибки отправки

                await message.answer(
                    f"✅ Приглашение отправлено пользователю ID: {invite_user_id}",
                    reply_markup=get_back_button('manage', clan_id)
                )
            else:
                await message.answer(
                    " Не удалось отправить приглашение.\n"
                    "Возможно, приглашение уже отправлено.",
                    reply_markup=get_back_button('main')
                )

            await state.finish()

        finally:
            db.close()

    async def process_remove_member(self, message: types.Message, state: FSMContext):
        """Обработка исключения участника"""
        try:
            remove_user_id = int(message.text.strip())
        except ValueError:
            await message.answer(
                " Некорректный ID пользователя.\n"
                "Введите числовой ID:",
                reply_markup=get_back_button('main')
            )
            return

        data = await state.get_data()
        clan_id = data.get('clan_id')

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            # Проверяем, состоит ли пользователь в клане
            user_role = clan_db.get_user_role(clan_id, remove_user_id)
            if not user_role:
                await message.answer(
                    " Пользователь не состоит в вашем клане.",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            # Проверяем права
            current_user_role = clan_db.get_user_role(clan_id, message.from_user.id)

            # Лидер может исключить кого угодно
            # Заместитель может исключить только обычных участников
            if current_user_role == 'deputy' and user_role != 'member':
                await message.answer(
                    " Заместитель может исключать только обычных участников.",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            # Нельзя исключить себя через эту команду
            if remove_user_id == message.from_user.id:
                await message.answer(
                    " Для выхода из клана используйте кнопку 'Покинуть клан'.",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            clan = clan_db.get_clan_by_id(clan_id)

            await state.update_data(remove_user_id=remove_user_id)

            # Запрашиваем подтверждение
            from database.crud import UserRepository
            user_to_remove = UserRepository.get_user_by_telegram_id(db, remove_user_id)
            username = user_to_remove.username if user_to_remove else f"ID: {remove_user_id}"

            await message.answer(
                f"⚠️ <b>Подтверждение исключения</b>\n\n"
                f"Вы уверены, что хотите исключить <b>{username}</b> из клана <b>{clan.name}</b>?",
                parse_mode="HTML",
                reply_markup=get_confirmation_keyboard('remove_member', clan_id, remove_user_id)
            )

            await state.finish()

        finally:
            db.close()

    async def process_set_deputy(self, message: types.Message, state: FSMContext):
        """Обработка назначения заместителя"""
        try:
            deputy_user_id = int(message.text.strip())
        except ValueError:
            await message.answer(
                " Некорректный ID пользователя.\n"
                "Введите числовой ID:",
                reply_markup=get_back_button('main')
            )
            return

        data = await state.get_data()
        clan_id = data.get('clan_id')

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            # Проверяем, состоит ли пользователь в клане
            user_role = clan_db.get_user_role(clan_id, deputy_user_id)
            if not user_role:
                await message.answer(
                    " Пользователь не состоит в вашем клане.",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            # Назначаем заместителя
            success = clan_db.update_member_role(clan_id, deputy_user_id, 'deputy')

            if success:
                await message.answer(
                    f"✅ Пользователь ID: {deputy_user_id} назначен заместителем!",
                    reply_markup=get_back_button('members', clan_id, 1)
                )
            else:
                await message.answer(
                    " Ошибка при назначении заместителя.",
                    reply_markup=get_back_button('main')
                )

            await state.finish()

        finally:
            db.close()

    async def process_transfer_leadership(self, message: types.Message, state: FSMContext):
        """Обработка передачи лидерства"""
        try:
            new_leader_id = int(message.text.strip())
        except ValueError:
            await message.answer(
                " Некорректный ID пользователя.\n"
                "Введите числовой ID:",
                reply_markup=get_back_button('main')
            )
            return

        data = await state.get_data()
        clan_id = data.get('clan_id')

        db = SessionLocal()
        clan_db = ClanDatabase(db)

        try:
            # Проверяем, состоит ли пользователь в клане
            user_role = clan_db.get_user_role(clan_id, new_leader_id)
            if not user_role:
                await message.answer(
                    " Пользователь не состоит в вашем клане.",
                    reply_markup=get_back_button('main')
                )
                await state.finish()
                return

            # Передаем лидерство
            success = clan_db.update_member_role(clan_id, new_leader_id, 'leader')

            if success:
                clan = clan_db.get_clan_by_id(clan_id)

                # Уведомляем нового лидера
                try:
                    await message.bot.send_message(
                        new_leader_id,
                        f"👑 <b>Вы стали лидером клана {clan.name}!</b>\n\n"
                        f"Лидерство передано пользователем {message.from_user.first_name}.",
                        parse_mode="HTML"
                    )
                except:
                    pass

                await message.answer(
                    f"✅ Лидерство передано пользователю ID: {new_leader_id}!\n"
                    f"Теперь вы заместитель в клане.",
                    reply_markup=get_clan_profile_keyboard(clan_id, 'deputy')
                )
            else:
                await message.answer(
                    " Ошибка при передаче лидерства.",
                    reply_markup=get_back_button('main')
                )

            await state.finish()

        finally:
            db.close()

    async def _show_clan_stats(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Показать статистику клана"""
        clan = clan_db.get_clan_by_id(clan_id)

        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            await self._show_main_menu(callback)
            return

        # Обновляем капитал клана
        clan_db.force_update_clan_coins(clan_id)

        # Обновляем объект клана из БД
        db = self._get_db_session()
        try:
            db.refresh(clan)
        except:
            clan = clan_db.get_clan_by_id(clan_id)  # Перезагружаем если refresh не работает
        finally:
            db.close()

        # Получаем информацию об участниках
        members = clan_db.get_clan_members(clan_id)

        # Считаем статистику
        leader_count = 0
        deputy_count = 0
        member_count = 0

        for member in members:
            if member.role == 'leader':
                leader_count += 1
            elif member.role == 'deputy':
                deputy_count += 1
            else:
                member_count += 1

        # Получаем средний баланс
        from database.models import TelegramUser
        from decimal import Decimal

        db = self._get_db_session()
        total_balance = Decimal('0')
        active_users = 0

        for member in members:
            user = db.query(TelegramUser).filter(TelegramUser.telegram_id == member.user_id).first()
            if user and user.coins is not None:
                total_balance += user.coins if isinstance(user.coins, Decimal) else Decimal(str(user.coins))
                active_users += 1

        avg_balance = (total_balance / active_users).quantize(Decimal('1')) if active_users > 0 else Decimal('0')
        db.close()

        # Формируем текст статистики
        from decimal import Decimal

        stats_text = (
            f"📊 <b>Статистика клана {clan.name}</b>\n\n"
            f"🏷️ <b>Тег:</b> [{clan.tag}]\n"
            f"📅 <b>Создан:</b> {clan.created_at.strftime('%d.%m.%Y')}\n"
            f"👥 <b>Участников:</b> {len(members)}\n"
            f"   👑 Лидеров: {leader_count}\n"
            f"   ⭐ Заместителей: {deputy_count}\n"
            f"   👤 Участников: {member_count}\n\n"
            f"💰 <b>Финансовая статистика:</b>\n"
            f"   • Общий капитал: {clan.total_coins:,} Монет\n"
            f"   • Средний баланс: {avg_balance:,} Монет\n"
            f"   • Активных с балансом: {active_users}\n\n"
            f"📈 <b>Позиция в топе:</b> {self._get_clan_rank(clan.id, clan_db)}\n"
            f"🔄 <b>Обновлено:</b> {datetime.now().strftime('%H:%M:%S')}"
        )

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🔄 Обновить", callback_data=clan_cb.new(
                action='stats', clan_id=clan_id, user_id=user_id, request_id=0, page=0
            )),
            InlineKeyboardButton("📈 График роста", callback_data=clan_cb.new(
                action='growth_chart', clan_id=clan_id, user_id=user_id, request_id=0, page=0
            ))
        )
        keyboard.add(
            InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
                action='profile', clan_id=clan_id, user_id=user_id, request_id=0, page=0
            ))
        )

        await callback.message.edit_text(stats_text, parse_mode="HTML", reply_markup=keyboard)

    def _get_clan_rank(self, clan_id: int, clan_db: ClanDatabase) -> str:
        """Получить позицию клана в топе"""
        # Обновляем все кланы перед получением топа
        clan_db.update_all_clans_coins()

        # Получаем отсортированный список кланов
        db = self._get_db_session()
        try:
            top_clans = db.query(Clan) \
                .filter(Clan.is_active == True) \
                .order_by(desc(Clan.total_coins)) \
                .limit(100) \
                .all()

            for rank, clan in enumerate(top_clans, 1):
                if clan.id == clan_id:
                    return f"#{rank}"

            return "Вне топ-100"
        finally:
            db.close()

    async def admin_update_clans_command(self, message: types.Message):
        """Команда для ручного обновления кланов (админы)"""
        # Проверяем права администратора (можно настроить под вашу систему)
        admin_ids = [123456789]  # Замените на ID админов

        if message.from_user.id not in admin_ids:
            await message.answer(" У вас нет прав для выполнения этой команды")
            return

        try:
            # Обновляем все кланы
            success = ClanBalanceUpdater.manual_update_all_clans()

            if success:
                await message.answer("✅ Капитал всех кланов успешно обновлен!")
            else:
                await message.answer("⚠️ Не удалось обновить капитал кланов")

        except Exception as e:
            logger.error(f"Error in admin update: {e}")
            await message.answer(" Ошибка при обновлении кланов")

    async def admin_update_clan_command(self, message: types.Message):
        """Команда для ручного обновления конкретного клана (админы)"""
        admin_ids = [123456789]  # Замените на ID админов

        if message.from_user.id not in admin_ids:
            await message.answer(" У вас нет прав для выполнения этой команды")
            return

        try:
            # Парсим ID клана из команды
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer(" Использование: /updateclan <ID_клана>")
                return

            clan_id = int(parts[1])
            success = ClanBalanceUpdater.manual_update_clan(clan_id)

            if success:
                await message.answer(f"✅ Капитал клана ID:{clan_id} успешно обновлен!")
            else:
                await message.answer(f"⚠️ Не удалось обновить клан ID:{clan_id}")

        except ValueError:
            await message.answer(" Неверный формат ID клана")
        except Exception as e:
            logger.error(f"Error in admin clan update: {e}")
            await message.answer(" Ошибка при обновлении клана")

    async def _show_clan_settings(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Показать настройки клана"""
        clan = clan_db.get_clan_by_id(clan_id)
        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            return

        user_role = clan_db.get_user_role(clan_id, user_id)
        if user_role not in ['leader', 'deputy']:
            await callback.answer(" У вас нет прав для изменения настроек", show_alert=True)
            return

        # Получаем текущие настройки
        settings = clan_db.get_clan_join_settings(clan_id)

        text = (
            f"⚙️ <b>Настройки клана {clan.name}</b>\n\n"
            f"📝 <b>Тип вступления:</b> {'Автоматический' if settings.get('join_type') == 'auto' else 'Ручной'}\n"
            f"✅ <b>Автопринятие заявок:</b> {'Включено' if settings.get('auto_accept_requests') else 'Выключено'}\n\n"
            f"<i>При автоматическом режиме пользователи присоединяются сразу.</i>\n"
            f"<i>При ручном - заявки приходят в ЛС для подтверждения.</i>"
        )

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton(
                "🔄 Автоматический режим" if settings.get('join_type') != 'auto' else "✅ Автоматический режим",
                callback_data=clan_cb.new(
                    action='set_join_auto', clan_id=clan_id, user_id=user_id, request_id=0, page=0
                )
            ),
            InlineKeyboardButton(
                "✋ Ручной режим" if settings.get('join_type') != 'manual' else "✅ Ручной режим",
                callback_data=clan_cb.new(
                    action='set_join_manual', clan_id=clan_id, user_id=user_id, request_id=0, page=0
                )
            )
        )

        if settings.get('join_type') == 'manual':
            keyboard.add(
                InlineKeyboardButton(
                    "✅ Вкл. авто-принятие" if not settings.get('auto_accept_requests') else "✅ Авто-принятие вкл.",
                    callback_data=clan_cb.new(
                        action='toggle_auto_accept', clan_id=clan_id, user_id=user_id, request_id=0, page=0
                    )
                )
            )

        keyboard.add(
            InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
                action='manage', clan_id=clan_id, user_id=user_id, request_id=0, page=0
            ))
        )

        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

    async def _set_join_type_auto(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Установить автоматический режим вступления"""
        clan = clan_db.get_clan_by_id(clan_id)
        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            return

        success = clan_db.update_clan_settings(clan_id, join_type='auto')
        if success:
            await callback.answer("✅ Автоматический режим включен", show_alert=True)
            await self._show_clan_settings(callback, clan_db, clan_id, user_id)
        else:
            await callback.answer(" Ошибка изменения настроек", show_alert=True)

    async def _set_join_type_manual(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Установить ручной режим вступления"""
        clan = clan_db.get_clan_by_id(clan_id)
        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            return

        success = clan_db.update_clan_settings(clan_id, join_type='manual')
        if success:
            await callback.answer("✅ Ручной режим включен", show_alert=True)
            await self._show_clan_settings(callback, clan_db, clan_id, user_id)
        else:
            await callback.answer(" Ошибка изменения настроек", show_alert=True)

    async def _toggle_auto_accept(self, callback: CallbackQuery, clan_db: ClanDatabase, clan_id: int, user_id: int):
        """Включить/выключить авто-принятие заявок"""
        clan = clan_db.get_clan_by_id(clan_id)
        if not clan:
            await callback.answer(" Клан не найден", show_alert=True)
            return

        settings = clan_db.get_clan_join_settings(clan_id)
        new_value = not settings.get('auto_accept_requests', False)

        success = clan_db.update_clan_settings(clan_id, auto_accept_requests=new_value)
        if success:
            status = "включено" if new_value else "выключено"
            await callback.answer(f"✅ Авто-принятие {status}", show_alert=True)
            await self._show_clan_settings(callback, clan_db, clan_id, user_id)
        else:
            await callback.answer(" Ошибка изменения настроек", show_alert=True)

    async def _send_request_notification(self, bot, clan_id: int, request_id: int, clan_db: ClanDatabase):
        """Отправить уведомление о заявке в ЛС лидерам"""
        try:
            # Получаем информацию о заявке
            request = clan_db.db.query(ClanJoinRequest).filter(
                ClanJoinRequest.id == request_id
            ).first()

            if not request:
                return

            clan = clan_db.get_clan_by_id(request.clan_id)
            if not clan:
                return

            # Получаем пользователя, подавшего заявку
            from database.crud import UserRepository
            db = SessionLocal()
            user_info = UserRepository.get_user_by_telegram_id(db, request.user_id)
            db.close()

            if not user_info:
                return

            # Отправляем уведомление всем лидерам и заместителям
            members = clan_db.get_clan_members(clan.id)
            for member in members:
                if member.role in ['leader', 'deputy']:
                    try:
                        # Формируем сообщение
                        username = user_info.username or user_info.first_name or f"ID: {user_info.telegram_id}"
                        message_text = (
                            f"📨 <b>Новая заявка в клан {clan.name}</b>\n\n"
                            f"👤 <b>Пользователь:</b> {username}\n"
                        )

                        if request.message:
                            message_text += f"📝 <b>Сообщение:</b> {request.message}\n\n"

                        message_text += (
                            f"📅 <b>Дата:</b> {request.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                            f"Используйте команду /clans для управления заявками."
                        )

                        # Создаем кнопки для быстрого принятия/отклонения
                        keyboard = InlineKeyboardMarkup(row_width=2)
                        keyboard.add(
                            InlineKeyboardButton("✅ Принять", callback_data=clan_cb.new(
                                action='approve_request_from_notification',
                                clan_id=clan.id,
                                user_id=request.user_id,
                                request_id=request.id,
                                page=0
                            )),
                            InlineKeyboardButton("❌ Отклонить", callback_data=clan_cb.new(
                                action='reject_request_from_notification',
                                clan_id=clan.id,
                                user_id=request.user_id,
                                request_id=request.id,
                                page=0
                            ))
                        )

                        # Отправляем сообщение
                        await bot.send_message(
                            chat_id=member.user_id,
                            text=message_text,
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )

                    except Exception as e:
                        logger.error(f"Error sending notification to user {member.user_id}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Error in send_request_notification: {e}")

    async def _handle_join_request_from_notification(self, callback: CallbackQuery, clan_db: ClanDatabase,
                                                     is_approve: bool, request_id: int, user_id: int, clan_id: int):
        """Обработать заявку из уведомления (принятие/отклонение)"""
        # Получаем информацию о заявке
        request = clan_db.db.query(ClanJoinRequest).filter(
            ClanJoinRequest.id == request_id
        ).first()

        if not request:
            await callback.answer(" Заявка не найдена", show_alert=True)
            return

        if is_approve:
            # Добавляем пользователя в клан
            success = clan_db.add_member(clan_id, request.user_id)
            if success:
                request.status = 'approved'
                clan_db.db.commit()

                # Уведомляем пользователя
                try:
                    clan = clan_db.get_clan_by_id(clan_id)
                    await callback.bot.send_message(
                        request.user_id,
                        f"✅ <b>Ваша заявка в клан {clan.name} одобрена!</b>\n\n"
                        f"Добро пожаловать в клан!",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error sending approval notification: {e}")

                await callback.answer("✅ Заявка одобрена!", show_alert=True)

                # Обновляем сообщение с уведомлением
                try:
                    await callback.message.edit_text(
                        f"✅ <b>Заявка одобрена!</b>\n\n"
                        f"Пользователь добавлен в клан.",
                        parse_mode="HTML"
                    )
                except:
                    pass
            else:
                await callback.answer(" Ошибка при одобрении заявки", show_alert=True)
        else:
            request.status = 'rejected'
            clan_db.db.commit()

            # Уведомляем пользователя об отказе
            try:
                clan = clan_db.get_clan_by_id(clan_id)
                await callback.bot.send_message(
                    request.user_id,
                    f"❌ <b>Ваша заявка в клан {clan.name} отклонена.</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error sending rejection notification: {e}")

            await callback.answer(" Заявка отклонена", show_alert=True)

            # Обновляем сообщение с уведомлением
            try:
                await callback.message.edit_text(
                    f"❌ <b>Заявка отклонена</b>\n\n"
                    f"Пользователю отправлено уведомление.",
                    parse_mode="HTML"
                )
            except:
                pass

    async def _send_request_notification(self, bot, clan_id: int, request_id: int, clan_db: ClanDatabase):
        """Отправить уведомление о заявке в ЛС лидерам"""
        try:
            # Получаем информацию о заявке
            request = clan_db.db.query(ClanJoinRequest).filter(
                ClanJoinRequest.id == request_id
            ).first()

            if not request:
                return

            clan = clan_db.get_clan_by_id(request.clan_id)
            if not clan:
                return

            # Получаем пользователя, подавшего заявку
            from database.models import TelegramUser
            user_info = clan_db.db.query(TelegramUser).filter(
                TelegramUser.telegram_id == request.user_id
            ).first()

            if not user_info:
                return

            # Отправляем уведомление всем лидерам и заместителям
            members = clan_db.get_clan_members(clan.id)
            for member in members:
                if member.role in ['leader', 'deputy']:
                    try:
                        # Формируем сообщение
                        username = user_info.username or user_info.first_name or f"ID: {user_info.telegram_id}"
                        message_text = (
                            f"📨 <b>Новая заявка в клан {clan.name}</b>\n\n"
                            f"👤 <b>Пользователь:</b> {username}\n"
                        )

                        if request.message:
                            message_text += f"📝 <b>Сообщение:</b> {request.message}\n\n"

                        message_text += (
                            f"📅 <b>Дата:</b> {request.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                            f"Вы можете принять или отклонить заявку прямо из этого сообщения."
                        )

                        # Создаем кнопки для быстрого принятия/отклонения
                        keyboard = InlineKeyboardMarkup(row_width=2)
                        keyboard.add(
                            InlineKeyboardButton("✅ Принять", callback_data=clan_cb.new(
                                action='approve_request_from_notification',
                                clan_id=clan.id,
                                user_id=request.user_id,
                                request_id=request.id,
                                page=0
                            )),
                            InlineKeyboardButton("❌ Отклонить", callback_data=clan_cb.new(
                                action='reject_request_from_notification',
                                clan_id=clan.id,
                                user_id=request.user_id,
                                request_id=request.id,
                                page=0
                            ))
                        )

                        # Отправляем сообщение
                        await bot.send_message(
                            chat_id=member.user_id,
                            text=message_text,
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )

                    except Exception as e:
                        logger.error(f"Error sending notification to user {member.user_id}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Error in send_request_notification: {e}")


# === Вспомогательные методы ===

    async def _resolve_user_identifier(self, db, identifier: str, message: types.Message = None):
        """Разрешить идентификатор пользователя (ID, @username, контакт)"""
        from database.crud import UserRepository

        # Если это контакт
        if message and message.contact:
            return UserRepository.get_user_by_telegram_id(db, message.contact.user_id)

        # Если это числовой ID
        if identifier.isdigit():
            return UserRepository.get_user_by_telegram_id(db, int(identifier))

        # Если это @username (убираем @)
        if identifier.startswith('@'):
            identifier = identifier[1:]

        # Ищем по username
        user = UserRepository.get_user_by_username(db, identifier)
        if user:
            return user

        # Ищем по first_name/last_name
        if message:
            users = UserRepository.search_users_by_name(db, identifier)
            if users:
                return users[0]

        return None


def register_clan_handlers(dp: Dispatcher, bot_username: str = None):
    """Регистрация обработчиков системы кланов"""
    handler = ClanHandler(bot_username)

    # Команды
    dp.register_message_handler(
        handler.clans_command,
        commands=['clans', 'кланы'],
        state="*"
    )

    # Обработчик start с пригласительной ссылкой
    dp.register_message_handler(
        handler.clan_start_handler,
        commands=['start'],
        state="*"
    )

    # Callback обработчики
    dp.register_callback_query_handler(
        handler.clan_callback_handler,
        clan_cb.filter(),
        state="*"
    )

    # FSM обработчики для создания клана
    dp.register_message_handler(
        handler.process_clan_name,
        state="clan_create_name"
    )
    dp.register_message_handler(
        handler.process_clan_tag,
        state="clan_create_tag"
    )
    dp.register_message_handler(
        handler.process_clan_description,
        state="clan_create_desc"
    )

    # FSM обработчики для поиска
    dp.register_message_handler(
        handler.process_clan_search,
        state="clan_search"
    )

    # FSM обработчики для заявок
    dp.register_message_handler(
        handler.process_apply_message,
        state="clan_apply_message"
    )

    # FSM обработчики для управления (ОБНОВЛЕННЫЕ)
    dp.register_message_handler(
        handler.process_invite_by_id,
        state="clan_invite_by_id"
    )
    dp.register_message_handler(
        handler.process_remove_member,
        state="clan_remove_member"
    )
    dp.register_message_handler(
        handler.process_set_deputy,
        state="clan_set_deputy"
    )
    dp.register_message_handler(
        handler.process_transfer_leadership,
        state="clan_transfer_leadership"
    )
    dp.register_message_handler(
        handler.process_edit_description,
        state="clan_edit_description"
    )
    dp.register_message_handler(
        handler.process_edit_avatar,
        state="clan_edit_avatar"
    )

    # Админские команды
    dp.register_message_handler(
        handler.admin_update_clans_command,
        commands=['updateclans'],
        state="*"
    )
    dp.register_message_handler(
        handler.admin_update_clan_command,
        commands=['updateclan'],
        state="*"
    )

    logger.info("✅ Обработчики системы кланов зарегистрированы")