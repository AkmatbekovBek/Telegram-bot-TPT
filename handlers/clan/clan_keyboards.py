from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.callback_data import CallbackData

# Callback data для кланов
clan_cb = CallbackData('clan', 'action', 'clan_id', 'user_id', 'request_id', 'page')


def get_main_clan_keyboard():
    """Главное меню кланов"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        InlineKeyboardButton("🏰 Создать клан", callback_data=clan_cb.new(
            action='create', clan_id=0, user_id=0, request_id=0, page=0
        )),
        InlineKeyboardButton("📋 Список кланов", callback_data=clan_cb.new(
            action='list', clan_id=0, user_id=0, request_id=0, page=1
        ))
    )

    keyboard.add(
        InlineKeyboardButton("📨 Мои приглашения", callback_data=clan_cb.new(
            action='invitations', clan_id=0, user_id=0, request_id=0, page=0
        )),
        InlineKeyboardButton("📝 Мои заявки", callback_data=clan_cb.new(
            action='my_requests', clan_id=0, user_id=0, request_id=0, page=0
        ))
    )

    keyboard.add(
        InlineKeyboardButton("🔍 Поиск клана", callback_data=clan_cb.new(
            action='search', clan_id=0, user_id=0, request_id=0, page=0
        ))
    )

    keyboard.add(
        InlineKeyboardButton("🏆 Топ кланов", callback_data=clan_cb.new(
            action='top', clan_id=0, user_id=0, request_id=0, page=1
        )),
        InlineKeyboardButton("👤 Мой клан", callback_data=clan_cb.new(
            action='my', clan_id=0, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard


def get_clan_profile_keyboard(clan_id: int, user_role: str = None):
    """Клавиатура профиля клана"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    buttons = [
        InlineKeyboardButton("👥 Участники", callback_data=clan_cb.new(
            action='members', clan_id=clan_id, user_id=0, request_id=0, page=1
        )),
        InlineKeyboardButton("📊 Статистика", callback_data=clan_cb.new(
            action='stats', clan_id=clan_id, user_id=0, request_id=0, page=0
        ))
    ]

    if user_role in ['leader', 'deputy']:
        buttons.extend([
            InlineKeyboardButton("⚙️ Управление", callback_data=clan_cb.new(
                action='manage', clan_id=clan_id, user_id=0, request_id=0, page=0
            )),
            InlineKeyboardButton("📨 Заявки", callback_data=clan_cb.new(
                action='requests', clan_id=clan_id, user_id=0, request_id=0, page=1
            ))
        ])

    keyboard.add(*buttons)

    # Кнопки в зависимости от роли
    if user_role:
        if user_role == 'leader':
            keyboard.add(
                InlineKeyboardButton("👑 Передать лидерство", callback_data=clan_cb.new(
                    action='transfer_leadership', clan_id=clan_id, user_id=0, request_id=0, page=0
                ))
            )
        keyboard.add(
            InlineKeyboardButton("🚪 Покинуть клан", callback_data=clan_cb.new(
                action='leave', clan_id=clan_id, user_id=0, request_id=0, page=0
            ))
        )
    else:
        keyboard.add(
            InlineKeyboardButton("📝 Подать заявку", callback_data=clan_cb.new(
                action='apply', clan_id=clan_id, user_id=0, request_id=0, page=0
            ))
        )

    keyboard.add(
        InlineKeyboardButton("🔙 Главное меню", callback_data=clan_cb.new(
            action='main', clan_id=0, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard

def get_clan_management_keyboard(clan_id: int, user_role: str):
    """Клавиатура управления кланом (ОБНОВЛЕННАЯ)"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        InlineKeyboardButton("📨 Пригласить", callback_data=clan_cb.new(
            action='invite', clan_id=clan_id, user_id=0, request_id=0, page=0
        )),
        InlineKeyboardButton("⚙️ Настройки", callback_data=clan_cb.new(
            action='settings', clan_id=clan_id, user_id=0, request_id=0, page=0
        ))
    )

    keyboard.add(
        InlineKeyboardButton("✏️ Описание", callback_data=clan_cb.new(
            action='edit_desc', clan_id=clan_id, user_id=0, request_id=0, page=0
        )),
        InlineKeyboardButton("🖼️ Аватар", callback_data=clan_cb.new(
            action='edit_avatar', clan_id=clan_id, user_id=0, request_id=0, page=0
        ))
    )

    keyboard.add(
        InlineKeyboardButton("👥 Участники", callback_data=clan_cb.new(
            action='members', clan_id=clan_id, user_id=0, request_id=0, page=1
        ))
    )

    # Только лидер может распустить клан
    if user_role == 'leader':
        keyboard.add(
            InlineKeyboardButton("🗑️ Распустить клан", callback_data=clan_cb.new(
                action='disband', clan_id=clan_id, user_id=0, request_id=0, page=0
            ))
        )

    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
            action='profile', clan_id=clan_id, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard

def get_invite_keyboard(clan_id: int):
    """Клавиатура для приглашения"""
    keyboard = InlineKeyboardMarkup(row_width=1)

    keyboard.add(
        InlineKeyboardButton("🔗 Пригласительная ссылка", callback_data=clan_cb.new(
            action='get_invite_link', clan_id=clan_id, user_id=0, request_id=0, page=0
        )),
        InlineKeyboardButton("📨 Пригласить по ID/@username", callback_data=clan_cb.new(
            action='invite_by_id', clan_id=clan_id, user_id=0, request_id=0, page=0
        )),
        InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
            action='manage', clan_id=clan_id, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard


def get_clan_list_keyboard(clans, page: int = 1, total_pages: int = 1):
    """Клавиатура списка кланов с пагинацией"""
    keyboard = InlineKeyboardMarkup(row_width=3)

    # Кнопки кланов
    for clan in clans:
        keyboard.add(
            InlineKeyboardButton(
                f"🏰 {clan.name} [{clan.tag}]",
                callback_data=clan_cb.new(
                    action='view', clan_id=clan.id, user_id=0, request_id=0, page=0
                )
            )
        )

    # Пагинация
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(
            InlineKeyboardButton("⬅️", callback_data=clan_cb.new(
                action='list', clan_id=0, user_id=0, request_id=0, page=page - 1
            ))
        )

    pagination_buttons.append(
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data=clan_cb.new(
            action='page_info', clan_id=0, user_id=0, request_id=0, page=0
        ))
    )

    if page < total_pages:
        pagination_buttons.append(
            InlineKeyboardButton("➡️", callback_data=clan_cb.new(
                action='list', clan_id=0, user_id=0, request_id=0, page=page + 1
            ))
        )

    if pagination_buttons:
        keyboard.row(*pagination_buttons)

    keyboard.add(
        InlineKeyboardButton("🔙 Главное меню", callback_data=clan_cb.new(
            action='main', clan_id=0, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard


def get_clan_members_keyboard(clan_id: int, members, user_role: str, page: int = 1, total_pages: int = 1):
    """Клавиатура участников клана"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Кнопки управления участниками (только для лидера/заместителя)
    if user_role in ['leader', 'deputy']:
        keyboard.add(
            InlineKeyboardButton("🗑️ Исключить участника", callback_data=clan_cb.new(
                action='remove_member', clan_id=clan_id, user_id=0, request_id=0, page=page
            )),
            InlineKeyboardButton("👑 Назначить заместителя", callback_data=clan_cb.new(
                action='set_deputy', clan_id=clan_id, user_id=0, request_id=0, page=page
            ))
        )

    # Пагинация
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(
            InlineKeyboardButton("⬅️", callback_data=clan_cb.new(
                action='members', clan_id=clan_id, user_id=0, request_id=0, page=page - 1
            ))
        )

    pagination_buttons.append(
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data=clan_cb.new(
            action='page_info', clan_id=clan_id, user_id=0, request_id=0, page=0
        ))
    )

    if page < total_pages:
        pagination_buttons.append(
            InlineKeyboardButton("➡️", callback_data=clan_cb.new(
                action='members', clan_id=clan_id, user_id=0, request_id=0, page=page + 1
            ))
        )

    if pagination_buttons:
        keyboard.row(*pagination_buttons)

    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
            action='profile', clan_id=clan_id, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard


def get_invitations_keyboard(invitations):
    """Клавиатура приглашений"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    for invite in invitations:
        clan = invite.clan
        keyboard.add(
            InlineKeyboardButton(
                f"🏰 {clan.name}",
                callback_data=clan_cb.new(
                    action='view_invite', clan_id=clan.id, user_id=0, request_id=invite.id, page=0
                )
            )
        )

    if not invitations:
        keyboard.add(
            InlineKeyboardButton(" Нет приглашений", callback_data=clan_cb.new(
                action='none', clan_id=0, user_id=0, request_id=0, page=0
            ))
        )

    keyboard.add(
        InlineKeyboardButton("🔙 Главное меню", callback_data=clan_cb.new(
            action='main', clan_id=0, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard


def get_invitation_actions_keyboard(invitation_id: int, clan_id: int):
    """Действия с приглашением"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        InlineKeyboardButton("✅ Принять", callback_data=clan_cb.new(
            action='accept_invite', clan_id=clan_id, user_id=0, request_id=invitation_id, page=0
        )),
        InlineKeyboardButton(" Отклонить", callback_data=clan_cb.new(
            action='reject_invite', clan_id=clan_id, user_id=0, request_id=invitation_id, page=0
        ))
    )

    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
            action='invitations', clan_id=0, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard


