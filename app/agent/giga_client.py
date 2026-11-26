import httpx

from app.config import settings


class GigaChatRequestError(RuntimeError):
    pass


def _to_gigachat_functions(tools: list[dict]) -> list[dict]:
    """Преобразует OpenAI-совместимые описания tools в формат функций GigaChat v1."""
    functions = []
    for tool in tools:
        function = tool.get("function")
        if not isinstance(function, dict):
            raise GigaChatRequestError("Описание tool имеет неверный формат")
        functions.append(function)
    return functions


def _to_gigachat_function_choice(tool_choice: str | dict) -> str | dict:
    """Преобразует выбор tool в поле function_call API GigaChat v1."""
    if isinstance(tool_choice, str):
        if tool_choice == "required":
            return "auto"
        return tool_choice

    function = tool_choice.get("function")
    if tool_choice.get("type") == "function" and isinstance(function, dict):
        name = function.get("name")
        if isinstance(name, str) and name:
            return {"name": name}
    raise GigaChatRequestError("Выбор tool имеет неверный формат")


async def send_gigachat_request(
    token: str,
    messages: list[dict],
    model: str | None = None,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> dict:
    """
    Отправляет запрос в GigaChat v1 с полученным OAuth-токеном.

    Описания tool преобразуются в поле ``functions``, а ``tool_choice`` — в
    ``function_call`` согласно контракту API GigaChat v1.
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
        payload["functions"] = _to_gigachat_functions(tools)
    if tool_choice:
        payload["function_call"] = _to_gigachat_function_choice(tool_choice)

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