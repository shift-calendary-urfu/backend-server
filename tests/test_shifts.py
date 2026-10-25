from datetime import date, time

import pytest
from sqlalchemy.exc import NoResultFound

from app.employees.model import Employee
from app.shifts.model import Shift

from tests.helpers import (
    add_employee,
    auth_header,
    create_shift,
    create_workplace,
    login,
    make_token,
    register_and_login,
    shift_payload,
)

OWNER_OR_ADMIN = "You must be the owner or admin of this workplace"
OWNER_OR_EMPLOYEE = "You must be the owner or employee of this workplace"
DAY = "2026-11-02"
OTHER_DAY = "2026-11-03"


def _starts_at(value: str, hhmm: str) -> bool:
    return value == hhmm or value.startswith(f"{hhmm}:")


def _params(workplace_id: int, **extra) -> dict:
    return {"workplace_id": workplace_id, **extra}


def _assert_shift(
    body: dict,
    *,
    user: dict,
    workplace_id: int,
    employee_id: int,
    day: str,
    start: str,
    end: str,
    notes: str | None,
) -> None:
    assert body["id"] >= 1
    assert body["workplace_id"] == workplace_id
    assert body["employee_id"] == employee_id
    assert body["date"] == day
    assert _starts_at(body["start_time"], start)
    assert _starts_at(body["end_time"], end)
    assert body["notes"] == notes
    assert body["first_name"] == user["first_name"]
    assert body["second_name"] == user["second_name"]
    assert body["third_name"] == user["third_name"]
    assert "status" not in body
    assert "is_active" not in body


async def _hire(session_factory, user_id: int, workplace_id: int, role: str = "employee") -> int:
    return await add_employee(
        session_factory,
        user_id=user_id,
        workplace_id=workplace_id,
        role=role,
    )


@pytest.mark.asyncio
async def test_shift_routes_require_token(client):
    params = _params(1, date=DAY)
    period = _params(1, date_from=DAY, date_to=OTHER_DAY)
    payload = shift_payload(1)

    create = await client.post("/shifts/", params=_params(1), json=payload)
    read = await client.get("/shifts/1", params=_params(1))
    by_date = await client.get("/shifts/", params=params)
    calendar = await client.get("/shifts/calendar/", params=period)
    update = await client.put(
        "/shifts/1",
        params=_params(1),
        json={"start_time": "10:00", "end_time": "19:00"},
    )
    delete_one = await client.delete("/shifts/1", params=_params(1))
    delete_day = await client.delete("/shifts/", params=params)
    duplicate = await client.post(
        "/shifts/duplicate/",
        params=_params(1),
        json={"dates": [OTHER_DAY], "shift_ids": [1]},
    )

    assert create.status_code == 401
    assert read.status_code == 401
    assert by_date.status_code == 401
    assert calendar.status_code == 401
    assert update.status_code == 401
    assert delete_one.status_code == 401
    assert delete_day.status_code == 401
    assert duplicate.status_code == 401


@pytest.mark.asyncio
async def test_shift_routes_reject_bad_tokens(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(client, headers, workplace["id"], employee_id)
    path = f"/shifts/{shift['id']}"
    params = _params(workplace["id"])
    tokens = (await login(client, worker["email"], worker["password"])).json()
    expired = make_token(worker["email"], worker["id"], expired=True)

    garbage = await client.get(path, params=params, headers=auth_header("not-a-jwt"))
    expired_response = await client.get(
        path, params=params, headers=auth_header(expired)
    )
    refresh = await client.get(
        path, params=params, headers=auth_header(tokens["refresh_token"])
    )

    assert garbage.status_code == 401
    assert garbage.json()["detail"] == "Could not validate the provided credential"
    assert expired_response.status_code == 401
    assert expired_response.json()["detail"] == "Token expired"
    assert refresh.status_code == 401


@pytest.mark.asyncio
async def test_create_shift_by_owner(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(
        client, first_name="Анна", second_name="Смирнова", third_name="Петровна"
    )
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])

    response = await client.post(
        "/shifts/",
        params=_params(workplace["id"]),
        json=shift_payload(
            employee_id,
            date=DAY,
            start_time="09:00",
            end_time="18:00",
            notes="Зал",
            status="cancelled",
        ),
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    _assert_shift(
        body,
        user=worker,
        workplace_id=workplace["id"],
        employee_id=employee_id,
        day=DAY,
        start="09:00",
        end="18:00",
        notes="Зал",
    )
    async with session_factory() as session:
        stored = await session.get(Shift, body["id"])
        assert stored.status == "planned"
        assert stored.is_active is True
        assert stored.employee_id == employee_id
        assert stored.date == date.fromisoformat(DAY)
        assert stored.start_time == time(9, 0)
        assert stored.end_time == time(18, 0)
        assert stored.notes == "Зал"


@pytest.mark.asyncio
async def test_create_shift_without_notes_or_patronymic(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client, third_name=None)
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])

    body = await create_shift(client, headers, workplace["id"], employee_id)

    _assert_shift(
        body,
        user=worker,
        workplace_id=workplace["id"],
        employee_id=employee_id,
        day=DAY,
        start="09:00",
        end="18:00",
        notes=None,
    )
    assert body["third_name"] is None


