import httpx

from app.config import settings


class GigaChatRequestError(RuntimeError):
    pass


async def send_gigachat_request(
    token: str,
    messages: list[dict],
    model: str | None = None,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> dict:
    """
    Отправляет запрос в GigaChat с полученным OAuth-токеном.
    """
    if not token:
        raise GigaChatRequestError("OAuth-токен GigaChat не задан")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": model or settings.GIGA_MODEL,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    try:
        async with httpx.AsyncClient(
            timeout=settings.GIGA_TIMEOUT_SECONDS,
            verify=False,
        ) as client:
            response = await client.post(
                settings.GIGA_CHAT_URL,
                headers=headers,
                json=payload,
            )
    except httpx.RequestError as error:
        raise GigaChatRequestError(
            f"Не удалось отправить запрос в GigaChat: {error}"
        ) from error

    if response.status_code != 200:
        raise GigaChatRequestError(
            f"Ошибка запроса к GigaChat: "
            f"{response.status_code} - {response.text}"
        )

    try:
        result = response.json()
    except ValueError as error:
        raise GigaChatRequestError("GigaChat вернул некорректный JSON") from error

    if not isinstance(result, dict):
        raise GigaChatRequestError("GigaChat вернул ответ неверного формата")

    return result