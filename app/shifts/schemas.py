from pydantic import (
    BaseModel, 
    Field, 
    ConfigDict,
    BeforeValidator, 
    model_validator, 
    RootModel
)

from typing import Annotated, Any

import datetime as dt


def parse_hh_mm(v: Any) -> dt.time:
    if isinstance(v, str):
        try:
            return dt.datetime.strptime(v, "%H:%M").time()
        except ValueError:
            raise ValueError("Время должно быть в формате HH:MM")
    if isinstance(v, dt.time):
        return v
    raise ValueError("Некорректный формат времени")

# Аннотация и сериализатор для времени в формате HH:MM для входных данных и вывода
TimeHHMM = Annotated[dt.time, BeforeValidator(parse_hh_mm)]


class ShiftBase(BaseModel):
    employee_id: Annotated[int, Field(
        ge=1,
        description="ID работника"    
    )]
    date: Annotated[dt.date, Field(
        description='Дата смены'
    )]
    start_time: Annotated[TimeHHMM, Field(
        description = 'Время начала смены',
        json_schema_extra={"type": "string", "format": "time", "example": "8:00"}
    )]
    end_time: Annotated[TimeHHMM, Field(
        description ='Конец времени смены',
        json_schema_extra={"type": "string", "format": "time", "example": "21:00"}        
    )]
    notes: Annotated[str | None, Field(
        default=None,
        description ="Примечания"
    )]

    @model_validator(mode='after')
    def validate_shift_times(self):
        start = self.start_time
        end = self.end_time

        if start.minute % 30 != 0 or end.minute % 30 != 0:
            raise ValueError("Время должно быть кратно 30 минутам")

        if end <= start:
            raise ValueError(
                "Время окончания смены должно быть строго позже времени начала"
            )

        return self


class ShiftCreate(ShiftBase):
    pass


class ShiftUserResponse(BaseModel):
    first_name: Annotated[str, Field(
        description="Имя работника"
    )]
    second_name: Annotated[str, Field(
        description="Фамилия работника"
    )]
    third_name: Annotated[str | None, Field(
        default=None,
        description="Отчество работника"
    )]


class ShiftResponse(ShiftBase, ShiftUserResponse):
    id: Annotated[int, Field(
        ge=1,
        description="ID смены"
    )]
    workplace_id: Annotated[int, Field(
        ge=1,
        description="ID места работы"
    )]


class ShiftUpdate(BaseModel):
    start_time: Annotated[TimeHHMM, Field(
            description = 'Время начала смены',
            json_schema_extra={"type": "string", "format": "time", "example": "8:00"}
        )]
    end_time: Annotated[TimeHHMM, Field(
        description ='Конец времени смены',
        json_schema_extra={"type": "string", "format": "time", "example": "21:00"}        
    )]

    @model_validator(mode='after')
    def validate_shift_times(self):
        start = self.start_time
        end = self.end_time

        if start.minute % 30 != 0 or end.minute % 30 != 0:
            raise ValueError("Время должно быть кратно 30 минутам")

        if end <= start:
            raise ValueError(
                "Время окончания смены должно быть строго позже времени начала"
            )

        return self


class CalendarResponse(RootModel[dict[dt.date, list[ShiftResponse]]]):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "2026-10-22": [
                        {
                            "first_name": "Иван",
                            "second_name": "Иванов",
                            "third_name": None,
                            "employee_id": 1,
                            "date": "2026-10-22",
                            "start_time": "08:00",
                            "end_time": "21:00",
                            "notes": None,
                            "id": 1,
                            "workplace_id": 1,
                        }
                    ]
                }
            ]
        }
    )


class ShiftsDublicate(BaseModel):
    dates: Annotated[list[dt.date], Field(
        default_factory=list,
        description="Список дат, на которые нужно размножить смены"
    )]
    shift_ids: Annotated[list[int], Field(
        default_factory=list,
        description="Список ID смен, которые нужно размножить"
    )]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "dates": ["2026-10-22", "2026-10-23"],
                    "shift_ids": [1, 2, 3]
                }
            ]
        }
    )