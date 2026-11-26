from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Literal


ActionName = Literal[
    "create_workplace",
    "update_workplace",
    "delete_workplace",
    "create_shifts",
]


@dataclass(frozen=True)
class PendingAction:
    """Одноразовое действие, которое ожидает подтверждения пользователя."""

    id: str
    user_id: int
    action: ActionName
    workplace_id: int | None
    payload: dict
    summary: str
    expires_at: datetime


_pending: dict[str, PendingAction] = {}
_TTL = timedelta(minutes=10)


def create_pending_action(
    user_id: int,
    action: ActionName,
    payload: dict,
    summary: str,
    workplace_id: int | None = None,
) -> PendingAction:
    """Сохраняет действие для подтверждения его владельцем в течение 10 минут.

    Args:
        user_id: ID пользователя, которому разрешено подтвердить или отменить
            действие.
        action: Тип ожидающей операции, включая создание графика смен.
        payload: Данные для исполнения после подтверждения.
        summary: Текст плана, который показывается пользователю до подтверждения.
        workplace_id: Рабочая точка, затронутая действием, если она есть.

    Returns:
        Сохранённое действие с криптографически случайным ID и временем истечения.
    """
    now = datetime.now(timezone.utc)
    pending = PendingAction(
        id=token_urlsafe(32),
        user_id=user_id,
        action=action,
        workplace_id=workplace_id,
        payload=payload,
        summary=summary,
        expires_at=now + _TTL,
    )
    _pending[pending.id] = pending
    return pending


def consume_pending_action(
    confirmation_id: str,
    user_id: int,
) -> tuple[PendingAction | None, Literal["ok", "expired", "invalid"]]:
    """Однократно извлекает ожидающее действие для его выполнения.

    Чужие и неизвестные ID возвращают ``invalid`` без раскрытия владельца.
    Просроченное действие удаляется и возвращается со статусом ``expired``;
    успешно подтверждённое действие удаляется до передачи вызывающему коду.

    Args:
        confirmation_id: Одноразовый идентификатор из ответа агента.
        user_id: ID текущего аутентифицированного пользователя.

    Returns:
        Пара из действия (или ``None``) и результата ``ok``, ``expired`` либо
        ``invalid``.
    """
    pending = _pending.get(confirmation_id)
    if pending is None:
        return None, "invalid"
    if pending.user_id != user_id:
        return None, "invalid"
    if pending.expires_at <= datetime.now(timezone.utc):
        _pending.pop(confirmation_id, None)
        return None, "expired"
    _pending.pop(confirmation_id, None)
    return pending, "ok"


def cancel_pending_action(confirmation_id: str, user_id: int) -> bool:
    """Отменяет ещё действующее действие, если оно принадлежит пользователю.

    Args:
        confirmation_id: Одноразовый идентификатор из ответа агента.
        user_id: ID пользователя, запросившего отмену.

    Returns:
        ``True``, если действие найдено, не истекло и удалено; иначе ``False``.
    """
    pending = _pending.get(confirmation_id)
    if pending is None or pending.user_id != user_id:
        return False
    if pending.expires_at <= datetime.now(timezone.utc):
        _pending.pop(confirmation_id, None)
        return False
    _pending.pop(confirmation_id, None)
    return True