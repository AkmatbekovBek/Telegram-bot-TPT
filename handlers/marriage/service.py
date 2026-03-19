import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WeddingState:
    chat_id: int
    initiator_id: int
    message_id: int
    created_at: datetime = field(default_factory=datetime.utcnow)

    # роли
    registrar_id: Optional[int] = None
    groom_id: Optional[int] = None
    bride_id: Optional[int] = None
    witness_id: Optional[int] = None
    witnessess_id: Optional[int] = None

    # подписи
    groom_signed: bool = False
    bride_signed: bool = False

    # гости
    guests: List[int] = field(default_factory=list)

    # кэш отображаемых имён (HTML-ссылки)
    display_names: Dict[int, str] = field(default_factory=dict)

    # резерв лицензии на свадьбу (для возврата при отмене)
    reserved_license: Optional[Dict] = None

    def is_user_taken(self, user_id: int) -> bool:
        if user_id in self.guests:
            return True
        return user_id in {
            self.registrar_id,
            self.groom_id,
            self.bride_id,
            self.witness_id,
            self.witnessess_id,
        }

    def are_roles_filled(self) -> bool:
        return all([
            self.registrar_id,
            self.groom_id,
            self.bride_id,
            self.witness_id,
            self.witnessess_id,
        ])

    def are_signatures_ready(self) -> bool:
        return self.groom_signed and self.bride_signed


# Один активный бракосочетательный процесс на чат
ACTIVE_WEDDINGS: Dict[int, WeddingState] = {}


def get_wedding(chat_id: int) -> Optional[WeddingState]:
    return ACTIVE_WEDDINGS.get(chat_id)


def set_wedding(state: WeddingState) -> None:
    ACTIVE_WEDDINGS[state.chat_id] = state


def clear_wedding(chat_id: int) -> Optional[WeddingState]:
    return ACTIVE_WEDDINGS.pop(chat_id, None)


@dataclass
class DivorceState:
    chat_id: int
    initiator_id: int
    groom_id: int
    bride_id: int
    message_id: int
    created_at: datetime = field(default_factory=datetime.utcnow)

    # роли
    judge_id: Optional[int] = None
    jurors: List[int] = field(default_factory=list)

    # подписи
    groom_signed: bool = False
    bride_signed: bool = False

    # кэш имен
    display_names: Dict[int, str] = field(default_factory=dict)

    def is_participant(self, user_id: int) -> bool:
        if user_id in self.jurors:
            return True
        return user_id in {
            self.groom_id,
            self.bride_id,
            self.judge_id,
        }

    def can_be_judge(self, user_id: int) -> bool:
        if self.judge_id:
            return False
        # Муж и жена не могут быть судьей
        if user_id in (self.groom_id, self.bride_id):
            return False
        # Присяжный не может быть судьей
        if user_id in self.jurors:
            return False
        return True

    def can_be_juror(self, user_id: int) -> bool:
        if user_id in self.jurors:
            return False
        # Муж и жена не могут быть присяжными
        if user_id in (self.groom_id, self.bride_id):
            return False
        # Судья не может быть присяжным
        if user_id == self.judge_id:
            return False
        return True

    def are_signatures_ready(self) -> bool:
        return self.groom_signed and self.bride_signed


ACTIVE_DIVORCES: Dict[int, DivorceState] = {}


def get_divorce(chat_id: int) -> Optional[DivorceState]:
    return ACTIVE_DIVORCES.get(chat_id)


def set_divorce(state: DivorceState) -> None:
    ACTIVE_DIVORCES[state.chat_id] = state


def clear_divorce(chat_id: int) -> Optional[DivorceState]:
    return ACTIVE_DIVORCES.pop(chat_id, None)
