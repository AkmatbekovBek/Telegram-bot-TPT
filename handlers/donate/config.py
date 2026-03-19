import logging
from datetime import datetime

# Конфигурация статусов ТОЧНО по ТЗ
STATUSES = [
    {
        "id": 1,
        "name": "обычный",
        "icon": "🐾",
        "price_rub": 0,
        "price_tenge": 0,
        "bonus_amount": 25000,
        "duration_days": 0,  # бессрочный
        "color": "#808080"
    },
    {
        "id": 2,
        "name": "бронза",
        "icon": "🌑",
        "price_rub": 1000,
        "price_tenge": 6500,
        "bonus_amount": 500_000,
        "duration_days": 30,
        "color": "#CD7F32"
    },
    {
        "id": 3,
        "name": "платина",
        "icon": "💰",
        "price_rub": 2500,
        "price_tenge": 16250,
        "bonus_amount": 1_500_000,
        "duration_days": 30,
        "color": "#E5E4E2"
    },
    {
        "id": 4,
        "name": "золото",
        "icon": "🥇",
        "price_rub": 5000,
        "price_tenge": 32500,
        "bonus_amount": 4_500_000,
        "duration_days": 30,
        "color": "#FFD700"
    },
    {
        "id": 5,
        "name": "бриллиант",
        "icon": "💎",
        "price_rub": 8000,
        "price_tenge": 52000,
        "bonus_amount": 10_000_000,
        "duration_days": 30,
        "color": "#B9F2FF"
    }
]

# Конфигурация бонусов
BONUS_COOLDOWN_HOURS = 24
SUPPORT_USERNAME: str = "@DanuGylbanu"
CHANNEL_USERNAME = "@@newsssm"
CHANNEL_LINK = "https://t.me/@newsssm"
# Конфигурация пакетов Монет
COIN_PACKAGES = [
    {"amount": 250_000, "rub_price": 100, "tenge_price": 650},
    {"amount": 600_000, "rub_price": 200, "tenge_price": 1300},
    {"amount": 1_300_000, "rub_price": 400, "tenge_price": 2600},
    {"amount": 2_800_000, "rub_price": 700, "tenge_price": 4550},
    {"amount": 6_000_000, "rub_price": 1200, "tenge_price": 7800},
    {"amount": 14_000_000, "rub_price": 2000, "tenge_price": 13000},
    {"amount": 28_000_000, "rub_price": 3500, "tenge_price": 22800},
    {"amount": 60_000_000, "rub_price": 6000, "tenge_price": 39150},
    {"amount": 110_000_000, "rub_price": 7500, "tenge_price": 49000},
]

logger = logging.getLogger(__name__)