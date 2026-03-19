from typing import Any, List

def build_divorce_message(state: Any) -> str:
    """Сообщение развода. state: DivorceState"""
    initiator = _name(state, state.initiator_id)
    groom = _name(state, state.groom_id)
    bride = _name(state, state.bride_id)
    judge = _name(state, state.judge_id)

    # Присяжные
    jurors: List[str] = [_name(state, uid) for uid in state.jurors if _name(state, uid)]
    jurors_text = ", ".join(jurors[:20])
    if len(jurors) > 20:
        jurors_text += f" и ещё {len(jurors) - 20}"

    groom_sig = "✅" if state.groom_signed else "❌"
    bride_sig = "✅" if state.bride_signed else "❌"

    text = (
        f"{initiator} предлагает провести развод\n\n"
        f"Муж: {groom}\n"
        f"Жена: {bride}\n\n"
        f"Судья: {judge}\n\n"
        f"Присяжные: {jurors_text}\n"
        f"Подписи: Муж {groom_sig} | Жена {bride_sig}"
    )
    return text


def build_divorce_quote() -> str:
    return (
        "Иногда нужно потерять «вместе», чтобы снова найти себя.\n"
        "Позвольте себе грустить, но не забывайте надеяться.\n"
        "Ваше лучшее ещё впереди.\n\n"
        "С уважением Команда @TopTashPlusBot"
    )

from .service import WeddingState


def _name(state: WeddingState, user_id: int | None) -> str:
    if not user_id:
        return ""
    return state.display_names.get(user_id, "")


def build_wedding_message(state: WeddingState) -> str:
    """Сообщение церемонии."""
    initiator = _name(state, state.initiator_id)

    groom = _name(state, state.groom_id)
    bride = _name(state, state.bride_id)
    witness = _name(state, state.witness_id)
    witnessess = _name(state, state.witnessess_id)
    registrar = _name(state, state.registrar_id)

    # Гости
    guests: List[str] = [_name(state, uid) for uid in state.guests if _name(state, uid)]
    guests_text = ", ".join(guests[:25])
    if len(guests) > 25:
        guests_text += f" и ещё {len(guests) - 25}"

    # Подписи
    groom_sig = "✅" if state.groom_signed else "❌"
    bride_sig = "✅" if state.bride_signed else "❌"

    text = (
        f"{initiator} предлагает провести церемонию бракосочетания\n\n"
        f"Жених: {groom}\n"
        f"Невеста: {bride}\n\n"
        f"Свидетель: {witness}\n"
        f"Свидетельница: {witnessess}\n\n"
        f"Регистратор: {registrar}\n"
        f"Гости: {guests_text}\n\n"
        f"Подписи: жених {groom_sig} | невеста {bride_sig}"
    )
    return text


def build_cancel_text() -> str:
    return "Свадьба отменена."


def build_success_text(groom: str, bride: str) -> str:
    # Текст из ТЗ (страница 6)
    return (
        "Поздравляем с бракосочетанием!\n\n"
        "Пусть ваша любовь будет крепкой, а семейное счастье — бесконечным. \n"
        "Желаем вам гармонии, уважения, взаимопонимания и радости в каждом дне, \n"
        "проведённом вместе.\n\n"
        "Счастья вам, любви и благополучия!\n\n"
        f"Жених: {groom}\n"
        f"Невеста: {bride}\n\n"
        "Регистратор: РДНО"
    )
