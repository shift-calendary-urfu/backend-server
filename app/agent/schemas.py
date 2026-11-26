"""Pydantic-схемы запросов и ответов агента."""

from datetime import time
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ListMyWorkplacesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            description=(
                "Текстовый запрос к агенту о рабочих точках или календаре смен. "
                "После удаления пробелов по краям должен содержать от 1 до 500 "
                "символов."
            ),
        ),
    ]

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Запрос не может быть пустым")
        return value


class WorkplaceAgentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: Annotated[int, Field(ge=1, description="Уникальный идентификатор рабочей точки.")]
    name: Annotated[str, Field(max_length=255, description="Название рабочей точки.")]
    address: Annotated[
        str | None,
        Field(max_length=500, description="Адрес рабочей точки; может отсутствовать."),
    ]
    description: Annotated[
        str | None,
        Field(max_length=5000, description="Описание рабочей точки; может отсутствовать."),
    ]
    workplace_type: Annotated[
        str,
        Field(max_length=50, description="Тип рабочей точки, например маркетплейс или другой вид места работы."),
    ]
    work_start_time: Annotated[
        str,
        Field(description="Время начала работы в формате HH:MM."),
    ]
    work_end_time: Annotated[
        str,
        Field(description="Время окончания работы в формате HH:MM."),
    ]

    @field_validator("work_start_time", "work_end_time", mode="before")
    @classmethod
    def format_work_time(cls, value: object) -> str:
        if isinstance(value, time):
            return value.strftime("%H:%M")
        if isinstance(value, str):
            return value
        raise ValueError("Некорректный формат времени")


class ListMyWorkplacesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workplaces: Annotated[
        list[WorkplaceAgentSummary],
        Field(description="Список рабочих точек, доступных текущему пользователю."),
    ]

    @property
    def count(self) -> int:
        return len(self.workplaces)


class AgentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Annotated[
        str,
        Field(
            min_length=1,
            description="Текстовый ответ агента на запрос пользователя.",
        ),
    ]
    confirmation_required: Annotated[
        bool,
        Field(
            description=(
                "Признак того, что агент подготовил действие, которое нужно "
                "отдельно подтвердить через POST /agent/confirm."
            ),
        ),
    ] = False
    confirmation_id: Annotated[
        str | None,
        Field(
            min_length=1,
            description=(
                "Идентификатор ожидающего действия для передачи в "
                "POST /agent/confirm; отсутствует, если подтверждение не требуется."
            ),
        ),
    ] = None
    confirmation_summary: Annotated[
        str | None,
        Field(
            min_length=1,
            description=(
                "Краткое описание подготовленного действия для подтверждения; "
                "отсутствует, если действие не ожидает подтверждения."
            ),
        ),
    ] = None


class WorkplaceMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workplace_id: Annotated[
        int | None,
        Field(default=None, ge=1, description="Идентификатор рабочей точки, к которой относится изменение."),
    ]
    name: Annotated[
        str | None,
        Field(default=None, max_length=255, description="Новое название рабочей точки."),
    ]
    address: Annotated[
        str | None,
        Field(default=None, max_length=500, description="Новый адрес рабочей точки."),
    ]
    phone: Annotated[
        str | None,
        Field(default=None, max_length=20, description="Новый контактный телефон рабочей точки."),
    ]
    description: Annotated[
        str | None,
        Field(default=None, max_length=5000, description="Новое описание рабочей точки."),
    ]
    workplace_type: Annotated[
        str | None,
        Field(default=None, max_length=50, description="Новый тип рабочей точки."),
    ]
    work_start_time: Annotated[
        str | None,
        Field(default=None, description="Новое время начала работы в формате HH:MM."),
    ]
    work_end_time: Annotated[
        str | None,
        Field(default=None, description="Новое время окончания работы в формате HH:MM."),
    ]


class ShiftScheduleRequest(BaseModel):
    """Параметры подготовки графика смен для одного сотрудника."""

    model_config = ConfigDict(extra="forbid")

    workplace_id: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "ID активной рабочей точки, для которой готовится график. "
                "Текущий пользователь должен быть её владельцем или администратором."
            ),
        ),
    ]
    employee_id: Annotated[
        int,
        Field(
            ge=1,
            description=(
                "ID одного активного сотрудника, состоящего в указанной рабочей "
                "точке; для остальных сотрудников смены не создаются."
            ),
        ),
    ]
    schedule: Annotated[
        str | None,
        Field(
            default=None,
            max_length=32,
            description=(
                "Цикл в формате «рабочие дни/выходные дни», например «5/2», "
                "«2/2» или «7/0»; число рабочих дней должно быть не меньше 1, "
                "а число выходных — не меньше 0. Цикл начинается сегодня с "
                "рабочего дня. При отсутствии или некорректном значении "
                "готовится только одна смена на сегодня, а period не применяется."
            ),
        ),
    ] = None
    period: Annotated[
        int,
        Field(
            ge=1,
            le=90,
            description=(
                "Длительность графика в календарных днях, начиная с сегодняшнего "
                "дня; допустимо от 1 до 90. Определяет временной диапазон для "
                "корректного schedule; при отсутствии или ошибке schedule "
                "планируется одна смена на сегодня независимо от period."
            ),
        ),
    ]
    start_time: Annotated[
        str | None,
        Field(
            default=None,
            pattern=r"^\d{1,2}:\d{2}$",
            description=(
                "Необязательное время начала каждой смены в формате HH:MM, "
                "с минутами 00 или 30. Должно передаваться вместе с end_time; "
                "если оба значения отсутствуют, берётся время открытия точки."
            ),
        ),
    ] = None
    end_time: Annotated[
        str | None,
        Field(
            default=None,
            pattern=r"^\d{1,2}:\d{2}$",
            description=(
                "Необязательное время окончания каждой смены в формате HH:MM, "
                "с минутами 00 или 30; должно быть позже start_time. Должно "
                "передаваться вместе с start_time; если оба значения отсутствуют, "
                "берётся время закрытия точки."
            ),
        ),
    ] = None

    @model_validator(mode="after")
    def validate_shift_time_pair(self) -> "ShiftScheduleRequest":
        """Проверяет, что переопределение времени задано целиком и допустимо."""
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Для переопределения времени укажите и start_time, и end_time")
        if self.start_time is not None and self.end_time is not None:
            try:
                start = datetime.strptime(self.start_time, "%H:%M").time()
                end = datetime.strptime(self.end_time, "%H:%M").time()
            except ValueError as error:
                raise ValueError("Время должно быть в формате HH:MM") from error
            if start.minute % 30 != 0 or end.minute % 30 != 0:
                raise ValueError("Время должно быть кратно 30 минутам")
            if end <= start:
                raise ValueError("Время окончания должно быть позже времени начала")
        return self


class AgentConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_id: Annotated[
        str,
        Field(
            min_length=1,
            description=(
                "Идентификатор ожидающего действия, полученный в ответе "
                "POST /agent/query."
            ),
        ),
    ]
    approved: Annotated[
        bool,
        Field(
            description=(
                "Решение по действию: true — выполнить, false — отменить. "
                "Подтверждение можно использовать один раз в течение 10 минут."
            ),
        ),
    ]


class AgentConfirmationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Annotated[
        Literal["executed", "cancelled", "expired", "invalid"],
        Field(
            description=(
                "Результат обработки подтверждения: executed — действие выполнено; "
                "cancelled — отменено; expired — срок истёк; invalid — "
                "идентификатор недействителен или выполнение запрещено."
            ),
        ),
    ]
    answer: Annotated[
        str,
        Field(min_length=1, description="Пояснение результата подтверждения действия."),
    ]