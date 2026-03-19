from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def start_menu_keyboard():
    """Клавиатура для главного меню при старте"""
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Основные кнопки с квадратными скобками
    keyboard.add(
        InlineKeyboardButton("Профиль", callback_data="profile"),
        InlineKeyboardButton("Донат", callback_data="donate"),
        InlineKeyboardButton("Ссылки", callback_data="links"),
        InlineKeyboardButton("Магазин", callback_data="shop"),
    )

    # Кнопки
    keyboard.row(InlineKeyboardButton("кланы", callback_data="clans"))

    # Реферальная ссылка в фигурных скобках
    keyboard.row(InlineKeyboardButton("реферальная ссылка", callback_data="reference"))

    return keyboard