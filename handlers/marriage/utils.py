import html
from typing import Optional

from aiogram import types


def display_name_from_user(u: types.User) -> str:
    if u.first_name:
        return u.first_name
    if u.username:
        return f"@{u.username}"
    return "Anonymous"


def user_link(user_id: int, name: str) -> str:
    safe = html.escape(name or "Anonymous")
    return f'<a href="tg://user?id={user_id}">{safe}</a>'


async def is_chat_admin_or_owner(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.is_chat_admin() or member.is_chat_creator()
    except Exception:
        return False


def role_name_by_key(role_key: str) -> str:
    mapping = {
        "registrar": "Регистратор",
        "groom": "Жених",
        "bride": "Невеста",
        "witness": "Свидетель",
        "witnessess": "Свидетельница",
    }
    return mapping.get(role_key, role_key)


def get_role_emoji(role_key: str) -> str:
    mapping = {
        "groom": "👱‍♂️",
        "bride": "👰‍♀️",
        "witness": "👱‍♂️",
        "witnessess": "👩‍🦰",
        "registrar": "👩‍⚖️",
        "guests": "💃",
    }
    return mapping.get(role_key, "")
