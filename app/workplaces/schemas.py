from datetime import time, datetime
from typing import Annotated, Any
from pydantic import (
    BaseModel, 
    Field, 
    field_validator, 
    BeforeValidator, 
    PlainSerializer, 
    ConfigDict,
    model_validator
)

from app.employees.schemas import EmployeeResponse


# Функция-валидатор для формата HH:MM
def parse_hh_mm(v: Any) -> time:
    if isinstance(v, str):
        try:
            return datetime.strptime(v, "%H:%M").time()
        except ValueError:
            raise ValueError("Время должно быть в формате HH:MM")
    if isinstance(v, time):
        return v
    raise ValueError("Некорректный формат времени")

# Аннотация и сериализатор для времени в формате HH:MM для входных данных и вывода
TimeHHMM = Annotated[time, BeforeValidator(parse_hh_mm)]
TimeOutputHHMM = Annotated[
    time, 
    PlainSerializer(lambda v: v.strftime("%H:%M"), return_type=str)
]


class WorkplaceBase(BaseModel):
    name: Annotated[str, Field(
        max_length=255, 
        description="Название рабочего пространства"
    )]
    address: Annotated[str | None, Field(
        max_length=500, 
        description="Адрес"
    )]
    phone: Annotated[str | None, Field(
        None, 
        max_length=20, 
        description="Контактный телефон"
    )]
    description: Annotated[str | None, Field(
        None, 
        description="Описание"
    )]
    
    workplace_type: Annotated[str, Field(
        max_length=50, 
        description="Тип (например, 'ozon', 'wildberries', 'yandex_market', 'other')"
    )]
    
    work_start_time: Annotated[TimeHHMM, Field(
        description="Время начала работы (HH:MM)", 
        json_schema_extra={"type": "string", "format": "time", "example": "09:00"}
    )]
    work_end_time: Annotated[TimeHHMM, Field(
        description="Время окончания работы (HH:MM)", 
        json_schema_extra={"type": "string", "format": "time", "example": "21:00"}
    )]

    @field_validator("work_end_time")
    @classmethod
    def validate_time_range(cls, v: time, info) -> time:
        start_time = info.data.get("work_start_time")
        if start_time and v <= start_time:
            raise ValueError("Время окончания работы должно быть строго позже времени начала")
        return v


class WorkplaceCreate(WorkplaceBase):
    pass


class WorkplaceResponse(WorkplaceBase):
    id: Annotated[int, Field(
        ge=1,
        description="ID рабочего пространства"
    )]
    owner_id: Annotated[int, Field(
        ge=1,
        description="ID владельца рабочего пространства"
    )]

    model_config = ConfigDict(from_attributes=True)


class WorkplaceWithEmployeesResponse(WorkplaceResponse):
    employees: Annotated[list[EmployeeResponse], Field(
        description="Список сотрудников рабочего пространства"
    )]


class WorkplaceUpdate(BaseModel):
    name: Annotated[str | None, Field(
        None,
        max_length=255, 
        description="Название рабочего пространства"
    )]
    address: Annotated[str | None, Field(
        None,
        max_length=500, 
        description="Адрес"
    )]
    phone: Annotated[str | None, Field(
        None, 
        max_length=20, 
        description="Контактный телефон"
    )]
    description: Annotated[str | None, Field(
        None, 
        description="Описание"
    )]
    
    workplace_type: Annotated[str | None, Field(
        None,
        max_length=50, 
        description="Тип (например, 'ozon', 'wildberries', 'yandex_market', 'other')"
    )]
    
    work_start_time: Annotated[TimeHHMM | None, Field(
        None,
        description="Время начала работы (HH:MM)", 
        json_schema_extra={"type": "string", "format": "time", "example": "09:00"}
    )]
    work_end_time: Annotated[TimeHHMM | None, Field(
        None,
        description="Время окончания работы (HH:MM)", 
        json_schema_extra={"type": "string", "format": "time", "example": "21:00"}
    )]

    @model_validator(mode='after')
    def validate_work_times(self) -> 'WorkplaceUpdate':
        start = self.work_start_time
        end = self.work_end_time

        if (start is None) != (end is None):
            raise ValueError("Необходимо указать оба времени: и начала, и окончания работы (или не указывать ни одного)")

        if start is not None and end is not None:
            if end <= start:
                raise ValueError("Время окончания работы должно быть строго позже времени начала")
                
        return self