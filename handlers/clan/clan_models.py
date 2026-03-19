# handlers/clan/clan_models.py
# Этот файл теперь просто переэкспортирует модели из database
from database.clan_models import (
    Clan, ClanMember, ClanInvitation, 
    ClanJoinRequest, ClanSettings
)

# Для обратной совместимости, можно оставить эти экспорты
__all__ = ['Clan', 'ClanMember', 'ClanInvitation', 'ClanJoinRequest', 'ClanSettings']