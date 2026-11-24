import json

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.giga_auth import GigaChatAuthError, get_gigachat_token
from app.agent.giga_client import GigaChatRequestError, send_gigachat_request
from app.agent.schemas import (
    AgentAnswer,
    ListMyWorkplacesRequest,
    WorkplaceMutationRequest,
)
from app.agent.tools import list_my_workplaces
from app.agent.confirmation import create_pending_action
from app.agent.authorization import get_workplace_access, can_mutate_workplace
from app.workplaces.services import WorkplaceServices
from app.workplaces.schemas import WorkplaceUpdate
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


UPDATE_WORKPLACE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_workplace",
        "description": (
            "Подготовить изменение рабочей точки. Изменение не выполняется до "
            "отдельного подтверждения пользователя."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workplace_id": {"type": "integer", "minimum": 1},
                "name": {"type": "string", "maxLength": 255},
                "address": {"type": "string", "maxLength": 500},
                "phone": {"type": "string", "maxLength": 20},
                "description": {"type": "string", "maxLength": 5000},
                "workplace_type": {"type": "string", "maxLength": 50},
                "work_start_time": {"type": "string"},
                "work_end_time": {"type": "string"},
            },
            "required": ["workplace_id"],
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
        confirmation_id: str | None = None
        confirmation_summary: str | None = None

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
                    "list_my_workplaces для чтения рабочих точек и "
                    "update_workplace только для подготовки изменения рабочей точки. "
                    "Никогда не представляй подготовленное изменение как выполненное. "
                    "Для создания и удаления не вызывай tools; сообщи, что действие "
                    "требует подтверждения через отдельный безопасный API."
                ),
            },
            {"role": "user", "content": request.query},
        ]

        try:
            first_response = await send_gigachat_request(
                token,
                messages,
                tools=[LIST_WORKPLACES_TOOL, UPDATE_WORKPLACE_TOOL],
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
            return AgentAnswer(
                answer=content.strip(),
                confirmation_required=confirmation_id is not None,
                confirmation_id=confirmation_id,
                confirmation_summary=confirmation_summary,
            )

        tool_messages: list[dict] = []
        executed = False

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue

            function = tool_call.get("function") or {}
            function_name = function.get("name")
            if function_name not in {"list_my_workplaces", "update_workplace"}:
                continue

            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError as error:
                raise AgentServiceError("GigaChat передал некорректные аргументы tool") from error

            if function_name == "list_my_workplaces":
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
                continue

            try:
                mutation = WorkplaceMutationRequest.model_validate(arguments)
            except ValidationError as error:
                raise AgentServiceError("GigaChat передал параметры tool в неверном формате") from error
            if mutation.workplace_id is None:
                raise AgentServiceError("Для изменения рабочей точки не указан workplace_id")

            role = await get_workplace_access(
                self.db,
                self.user,
                mutation.workplace_id,
            )
            if not can_mutate_workplace(role, "update_workplace"):
                raise AgentServiceError("У вас нет прав на изменение этой рабочей точки")

            payload = mutation.model_dump(exclude={"workplace_id"}, exclude_none=True)
            if not payload:
                raise AgentServiceError("Изменение не содержит ни одного поля")
            try:
                update = WorkplaceUpdate.model_validate(payload)
            except ValidationError as error:
                raise AgentServiceError("GigaChat передал некорректные поля изменения") from error

            workplace = await WorkplaceServices(self.db).get_by_id(mutation.workplace_id)
            changes = []
            field_names = {
                "name": "название",
                "address": "адрес",
                "phone": "телефон",
                "description": "описание",
                "workplace_type": "тип",
                "work_start_time": "время начала",
                "work_end_time": "время окончания",
            }
            for field, label in field_names.items():
                value = getattr(update, field)
                if value is not None:
                    old_value = getattr(workplace, field)
                    old_text = old_value.strftime("%H:%M") if hasattr(old_value, "strftime") else str(old_value)
                    new_text = value.strftime("%H:%M") if hasattr(value, "strftime") else str(value)
                    changes.append(f"{label}: {old_text} -> {new_text}")

            summary = (
                f"Изменить рабочую точку «{workplace.name}» "
                f"(ID {workplace.id}) — " + "; ".join(changes)
            )
            pending = create_pending_action(
                user_id=self.user.id,
                action="update_workplace",
                workplace_id=workplace.id,
                payload=update.model_dump(exclude_none=True),
                summary=summary,
            )
            confirmation_id = pending.id
            confirmation_summary = summary
            tool_call_id = tool_call.get("id")
            tool_messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(
                        {
                            "confirmation_required": True,
                            "confirmation_id": pending.id,
                            "summary": summary,
                        },
                        ensure_ascii=False,
                    ),
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

        return AgentAnswer(
            answer=content.strip(),
            confirmation_required=confirmation_id is not None,
            confirmation_id=confirmation_id,
            confirmation_summary=confirmation_summary,
        )

    @staticmethod
    def _get_choice(response: dict) -> dict:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AgentServiceError("GigaChat не вернул choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise AgentServiceError("GigaChat вернул некорректный choices")
        return choice
