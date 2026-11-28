import datetime as dt

import pytest

from tests.helpers import (
    add_employee,
    create_shift,
    create_workplace,
    register_and_login,
)

REPORT_URL = "/shifts/reports/employee"
NO_ACCESS = "You must be the owner or admin of this workplace, or this employee"

# «Сегодня» в тестах зафиксировано, чтобы результат не зависел от даты запуска
TODAY = dt.date(2026, 11, 15)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("app.shifts.services._today", lambda: TODAY)


def _params(workplace_id: int, employee_id: int, month: int = 11, year: int = 2026) -> dict:
    return {
        "workplace_id": workplace_id,
        "employee_id": employee_id,
        "month": month,
        "year": year,
    }


@pytest.mark.asyncio
async def test_employee_report_requires_token(client):
    response = await client.get(REPORT_URL, params=_params(1, 1))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_employee_report_shifts_until_today_with_notes(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _ = await register_and_login(
        client, first_name="Анна", second_name="Смирнова", third_name="Петровна"
    )
    colleague, _ = await register_and_login(client)
    # Точка работает с 09:00 до 21:00 (значение по умолчанию в helpers)
    workplace = await create_workplace(client, headers)
    employee_id = await add_employee(
        session_factory, user_id=worker["id"], workplace_id=workplace["id"]
    )
    colleague_id = await add_employee(
        session_factory, user_id=colleague["id"], workplace_id=workplace["id"]
    )

    # Создаём не по порядку — в отчёте смены должны идти по датам
    partial = await create_shift(
        client, headers, workplace["id"], employee_id,
        date="2026-11-03", start_time="09:00", end_time="18:00",
        notes="Ушла раньше по согласованию",
    )
    full = await create_shift(
        client, headers, workplace["id"], employee_id,
        date="2026-11-02", start_time="09:00", end_time="21:00",
    )
    # Смена ровно «сегодня» учитывается
    today_shift = await create_shift(
        client, headers, workplace["id"], employee_id,
        date=TODAY.isoformat(), start_time="10:00", end_time="14:00",
        notes="Подмена",
    )
    # Не попадают: будущая смена, удалённая, другой месяц, смена коллеги
    await create_shift(client, headers, workplace["id"], employee_id, date="2026-11-20")
    removed = await create_shift(
        client, headers, workplace["id"], employee_id, date="2026-11-04"
    )
    await client.delete(
        f"/shifts/{removed['id']}",
        params={"workplace_id": workplace["id"]},
        headers=headers,
    )
    await create_shift(client, headers, workplace["id"], employee_id, date="2026-10-31")
    await create_shift(client, headers, workplace["id"], colleague_id, date="2026-11-05")

    response = await client.get(
        REPORT_URL, params=_params(workplace["id"], employee_id), headers=headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["employee_id"] == employee_id
    assert body["full_name"] == "Смирнова Анна Петровна"
    assert body["workplace_id"] == workplace["id"]
    assert body["period"] == "2026-11"
    assert body["date_from"] == "2026-11-01"
    assert body["date_to"] == "2026-11-15"
    assert body["total_shifts"] == 3
    assert body["total_hours"] == 25
    assert body["full_shifts_count"] == 1
    assert body["full_shifts_hours"] == 12

    assert [item["shift_id"] for item in body["shifts"]] == [
        full["id"], partial["id"], today_shift["id"]
    ]
    assert body["shifts"][0] == {
        "shift_id": full["id"],
        "date": "2026-11-02",
        "start_time": "09:00:00",
        "end_time": "21:00:00",
        "hours": 12,
        "is_full_shift": True,
        "notes": None,
    }
    assert body["shifts"][1]["hours"] == 9
    assert body["shifts"][1]["is_full_shift"] is False
    assert body["shifts"][1]["notes"] == "Ушла раньше по согласованию"
    assert body["shifts"][2]["notes"] == "Подмена"


@pytest.mark.asyncio
async def test_employee_report_past_and_future_months(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _ = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_id = await add_employee(
        session_factory, user_id=worker["id"], workplace_id=workplace["id"]
    )
    await create_shift(client, headers, workplace["id"], employee_id, date="2026-10-31")
    await create_shift(client, headers, workplace["id"], employee_id, date="2026-12-01")

    past = await client.get(
        REPORT_URL, params=_params(workplace["id"], employee_id, month=10), headers=headers
    )
    future = await client.get(
        REPORT_URL, params=_params(workplace["id"], employee_id, month=12), headers=headers
    )

    # Прошлый месяц — целиком, до последнего дня
    assert past.status_code == 200, past.text
    assert past.json()["date_to"] == "2026-10-31"
    assert past.json()["total_shifts"] == 1

    # Будущий месяц — смены ещё не отработаны
    assert future.status_code == 200, future.text
    assert future.json()["total_shifts"] == 0
    assert future.json()["total_hours"] == 0
    assert future.json()["shifts"] == []


@pytest.mark.asyncio
async def test_employee_report_permissions(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    admin, admin_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    colleague, _ = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await add_employee(
        session_factory, user_id=admin["id"], workplace_id=workplace["id"], role="admin"
    )
    worker_id = await add_employee(
        session_factory, user_id=worker["id"], workplace_id=workplace["id"]
    )
    colleague_id = await add_employee(
        session_factory, user_id=colleague["id"], workplace_id=workplace["id"]
    )

    worker_params = _params(workplace["id"], worker_id)
    colleague_params = _params(workplace["id"], colleague_id)

    by_owner = await client.get(REPORT_URL, params=colleague_params, headers=owner_headers)
    by_admin = await client.get(REPORT_URL, params=colleague_params, headers=admin_headers)
    worker_self = await client.get(REPORT_URL, params=worker_params, headers=worker_headers)
    worker_other = await client.get(
        REPORT_URL, params=colleague_params, headers=worker_headers
    )
    by_stranger = await client.get(
        REPORT_URL, params=worker_params, headers=stranger_headers
    )

    assert by_owner.status_code == 200, by_owner.text
    assert by_admin.status_code == 200, by_admin.text
    assert worker_self.status_code == 200, worker_self.text
    assert worker_other.status_code == 403
    assert worker_other.json()["detail"] == NO_ACCESS
    assert by_stranger.status_code == 403
    assert by_stranger.json()["detail"] == NO_ACCESS


@pytest.mark.asyncio
async def test_employee_report_cannot_use_other_workplace(client, session_factory):
    """Работник своей точки не получает доступ, подставив ID чужой точки."""
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    own_workplace = await create_workplace(client, owner_headers)
    other_workplace = await create_workplace(client, owner_headers)
    worker_id = await add_employee(
        session_factory, user_id=worker["id"], workplace_id=own_workplace["id"]
    )

    response = await client.get(
        REPORT_URL,
        params=_params(other_workplace["id"], worker_id),
        headers=worker_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == NO_ACCESS


@pytest.mark.asyncio
async def test_employee_report_fired_employee(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    worker_id = await add_employee(
        session_factory,
        user_id=worker["id"],
        workplace_id=workplace["id"],
        is_active=False,
    )
    params = _params(workplace["id"], worker_id)

    by_owner = await client.get(REPORT_URL, params=params, headers=owner_headers)
    by_worker = await client.get(REPORT_URL, params=params, headers=worker_headers)

    # Владелец видит историю уволенного сотрудника, сам уволенный — уже нет
    assert by_owner.status_code == 200, by_owner.text
    assert by_worker.status_code == 403


@pytest.mark.asyncio
async def test_employee_report_errors(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _ = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    other_workplace = await create_workplace(client, headers)
    worker_id = await add_employee(
        session_factory, user_id=worker["id"], workplace_id=workplace["id"]
    )

    bad_month = await client.get(
        REPORT_URL, params=_params(workplace["id"], worker_id, month=13), headers=headers
    )
    bad_year = await client.get(
        REPORT_URL, params=_params(workplace["id"], worker_id, year=1999), headers=headers
    )
    missing_employee = await client.get(
        REPORT_URL,
        params={"workplace_id": workplace["id"], "month": 11, "year": 2026},
        headers=headers,
    )
    # Сотрудник есть, но в другой точке
    wrong_workplace = await client.get(
        REPORT_URL, params=_params(other_workplace["id"], worker_id), headers=headers
    )
    unknown_employee = await client.get(
        REPORT_URL, params=_params(workplace["id"], 999_999), headers=headers
    )

    await client.delete(f"/workplaces/{workplace['id']}", headers=headers)
    deleted = await client.get(
        REPORT_URL, params=_params(workplace["id"], worker_id), headers=headers
    )

    assert bad_month.status_code == 400
    assert bad_month.json()["detail"] == "Month must be between 1 and 12"
    assert bad_year.status_code == 400
    assert bad_year.json()["detail"] == "Year must be between 2000 and 2100"
    assert missing_employee.status_code == 422
    assert wrong_workplace.status_code == 404
    assert wrong_workplace.json()["detail"] == "Employee not found"
    assert unknown_employee.status_code == 404
    assert unknown_employee.json()["detail"] == "Employee not found"
    assert deleted.status_code == 404
    assert deleted.json()["detail"] == "Workplace not found"
