from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Literal


ActionName = Literal["create_workplace", "update_workplace", "delete_workplace"]


@dataclass(frozen=True)
class PendingAction:
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
    pending = _pending.get(confirmation_id)
    if pending is None or pending.user_id != user_id:
        return False
    if pending.expires_at <= datetime.now(timezone.utc):
        _pending.pop(confirmation_id, None)
        return False
    _pending.pop(confirmation_id, None)
    return True