import json

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.giga_auth import GigaChatAuthError, get_gigachat_token
from app.agent.giga_client import GigaChatRequestError, send_gigachat_request
from app.agent.schemas import (
    AgentAnswer,
    EmployeeLookupRequest,
    EmployeeShiftsRequest,
    ListMyWorkplacesRequest,
    ShiftScheduleRequest,
    WorkplaceShiftsRequest,
    WorkplaceMutationRequest,
)
from app.agent.tools import (
    EmployeeLookupToolError,
    ShiftViewToolError,
    ShiftScheduleToolError,
    get_employee_shifts,
    get_workplace_shifts,
    lookup_employee,
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

LOOKUP_EMPLOYEE_BY_NAME_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_employee_by_full_name",
        "description": (
            "Найти активного сотрудника по ФИО или его части и вернуть employee_id. "
            "Используй этот инструмент до того, как просить пользователя сообщить "
            "ID сотрудника. Если у пользователя одна управляемая рабочая точка, "
            "она выбирается автоматически; если точек несколько, сначала попроси "
            "выбрать точку по возвращённому списку. Не выбирай сотрудника наугад: "
            "при нескольких совпадениях попроси пользователя уточнить, кто именно."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "full_name": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 500,
                    "description": "Полное имя, ФИО или часть ФИО сотрудника.",
                },
                "workplace_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "ID выбранной рабочей точки, если он уже известен.",
                },
                "workplace_name": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 255,
                    "description": "Название выбранной пользователем рабочей точки.",
                },
            },
            "required": ["full_name"],
            "additionalProperties": False,
        },
    },
}

LOOKUP_EMPLOYEE_BY_PHONE_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_employee_by_phone",
        "description": (
            "Найти активного сотрудника по телефону и вернуть employee_id. "
            "Используй этот инструмент до того, как просить пользователя сообщить "
            "ID сотрудника. Если у пользователя одна управляемая рабочая точка, "
            "она выбирается автоматически; если точек несколько, попроси выбрать "
            "точку по возвращённому списку. Не выбирай сотрудника наугад: при "
            "нескольких совпадениях попроси пользователя уточнить, кто именно."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 32,
                    "description": "Телефон сотрудника в формате +7XXXXXXXXXX или 8XXXXXXXXXX.",
                },
                "workplace_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "ID выбранной рабочей точки, если он уже известен.",
                },
                "workplace_name": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 255,
                    "description": "Название выбранной пользователем рабочей точки.",
                },
            },
            "required": ["phone"],
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
            "или подготовить смены/график и известны ID сотрудника и рабочей точки "
            "(ID сотрудника может быть получен из lookup_employee_by_full_name или "
            "lookup_employee_by_phone). Не вызывай функцию, пока поиск не вернул "
            "ровно одного сотрудника и рабочая точка не выбрана однозначно. "
            "Цикл рассчитывает серверная "
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

GET_EMPLOYEE_SHIFTS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_employee_shifts",
        "description": (
            "Показать смены одного сотрудника за период до 90 дней. Сотрудник "
            "может смотреть только свои смены; владелец или администратор — "
            "смены любого сотрудника своей точки. Если employee_id неизвестен "
            "и речь о самом пользователе, вызови инструмент без employee_id. "
            "Если запрошен другой сотрудник, сначала найди его по ФИО или "
            "телефону. Если не указаны обе даты, показываются ближайшие 30 дней "
            "включительно, начиная с сегодняшнего дня. Для периода укажи обе "
            "даты date_from и date_to включительно. Если у самого сотрудника "
            "несколько точек, попроси выбрать одну из возвращённых."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "ID сотрудника; не передавай для просмотра смен "
                        "самого пользователя, если ID неизвестен."
                    ),
                },
                "workplace_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "ID выбранной рабочей точки, если он известен.",
                },
                "date_from": {
                    "type": "string",
                    "format": "date",
                    "description": "Начало периода включительно, YYYY-MM-DD.",
                },
                "date_to": {
                    "type": "string",
                    "format": "date",
                    "description": "Конец периода включительно; максимум 90 дней.",
                },
            },
            "additionalProperties": False,
        },
    },
}

GET_WORKPLACE_SHIFTS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_workplace_shifts",
        "description": (
            "Показать смены всех сотрудников рабочей точки за период до 30 дней. "
            "Доступно только владельцу или администратору точки. Если точка "
            "неизвестна, используй инструмент без ID: единственная управляемая "
            "точка выберется автоматически, а при нескольких нужно попросить "
            "пользователя выбрать. Если не указаны обе даты, показываются "
            "ближайшие 30 дней включительно, начиная с сегодняшнего дня. "
            "Для другого периода укажи обе даты date_from и date_to включительно."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workplace_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "ID выбранной рабочей точки, если он известен.",
                },
                "workplace_name": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 255,
                    "description": "Название точки, выбранной пользователем.",
                },
                "date_from": {
                    "type": "string",
                    "format": "date",
                    "description": "Начало периода включительно, YYYY-MM-DD.",
                },
                "date_to": {
                    "type": "string",
                    "format": "date",
                    "description": "Конец периода включительно; максимум 30 дней.",
                },
            },
            "additionalProperties": False,
        },
    },
}


