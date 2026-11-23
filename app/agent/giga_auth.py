import asyncio
import time
import uuid

import httpx

from app.config import settings


class GigaChatAuthError(RuntimeError):
    pass


_token: str | None = None
_token_expires_at: float = 0
_token_lock = asyncio.Lock()


def _parse_expiration(payload: dict) -> float:
    expires_at = payload.get("expires_at")
    if isinstance(expires_at, (int, float)):
        timestamp = float(expires_at)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return timestamp

    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)):
        return time.time() + float(expires_in)

    return time.time() + 29 * 60


async def get_gigachat_token(authorization_key: str | None = None) -> str:
    """
    Получает и кэширует OAuth-токен GigaChat до окончания его срока действия.
    """
    authorization_key = authorization_key or settings.GIGA_API_KEY
    if not authorization_key or authorization_key == "key":
        raise GigaChatAuthError("GIGA_API_KEY не задан")

    global _token, _token_expires_at

    async with _token_lock:
        if _token and time.time() < _token_expires_at - 60:
            return _token

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {authorization_key}",
        }

        try:
            async with httpx.AsyncClient(
                timeout=settings.GIGA_TIMEOUT_SECONDS,
                verify=False,
            ) as client:
                response = await client.post(
                    settings.GIGA_AUTH_URL,
                    headers=headers,
                    data={"scope": "GIGACHAT_API_PERS"},
                )
        except httpx.RequestError as error:
            raise GigaChatAuthError(
                f"Не удалось запросить токен GigaChat: {error}"
            ) from error

        if response.status_code != 200:
            raise GigaChatAuthError(
                f"Ошибка получения токена GigaChat: "
                f"{response.status_code} - {response.text}"
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise GigaChatAuthError("GigaChat вернул некорректный JSON") from error

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GigaChatAuthError("GigaChat не вернул access_token")

        _token = access_token
        _token_expires_at = _parse_expiration(payload)
        return _token
