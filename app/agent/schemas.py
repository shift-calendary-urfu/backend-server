from datetime import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ListMyWorkplacesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            description="Запрос пользователя о его рабочих точках",
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

    id: Annotated[int, Field(ge=1)]
    name: Annotated[str, Field(max_length=255)]
    address: Annotated[str | None, Field(max_length=500)]
    description: Annotated[str | None, Field(max_length=5000)]
    workplace_type: Annotated[str, Field(max_length=50)]
    work_start_time: str
    work_end_time: str

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

    workplaces: list[WorkplaceAgentSummary]

    @property
    def count(self) -> int:
        return len(self.workplaces)


class AgentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Annotated[
        str,
        Field(min_length=1, description="Финальный ответ пользователя"),
    ]
    confirmation_required: bool = False
    confirmation_id: Annotated[str | None, Field(min_length=1)] = None
    confirmation_summary: Annotated[str | None, Field(min_length=1)] = None


class WorkplaceMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workplace_id: Annotated[int | None, Field(default=None, ge=1)]
    name: Annotated[str | None, Field(default=None, max_length=255)]
    address: Annotated[str | None, Field(default=None, max_length=500)]
    phone: Annotated[str | None, Field(default=None, max_length=20)]
    description: Annotated[str | None, Field(default=None, max_length=5000)]
    workplace_type: Annotated[str | None, Field(default=None, max_length=50)]
    work_start_time: Annotated[str | None, Field(default=None)]
    work_end_time: Annotated[str | None, Field(default=None)]


class AgentConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_id: Annotated[str, Field(min_length=1)]
    approved: bool


class AgentConfirmationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["executed", "cancelled", "expired", "invalid"]
    answer: Annotated[str, Field(min_length=1)]