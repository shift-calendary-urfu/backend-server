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


class ShiftsDuplicate(BaseModel):
    dates: Annotated[list[dt.date], Field(
        min_length=1,
        description="Список дат, на которые нужно размножить смены"
    )]
    shift_ids: Annotated[list[int], Field(
        min_length=1,
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


class ShiftsDuplicateResponse(BaseModel):
    count_duplicated_shifts_created: Annotated[int, Field(
        ge=0,
        description="Количество успешно созданных дубликатов смен"
    )]
    workplace_id: Annotated[int, Field(
        ge=1,
        description="ID рабочего пространства, в котором были созданы дубликаты смен"
    )]
    period: Annotated[dict[str, dt.date], Field(
        description="Период, на который были созданы дубликаты смен",
        json_schema_extra={
            "example": {
                "start_date": "2026-10-22",
                "end_date": "2026-10-23"
            }
        }
    )]
    message: Annotated[str, Field(
        description="Сообщения о процессе создания дубликатов смен"
    )]


class EmployeeReportItem(BaseModel):
    """
    Строка отчёта по одному сотруднику за месяц.
    """
    employee_id: Annotated[int, Field(
        ge=1,
        description="ID работника"
    )]
    full_name: Annotated[str, Field(
        description="ФИО работника"
    )]
    hours_worked: Annotated[float, Field(
        ge=0,
        description="Количество отработанных часов за месяц (все смены)"
    )]
    full_shifts_count: Annotated[int, Field(
        ge=0,
        description="Количество полных смен (от открытия до закрытия рабочей точки)"
    )]
    full_shifts_hours: Annotated[float, Field(
        ge=0,
        description="Количество часов, отработанных в полных сменах"
    )]


class CalendarReportResponse(BaseModel):
    """
    Отчёт по рабочей точке за месяц.
    """
    workplace_id: Annotated[int, Field(
        ge=1,
        description="ID рабочего пространства"
    )]
    period: Annotated[str, Field(
        pattern=r"^\d{4}-\d{2}$",
        description="Период отчёта в формате YYYY-MM"
    )]
    total_hours: Annotated[float, Field(
        ge=0,
        description="Общее количество отработанных часов на точке за месяц"
    )]
    total_shifts: Annotated[int, Field(
        ge=0,
        description="Общее количество смен на точке за месяц"
    )]
    employees: Annotated[list[EmployeeReportItem], Field(
        description="Отчёт по каждому работнику"
    )]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "workplace_id": 1,
                    "period": "2026-10",
                    "total_hours": 58.0,
                    "total_shifts": 5,
                    "employees": [
                        {
                            "employee_id": 1,
                            "full_name": "Иванов Иван Иванович",
                            "hours_worked": 34.0,
                            "full_shifts_count": 2,
                            "full_shifts_hours": 26.0
                        },
                        {
                            "employee_id": 2,
                            "full_name": "Смирнова Анна",
                            "hours_worked": 24.0,
                            "full_shifts_count": 2,
                            "full_shifts_hours": 24.0
                        }
                    ]
                }
            ]
        }
    )
