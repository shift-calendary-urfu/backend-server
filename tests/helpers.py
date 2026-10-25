from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

import jwt
from sqlalchemy import update

from app.config import settings
from app.employees.model import Employee
from app.shifts.model import Shift
from app.shift_templates.models import ShiftTemplate
from app.users.model import User


_phone_counter = 0


def next_phone() -> str:
    global _phone_counter
    _phone_counter += 1
    return f"+7{7000000000 + _phone_counter}"


def auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def make_token(
    email: str,
    user_id: int,
    *,
    token_type: str = "access",
    expired: bool = False,
) -> str:
    expires_at = datetime.now(timezone.utc) + (
        timedelta(minutes=-5) if expired else timedelta(minutes=30)
    )
    return jwt.encode(
        {
            "sub": email,
            "id": user_id,
            "exp": expires_at,
            "token_type": token_type,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


async def register_user(client, **overrides) -> dict:
    payload = {
        "first_name": "Иван",
        "second_name": "Иванов",
        "third_name": "Иванович",
        "email": f"user-{uuid4().hex}@example.com",
        "phone": next_phone(),
        "password": "Password1",
    }
    payload.update(overrides)
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    body["password"] = payload["password"]
    return body


async def login(client, email: str, password: str):
    return await client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )


async def register_and_login(client, **overrides) -> tuple[dict, dict[str, str]]:
    user = await register_user(client, **overrides)
    response = await login(client, user["email"], user["password"])
    assert response.status_code == 200, response.text
    return user, auth_header(response.json()["access_token"])


def workplace_payload(**overrides) -> dict:
    payload = {
        "name": "ПВЗ на Ленина",
        "address": f"ул. Ленина, {uuid4().hex[:8]}",
        "phone": "+79990001122",
        "description": "Основная точка",
        "workplace_type": "ozon",
        "work_start_time": "09:00",
        "work_end_time": "21:00",
    }
    payload.update(overrides)
    return payload


async def create_workplace(client, headers, **overrides) -> dict:
    response = await client.post(
        "/workplaces/",
        json=workplace_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def employee_payload(phone: str, **overrides) -> dict:
    payload = {
        "phone": phone,
        "role": "employee",
        "position": "Кассир",
    }
    payload.update(overrides)
    return payload


async def create_employee(
    client,
    headers,
    workplace_id: int,
    phone: str,
    **overrides,
) -> dict:
    response = await client.post(
        "/employees/",
        params={"workplace_id": workplace_id},
        json=employee_payload(phone, **overrides),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def shift_payload(employee_id: int, **overrides) -> dict:
    payload = {
        "employee_id": employee_id,
        "date": "2026-11-02",
        "start_time": "09:00",
        "end_time": "18:00",
    }
    payload.update(overrides)
    if isinstance(payload.get("date"), date):
        payload["date"] = payload["date"].isoformat()
    return payload


async def create_shift(
    client,
    headers,
    workplace_id: int,
    employee_id: int,
    **overrides,
) -> dict:
    response = await client.post(
        "/shifts/",
        params={"workplace_id": workplace_id},
        json=shift_payload(employee_id, **overrides),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_employee(
    session_factory,
    *,
    user_id: int,
    workplace_id: int,
    role: str = "employee",
    position: str | None = "Кассир",
    is_active: bool = True,
) -> int:
    async with session_factory() as session:
        employee = Employee(
            user_id=user_id,
            workplace_id=workplace_id,
            role=role,
            position=position,
            is_active=is_active,
            hire_date=date.today(),
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def add_shift(session_factory, *, workplace_id: int, employee_id: int) -> int:
    async with session_factory() as session:
        shift = Shift(
            workplace_id=workplace_id,
            employee_id=employee_id,
            date=date.today(),
            start_time=time(9, 0),
            end_time=time(18, 0),
            status="planned",
            is_active=True,
        )
        session.add(shift)
        await session.commit()
        await session.refresh(shift)
        return shift.id


async def add_template(session_factory, *, workplace_id: int, employee_id: int) -> int:
    async with session_factory() as session:
        template = ShiftTemplate(
            workplace_id=workplace_id,
            employee_id=employee_id,
            work_pattern="2/2",
            shift_duration_hours=12,
            default_start_time=time(9, 0),
            cycle_start_date=date.today(),
            is_active=True,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template.id


async def set_user_active(session_factory, user_id: int, is_active: bool) -> None:
    async with session_factory() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(is_active=is_active)
        )
        await session.commit()
