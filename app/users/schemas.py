from pydantic import BaseModel, ConfigDict, Field, EmailStr, SecretStr

from typing import Annotated


class UserBase(BaseModel):
    first_name: Annotated[str, Field(description="Имя пользователя")]
    second_name: Annotated[str, Field(description="Фамилия пользователя")]
    third_name: Annotated[str, Field(default=None, description="Отчество пользователя")]
    email: Annotated[EmailStr, Field(description="Email пользователя")]
    phone: Annotated[str, Field(
        pattern=r'^(\+7\d{10}|8\d{10})$',
        description="Телефон пользователя в формате +7XXXXXXXXXX или 8XXXXXXXXXX",
    )]


class UserCreate(UserBase):
    password: Annotated[SecretStr, Field(
        min_length=8,
        description="Пароль (минимум 8 символов)"
    )]


class UserResponse(UserBase):
    id: Annotated[int, Field(...)]
    is_active: Annotated[bool, Field(
        description="Существует ли пользователь"
    )]

    model_config = ConfigDict(from_attributes=True)
