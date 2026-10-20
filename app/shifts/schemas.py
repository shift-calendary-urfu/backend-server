from pydantic import BaseModel, Field, BeforeValidator

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
        description = 'Время начала смены'
    )]
    end_time: Annotated[TimeHHMM, Field(
        description ='Конец времени смены'
    )]
    notes: Annotated[str | None, Field(
        default=None,
        description ="Примечания"
    )]


class ShiftCreate(ShiftBase):
    pass