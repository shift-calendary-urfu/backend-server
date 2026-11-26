import json

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.giga_auth import GigaChatAuthError, get_gigachat_token
from app.agent.giga_client import GigaChatRequestError, send_gigachat_request
from app.agent.schemas import (
    AgentAnswer,
    ListMyWorkplacesRequest,
    ShiftScheduleRequest,
    WorkplaceMutationRequest,
)
from app.agent.tools import (
    ShiftScheduleToolError,
    list_my_workplaces,
    prepare_shift_schedule,
)
from app.agent.confirmation import create_pending_action
from app.agent.authorization import get_workplace_access, can_mutate_workplace
from app.workplaces.services import WorkplaceServices
from app.workplaces.schemas import WorkplaceUpdate
from app.exceptions import EmployeeNotFoundException, WorkplaceNotFoundException
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

CREATE_SHIFT_SCHEDULE_TOOL = {
    "type": "function",
    "function": {
        "name": "create_shift_schedule",
        "description": (
            "Подготовить график смен для одного сотрудника рабочей точки. "
            "Вызывай эту функцию, когда пользователь просит составить, создать "
            "или подготовить смены/график и указал ID сотрудника и рабочей точки, "
            "даже если запрос сформулирован другими словами. ID сотрудника и "
            "рабочей точки должны быть явно известны. Цикл рассчитывает серверная "
            "логика: первый день — сегодня, period — число календарных дней, "
            "schedule — рабочие/выходные (например 5/2; 7/0 допустимо). Если "
            "schedule отсутствует или некорректен, подготавливается одна смена "
            "на сегодня. По умолчанию используются часы рабочей точки; можно "
            "указать оба значения времени. Уже занятые сменами даты пропускаются. "
            "Тул только показывает полный план и запрашивает подтверждение; "
            "смены не создаются до отдельного подтверждения пользователя."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workplace_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "ID активной рабочей точки, где пользователь является "
                        "владельцем или администратором."
                    ),
                },
                "employee_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "ID одного активного сотрудника, состоящего в указанной "
                        "рабочей точке."
                    ),
                },
                "schedule": {
                    "type": "string",
                    "maxLength": 32,
                    "description": (
                        "Необязательный график «рабочие/выходные дни», например "
                        "5/2, 2/2 или 7/0. Первый день цикла — сегодня. Если "
                        "отсутствует или некорректен, планируется одна смена "
                        "на сегодня, а period игнорируется."
                    ),
                },
                "period": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 90,
                    "description": (
                        "Число календарных дней от сегодня, от 1 до 90; "
                        "применяется при корректном schedule."
                    ),
                },
                "start_time": {
                    "type": "string",
                    "pattern": r"^\d{1,2}:\d{2}$",
                    "description": (
                        "Необязательное время начала HH:MM с минутами 00 или 30. "
                        "Передаётся только вместе с end_time; иначе используются "
                        "часы рабочей точки."
                    ),
                },
                "end_time": {
                    "type": "string",
                    "pattern": r"^\d{1,2}:\d{2}$",
                    "description": (
                        "Необязательное время окончания HH:MM с минутами 00 или 30, "
                        "позже start_time. Передаётся только вместе со start_time; "
                        "иначе используются часы рабочей точки."
                    ),
                },
            },
            "required": ["workplace_id", "employee_id", "period"],
            "additionalProperties": False,
        },
    },
}


class AgentServiceError(RuntimeError):
    """Ошибка обработки запроса агента или ответа внешней модели."""


UNSUPPORTED_CALENDAR_REQUEST_ANSWER = (
    "Я могу работать только с доступными сейчас операциями календаря смен: "
    "вывести ваши рабочие точки, подготовить изменение рабочей точки или "
    "составить график смен одного сотрудника с последующим подтверждением. "
    "Запрошенную информацию пока можно получить только вручную."
)


