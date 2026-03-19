import logging
import secrets
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_
from datetime import datetime, timedelta

from database.clan_models import Clan, ClanMember, ClanInvitation, ClanJoinRequest, ClanSettings, ClanInviteCode
from database.models import TelegramUser

logger = logging.getLogger(__name__)


class ClanDatabase:
    """Класс для работы с БД кланов"""

    def __init__(self, db: Session):
        self.db = db
        self.request_model = ClanJoinRequest
        self.invitation_model = ClanInvitation

    # === CRUD для кланов ===

    def create_clan(self, name: str, tag: str, description: str, creator_id: int, avatar: str = None) -> Optional[Clan]:
        """Создать новый клан"""
        try:
            # Проверяем уникальность имени и тега
            if self.db.query(Clan).filter(Clan.name == name).first():
                raise ValueError("Клан с таким именем уже существует")

            if self.db.query(Clan).filter(Clan.tag == tag).first():
                raise ValueError("Клан с таким тегом уже существует")

            # Получаем стоимость создания
            settings = self.get_clan_settings()

            # Создаем клан
            clan = Clan(
                name=name,
                tag=tag,
                description=description,
                avatar=avatar,
                total_coins=0,
                last_updated=datetime.now(),
                is_active=True
            )
            self.db.add(clan)
            self.db.flush()  # Получаем ID клана

            # Добавляем создателя как лидера
            leader = ClanMember(
                clan_id=clan.id,
                user_id=creator_id,
                role='leader',
                coins_contributed=0,
                joined_at=datetime.now()
            )
            self.db.add(leader)

            # Обновляем капитал клана
            self._update_clan_total_coins(clan.id)

            self.db.commit()
            return clan

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating clan: {e}")
            return None

    def get_clan_by_id(self, clan_id: int) -> Optional[Clan]:
        """Получить клан по ID"""
        return self.db.query(Clan).filter(Clan.id == clan_id).first()

    def get_clan_by_name(self, name: str) -> Optional[Clan]:
        """Получить клан по имени"""
        return self.db.query(Clan).filter(Clan.name == name).first()

    def get_clan_by_tag(self, tag: str) -> Optional[Clan]:
        """Получить клан по тегу"""
        return self.db.query(Clan).filter(Clan.tag == tag).first()

    def update_clan(self, clan_id: int, **kwargs) -> bool:
        """Обновить информацию о клане"""
        try:
            clan = self.get_clan_by_id(clan_id)
            if not clan:
                return False

            for key, value in kwargs.items():
                if hasattr(clan, key):
                    setattr(clan, key, value)

            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating clan: {e}")
            return False

    def delete_clan(self, clan_id: int) -> bool:
        """Удалить клан"""
        try:
            clan = self.get_clan_by_id(clan_id)
            if not clan:
                return False

            self.db.delete(clan)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting clan: {e}")
            return False

    # === Участники клана ===

    def add_member(self, clan_id: int, user_id: int, role: str = 'member') -> bool:
        """Добавить участника в клан"""
        try:
            # Проверяем, не состоит ли уже пользователь в клане
            existing = self.db.query(ClanMember).filter(
                ClanMember.user_id == user_id,
                ClanMember.clan_id == clan_id
            ).first()

            if existing:
                return False

            member = ClanMember(
                clan_id=clan_id,
                user_id=user_id,
                role=role,
                coins_contributed=0,
                joined_at=datetime.now()
            )
            self.db.add(member)

            # Обновляем общее количество Монет клана
            self._update_clan_total_coins(clan_id)

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error adding member: {e}")
            return False

    def remove_member(self, clan_id: int, user_id: int) -> bool:
        """Удалить участника из клана"""
        try:
            member = self.db.query(ClanMember).filter(
                ClanMember.clan_id == clan_id,
                ClanMember.user_id == user_id
            ).first()

            if not member:
                return False

            # Если это последний участник или лидер - удаляем клан
            members_count = self.db.query(ClanMember).filter(
                ClanMember.clan_id == clan_id
            ).count()

            if members_count == 1 or member.role == 'leader':
                return self.delete_clan(clan_id)

            self.db.delete(member)

            # Обновляем общее количество Монет клана
            self._update_clan_total_coins(clan_id)

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error removing member: {e}")
            return False

    def get_user_balance(self, user_id: int) -> int:
        """Получить баланс пользователя"""
        user = self.db.query(TelegramUser).filter(TelegramUser.telegram_id == user_id).first()

        if user and hasattr(user, 'coins'):
            try:
                coins_value = user.coins
                if coins_value is not None:
                    if hasattr(coins_value, 'to_integral_value'):
                        return int(coins_value.to_integral_value())
                    return int(coins_value)
            except (ValueError, TypeError):
                return 0
        return 0

    def get_clan_members(self, clan_id: int) -> List[ClanMember]:
        """Получить всех участников клана"""
        return self.db.query(ClanMember).filter(
            ClanMember.clan_id == clan_id
        ).all()

    def get_user_clan(self, user_id: int) -> Optional[Clan]:
        """Получить клан пользователя"""
        member = self.db.query(ClanMember).filter(
            ClanMember.user_id == user_id
        ).first()

        if member:
            return self.get_clan_by_id(member.clan_id)
        return None

    def get_user_role(self, clan_id: int, user_id: int) -> Optional[str]:
        """Получить роль пользователя в клане"""
        member = self.db.query(ClanMember).filter(
            ClanMember.clan_id == clan_id,
            ClanMember.user_id == user_id
        ).first()

        return member.role if member else None

    def update_member_role(self, clan_id: int, user_id: int, new_role: str) -> bool:
        """Изменить роль участника"""
        try:
            member = self.db.query(ClanMember).filter(
                ClanMember.clan_id == clan_id,
                ClanMember.user_id == user_id
            ).first()

            if not member:
                return False

            # Если назначаем нового лидера, нужно снять старого
            if new_role == 'leader':
                old_leader = self.db.query(ClanMember).filter(
                    ClanMember.clan_id == clan_id,
                    ClanMember.role == 'leader'
                ).first()

                if old_leader:
                    old_leader.role = 'deputy' if old_leader.user_id != user_id else 'leader'

            member.role = new_role
            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating member role: {e}")
            return False

    # === Приглашения (по ID и username) ===

    def create_invitation(self, clan_id: int, from_user_id: int, to_user_id: int) -> bool:
        """Создать приглашение в клан"""
        try:
            # Проверяем, не состоит ли уже пользователь в клане
            existing_member = self.db.query(ClanMember).filter(
                ClanMember.user_id == to_user_id,
                ClanMember.clan_id == clan_id
            ).first()

            if existing_member:
                return False

            # Проверяем, нет ли уже приглашения
            existing_invite = self.db.query(ClanInvitation).filter(
                ClanInvitation.clan_id == clan_id,
                ClanInvitation.to_user_id == to_user_id,
                ClanInvitation.status == 'pending'
            ).first()

            if existing_invite:
                return False

            invitation = ClanInvitation(
                clan_id=clan_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                status='pending',
                created_at=datetime.now()
            )
            self.db.add(invitation)
            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating invitation: {e}")
            return False

    def get_user_invitations(self, user_id: int) -> List[ClanInvitation]:
        """Получить приглашения пользователя"""
        return self.db.query(ClanInvitation).filter(
            ClanInvitation.to_user_id == user_id,
            ClanInvitation.status == 'pending'
        ).all()

    def accept_invitation(self, invitation_id: int) -> bool:
        """Принять приглашение"""
        try:
            invitation = self.db.query(ClanInvitation).filter(
                ClanInvitation.id == invitation_id
            ).first()

            if not invitation:
                return False

            # Добавляем пользователя в клан
            success = self.add_member(invitation.clan_id, invitation.to_user_id)

            if success:
                invitation.status = 'accepted'
                self.db.commit()
                return True

            return False

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error accepting invitation: {e}")
            return False

    def reject_invitation(self, invitation_id: int) -> bool:
        """Отклонить приглашение"""
        try:
            invitation = self.db.query(ClanInvitation).filter(
                ClanInvitation.id == invitation_id
            ).first()

            if not invitation:
                return False

            invitation.status = 'rejected'
            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error rejecting invitation: {e}")
            return False

    # === Пригласительные коды (ссылки) ===

    def generate_invite_code(self, clan_id: int, creator_id: int, expires_hours: int = 24) -> Optional[ClanInviteCode]:
        """Сгенерировать код приглашения"""
        try:
            # Генерируем уникальный код
            while True:
                code = secrets.token_urlsafe(8)[:10].upper()
                existing = self.db.query(ClanInviteCode).filter(
                    ClanInviteCode.code == code
                ).first()
                if not existing:
                    break

            # Создаем запись
            invite_code = ClanInviteCode(
                clan_id=clan_id,
                creator_id=creator_id,
                code=code,
                expires_at=datetime.now() + timedelta(hours=expires_hours),
                is_active=True
            )
            self.db.add(invite_code)
            self.db.commit()
            return invite_code

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error generating invite code: {e}")
            return None

    def get_invite_code(self, code: str) -> Optional[ClanInviteCode]:
        """Получить информацию о коде приглашения"""
        return self.db.query(ClanInviteCode).filter(
            ClanInviteCode.code == code,
            ClanInviteCode.is_active == True,
            ClanInviteCode.expires_at > datetime.now()
        ).first()

    def use_invite_code(self, code: str, user_id: int) -> bool:
        """Использовать код приглашения"""
        try:
            invite_code = self.get_invite_code(code)
            if not invite_code:
                return False

            # Добавляем пользователя в клан
            success = self.add_member(invite_code.clan_id, user_id)
            if success:
                invite_code.is_active = False
                invite_code.used_at = datetime.now()
                invite_code.used_by_id = user_id
                self.db.commit()
                return True

            return False

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error using invite code: {e}")
            return False

    def get_clan_invite_codes(self, clan_id: int) -> List[ClanInviteCode]:
        """Получить все активные коды приглашений клана"""
        return self.db.query(ClanInviteCode).filter(
            ClanInviteCode.clan_id == clan_id,
            ClanInviteCode.is_active == True,
            ClanInviteCode.expires_at > datetime.now()
        ).all()

    # === Заявки на вступление ===

    def create_join_request(self, clan_id: int, user_id: int, message: str = None) -> bool:
        """Создать заявку на вступление"""
        try:
            # Проверяем, не состоит ли уже пользователь в клане
            existing_member = self.db.query(ClanMember).filter(
                ClanMember.user_id == user_id,
                ClanMember.clan_id == clan_id
            ).first()

            if existing_member:
                return False

            # Проверяем, нет ли уже активной заявки
            existing_request = self.db.query(ClanJoinRequest).filter(
                ClanJoinRequest.clan_id == clan_id,
                ClanJoinRequest.user_id == user_id,
                ClanJoinRequest.status == 'pending'
            ).first()

            if existing_request:
                return False

            request = ClanJoinRequest(
                clan_id=clan_id,
                user_id=user_id,
                message=message,
                status='pending',
                created_at=datetime.now()
            )
            self.db.add(request)
            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating join request: {e}")
            return False

    def get_clan_join_requests(self, clan_id: int) -> List[ClanJoinRequest]:
        """Получить заявки на вступление в клан"""
        requests = self.db.query(ClanJoinRequest).filter(
            ClanJoinRequest.clan_id == clan_id,
            ClanJoinRequest.status == 'pending'
        ).all()
        logger.info(f"Found {len(requests)} pending requests for clan {clan_id}")
        return requests

    def process_join_request(self, request_id: int, approve: bool) -> bool:
        """Обработать заявку на вступление"""
        try:
            request = self.db.query(ClanJoinRequest).filter(
                ClanJoinRequest.id == request_id
            ).first()

            if not request:
                return False

            if approve:
                # Добавляем пользователя в клан
                success = self.add_member(request.clan_id, request.user_id)
                if success:
                    request.status = 'approved'
            else:
                request.status = 'rejected'

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error processing join request: {e}")
            return False

    def get_user_pending_requests(self, user_id: int) -> List[ClanJoinRequest]:
        """Получить активные заявки пользователя"""
        # Используем self.request_model, так как он определен в __init__
        requests = self.db.query(self.request_model).filter(
            self.request_model.user_id == user_id,
            self.request_model.status == 'pending'
        ).all()
        logger.info(f"Found {len(requests)} pending requests for user {user_id}")
        return requests

    def delete_join_request(self, request_id: int, user_id: int) -> bool:
        """Удалить (отозвать) заявку на вступление"""
        try:
            request = self.db.query(self.request_model).filter(
                self.request_model.id == request_id,
                self.request_model.user_id == user_id,
                self.request_model.status == 'pending'
            ).first()

            if not request:
                return False

            self.db.delete(request)
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting join request: {e}")
            self.db.rollback()
            return False

    # === Топ кланов ===

    def get_top_clans(self, limit: int = 10) -> List[Clan]:
        """Получить топ кланов по Сомам"""
        return self.db.query(Clan).filter(
            Clan.is_active == True
        ).order_by(desc(Clan.total_coins)).limit(limit).all()

    def search_clans(self, query: str, limit: int = 10) -> List[Clan]:
        """Поиск кланов по имени или тегу"""
        return self.db.query(Clan).filter(
            Clan.is_active == True,
            or_(
                Clan.name.ilike(f"%{query}%"),
                Clan.tag.ilike(f"%{query}%")
            )
        ).limit(limit).all()

    def get_all_clans(self, limit: int = 50) -> List[Clan]:
        """Получить все активные кланы"""
        return self.db.query(Clan).filter(
            Clan.is_active == True
        ).order_by(desc(Clan.created_at)).limit(limit).all()

    # === Поиск пользователей для приглашения ===

    def search_user_by_username(self, username: str) -> Optional[TelegramUser]:
        """Найти пользователя по username"""
        if username.startswith('@'):
            username = username[1:]

        return self.db.query(TelegramUser).filter(
            TelegramUser.username.ilike(f"%{username}%")
        ).first()

    def search_users_by_name(self, name: str, limit: int = 10) -> List[TelegramUser]:
        """Поиск пользователей по имени"""
        return self.db.query(TelegramUser).filter(
            or_(
                TelegramUser.first_name.ilike(f"%{name}%"),
                TelegramUser.username.ilike(f"%{name}%")
            )
        ).limit(limit).all()

    # === Автоматическое обновление капитала ===

    def _update_clan_total_coins(self, clan_id: int):
        """Обновить общее количество Монет клана"""
        # Получаем всех участников клана
        members = self.get_clan_members(clan_id)

        if not members:
            clan = self.get_clan_by_id(clan_id)
            if clan:
                clan.total_coins = 0
                clan.last_updated = datetime.now()
            return

        # Суммируем балансы всех участников
        total_coins = 0
        for member in members:
            user = self.db.query(TelegramUser).filter(TelegramUser.telegram_id == member.user_id).first()
            if user and hasattr(user, 'coins'):
                # Преобразуем Decimal в int для сложения
                coins_value = user.coins
                if coins_value is not None:
                    try:
                        # Преобразуем Decimal в int
                        if hasattr(coins_value, 'to_integral_value'):
                            total_coins += int(coins_value.to_integral_value())
                        else:
                            total_coins += int(coins_value)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error converting coins value for user {member.user_id}: {e}")
                        total_coins += 0

        # Обновляем клан
        clan = self.get_clan_by_id(clan_id)
        if clan:
            clan.total_coins = total_coins
            clan.last_updated = datetime.now()
            logger.debug(f"Updated clan {clan_id} total coins to {total_coins}")

    def update_all_clans_coins(self) -> bool:
        """Обновить капитал всех активных кланов"""
        try:
            active_clans = self.db.query(Clan).filter(Clan.is_active == True).all()
            updated_count = 0

            for clan in active_clans:
                # Проверяем, нужно ли обновлять (если прошло больше 5 минут)
                if clan.last_updated and datetime.now() - clan.last_updated < timedelta(minutes=5):
                    continue

                self._update_clan_total_coins(clan.id)
                updated_count += 1

            self.db.commit()
            logger.info(f"✅ Обновлен капитал {updated_count} кланов")
            return True
        except Exception as e:
            logger.error(f"Error updating all clans coins: {e}")
            self.db.rollback()
            return False

    def update_clan_coins_for_user(self, user_id: int):
        """Обновить Монеты клана при изменении баланса пользователя"""
        try:
            clan = self.get_user_clan(user_id)
            if clan:
                # Проверяем, когда было последнее обновление
                if clan.last_updated and datetime.now() - clan.last_updated < timedelta(minutes=1):
                    return

                self._update_clan_total_coins(clan.id)
                self.db.commit()
                logger.debug(f"Updated clan coins for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating clan coins for user: {e}")
            self.db.rollback()

    def get_clan_settings(self) -> ClanSettings:
        """Получить настройки кланов"""
        settings = self.db.query(ClanSettings).first()
        if not settings:
            settings = ClanSettings()
            self.db.add(settings)
            self.db.commit()
        return settings

    def force_update_clan_coins(self, clan_id: int) -> bool:
        """Принудительно обновить капитал клана"""
        try:
            self._update_clan_total_coins(clan_id)
            self.db.commit()
            logger.info(f"✅ Обновлен капитал клана ID: {clan_id}")
            return True
        except Exception as e:
            logger.error(f"Error force updating clan coins: {e}")
            self.db.rollback()
            return False

    def get_clans_needing_update(self, minutes: int = 5) -> List[Clan]:
        """Получить кланы, которые нужно обновить"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return self.db.query(Clan).filter(
            Clan.is_active == True,
            (Clan.last_updated == None) | (Clan.last_updated < cutoff_time)
        ).all()

    def auto_update_stale_clans(self) -> int:
        """Автоматически обновить устаревшие кланы"""
        try:
            clans_to_update = self.get_clans_needing_update()
            updated_count = 0

            for clan in clans_to_update:
                self._update_clan_total_coins(clan.id)
                updated_count += 1

            if updated_count > 0:
                self.db.commit()
                logger.info(f"✅ Автообновлено {updated_count} устаревших кланов")

            return updated_count
        except Exception as e:
            logger.error(f"Error in auto update: {e}")
            self.db.rollback()
            return 0

    def get_clan_stats(self, clan_id: int) -> dict:
        """Получить статистику клана"""
        clan = self.get_clan_by_id(clan_id)
        if not clan:
            return {}

        members = self.get_clan_members(clan_id)

        leader = None
        deputy = None
        member_count = 0
        total_balance = 0

        for member in members:
            if member.role == 'leader':
                leader = member
            elif member.role == 'deputy':
                deputy = member
            member_count += 1

            # Добавляем баланс пользователя
            user_balance = self.get_user_balance(member.user_id)
            total_balance += user_balance

        avg_balance = total_balance // member_count if member_count > 0 else 0

        return {
            'clan': clan,
            'members_count': member_count,
            'leader': leader,
            'deputy': deputy,
            'total_balance': total_balance,
            'avg_balance': avg_balance
        }

    def update_clan_settings(self, clan_id: int, auto_accept_requests: bool = None,
                             join_type: str = None) -> bool:
        """Обновить настройки клана"""
        try:
            clan = self.get_clan_by_id(clan_id)
            if not clan:
                return False

            if auto_accept_requests is not None:
                clan.auto_accept_requests = auto_accept_requests
            if join_type is not None:
                clan.join_type = join_type  # 'auto' или 'manual'

            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating clan settings: {e}")
            return False

    def get_clan_join_settings(self, clan_id: int) -> dict:
        """Получить настройки вступления в клан"""
        clan = self.get_clan_by_id(clan_id)
        if not clan:
            return {}

        return {
            'auto_accept_requests': getattr(clan, 'auto_accept_requests', False),
            'join_type': getattr(clan, 'join_type', 'manual')
        }

    def process_join_request_with_settings(self, request_id: int) -> bool:
        """Обработать заявку с учетом настроек клана"""
        try:
            request = self.db.query(ClanJoinRequest).filter(
                ClanJoinRequest.id == request_id
            ).first()

            if not request:
                return False

            clan = self.get_clan_by_id(request.clan_id)
            if not clan:
                return False

            # Если включено автоматическое принятие
            if getattr(clan, 'auto_accept_requests', False):
                # Добавляем пользователя в клан
                success = self.add_member(clan.id, request.user_id)
                if success:
                    request.status = 'approved'
                    self.db.commit()

                    # Отправляем уведомление лидеру
                    self.notify_leader_about_auto_join(clan.id, request.user_id)
                    return True
            else:
                # Требуется ручное подтверждение
                request.status = 'pending'
                self.db.commit()

                # Отправляем уведомление лидеру о новой заявке
                self.notify_leader_about_request(clan.id, request_id)
                return True

            return False
        except Exception as e:
            logger.error(f"Error processing join request with settings: {e}")
            self.db.rollback()
            return False

    def notify_leader_about_auto_join(self, clan_id: int, user_id: int):
        """Уведомить лидера об авто-присоединении"""
        # Эта функция будет использоваться в ClanHandler
        pass

    def notify_leader_about_request(self, clan_id: int, request_id: int):
        """Уведомить лидера о новой заявке"""
        # Эта функция будет использоваться в ClanHandler
        pass