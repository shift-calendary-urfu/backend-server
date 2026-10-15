from pydantic import BaseModel, Field

from typing import Annotated

from datetime import date

class EmployeeUserResponse(BaseModel):
    id: Annotated[int, Field(description="ID пользователя")]
    first_name: Annotated[str, Field(description="Имя пользователя")]
    second_name: Annotated[str, Field(description="Фамилия пользователя")]
    third_name: Annotated[str | None, Field(description="Отчество пользователя")]


class EmployeeResponse(BaseModel):
    id: Annotated[int, Field(
        description="ID сотрудника"
    )]
    user_id: Annotated[int, Field(
        description="ID пользователя"
    )]
    workplace_id: Annotated[int, Field(
        description="ID рабочего пространства"
    )]
    role: Annotated[str, Field(
        description="Роль сотрудника"
    )]
    position: Annotated[str | None, Field(
        description="Должность сотрудника"
    )]
    hire_date: Annotated[date | None, Field(
        description="Дата найма сотрудника"
    )]
    is_active: Annotated[bool, Field(
        description="Статус активности сотрудника"
    )]
    

    user: Annotated[EmployeeUserResponse, Field(
        description="Информация о пользователе (имя, фамилия, отчество)"
    )]