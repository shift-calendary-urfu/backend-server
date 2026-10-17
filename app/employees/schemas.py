from pydantic import BaseModel, Field

from typing import Annotated

from datetime import date


class EmployeeCreate(BaseModel):
    phone: Annotated[str, Field(
        pattern=r'^(\+7\d{10}|8\d{10})$',
        description="Телефон сотрудника (формат: +7XXXXXXXXXX, 8XXXXXXXXXX)"
    )]
    role: Annotated[str, Field(
        pattern="^(owner|admin|employee)$",
        description="Роль сотрудника ('owner', 'admin', 'employee')"
    )]
    position: Annotated[str | None, Field(
        default=None,
        description="Должность сотрудника"
    )]


class EmployeeUpdate(BaseModel):
    role: Annotated[str | None, Field(
        default=None,
        pattern="^(owner|admin|employee)$",
        description="Роль сотрудника ('admin', 'employee')"
    )]
    position: Annotated[str | None, Field(
        default=None,
        description="Должность сотрудника"
    )]


class EmployeeUserResponse(BaseModel):
    id: Annotated[int, Field(
        description="ID пользователя"
    )]
    first_name: Annotated[str, Field(
        description="Имя пользователя"
    )]
    second_name: Annotated[str, Field(
        description="Фамилия пользователя"
    )]
    third_name: Annotated[str | None, Field(
        default=None,
        description="Отчество пользователя"
    )]
    phone: Annotated[str, Field(
        description="Телефон пользователя"
    )]


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
        pattern="^(owner|admin|employee)$",
        description="Роль сотрудника ('owner', 'admin', 'employee')"
    )]
    position: Annotated[str | None, Field(
        default=None,
        description="Должность сотрудника"
    )]
    hire_date: Annotated[date | None, Field(
        default=None,
        description="Дата найма сотрудника"
    )]
    is_active: Annotated[bool, Field(
        description="Статус активности сотрудника"
    )]
    

    user: Annotated[EmployeeUserResponse, Field(
        description="Информация о пользователе (имя, фамилия, отчество)"
    )]