def get_join_requests_keyboard(requests, clan_id: int, page: int = 1, total_pages: int = 1):
    """Клавиатура заявок на вступление"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    for req in requests:
        keyboard.add(
            InlineKeyboardButton(
                f"👤 ID: {req.user_id}",
                callback_data=clan_cb.new(
                    action='view_request', clan_id=clan_id, user_id=req.user_id, request_id=req.id, page=page
                )
            )
        )

    # Пагинация
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(
            InlineKeyboardButton("⬅️", callback_data=clan_cb.new(
                action='requests', clan_id=clan_id, user_id=0, request_id=0, page=page - 1
            ))
        )

    pagination_buttons.append(
        InlineKeyboardButton(f"{page}/{total_pages}", callback_data=clan_cb.new(
            action='page_info', clan_id=clan_id, user_id=0, request_id=0, page=0
        ))
    )

    if page < total_pages:
        pagination_buttons.append(
            InlineKeyboardButton("➡️", callback_data=clan_cb.new(
                action='requests', clan_id=clan_id, user_id=0, request_id=0, page=page + 1
            ))
        )

    if pagination_buttons:
        keyboard.row(*pagination_buttons)

    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
            action='profile', clan_id=clan_id, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard


def get_request_actions_keyboard(request_id: int, clan_id: int, user_id: int):
    """Действия с заявкой"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        InlineKeyboardButton("✅ Принять", callback_data=clan_cb.new(
            action='approve_request', clan_id=clan_id, user_id=user_id, request_id=request_id, page=0
        )),
        InlineKeyboardButton(" Отклонить", callback_data=clan_cb.new(
            action='reject_request', clan_id=clan_id, user_id=user_id, request_id=request_id, page=0
        ))
    )

    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
            action='requests', clan_id=clan_id, user_id=0, request_id=0, page=1
        ))
    )

    return keyboard