@pytest.mark.asyncio
async def test_create_shift_by_admin_only_in_own_workplace(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    admin, admin_headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    _other_owner, other_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    other = await create_workplace(client, other_headers)
    await _hire(session_factory, admin["id"], workplace["id"], role="admin")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    foreign_employee_id = await _hire(session_factory, worker["id"], other["id"])

    created = await client.post(
        "/shifts/",
        params=_params(workplace["id"]),
        json=shift_payload(employee_id, notes="От администратора"),
        headers=admin_headers,
    )
    foreign = await client.post(
        "/shifts/",
        params=_params(other["id"]),
        json=shift_payload(foreign_employee_id),
        headers=admin_headers,
    )

    assert created.status_code == 201
    assert created.json()["notes"] == "От администратора"
    assert created.json()["employee_id"] == employee_id
    assert foreign.status_code == 403
    assert foreign.json()["detail"] == OWNER_OR_ADMIN


@pytest.mark.asyncio
async def test_create_shift_forbidden_for_employee_and_stranger(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    payload = shift_payload(employee_id)

    worker_attempt = await client.post(
        "/shifts/",
        params=_params(workplace["id"]),
        json=payload,
        headers=worker_headers,
    )
    stranger_attempt = await client.post(
        "/shifts/",
        params=_params(workplace["id"]),
        json=payload,
        headers=stranger_headers,
    )

    assert worker_attempt.status_code == 403
    assert worker_attempt.json()["detail"] == OWNER_OR_ADMIN
    assert stranger_attempt.status_code == 403
    assert stranger_attempt.json()["detail"] == OWNER_OR_ADMIN


@pytest.mark.asyncio
async def test_create_shift_rejects_unknown_or_inactive_employee(
    client, session_factory
):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    inactive_id = await add_employee(
        session_factory,
        user_id=worker["id"],
        workplace_id=workplace["id"],
        is_active=False,
    )

    unknown = await client.post(
        "/shifts/",
        params=_params(workplace["id"]),
        json=shift_payload(999999),
        headers=headers,
    )
    inactive = await client.post(
        "/shifts/",
        params=_params(workplace["id"]),
        json=shift_payload(inactive_id),
        headers=headers,
    )

    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Employee not found or not active"
    assert inactive.status_code == 404
    assert inactive.json()["detail"] == "Employee not found or not active"


@pytest.mark.asyncio
async def test_create_shift_rejects_employee_of_another_workplace(
    client, session_factory
):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers, name="Первая")
    other = await create_workplace(client, headers, name="Вторая")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])

    response = await client.post(
        "/shifts/",
        params=_params(other["id"]),
        json=shift_payload(employee_id),
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Employee not found or not active"


@pytest.mark.asyncio
async def test_create_shift_on_deleted_workplace(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    await client.delete(f"/workplaces/{workplace['id']}", headers=headers)

    response = await client.post(
        "/shifts/",
        params=_params(workplace["id"]),
        json=shift_payload(employee_id),
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Employee not found or not active"


@pytest.mark.asyncio
async def test_create_shift_rejects_invalid_body(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    params = _params(workplace["id"])

    async def post(**overrides):
        return await client.post(
            "/shifts/",
            params=params,
            json=shift_payload(employee_id, **overrides),
            headers=headers,
        )

    reversed_times = await post(start_time="18:00", end_time="09:00")
    equal_times = await post(start_time="09:00", end_time="09:00")
    overnight = await post(start_time="23:30", end_time="00:00")
    not_half_hour = await post(start_time="09:15", end_time="18:15")
    unpadded = await post(start_time="9:00", end_time="18:00")
    with_seconds = await post(start_time="09:00:00", end_time="18:00")
    bad_date = await post(date="02.11.2026")
    missing_employee = await client.post(
        "/shifts/",
        params=params,
        json={"date": DAY, "start_time": "09:00", "end_time": "18:00"},
        headers=headers,
    )
    zero_employee = await client.post(
        "/shifts/",
        params=params,
        json=shift_payload(0),
        headers=headers,
    )
    zero_workplace = await client.post(
        "/shifts/",
        params=_params(0),
        json=shift_payload(employee_id),
        headers=headers,
    )
    missing_workplace = await client.post(
        "/shifts/",
        json=shift_payload(employee_id),
        headers=headers,
    )

    assert reversed_times.status_code == 422
    assert equal_times.status_code == 422
    assert overnight.status_code == 422
    assert not_half_hour.status_code == 422
    assert unpadded.status_code == 201
    assert _starts_at(unpadded.json()["start_time"], "09:00")
    assert _starts_at(unpadded.json()["end_time"], "18:00")
    assert with_seconds.status_code == 422
    assert bad_date.status_code == 422
    assert missing_employee.status_code == 422
    assert zero_employee.status_code == 422
    assert zero_workplace.status_code == 403
    assert zero_workplace.json()["detail"] == OWNER_OR_ADMIN
    assert missing_workplace.status_code == 422


@pytest.mark.asyncio
async def test_create_shift_accepts_half_hour_slot(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])

    body = await create_shift(
        client,
        headers,
        workplace["id"],
        employee_id,
        start_time="10:30",
        end_time="11:00",
    )

    assert _starts_at(body["start_time"], "10:30")
    assert _starts_at(body["end_time"], "11:00")


@pytest.mark.asyncio
async def test_two_shifts_same_day_are_allowed(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    first = await create_shift(
        client, headers, workplace["id"], employee_id, start_time="09:00", end_time="12:00"
    )
    second = await create_shift(
        client, headers, workplace["id"], employee_id, start_time="12:00", end_time="18:00"
    )

    listed = await client.get(
        "/shifts/",
        params=_params(workplace["id"], date=DAY),
        headers=headers,
    )

    assert first["id"] != second["id"]
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {first["id"], second["id"]}


@pytest.mark.asyncio
async def test_get_shift_by_id_for_owner_admin_and_employee(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    admin, admin_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(
        client, first_name="Илья", second_name="Белов", third_name="Олегович"
    )
    colleague, colleague_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await _hire(session_factory, admin["id"], workplace["id"], role="admin")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    await _hire(session_factory, colleague["id"], workplace["id"])
    shift = await create_shift(
        client, owner_headers, workplace["id"], employee_id, notes="Утро"
    )
    path = f"/shifts/{shift['id']}"
    params = _params(workplace["id"])

    owner_response = await client.get(path, params=params, headers=owner_headers)
    admin_response = await client.get(path, params=params, headers=admin_headers)
    worker_response = await client.get(path, params=params, headers=worker_headers)
    colleague_response = await client.get(
        path, params=params, headers=colleague_headers
    )

    assert owner_response.status_code == 200
    assert admin_response.status_code == 200
    assert worker_response.status_code == 200
    assert colleague_response.status_code == 200
    _assert_shift(
        colleague_response.json(),
        user=worker,
        workplace_id=workplace["id"],
        employee_id=employee_id,
        day=DAY,
        start="09:00",
        end="18:00",
        notes="Утро",
    )


@pytest.mark.asyncio
async def test_get_missing_or_inactive_shift(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers, name="Своя")
    other = await create_workplace(client, headers, name="Другая")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(client, headers, workplace["id"], employee_id)
    await client.delete(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )

    # get_shift_by_id вызывает result.one() раньше проверки «смена не найдена»,
    # поэтому отсутствующая строка не становится ответом 404.
    with pytest.raises(NoResultFound):
        await client.get(
            "/shifts/999999", params=_params(workplace["id"]), headers=headers
        )
    with pytest.raises(NoResultFound):
        await client.get(
            f"/shifts/{shift['id']}",
            params=_params(workplace["id"]),
            headers=headers,
        )
    with pytest.raises(NoResultFound):
        await client.get(
            f"/shifts/{shift['id']}",
            params=_params(other["id"]),
            headers=headers,
        )
    bad_id = await client.get(
        "/shifts/abc", params=_params(workplace["id"]), headers=headers
    )
    zero_id = await client.get(
        "/shifts/0", params=_params(workplace["id"]), headers=headers
    )

    assert bad_id.status_code == 422
    assert zero_id.status_code == 422


@pytest.mark.asyncio
async def test_get_shift_forbidden(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    outsider, outsider_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    other = await create_workplace(client, owner_headers, name="Другая")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    await add_employee(
        session_factory,
        user_id=outsider["id"],
        workplace_id=workplace["id"],
        is_active=False,
    )
    shift = await create_shift(client, owner_headers, workplace["id"], employee_id)

    stranger = await client.get(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        headers=outsider_headers,
    )
    wrong_scope = await client.get(
        f"/shifts/{shift['id']}",
        params=_params(other["id"]),
        headers=worker_headers,
    )

    assert stranger.status_code == 403
    assert stranger.json()["detail"] == OWNER_OR_EMPLOYEE
    assert wrong_scope.status_code == 403
    assert wrong_scope.json()["detail"] == OWNER_OR_EMPLOYEE


@pytest.mark.asyncio
async def test_shift_of_deactivated_employee_stays_readable(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(
        client, first_name="Кирилл", second_name="Носов", third_name=None
    )
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(
        client, headers, workplace["id"], employee_id, notes="До увольнения"
    )
    async with session_factory() as session:
        stored = await session.get(Employee, employee_id)
        stored.is_active = False
        await session.commit()

    response = await client.get(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )
    create_again = await client.post(
        "/shifts/",
        params=_params(workplace["id"]),
        json=shift_payload(employee_id, date=OTHER_DAY),
        headers=headers,
    )

    assert response.status_code == 200
    _assert_shift(
        response.json(),
        user=worker,
        workplace_id=workplace["id"],
        employee_id=employee_id,
        day=DAY,
        start="09:00",
        end="18:00",
        notes="До увольнения",
    )
    assert create_again.status_code == 404
    assert create_again.json()["detail"] == "Employee not found or not active"


@pytest.mark.asyncio
async def test_update_shift_changes_only_time(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    other, _other_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    other_employee_id = await _hire(session_factory, other["id"], workplace["id"])
    shift = await create_shift(
        client, headers, workplace["id"], employee_id, notes="Не трогать"
    )

    response = await client.put(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        json={
            "start_time": "10:00",
            "end_time": "19:30",
            "date": "2030-01-01",
            "notes": "не должно сохраниться",
            "employee_id": other_employee_id,
            "status": "cancelled",
        },
        headers=headers,
    )

    assert response.status_code == 200
    _assert_shift(
        response.json(),
        user=worker,
        workplace_id=workplace["id"],
        employee_id=employee_id,
        day=DAY,
        start="10:00",
        end="19:30",
        notes="Не трогать",
    )
    async with session_factory() as session:
        stored = await session.get(Shift, shift["id"])
        assert stored.status == "planned"
        assert stored.date == date.fromisoformat(DAY)
        assert stored.employee_id == employee_id
        assert stored.notes == "Не трогать"
        assert stored.start_time == time(10, 0)
        assert stored.end_time == time(19, 30)


@pytest.mark.asyncio
async def test_update_shift_by_admin(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    admin, admin_headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await _hire(session_factory, admin["id"], workplace["id"], role="admin")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(client, owner_headers, workplace["id"], employee_id)

    response = await client.put(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        json={"start_time": "08:00", "end_time": "16:30"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert _starts_at(response.json()["start_time"], "08:00")
    assert _starts_at(response.json()["end_time"], "16:30")


@pytest.mark.asyncio
async def test_update_shift_rejects_invalid_or_missing(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers, name="Своя")
    other = await create_workplace(client, headers, name="Другая")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(
        client, headers, workplace["id"], employee_id, notes="Исходная"
    )
    path = f"/shifts/{shift['id']}"
    valid_time = {"start_time": "11:00", "end_time": "12:00"}

    only_start = await client.put(
        path,
        params=_params(workplace["id"]),
        json={"start_time": "11:00"},
        headers=headers,
    )
    bad_step = await client.put(
        path,
        params=_params(workplace["id"]),
        json={"start_time": "11:10", "end_time": "12:00"},
        headers=headers,
    )
    missing = await client.put(
        "/shifts/999999",
        params=_params(workplace["id"]),
        json=valid_time,
        headers=headers,
    )
    wrong_workplace = await client.put(
        path, params=_params(other["id"]), json=valid_time, headers=headers
    )
    await client.delete(path, params=_params(workplace["id"]), headers=headers)
    deleted = await client.put(
        path, params=_params(workplace["id"]), json=valid_time, headers=headers
    )

    assert only_start.status_code == 422
    assert bad_step.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Shift not found or not active"
    assert wrong_workplace.status_code == 404
    assert wrong_workplace.json()["detail"] == "Shift not found or not active"
    assert deleted.status_code == 404
    assert deleted.json()["detail"] == "Shift not found or not active"
    async with session_factory() as session:
        saved = await session.get(Shift, shift["id"])
        assert saved.notes == "Исходная"
        assert saved.start_time == time(9, 0)
        assert saved.is_active is False


@pytest.mark.asyncio
async def test_update_shift_forbidden(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(client, owner_headers, workplace["id"], employee_id)
    payload = {"start_time": "12:00", "end_time": "13:00"}

    worker_attempt = await client.put(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        json=payload,
        headers=worker_headers,
    )
    stranger_attempt = await client.put(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        json=payload,
        headers=stranger_headers,
    )
    saved = await client.get(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        headers=owner_headers,
    )

    assert worker_attempt.status_code == 403
    assert worker_attempt.json()["detail"] == OWNER_OR_ADMIN
    assert stranger_attempt.status_code == 403
    assert _starts_at(saved.json()["start_time"], "09:00")
    assert _starts_at(saved.json()["end_time"], "18:00")


@pytest.mark.asyncio
async def test_delete_shift_is_soft(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers, name="Своя")
    other = await create_workplace(client, headers, name="Другая")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    other_employee_id = await _hire(session_factory, worker["id"], other["id"])
    shift = await create_shift(client, headers, workplace["id"], employee_id)
    foreign = await create_shift(client, headers, other["id"], other_employee_id)

    wrong_workplace = await client.delete(
        f"/shifts/{foreign['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )
    response = await client.delete(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )
    again = await client.delete(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )
    foreign_still_there = await client.get(
        f"/shifts/{foreign['id']}",
        params=_params(other["id"]),
        headers=headers,
    )

    assert wrong_workplace.status_code == 404
    assert wrong_workplace.json()["detail"] == "Shift not found or not active"
    assert response.status_code == 200
    assert response.json() == {"message": "Смена успешно удалена"}
    assert again.status_code == 404
    assert again.json()["detail"] == "Shift not found or not active"
    assert foreign_still_there.status_code == 200
    async with session_factory() as session:
        stored = await session.get(Shift, shift["id"])
        kept = await session.get(Shift, foreign["id"])
        assert stored.is_active is False
        assert stored.status == "planned"
        assert kept.is_active is True


@pytest.mark.asyncio
async def test_delete_shift_forbidden(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(client, owner_headers, workplace["id"], employee_id)
    path = f"/shifts/{shift['id']}"
    params = _params(workplace["id"])

    worker_attempt = await client.delete(path, params=params, headers=worker_headers)
    stranger_attempt = await client.delete(
        path, params=params, headers=stranger_headers
    )
    saved = await client.get(path, params=params, headers=owner_headers)

    assert worker_attempt.status_code == 403
    assert worker_attempt.json()["detail"] == OWNER_OR_ADMIN
    assert stranger_attempt.status_code == 403
    assert saved.status_code == 200


@pytest.mark.asyncio
async def test_delete_shifts_by_date(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers, name="Своя")
    other = await create_workplace(client, headers, name="Другая")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    other_employee_id = await _hire(session_factory, worker["id"], other["id"])
    morning = await create_shift(
        client, headers, workplace["id"], employee_id, date=DAY, start_time="09:00", end_time="13:00"
    )
    evening = await create_shift(
        client, headers, workplace["id"], employee_id, date=DAY, start_time="14:00", end_time="18:00"
    )
    another_day = await create_shift(
        client, headers, workplace["id"], employee_id, date=OTHER_DAY
    )
    other_place = await create_shift(
        client, headers, other["id"], other_employee_id, date=DAY
    )

    response = await client.delete(
        "/shifts/",
        params=_params(workplace["id"], date=DAY),
        headers=headers,
    )
    day_after = await client.get(
        "/shifts/", params=_params(workplace["id"], date=DAY), headers=headers
    )
    other_day = await client.get(
        "/shifts/",
        params=_params(workplace["id"], date=OTHER_DAY),
        headers=headers,
    )
    other_workplace = await client.get(
        "/shifts/", params=_params(other["id"], date=DAY), headers=headers
    )
    repeat = await client.delete(
        "/shifts/", params=_params(workplace["id"], date=DAY), headers=headers
    )

    assert response.status_code == 200
    assert response.json() == {"message": f"Смены успешно удалены, дата {DAY}"}
    assert day_after.status_code == 404
    assert other_day.status_code == 200
    assert {item["id"] for item in other_day.json()} == {another_day["id"]}
    assert other_workplace.status_code == 200
    assert {item["id"] for item in other_workplace.json()} == {other_place["id"]}
    assert repeat.status_code == 404
    assert repeat.json()["detail"] == (
        f"Shifts not found or not active on this date={DAY}"
    )
    async with session_factory() as session:
        assert (await session.get(Shift, morning["id"])).is_active is False
        assert (await session.get(Shift, evening["id"])).is_active is False
        assert (await session.get(Shift, another_day["id"])).is_active is True
        assert (await session.get(Shift, other_place["id"])).is_active is True


@pytest.mark.asyncio
async def test_delete_shifts_by_date_not_found_and_forbidden(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await _hire(session_factory, worker["id"], workplace["id"])
    params = _params(workplace["id"], date="2026-12-31")

    empty = await client.delete("/shifts/", params=params, headers=owner_headers)
    worker_attempt = await client.delete(
        "/shifts/", params=params, headers=worker_headers
    )
    stranger_attempt = await client.delete(
        "/shifts/", params=params, headers=stranger_headers
    )
    bad_date = await client.delete(
        "/shifts/",
        params=_params(workplace["id"], date="31.12.2026"),
        headers=owner_headers,
    )

    assert empty.status_code == 404
    assert empty.json()["detail"] == (
        "Shifts not found or not active on this date=2026-12-31"
    )
    assert worker_attempt.status_code == 403
    assert worker_attempt.json()["detail"] == OWNER_OR_ADMIN
    assert stranger_attempt.status_code == 403
    assert bad_date.status_code == 422


@pytest.mark.asyncio
async def test_get_shifts_by_date(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    anna, anna_headers = await register_and_login(
        client, first_name="Анна", second_name="Смирнова", third_name="Петровна"
    )
    oleg, _oleg_headers = await register_and_login(
        client, first_name="Олег", second_name="Орлов", third_name=None
    )
    workplace = await create_workplace(client, owner_headers, name="Своя")
    other = await create_workplace(client, owner_headers, name="Другая")
    anna_id = await _hire(session_factory, anna["id"], workplace["id"])
    oleg_id = await _hire(session_factory, oleg["id"], workplace["id"])
    other_employee_id = await _hire(session_factory, anna["id"], other["id"])
    anna_shift = await create_shift(
        client,
        owner_headers,
        workplace["id"],
        anna_id,
        date=DAY,
        notes="Касса",
        start_time="09:00",
        end_time="15:00",
    )
    oleg_shift = await create_shift(
        client,
        owner_headers,
        workplace["id"],
        oleg_id,
        date=DAY,
        start_time="15:00",
        end_time="21:00",
    )
    await create_shift(
        client, owner_headers, workplace["id"], anna_id, date=OTHER_DAY
    )
    await create_shift(
        client, owner_headers, other["id"], other_employee_id, date=DAY, notes="Чужая"
    )
    hidden = await create_shift(
        client,
        owner_headers,
        workplace["id"],
        anna_id,
        date=DAY,
        start_time="08:00",
        end_time="09:00",
    )
    await client.delete(
        f"/shifts/{hidden['id']}",
        params=_params(workplace["id"]),
        headers=owner_headers,
    )

    owner_response = await client.get(
        "/shifts/", params=_params(workplace["id"], date=DAY), headers=owner_headers
    )
    employee_response = await client.get(
        "/shifts/", params=_params(workplace["id"], date=DAY), headers=anna_headers
    )

    assert owner_response.status_code == 200
    assert employee_response.status_code == 200
    rows = {item["id"]: item for item in employee_response.json()}
    assert set(rows) == {anna_shift["id"], oleg_shift["id"]}
    _assert_shift(
        rows[anna_shift["id"]],
        user=anna,
        workplace_id=workplace["id"],
        employee_id=anna_id,
        day=DAY,
        start="09:00",
        end="15:00",
        notes="Касса",
    )
    assert rows[oleg_shift["id"]]["first_name"] == "Олег"
    assert rows[oleg_shift["id"]]["third_name"] is None
    assert {item["id"] for item in owner_response.json()} == set(rows)


@pytest.mark.asyncio
async def test_get_shifts_by_date_not_found_and_forbidden(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    outsider, outsider_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await _hire(session_factory, worker["id"], workplace["id"])
    await add_employee(
        session_factory,
        user_id=outsider["id"],
        workplace_id=workplace["id"],
        is_active=False,
    )

    empty = await client.get(
        "/shifts/",
        params=_params(workplace["id"], date="2026-12-31"),
        headers=owner_headers,
    )
    stranger = await client.get(
        "/shifts/",
        params=_params(workplace["id"], date=DAY),
        headers=outsider_headers,
    )
    missing_date = await client.get(
        "/shifts/", params=_params(workplace["id"]), headers=owner_headers
    )

    assert empty.status_code == 404
    assert empty.json()["detail"] == (
        "Shifts not found or not active on this date=2026-12-31"
    )
    assert stranger.status_code == 403
    assert stranger.json()["detail"] == OWNER_OR_EMPLOYEE
    assert missing_date.status_code == 422


@pytest.mark.asyncio
async def test_calendar_groups_inclusive_period(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(
        client, first_name="Анна", second_name="Смирнова", third_name="Петровна"
    )
    workplace = await create_workplace(client, owner_headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    first = await create_shift(
        client, owner_headers, workplace["id"], employee_id, date="2026-11-02", notes="А"
    )
    second = await create_shift(
        client,
        owner_headers,
        workplace["id"],
        employee_id,
        date="2026-11-02",
        start_time="18:00",
        end_time="21:00",
        notes="Б",
    )
    third = await create_shift(
        client, owner_headers, workplace["id"], employee_id, date="2026-11-04", notes="В"
    )
    await create_shift(
        client, owner_headers, workplace["id"], employee_id, date="2026-11-05"
    )
    removed = await create_shift(
        client,
        owner_headers,
        workplace["id"],
        employee_id,
        date="2026-11-04",
        start_time="12:00",
        end_time="16:00",
    )
    await client.delete(
        f"/shifts/{removed['id']}",
        params=_params(workplace["id"]),
        headers=owner_headers,
    )

    response = await client.get(
        "/shifts/calendar/",
        params=_params(
            workplace["id"], date_from="2026-11-02", date_to="2026-11-04"
        ),
        headers=worker_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert list(body) == ["2026-11-02", "2026-11-04"]
    assert {item["id"] for item in body["2026-11-02"]} == {first["id"], second["id"]}
    assert {item["id"] for item in body["2026-11-04"]} == {third["id"]}
    matched = next(item for item in body["2026-11-02"] if item["id"] == first["id"])
    _assert_shift(
        matched,
        user=worker,
        workplace_id=workplace["id"],
        employee_id=employee_id,
        day="2026-11-02",
        start="09:00",
        end="18:00",
        notes="А",
    )


@pytest.mark.asyncio
async def test_calendar_not_found_and_forbidden(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    outsider, outsider_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    await add_employee(
        session_factory,
        user_id=outsider["id"],
        workplace_id=workplace["id"],
        is_active=False,
    )
    shift = await create_shift(
        client, owner_headers, workplace["id"], employee_id, date=DAY
    )

    empty = await client.get(
        "/shifts/calendar/",
        params=_params(
            workplace["id"], date_from="2026-12-01", date_to="2026-12-02"
        ),
        headers=owner_headers,
    )
    inverted = await client.get(
        "/shifts/calendar/",
        params=_params(
            workplace["id"], date_from="2026-11-10", date_to="2026-11-01"
        ),
        headers=owner_headers,
    )
    stranger = await client.get(
        "/shifts/calendar/",
        params=_params(workplace["id"], date_from=DAY, date_to=DAY),
        headers=outsider_headers,
    )
    missing_bound = await client.get(
        "/shifts/calendar/",
        params=_params(workplace["id"], date_from=DAY),
        headers=owner_headers,
    )
    still_there = await client.get(
        f"/shifts/{shift['id']}",
        params=_params(workplace["id"]),
        headers=owner_headers,
    )

    assert empty.status_code == 404
    assert empty.json()["detail"] == (
        "Shifts not found or not active between 2026-12-01 and 2026-12-02"
    )
    assert inverted.status_code == 404
    assert inverted.json()["detail"] == (
        "Shifts not found or not active between 2026-11-10 and 2026-11-01"
    )
    assert stranger.status_code == 403
    assert stranger.json()["detail"] == OWNER_OR_EMPLOYEE
    assert missing_bound.status_code == 422
    assert still_there.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_shifts(client, session_factory):
    _owner, headers = await register_and_login(client)
    anna, _anna_headers = await register_and_login(
        client, first_name="Анна", second_name="Смирнова", third_name="Петровна"
    )
    oleg, _oleg_headers = await register_and_login(
        client, first_name="Олег", second_name="Орлов", third_name=None
    )
    workplace = await create_workplace(client, headers)
    anna_id = await _hire(session_factory, anna["id"], workplace["id"])
    oleg_id = await _hire(session_factory, oleg["id"], workplace["id"])
    morning = await create_shift(
        client,
        headers,
        workplace["id"],
        anna_id,
        date=DAY,
        start_time="09:00",
        end_time="15:00",
        notes="Утро",
    )
    evening = await create_shift(
        client,
        headers,
        workplace["id"],
        oleg_id,
        date=DAY,
        start_time="15:00",
        end_time="21:00",
    )

    response = await client.post(
        "/shifts/duplicate/",
        params=_params(workplace["id"]),
        json={
            "dates": ["2026-12-24", "2026-12-01"],
            "shift_ids": [evening["id"], morning["id"]],
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count_duplicated_shifts_created"] == 4
    assert body["workplace_id"] == workplace["id"]
    assert body["period"] == {
        "start_date": "2026-12-01",
        "end_date": "2026-12-24",
    }
    assert body["message"] == (
        "Смены успешно скопированы на период с 2026-12-01 по 2026-12-24"
    )

    original = await client.get(
        "/shifts/", params=_params(workplace["id"], date=DAY), headers=headers
    )
    assert {item["id"] for item in original.json()} == {morning["id"], evening["id"]}

    for target in ("2026-12-01", "2026-12-24"):
        copied = await client.get(
            "/shifts/",
            params=_params(workplace["id"], date=target),
            headers=headers,
        )
        assert copied.status_code == 200
        rows = {(item["employee_id"], item["notes"]) for item in copied.json()}
        assert rows == {(anna_id, "Утро"), (oleg_id, None)}
        anna_copy = next(
            item for item in copied.json() if item["employee_id"] == anna_id
        )
        assert _starts_at(anna_copy["start_time"], "09:00")
        assert _starts_at(anna_copy["end_time"], "15:00")
        assert anna_copy["first_name"] == "Анна"
        assert anna_copy["id"] not in {morning["id"], evening["id"]}


@pytest.mark.asyncio
async def test_duplicate_onto_the_same_date_adds_another_row(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(client, headers, workplace["id"], employee_id, notes="Оригинал")

    response = await client.post(
        "/shifts/duplicate/",
        params=_params(workplace["id"]),
        json={"dates": [DAY], "shift_ids": [shift["id"]]},
        headers=headers,
    )
    listed = await client.get(
        "/shifts/", params=_params(workplace["id"], date=DAY), headers=headers
    )

    assert response.status_code == 200
    assert response.json()["count_duplicated_shifts_created"] == 1
    assert len(listed.json()) == 2
    assert {item["notes"] for item in listed.json()} == {"Оригинал"}


@pytest.mark.asyncio
async def test_duplicate_repeated_id_counts_unique_rows(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(client, headers, workplace["id"], employee_id)

    response = await client.post(
        "/shifts/duplicate/",
        params=_params(workplace["id"]),
        json={
            "dates": ["2026-12-02"],
            "shift_ids": [shift["id"], shift["id"]],
        },
        headers=headers,
    )
    listed = await client.get(
        "/shifts/",
        params=_params(workplace["id"], date="2026-12-02"),
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["count_duplicated_shifts_created"] == 1
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_duplicate_permissions_and_validation(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    admin, admin_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await _hire(session_factory, admin["id"], workplace["id"], role="admin")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    shift = await create_shift(client, owner_headers, workplace["id"], employee_id)
    params = _params(workplace["id"])

    worker_attempt = await client.post(
        "/shifts/duplicate/",
        params=params,
        json={"dates": [OTHER_DAY], "shift_ids": [shift["id"]]},
        headers=worker_headers,
    )
    stranger_attempt = await client.post(
        "/shifts/duplicate/",
        params=params,
        json={"dates": [OTHER_DAY], "shift_ids": [shift["id"]]},
        headers=stranger_headers,
    )
    empty_dates = await client.post(
        "/shifts/duplicate/",
        params=params,
        json={"dates": [], "shift_ids": [shift["id"]]},
        headers=owner_headers,
    )
    empty_ids = await client.post(
        "/shifts/duplicate/",
        params=params,
        json={"dates": [OTHER_DAY], "shift_ids": []},
        headers=owner_headers,
    )
    admin_attempt = await client.post(
        "/shifts/duplicate/",
        params=params,
        json={"dates": ["2026-12-15"], "shift_ids": [shift["id"]]},
        headers=admin_headers,
    )

    assert worker_attempt.status_code == 403
    assert worker_attempt.json()["detail"] == OWNER_OR_ADMIN
    assert stranger_attempt.status_code == 403
    assert empty_dates.status_code == 422
    assert empty_ids.status_code == 422
    assert admin_attempt.status_code == 200
    assert admin_attempt.json()["count_duplicated_shifts_created"] == 1


@pytest.mark.asyncio
async def test_duplicate_missing_shifts_creates_nothing(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _worker_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers, name="Своя")
    other = await create_workplace(client, headers, name="Другая")
    employee_id = await _hire(session_factory, worker["id"], workplace["id"])
    other_employee_id = await _hire(session_factory, worker["id"], other["id"])
    shift = await create_shift(client, headers, workplace["id"], employee_id)
    foreign = await create_shift(
        client, headers, other["id"], other_employee_id, date=DAY
    )
    inactive = await create_shift(
        client,
        headers,
        workplace["id"],
        employee_id,
        date=OTHER_DAY,
        start_time="10:00",
        end_time="12:00",
    )
    await client.delete(
        f"/shifts/{inactive['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )
    target = "2026-12-20"

    mixed = await client.post(
        "/shifts/duplicate/",
        params=_params(workplace["id"]),
        json={"dates": [target], "shift_ids": [shift["id"], 999999]},
        headers=headers,
    )
    inactive_only = await client.post(
        "/shifts/duplicate/",
        params=_params(workplace["id"]),
        json={"dates": [target], "shift_ids": [inactive["id"]]},
        headers=headers,
    )
    foreign_only = await client.post(
        "/shifts/duplicate/",
        params=_params(workplace["id"]),
        json={"dates": [target], "shift_ids": [foreign["id"]]},
        headers=headers,
    )
    several_missing = await client.post(
        "/shifts/duplicate/",
        params=_params(workplace["id"]),
        json={"dates": [target], "shift_ids": [999999, 999998]},
        headers=headers,
    )
    created = await client.get(
        "/shifts/", params=_params(workplace["id"], date=target), headers=headers
    )
    original = await client.get(
        "/shifts/", params=_params(workplace["id"], date=DAY), headers=headers
    )

    assert mixed.status_code == 404
    assert mixed.json()["detail"] == "Shifts not found or not active: [999999]"
    assert inactive_only.status_code == 404
    assert inactive_only.json()["detail"] == (
        f"Shifts not found or not active: [{inactive['id']}]"
    )
    assert foreign_only.status_code == 404
    assert foreign_only.json()["detail"] == (
        f"Shifts not found or not active: [{foreign['id']}]"
    )
    assert several_missing.status_code == 404
    assert several_missing.json()["detail"] == (
        "Shifts not found or not active: [999998, 999999]"
    )
    assert created.status_code == 404
    assert {item["id"] for item in original.json()} == {shift["id"]}