class AgentServiceError(RuntimeError):
    """Ошибка обработки запроса агента или ответа внешней модели."""


UNSUPPORTED_CALENDAR_REQUEST_ANSWER = (
    "Я могу работать только с доступными сейчас операциями календаря смен: "
    "вывести ваши рабочие точки, найти сотрудника по ФИО или телефону, "
    "посмотреть смены сотрудника или точки, подготовить изменение рабочей "
    "точки или составить график смен одного сотрудника с последующим подтверждением. "
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
                    "подходящего доступного tool, не выдумывай данные и не вызывай неизвестные "
                    "tools. Сообщи, что такую операцию пока можно выполнить "
                    "только вручную, и перечисли доступные возможности: вывести "
                    "рабочие точки пользователя, найти сотрудника по ФИО или "
                    "телефону, посмотреть смены сотрудника или всей рабочей точки, "
                    "подготовить изменение рабочей точки или составить график "
                    "смен одного сотрудника. "
                    "ВАЖНО: если пользователь просит посмотреть, показать или "
                    "узнать смены, обязательно вызови подходящий tool и не отвечай "
                    "по памяти или без данных инструмента. Для смен самого "
                    "пользователя вызови get_employee_shifts без employee_id. "
                    "Для смен конкретного другого сотрудника сначала вызови "
                    "lookup_employee_by_full_name или lookup_employee_by_phone, "
                    "затем после однозначного результата обязательно вызови "
                    "get_employee_shifts с полученными ID. Для запроса смен всех "
                    "сотрудников или расписания рабочей точки обязательно вызови "
                    "get_workplace_shifts; не ищи сотрудников по отдельности. "
                    "Инструменты просмотра сами находят доступные рабочие точки: "
                    "вызывай их без workplace_id, если точка не указана; при "
                    "нескольких точках спроси пользователя, какую выбрать. "
                    "Не проси пользователя сообщать ID, если его можно получить "
                    "через lookup tool. Если период просмотра не указан, передай "
                    "вызов без дат: инструмент покажет ближайшие 30 дней включая "
                    "сегодняшний. Для смен одного сотрудника максимум — 90 "
                    "календарных дней, для всех смен точки — 30 дней; обе "
                    "граничные даты включаются. Не запрашивай период, если его "
                    "можно определить из запроса; если он длиннее максимума, "
                    "попроси пользователя указать допустимый диапазон. "
                    "После результата со статусом workplace_required попроси "
                    "выбрать точку; при неоднозначном поиске сотрудника перечисли "
                    "совпадения и попроси выбрать, никогда не угадывай. Если "
                    "инструмент вернул no_shifts, сообщи, что смен за период нет. "
                    "После успешного просмотра смен всегда дай полный и конкретный "
                    "ответ, не ограничивайся фразой «вот график» или общим "
                    "подтверждением. Для одного сотрудника укажи его имя, "
                    "подтверждённый график (например, 2/2 или 5/2), если он явно "
                    "указан в запросе или однозначно следует из дат смен, часы "
                    "работы и перечисли все даты смен из результата инструмента. "
                    "Если график нельзя достоверно определить, не угадывай и "
                    "просто укажи даты и время смен. Для графика рабочей точки "
                    "сгруппируй смены по сотрудникам и для каждого перечисли "
                    "имя, даты и время; указывай цикл только если он достоверен. "
                    "Используй даты и часы именно из результата инструмента, "
                    "не пропускай смены и не добавляй отсутствующие. Например: "
                    "«У Ивана Ивановича график 2/2, работа с 09:00 до 21:00. "
                    "Смены запланированы на 26 ноября, 27 ноября, 30 ноября, "
                    "1 декабря, 4 декабря, 5 декабря, 8 декабря и 9 декабря». "
                    "Если пользователь явно просит составить, создать или "
                    "подготовить смены, сначала используй подходящий поиск "
                    "сотрудника по указанному ФИО или телефону, если employee_id "
                    "неизвестен. Если workplace_id неизвестен, вызови lookup tool "
                    "без него: при одной управляемой точке инструмент выберет её, "
                    "а при нескольких вернёт варианты, из которых нужно попросить "
                    "пользователя выбрать. При одном найденном сотруднике и "
                    "известной точке обязательно вызови create_shift_schedule и "
                    "передай ID, график и период без изменений. Если совпадений "
                    "несколько, перечисли варианты и спроси пользователя; никогда "
                    "не выбирай совпадение самостоятельно. Если по имени или "
                    "телефону нельзя найти сотрудника, уточни данные, а не ID, "
                    "если пользователь может их сообщить. "
                    "Используй tool list_my_workplaces для чтения рабочих точек и "
                    "lookup_employee_by_full_name или lookup_employee_by_phone "
                    "для поиска сотрудников только в доступных для управления "
                    "сменами точках. Обычному сотруднику разрешён просмотр "
                    "только собственных смен; права проверяются инструментом. "
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
                    LOOKUP_EMPLOYEE_BY_NAME_TOOL,
                    LOOKUP_EMPLOYEE_BY_PHONE_TOOL,
                    GET_EMPLOYEE_SHIFTS_TOOL,
                    GET_WORKPLACE_SHIFTS_TOOL,
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
        lookup_call_count = 0
        resolved_lookup: tuple[int, int] | None = None
        lookup_was_called = any(
            isinstance(call, dict)
            and isinstance(call.get("function"), dict)
            and call["function"].get("name")
            in {"lookup_employee_by_full_name", "lookup_employee_by_phone"}
            for call in tool_calls
        )

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue

            function = tool_call.get("function") or {}
            function_name = function.get("name")
            if function_name not in {
                "list_my_workplaces",
                "lookup_employee_by_full_name",
                "lookup_employee_by_phone",
                "get_employee_shifts",
                "get_workplace_shifts",
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
                                    "Доступны list_my_workplaces, поиск сотрудника "
                                    "по ФИО или телефону, просмотр смен сотрудника "
                                    "или точки, подготовка update_workplace и "
                                    "create_shift_schedule."
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

            if function_name in {"get_employee_shifts", "get_workplace_shifts"}:
                if function_name == "get_employee_shifts" and lookup_was_called:
                    tool_messages.append(
                        {
                            "role": "tool",
                            "content": json.dumps(
                                {
                                    "error": (
                                        "Сначала дождитесь результата поиска "
                                        "сотрудника, затем используйте только "
                                        "возвращённые employee_id и workplace_id."
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
                try:
                    if function_name == "get_employee_shifts":
                        request = EmployeeShiftsRequest.model_validate(arguments)
                        result = await get_employee_shifts(
                            request,
                            self.user,
                            self.db,
                        )
                    else:
                        request = WorkplaceShiftsRequest.model_validate(arguments)
                        result = await get_workplace_shifts(
                            request,
                            self.user,
                            self.db,
                        )
                    tool_result = result.model_dump(mode="json")
                except (ValidationError, ShiftViewToolError) as error:
                    tool_result = {"error": str(error)}
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

            if function_name in {
                "lookup_employee_by_full_name",
                "lookup_employee_by_phone",
            }:
                lookup_call_count += 1
                try:
                    request = EmployeeLookupRequest.model_validate(arguments)
                    expected_field = (
                        "full_name"
                        if function_name == "lookup_employee_by_full_name"
                        else "phone"
                    )
                    if getattr(request, expected_field) is None:
                        tool_result = {
                            "error": f"Для этого поиска необходимо указать {expected_field}."
                        }
                    else:
                        result = await lookup_employee(request, self.user, self.db)
                        tool_result = result.model_dump(mode="json")
                        if (
                            result.status == "matches"
                            and result.workplace is not None
                            and len(result.employees) == 1
                        ):
                            resolved_lookup = (
                                result.workplace.id,
                                result.employees[0].employee_id,
                            )
                        else:
                            resolved_lookup = None
                except (ValidationError, EmployeeLookupToolError) as error:
                    tool_result = {"error": str(error)}
                    resolved_lookup = None
                if lookup_call_count > 1:
                    resolved_lookup = None
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

            if function_name == "create_shift_schedule":
                if lookup_was_called:
                    tool_result = {
                        "error": (
                            "Сначала дождитесь результата поиска сотрудника и "
                            "используйте только возвращённый employee_id."
                        )
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

                tool_result, confirmation_id, confirmation_summary = (
                    await self._prepare_shift_schedule(arguments)
                )

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
            final_response = await send_gigachat_request(
                token,
                messages,
                **(
                    {
                        "tools": [
                            CREATE_SHIFT_SCHEDULE_TOOL,
                            GET_EMPLOYEE_SHIFTS_TOOL,
                        ],
                        "tool_choice": "auto",
                    }
                    if lookup_was_called
                    else {}
                ),
            )
        except GigaChatRequestError as error:
            raise AgentServiceError(str(error)) from error

        final_choice = self._get_choice(final_response)
        final_message = final_choice.get("message") or {}
        follow_up_calls = final_message.get("tool_calls") or []
        follow_up_function_call = final_message.get("function_call")
        if not follow_up_calls and isinstance(follow_up_function_call, dict):
            name = follow_up_function_call.get("name")
            arguments = follow_up_function_call.get("arguments") or {}
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments, ensure_ascii=False)
            if isinstance(name, str) and isinstance(arguments, str):
                follow_up_calls = [
                    {
                        "function": {"name": name, "arguments": arguments},
                    }
                ]

        if follow_up_calls:
            follow_up_tool_messages = []
            for call in follow_up_calls:
                function = call.get("function") if isinstance(call, dict) else None
                if not isinstance(function, dict) or function.get("name") not in {
                    "create_shift_schedule",
                    "get_employee_shifts",
                }:
                    continue
                function_name = function["name"]
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError as error:
                    raise AgentServiceError(
                        "GigaChat передал некорректные аргументы tool"
                    ) from error
                if not isinstance(arguments, dict):
                    tool_result = {
                        "error": "GigaChat передал аргументы tool в неверном формате."
                    }
                elif lookup_call_count != 1 or resolved_lookup is None:
                    tool_result = {
                        "error": (
                            "Поиск не вернул ровно одного сотрудника в однозначно "
                            "выбранной рабочей точке. Спросите пользователя, кого "
                            "или какую точку он имеет в виду."
                        )
                    }
                elif (
                    function_name == "create_shift_schedule"
                    and (
                        arguments.get("workplace_id") != resolved_lookup[0]
                        or arguments.get("employee_id") != resolved_lookup[1]
                    )
                ):
                    tool_result = {
                        "error": (
                            "Используйте только workplace_id и employee_id, "
                            "возвращённые последним поиском."
                        )
                    }
                elif (
                    function_name == "get_employee_shifts"
                    and arguments.get("employee_id") != resolved_lookup[1]
                ):
                    tool_result = {
                        "error": (
                            "Используйте только employee_id, возвращённый "
                            "последним поиском сотрудника."
                        )
                    }
                elif (
                    function_name == "get_employee_shifts"
                    and arguments.get("workplace_id") not in {None, resolved_lookup[0]}
                ):
                    tool_result = {
                        "error": (
                            "Используйте только workplace_id, возвращённый "
                            "последним поиском сотрудника."
                        )
                    }
                elif function_name == "create_shift_schedule" and confirmation_id is not None:
                    tool_result = {
                        "error": (
                            "За один запрос можно подготовить только одно "
                            "действие, требующее подтверждения."
                        )
                    }
                else:
                    if function_name == "create_shift_schedule":
                        (
                            tool_result,
                            confirmation_id,
                            confirmation_summary,
                        ) = await self._prepare_shift_schedule(arguments)
                    else:
                        try:
                            arguments["workplace_id"] = resolved_lookup[0]
                            request = EmployeeShiftsRequest.model_validate(arguments)
                            result = await get_employee_shifts(
                                request,
                                self.user,
                                self.db,
                            )
                            tool_result = result.model_dump(mode="json")
                        except (ValidationError, ShiftViewToolError) as error:
                            tool_result = {"error": str(error)}
                follow_up_tool_messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(tool_result, ensure_ascii=False),
                        **(
                            {"tool_call_id": call.get("id")}
                            if call.get("id")
                            else {}
                        ),
                    }
                )
            if follow_up_tool_messages:
                if isinstance(follow_up_function_call, dict):
                    for tool_message in follow_up_tool_messages:
                        tool_message["role"] = "function"
                        tool_message["name"] = follow_up_function_call["name"]
                        tool_message.pop("tool_call_id", None)
                messages.extend([final_message, *follow_up_tool_messages])
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

    async def _prepare_shift_schedule(
        self,
        arguments: dict,
    ) -> tuple[dict, str | None, str | None]:
        try:
            request = ShiftScheduleRequest.model_validate(arguments)
            plan = await prepare_shift_schedule(request, self.user, self.db)
        except (
            ValidationError,
            ShiftScheduleToolError,
            EmployeeNotFoundException,
            WorkplaceNotFoundException,
        ) as error:
            return {"error": str(error)}, None, None

        if not plan["shifts"]:
            return (
                {
                    "confirmation_required": False,
                    "summary": plan["summary"],
                    "message": (
                        "Новых смен нет: все даты уже заняты существующими сменами."
                    ),
                },
                None,
                None,
            )

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
        return (
            {
                "confirmation_required": True,
                "confirmation_id": pending.id,
                "summary": plan["summary"],
            },
            pending.id,
            plan["summary"],
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
