"""
Конфигурация системы обработки чеков
"""
import os
from typing import List

# ID админ-группы для пересылки чеков
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-5111502237"))

# ИСПРАВЛЕНО: Используем те же ID администраторов, что и в admin_constants.py
ADMIN_IDS = [
    6090751674,
    1054684037,
    8360234437
] + [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Текст для кнопок
CHECK_BUTTONS = {
    "approve": "✅ Выдать",
    "ban": " Забанить",
    "remove_limit": "🔓 Снять лимит"
}

# Сообщения для уведомлений
CHECK_MESSAGES = {
    "user_check_sent": "✅ Чек отправлен на проверку администратору.",
    "user_donate_approved": "✅ Ваш донат успешно подтверждён! Вам начислено {amount} монет",
    "user_status_approved": "✅ Ваш статус успешно активирован!",
    "user_banned": " Ваш чек не прошёл проверку. Доступ к боту заблокирован.",
    "user_limit_removed": "✅ Лимит на передачу монет снят",

    "admin_check_received": "📥 Новый чек от пользователя",
    "admin_donate_given": "✅ Выдано {amount} монет пользователю @{username}",
    "admin_status_given": "✅ Активирован статус {status_name} пользователю @{username}",
    "admin_user_banned": " Пользователь @{username} был забанен за фальшивый чек",
    "admin_limit_removed": "🔓 С пользователя @{username} снят лимит"
}

# Бан-лист
BAN_LIST_FILE = "ban_list.json"