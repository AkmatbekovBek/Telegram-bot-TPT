from datetime import datetime
from typing import List
from database.clan_models import Clan, ClanMember
from database import SessionLocal


def format_clan_info(clan: Clan, user_role: str = None) -> str:
    """Форматировать информацию о клане"""
    db = SessionLocal()

    try:
        from database.models import TelegramUser

        leader = None
        deputy = None

        # Вместо joinedload, получаем участников отдельным запросом
        members = db.query(ClanMember).filter(
            ClanMember.clan_id == clan.id
        ).all()

        members_count = len(members)

        # Ищем лидера и заместителя
        for member in members:
            user = db.query(TelegramUser).filter(
                TelegramUser.telegram_id == member.user_id
            ).first()

            if not user:
                continue

            if member.role == 'leader':
                leader = user
            elif member.role == 'deputy':
                deputy = user

        # Формируем текст
        text = f"🏰 <b>{clan.name}</b> [{clan.tag}]\n\n"

        if clan.avatar:
            text += "🖼️ <i>У клана есть аватар</i>\n\n"

        if clan.description:
            text += f"📝 <b>Описание:</b> {clan.description}\n"

        text += f"👥 <b>Участников:</b> {members_count}\n"
        text += f"💰 <b>Общий капитал:</b> {clan.total_coins:,} Монет\n"
        text += f"📅 <b>Создан:</b> {clan.created_at.strftime('%d.%m.%Y')}\n\n"

        if leader:
            # Используем актуальный username или имя
            leader_name = leader.username or leader.first_name or f"ID: {leader.telegram_id}"
            text += f"👑 <b>Лидер:</b> {leader_name}\n"

        if deputy:
            deputy_name = deputy.username or deputy.first_name or f"ID: {deputy.telegram_id}"
            text += f"⭐ <b>Заместитель:</b> {deputy_name}\n"

        if user_role:
            text += f"\n🎭 <b>Ваша роль:</b> {get_role_name(user_role)}"

        return text

    finally:
        db.close()


def format_member_info(member: ClanMember) -> str:
    """Форматировать информацию об участнике"""
    db = SessionLocal()
    try:
        from database.models import TelegramUser
        user = db.query(TelegramUser).filter(
            TelegramUser.telegram_id == member.user_id
        ).first()

        if not user:
            return f"ID: {member.user_id} (пользователь не найден)"

        username = user.username or user.first_name or f"ID: {user.telegram_id}"
        role_icon = "👑" if member.role == 'leader' else "⭐" if member.role == 'deputy' else "👤"

        text = f"{role_icon} <b>{username}</b>\n"
        text += f"🎭 <b>Роль:</b> {get_role_name(member.role)}\n"
        text += f"💰 <b>Вклад:</b> {member.coins_contributed:,} Монет\n"
        text += f"📅 <b>В клане с:</b> {member.joined_at.strftime('%d.%m.%Y')}"

        return text
    finally:
        db.close()


def format_clan_top(clans: List[Clan], start_rank: int = 1) -> str:
    """Форматировать топ кланов"""
    if not clans:
        return "🏆 <b>Топ кланов</b>\n\nПока нет кланов."

    text = "🏆 <b>ТОП КЛАНОВ</b>\n\n"

    for idx, clan in enumerate(clans, start=start_rank):
        # Получаем количество участников отдельным запросом
        db = SessionLocal()
        members_count = db.query(ClanMember).filter(
            ClanMember.clan_id == clan.id
        ).count()
        db.close()

        # Определяем эмодзи для места
        if idx == 1:
            place_emoji = "🥇"
        elif idx == 2:
            place_emoji = "🥈"
        elif idx == 3:
            place_emoji = "🥉"
        else:
            place_emoji = f"{idx}."

        text += f"{place_emoji} <b>{clan.name}</b> [{clan.tag}]\n"
        text += f"   👥 Участников: {members_count}\n"
        text += f"   💰 Капитал: {clan.total_coins:,} Монет\n\n"

    return text


def get_role_name(role: str) -> str:
    """Получить читаемое название роли"""
    role_names = {
        'leader': 'Лидер',
        'deputy': 'Заместитель',
        'member': 'Участник'
    }
    return role_names.get(role, role)


def format_clan_short_info(clan: Clan) -> str:
    """Краткая информация о клане"""
    db = SessionLocal()
    members_count = db.query(ClanMember).filter(
        ClanMember.clan_id == clan.id
    ).count()
    db.close()

    return f"🏰 {clan.name} [{clan.tag}] | 👥 {members_count} | 💰 {clan.total_coins:,}"


def format_invitation_info(invitation) -> str:
    """Информация о приглашении"""
    clan = invitation.clan
    db = SessionLocal()
    members_count = db.query(ClanMember).filter(
        ClanMember.clan_id == clan.id
    ).count()
    db.close()

    text = f"📨 <b>Приглашение в клан {clan.name}</b>\n\n"
    text += f"🏷️ <b>Тег:</b> {clan.tag}\n"
    text += f"📝 <b>Описание:</b> {clan.description[:100] if clan.description else 'Нет описания'}...\n"
    text += f"👥 <b>Участников:</b> {members_count}\n"
    text += f"💰 <b>Капитал:</b> {clan.total_coins:,}"
    return text


def format_join_request_info(request) -> str:
    """Информация о заявке на вступление"""
    db = SessionLocal()
    try:
        from database.models import TelegramUser
        user = db.query(TelegramUser).filter(
            TelegramUser.telegram_id == request.user_id
        ).first()
    finally:
        db.close()

    username = user.username if user else f"ID: {request.user_id}"

    text = f"📝 <b>Заявка от {username}</b>\n\n"

    if request.message:
        text += f"💬 <b>Сообщение:</b> {request.message}\n\n"

    text += f"📅 <b>Дата:</b> {request.created_at.strftime('%d.%m.%Y %H:%M')}"

    return text


def format_time_since_update(last_updated: datetime) -> str:
    """Форматировать время с последнего обновления"""
    if not last_updated:
        return "никогда"

    delta = datetime.now() - last_updated

    if delta.days > 0:
        return f"{delta.days} дн. назад"
    elif delta.seconds // 3600 > 0:
        return f"{delta.seconds // 3600} ч. назад"
    elif delta.seconds // 60 > 0:
        return f"{delta.seconds // 60} мин. назад"
    else:
        return "только что"