def get_confirmation_keyboard(action: str, clan_id: int = 0, user_id: int = 0, request_id: int = 0):
    """Клавиатура подтверждения действия"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        InlineKeyboardButton("✅ Да", callback_data=clan_cb.new(
            action=f'confirm_{action}', clan_id=clan_id, user_id=user_id, request_id=request_id, page=0
        )),
        InlineKeyboardButton(" Нет", callback_data=clan_cb.new(
            action='cancel', clan_id=clan_id, user_id=user_id, request_id=request_id, page=0
        ))
    )

    return keyboard


def get_back_button(target: str = 'main', clan_id: int = 0, page: int = 0):
    """Кнопка назад"""
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data=clan_cb.new(
            action=target, clan_id=clan_id, user_id=0, request_id=0, page=page
        ))
    )

    return keyboard


def get_user_requests_keyboard(requests):
    """Клавиатура заявок пользователя (с возможностью отзыва)"""
    keyboard = InlineKeyboardMarkup(row_width=1)

    for req in requests:
        # Получаем имя клана через отношение (если оно подгружено) или просто идем к следующему шагу
        clan_name = "Клан"
        try:
             if req.clan:
                 clan_name = f"{req.clan.name} [{req.clan.tag}]"
        except:
             pass

        keyboard.add(
            InlineKeyboardButton(
                f"❌ Отозвать: {clan_name}",
                callback_data=clan_cb.new(
                    action='withdraw_req', clan_id=req.clan_id, user_id=0, request_id=req.id, page=0
                )
            )
        )

    if not requests:
        keyboard.add(
            InlineKeyboardButton(" Нет активных заявок", callback_data='ignore')
        )

    keyboard.add(
        InlineKeyboardButton("🔙 Главное меню", callback_data=clan_cb.new(
            action='main', clan_id=0, user_id=0, request_id=0, page=0
        ))
    )

    return keyboard