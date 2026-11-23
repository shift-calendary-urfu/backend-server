import json

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.giga_auth import GigaChatAuthError, get_gigachat_token
from app.agent.giga_client import GigaChatRequestError, send_gigachat_request
from app.agent.schemas import AgentAnswer, ListMyWorkplacesRequest
from app.agent.tools import list_my_workplaces
from app.users.model import User


LIST_WORKPLACES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_my_workplaces",
        "description": (
            "Получить рабочие точки пользователя, включая точки его владения "
            "и точки, где он активный сотрудник"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 500,
                    "description": "Запрос пользователя о рабочих точках",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


class AgentServiceError(RuntimeError):
    pass


class AgentService:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    async def process(self, query: str) -> AgentAnswer:
        try:
            request = ListMyWorkplacesRequest(query=query)
        except ValidationError as error:
            raise AgentServiceError("Некорректный запрос пользователя") from error

        try:
            token = await get_gigachat_token()
        except GigaChatAuthError as error:
            raise AgentServiceError(str(error)) from error

        messages = [
            {
                "role": "system",
                "content": (
                    "Ты помощник календаря смен. Используй tool "
                    "list_my_workplaces только для запросов о рабочих точках "
                    "пользователя. Для других операций не вызывай tools."
                ),
            },
            {"role": "user", "content": request.query},
        ]

        try:
            first_response = await send_gigachat_request(
                token,
                messages,
                tools=[LIST_WORKPLACES_TOOL],
                tool_choice="auto",
            )
        except GigaChatRequestError as error:
            raise AgentServiceError(str(error)) from error

        choice = self._get_choice(first_response)
        assistant_message = choice.get("message") or {}
        tool_calls = assistant_message.get("tool_calls") or []

        if not tool_calls:
            content = assistant_message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise AgentServiceError("GigaChat не вернул текстовый ответ")
            return AgentAnswer(answer=content.strip())

        tool_messages: list[dict] = []
        executed = False

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue

            function = tool_call.get("function") or {}
            if function.get("name") != "list_my_workplaces":
                continue

            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError as error:
                raise AgentServiceError("GigaChat передал некорректные аргументы tool") from error

            try:
                tool_request = ListMyWorkplacesRequest.model_validate(arguments)
            except ValidationError as error:
                raise AgentServiceError("GigaChat передал параметры tool в неверном формате") from error

            result = await list_my_workplaces(self.user, self.db)
            tool_call_id = tool_call.get("id")
            tool_messages.append(
                {
                    "role": "tool",
                    "content": result.model_dump_json(ensure_ascii=False),
                    **({"tool_call_id": tool_call_id} if tool_call_id else {}),
                }
            )
            executed = True

        if not executed:
            raise AgentServiceError("GigaChat вызвал неизвестный tool")

        messages.append(assistant_message)
        messages.extend(tool_messages)

        try:
            final_response = await send_gigachat_request(token, messages)
        except GigaChatRequestError as error:
            raise AgentServiceError(str(error)) from error

        final_choice = self._get_choice(final_response)
        final_message = final_choice.get("message") or {}
        content = final_message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AgentServiceError("GigaChat не вернул итоговый ответ")

        return AgentAnswer(answer=content.strip())

    @staticmethod
    def _get_choice(response: dict) -> dict:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AgentServiceError("GigaChat не вернул choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise AgentServiceError("GigaChat вернул некорректный choices")
        return choice
