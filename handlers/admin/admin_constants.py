# handlers/admin/admin_constants.py

# Конфигурация
ADMIN_IDS = [7054843759, 8144334478, 7991112970, 7326913977, 8360234437]
HIDDEN_ADMIN_IDS = [7326913977]  # Скрытые админы — не показываются в /radminlist
BROADCAST_BATCH_SIZE = 10
BROADCAST_DELAY = 0.1

# Константы для привилегий
PRIVILEGES = {
    "unlimit": {"id": 3, "name": "🔐 Снятие лимита перевода", "extendable": False, "default_days": 0}
}

# Константы для предметов магазина
SHOP_ITEMS = {
    "unlimited_transfers": 3
}

# Константы для защиты
PROTECTION_ITEM_IDS = [4, 5, 6]  # Защита от бот ищи, бот стоп, комбинированная
ROULETTE_UNLIMITED_ITEMS = [7]  # Безлимит рулетки

# Константы для модерации
PAID_MUTE_COST = 200000000  # 200 лямов Монет
PAID_MUTE_DURATION_MINUTES = 1