class AgentService:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    async def process(self, query: str) -> AgentAnswer:
        """Обрабатывает запрос, исполняя только разрешённые серверные инструменты.

        Вызовы чтения и подготовки изменений валидируются отдельно от текста
        модели. ``create_shift_schedule`` делегирует построение дат и проверку
        конфликтов ``ShiftServices``; сам агент не рассчитывает расписание и
        не пишет смены. План сохраняется как ожидающее действие и возвращается
        вместе с явным запросом подтверждения. За один запрос разрешено
        подготовить максимум одно действие, требующее подтверждения.

        Args:
            query: Текст запроса пользователя после валидации входной схемой.

        Returns:
            Ответ агента; если подготовлено действие, включает идентификатор
            подтверждения и его резюме, которое также добавляется к тексту ответа.

        Raises:
            AgentServiceError: При ошибке авторизации внешнего сервиса,
                некорректном ответе модели или ошибке выполнения запроса.
        """
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
                    "Ты помощник календаря смен. Отвечай только на вопросы, "
                    "связанные с календарем смен и рабочими точками. На вопросы "
                    "не по теме (например, общие знания, погода, анекдоты, "
                    "программирование или личные советы) не отвечай по существу: "
                    "вежливо сообщи, что помогаешь только с календарем смен. "
                    "Если вопрос связан с календарем смен, но для него нет "
                    "подходящего доступного tool (например, запрос информации "
                    "о сотруднике), не выдумывай данные и не вызывай неизвестные "
                    "tools. Сообщи, что такую операцию пока можно выполнить "
                    "только вручную, и перечисли доступные возможности: вывести "
                    "рабочие точки пользователя, подготовить изменение рабочей "
                    "точки или составить график смен одного сотрудника. "
                    "Если пользователь явно просит составить, создать или "
                    "подготовить смены и в запросе указаны ID рабочей точки и "
                    "сотрудника, обязательно вызови create_shift_schedule; не "
                    "отказывай и не говори, что операция недоступна. Передай "
                    "указанные ID, график и период без изменений. Если ID "
                    "сотрудника или рабочей точки не указан, уточни недостающий "
                    "ID и не вызывай этот tool. "
                    "Используй tool list_my_workplaces для чтения рабочих точек и "
                    "update_workplace только для подготовки изменения рабочей точки. "
                    "Используй create_shift_schedule только для подготовки графика; "
                    "сервер рассчитывает его, а создание смен требует отдельного "
                    "подтверждения. Никогда не представляй подготовленное изменение "
                    "или график как выполненные до подтверждения. "
                    "Для создания или удаления рабочей точки не вызывай tools; "
                    "сообщи, что такая операция сейчас недоступна через агента."
                ),
            },
            {"role": "user", "content": request.query},
        ]

        try:
            first_response = await send_gigachat_request(
                token,
                messages,
                tools=[
                    LIST_WORKPLACES_TOOL,
                    UPDATE_WORKPLACE_TOOL,
                    CREATE_SHIFT_SCHEDULE_TOOL,
                ],
                tool_choice="auto",
            )
        except GigaChatRequestError as error:
            raise AgentServiceError(str(error)) from error

        choice = self._get_choice(first_response)
        assistant_message = choice.get("message") or {}
        tool_calls = assistant_message.get("tool_calls") or []
        function_call = assistant_message.get("function_call")
        if not tool_calls and isinstance(function_call, dict):
            function_name = function_call.get("name")
            arguments = function_call.get("arguments") or {}
            if not isinstance(function_name, str) or not function_name:
                raise AgentServiceError("GigaChat вернул некорректный вызов функции")
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments, ensure_ascii=False)
            if not isinstance(arguments, str):
                raise AgentServiceError("GigaChat вернул некорректные аргументы функции")
            tool_calls = [
                {
                    "function": {
                        "name": function_name,
                        "arguments": arguments,
                    }
                }
            ]

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
            if function_name not in {
                "list_my_workplaces",
                "update_workplace",
                "create_shift_schedule",
            }:
                tool_messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {
                                "error": (
                                    "Эта операция пока недоступна. "
                                    "Доступны list_my_workplaces, подготовка "
                                    "update_workplace и create_shift_schedule."
                                )
                            },
                            ensure_ascii=False,
                        ),
                        **(
                            {"tool_call_id": tool_call.get("id")}
                            if tool_call.get("id")
                            else {}
                        ),
                    }
                )
                continue

            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError as error:
                raise AgentServiceError("GigaChat передал некорректные аргументы tool") from error

            if (
                function_name in {"update_workplace", "create_shift_schedule"}
                and confirmation_id is not None
            ):
                tool_messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {
                                "error": (
                                    "За один запрос можно подготовить только одно "
                                    "действие, требующее подтверждения."
                                )
                            },
                            ensure_ascii=False,
                        ),
                        **(
                            {"tool_call_id": tool_call.get("id")}
                            if tool_call.get("id")
                            else {}
                        ),
                    }
                )
                executed = True
                continue

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

            if function_name == "create_shift_schedule":
                try:
                    request = ShiftScheduleRequest.model_validate(arguments)
                    plan = await prepare_shift_schedule(
                        request,
                        self.user,
                        self.db,
                    )
                except (
                    ValidationError,
                    ShiftScheduleToolError,
                    EmployeeNotFoundException,
                    WorkplaceNotFoundException,
                ) as error:
                    tool_result = {"error": str(error)}
                else:
                    if not plan["shifts"]:
                        tool_result = {
                            "confirmation_required": False,
                            "summary": plan["summary"],
                            "message": (
                                "Новых смен нет: все даты уже заняты "
                                "существующими сменами."
                            ),
                        }
                    else:
                        pending = create_pending_action(
                            user_id=self.user.id,
                            action="create_shifts",
                            workplace_id=plan["workplace_id"],
                            payload={
                                "employee_id": plan["employee_id"],
                                "shifts": plan["shifts"],
                            },
                            summary=plan["summary"],
                        )
                        confirmation_id = pending.id
                        confirmation_summary = plan["summary"]
                        tool_result = {
                            "confirmation_required": True,
                            "confirmation_id": pending.id,
                            "summary": plan["summary"],
                        }

                tool_messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(tool_result, ensure_ascii=False),
                        **(
                            {"tool_call_id": tool_call.get("id")}
                            if tool_call.get("id")
                            else {}
                        ),
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
            return AgentAnswer(answer=UNSUPPORTED_CALENDAR_REQUEST_ANSWER)

        if isinstance(function_call, dict):
            for tool_message in tool_messages:
                tool_message["role"] = "function"
                tool_message["name"] = function_call["name"]
                tool_message.pop("tool_call_id", None)

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

        answer = content.strip()
        if confirmation_id is not None and confirmation_summary:
            if confirmation_summary not in answer:
                answer = f"{answer}\n\n{confirmation_summary}"
            answer = f"{answer}\nПодтвердите действие, чтобы выполнить его."

        return AgentAnswer(
            answer=answer,
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
