from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def wedding_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура строго по ТЗ."""
    kb = InlineKeyboardMarkup(row_width=3)

    # 1 ряд
    kb.row(
        InlineKeyboardButton(text="Регистратор", callback_data="marriage:role:registrar"),
        InlineKeyboardButton(text="Жених", callback_data="marriage:role:groom"),
        InlineKeyboardButton(text="Невеста", callback_data="marriage:role:bride"),
    )

    # 2 ряд
    kb.row(
        InlineKeyboardButton(text="Свидетель", callback_data="marriage:role:witness"),
        InlineKeyboardButton(text="Свидетельница", callback_data="marriage:role:witnessess"),
    )

    # 3 ряд
    kb.row(
        InlineKeyboardButton(text="Поженить", callback_data="marriage:marry"),
        InlineKeyboardButton(text="Подпись", callback_data="marriage:sign"),
        InlineKeyboardButton(text="Гости", callback_data="marriage:guest"),
    )

    # 4 ряд
    kb.row(
        InlineKeyboardButton(text="Отменить свадьбу", callback_data="marriage:cancel"),
    )

    return kb


def divorce_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура развода."""
    kb = InlineKeyboardMarkup(row_width=2)

    # 1 ряд - Присяжные
    kb.row(
        InlineKeyboardButton(text="Присяжные", callback_data="divorce:role:juror"),
    )

    # 2 ряд - Судья (кнопки под ним)
    kb.row(
        InlineKeyboardButton(text="Судья", callback_data="divorce:role:judge"),
        InlineKeyboardButton(text="Подпись", callback_data="divorce:sign"),
        InlineKeyboardButton(text="Развести", callback_data="divorce:process"),
    )

    # 3 ряд - Отменить
    kb.row(
        InlineKeyboardButton(text="Отменить развод", callback_data="divorce:cancel"),
    )

    return kb
