import pytest

from app.employees.model import Employee
from app.shifts.model import Shift
from app.shift_templates.models import ShiftTemplate
from app.workplaces.model import Workplace

from tests.helpers import (
    add_employee,
    add_shift,
    add_template,
    create_workplace,
    register_and_login,
    workplace_payload,
)


def _starts_at(value: str, hhmm: str) -> bool:
    return value == hhmm or value.startswith(f"{hhmm}:")


@pytest.mark.asyncio
async def test_create_workplace_requires_token(client):
    response = await client.post("/workplaces/", json=workplace_payload())

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_workplace_makes_current_user_owner(client):
    user, headers = await register_and_login(client)
    payload = workplace_payload(name="ПВЗ Север", address="ул. Мира, 5")

    response = await client.post("/workplaces/", json=payload, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["owner_id"] == user["id"]
    assert body["name"] == payload["name"]
    assert body["address"] == payload["address"]
    assert body["phone"] == payload["phone"]
    assert body["description"] == payload["description"]
    assert body["workplace_type"] == payload["workplace_type"]
    assert _starts_at(body["work_start_time"], "09:00")
    assert _starts_at(body["work_end_time"], "21:00")


@pytest.mark.asyncio
async def test_create_workplace_without_optional_fields(client):
    _user, headers = await register_and_login(client)
    payload = workplace_payload()
    del payload["phone"]
    del payload["description"]

    response = await client.post("/workplaces/", json=payload, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["phone"] is None
    assert body["description"] is None


@pytest.mark.asyncio
async def test_create_workplace_rejects_invalid_schedule(client):
    _user, headers = await register_and_login(client)

    reversed_times = await client.post(
        "/workplaces/",
        json=workplace_payload(work_start_time="21:00", work_end_time="09:00"),
        headers=headers,
    )
    equal_times = await client.post(
        "/workplaces/",
        json=workplace_payload(work_start_time="09:00", work_end_time="09:00"),
        headers=headers,
    )
    bad_format = await client.post(
        "/workplaces/",
        json=workplace_payload(work_start_time="9 утра", work_end_time="21:00"),
        headers=headers,
    )
    missing_name = await client.post(
        "/workplaces/",
        json={"address": "ул. Мира, 1", "workplace_type": "ozon"},
        headers=headers,
    )

    assert reversed_times.status_code == 422
    assert equal_times.status_code == 422
    assert bad_format.status_code == 422
    assert missing_name.status_code == 422


@pytest.mark.asyncio
async def test_create_workplace_rejects_too_long_name(client):
    _user, headers = await register_and_login(client)

    response = await client.post(
        "/workplaces/",
        json=workplace_payload(name="А" * 256),
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_address_and_type_for_same_owner(client):
    _user, headers = await register_and_login(client)
    payload = workplace_payload(address="ул. Ленина, 1", workplace_type="ozon")
    await create_workplace(client, headers, **payload)

    response = await client.post("/workplaces/", json=payload, headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Workplace with this address and type already exists."
    )


@pytest.mark.asyncio
async def test_same_address_is_allowed_for_other_type_or_owner(client):
    _owner, headers = await register_and_login(client)
    _other, other_headers = await register_and_login(client)
    address = "ул. Ленина, 10"
    await create_workplace(
        client, headers, address=address, workplace_type="ozon"
    )

    other_type = await client.post(
        "/workplaces/",
        json=workplace_payload(address=address, workplace_type="wildberries"),
        headers=headers,
    )
    other_owner = await client.post(
        "/workplaces/",
        json=workplace_payload(address=address, workplace_type="ozon"),
        headers=other_headers,
    )

    assert other_type.status_code == 201
    assert other_owner.status_code == 201


@pytest.mark.asyncio
async def test_list_returns_owned_and_employed_active_workplaces(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    employee_user, employee_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)

    owned = await create_workplace(client, owner_headers, name="Своя точка")
    employed = await create_workplace(client, stranger_headers, name="Чужая точка")
    await create_workplace(client, stranger_headers, name="Скрытая точка")
    await add_employee(
        session_factory,
        user_id=employee_user["id"],
        workplace_id=employed["id"],
        role="employee",
    )
    inactive = await create_workplace(client, owner_headers, name="Удалённая точка")
    await client.delete(f"/workplaces/{inactive['id']}", headers=owner_headers)

    owner_list = await client.get("/workplaces/", headers=owner_headers)
    employee_list = await client.get("/workplaces/", headers=employee_headers)
    stranger_list = await client.get("/workplaces/", headers=stranger_headers)

    assert owner_list.status_code == 200
    assert {item["id"] for item in owner_list.json()} == {owned["id"]}
    assert {item["id"] for item in employee_list.json()} == {employed["id"]}
    assert {item["name"] for item in stranger_list.json()} == {
        "Чужая точка",
        "Скрытая точка",
    }


@pytest.mark.asyncio
async def test_list_hides_workplace_from_inactive_employee(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    employee_user, employee_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await add_employee(
        session_factory,
        user_id=employee_user["id"],
        workplace_id=workplace["id"],
        is_active=False,
    )

    response = await client.get("/workplaces/", headers=employee_headers)

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_requires_token(client):
    response = await client.get("/workplaces/")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_workplace_for_owner_employee_and_admin(client, session_factory):
    owner, owner_headers = await register_and_login(client)
    employee_user, employee_headers = await register_and_login(client)
    admin_user, admin_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers, name="Точка с людьми")
    await add_employee(
        session_factory,
        user_id=employee_user["id"],
        workplace_id=workplace["id"],
        role="employee",
        position="Кассир",
    )
    await add_employee(
        session_factory,
        user_id=admin_user["id"],
        workplace_id=workplace["id"],
        role="admin",
        position="Администратор",
    )

    owner_response = await client.get(
        f"/workplaces/{workplace['id']}", headers=owner_headers
    )
    employee_response = await client.get(
        f"/workplaces/{workplace['id']}", headers=employee_headers
    )
    admin_response = await client.get(
        f"/workplaces/{workplace['id']}", headers=admin_headers
    )

    assert owner_response.status_code == 200
    assert employee_response.status_code == 200
    assert admin_response.status_code == 200
    body = owner_response.json()
    assert body["name"] == "Точка с людьми"
    assert body["owner_id"] == owner["id"]
    roles = {item["role"] for item in body["employees"]}
    assert roles == {"employee", "admin"}
    assert all(item["user"]["id"] for item in body["employees"])


@pytest.mark.asyncio
async def test_get_workplace_forbidden_for_stranger_and_missing(client):
    _owner, owner_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)

    stranger = await client.get(
        f"/workplaces/{workplace['id']}", headers=stranger_headers
    )
    missing = await client.get("/workplaces/999999", headers=owner_headers)
    unauthenticated = await client.get(f"/workplaces/{workplace['id']}")

    assert stranger.status_code == 403
    assert stranger.json()["detail"] == (
        "You must be the owner or employee of this workplace"
    )
    assert missing.status_code == 403
    assert unauthenticated.status_code == 401


@pytest.mark.asyncio
async def test_get_deleted_workplace_returns_not_found_for_owner(client):
    _owner, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    await client.delete(f"/workplaces/{workplace['id']}", headers=headers)

    response = await client.get(f"/workplaces/{workplace['id']}", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Workplace not found"


@pytest.mark.asyncio
async def test_update_workplace_by_owner(client):
    _owner, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)

    response = await client.put(
        f"/workplaces/{workplace['id']}",
        json={"name": "Новое имя", "description": "Обновлено"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Новое имя"
    assert response.json()["description"] == "Обновлено"
    saved = (
        await client.get(f"/workplaces/{workplace['id']}", headers=headers)
    ).json()
    assert saved["name"] == "Новое имя"
    assert saved["description"] == "Обновлено"
    assert saved["address"] == workplace["address"]


@pytest.mark.asyncio
async def test_update_workplace_schedule(client):
    _owner, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)

    response = await client.put(
        f"/workplaces/{workplace['id']}",
        json={"work_start_time": "10:00", "work_end_time": "22:00"},
        headers=headers,
    )

    assert response.status_code == 200
    saved = (
        await client.get(f"/workplaces/{workplace['id']}", headers=headers)
    ).json()
    assert _starts_at(saved["work_start_time"], "10:00")
    assert _starts_at(saved["work_end_time"], "22:00")


@pytest.mark.asyncio
async def test_update_workplace_rejects_partial_or_invalid_schedule(client):
    _owner, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)

    only_start = await client.put(
        f"/workplaces/{workplace['id']}",
        json={"work_start_time": "10:00"},
        headers=headers,
    )
    reversed_times = await client.put(
        f"/workplaces/{workplace['id']}",
        json={"work_start_time": "18:00", "work_end_time": "09:00"},
        headers=headers,
    )

    assert only_start.status_code == 422
    assert reversed_times.status_code == 422


@pytest.mark.asyncio
async def test_update_and_delete_forbidden_for_admin_and_employee(
    client, session_factory
):
    _owner, owner_headers = await register_and_login(client)
    employee_user, employee_headers = await register_and_login(client)
    admin_user, admin_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await add_employee(
        session_factory,
        user_id=employee_user["id"],
        workplace_id=workplace["id"],
        role="employee",
    )
    await add_employee(
        session_factory,
        user_id=admin_user["id"],
        workplace_id=workplace["id"],
        role="admin",
    )

    employee_put = await client.put(
        f"/workplaces/{workplace['id']}",
        json={"name": "Чужое"},
        headers=employee_headers,
    )
    admin_put = await client.put(
        f"/workplaces/{workplace['id']}",
        json={"name": "Чужое"},
        headers=admin_headers,
    )
    employee_delete = await client.delete(
        f"/workplaces/{workplace['id']}", headers=employee_headers
    )
    admin_delete = await client.delete(
        f"/workplaces/{workplace['id']}", headers=admin_headers
    )

    assert employee_put.status_code == 403
    assert admin_put.status_code == 403
    assert employee_delete.status_code == 403
    assert admin_delete.status_code == 403
    assert admin_put.json()["detail"] == "You must be the owner of this workplace"
    saved = (
        await client.get(f"/workplaces/{workplace['id']}", headers=owner_headers)
    ).json()
    assert saved["name"] == workplace["name"]


@pytest.mark.asyncio
async def test_delete_workplace_soft_deletes_related_rows(client, session_factory):
    _owner, headers = await register_and_login(client)
    employee_user, _employee_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers, address="ул. Гагарина, 3")
    employee_id = await add_employee(
        session_factory,
        user_id=employee_user["id"],
        workplace_id=workplace["id"],
    )
    shift_id = await add_shift(
        session_factory,
        workplace_id=workplace["id"],
        employee_id=employee_id,
    )
    template_id = await add_template(
        session_factory,
        workplace_id=workplace["id"],
        employee_id=employee_id,
    )

    response = await client.delete(f"/workplaces/{workplace['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"detail": "Workplace deleted successfully"}

    async with session_factory() as session:
        stored_workplace = await session.get(Workplace, workplace["id"])
        stored_employee = await session.get(Employee, employee_id)
        stored_shift = await session.get(Shift, shift_id)
        stored_template = await session.get(ShiftTemplate, template_id)
        assert stored_workplace.is_active is False
        assert stored_employee.is_active is False
        assert stored_shift.is_active is False
        assert stored_template.is_active is False

    listed = await client.get("/workplaces/", headers=headers)
    assert listed.json() == []


@pytest.mark.asyncio
async def test_second_delete_returns_not_found(client):
    _owner, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    await client.delete(f"/workplaces/{workplace['id']}", headers=headers)

    response = await client.delete(f"/workplaces/{workplace['id']}", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Workplace not found"


@pytest.mark.asyncio
async def test_delete_unknown_workplace_is_forbidden(client):
    _owner, headers = await register_and_login(client)

    response = await client.delete("/workplaces/999999", headers=headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_same_address_can_be_created_after_delete(client):
    _owner, headers = await register_and_login(client)
    payload = workplace_payload(address="ул. Мира, 8", workplace_type="yandex_market")
    workplace = await create_workplace(client, headers, **payload)
    await client.delete(f"/workplaces/{workplace['id']}", headers=headers)

    response = await client.post("/workplaces/", json=payload, headers=headers)

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_employees_of_workplace(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    active_user, active_headers = await register_and_login(client)
    inactive_user, _inactive_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await add_employee(
        session_factory,
        user_id=active_user["id"],
        workplace_id=workplace["id"],
        role="employee",
        position="Кассир",
    )
    await add_employee(
        session_factory,
        user_id=inactive_user["id"],
        workplace_id=workplace["id"],
        role="employee",
        is_active=False,
    )

    owner_response = await client.get(
        f"/workplaces/{workplace['id']}/employees",
        headers=owner_headers,
    )
    employee_response = await client.get(
        f"/workplaces/{workplace['id']}/employees",
        headers=active_headers,
    )
    stranger_response = await client.get(
        f"/workplaces/{workplace['id']}/employees",
        headers=stranger_headers,
    )
    empty_owner = await register_and_login(client)
    empty_workplace = await create_workplace(client, empty_owner[1])
    empty_response = await client.get(
        f"/workplaces/{empty_workplace['id']}/employees",
        headers=empty_owner[1],
    )

    assert owner_response.status_code == 200
    assert employee_response.status_code == 200
    employees = owner_response.json()
    assert len(employees) == 1
    assert employees[0]["user_id"] == active_user["id"]
    assert employees[0]["workplace_id"] == workplace["id"]
    assert employees[0]["role"] == "employee"
    assert employees[0]["position"] == "Кассир"
    assert employees[0]["is_active"] is True
    assert employees[0]["user"]["phone"] == active_user["phone"]
    assert employees[0]["user"]["first_name"] == active_user["first_name"]
    assert stranger_response.status_code == 403
    assert empty_response.status_code == 200
    assert empty_response.json() == []


@pytest.mark.asyncio
async def test_deleted_workplace_employees_are_hidden(client, session_factory):
    _owner, headers = await register_and_login(client)
    employee_user, _employee_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    await add_employee(
        session_factory,
        user_id=employee_user["id"],
        workplace_id=workplace["id"],
    )
    await client.delete(f"/workplaces/{workplace['id']}", headers=headers)

    response = await client.get(
        f"/workplaces/{workplace['id']}/employees",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_employees_route_requires_token(client):
    response = await client.get("/workplaces/1/employees")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_workplace_id_must_be_integer(client):
    _user, headers = await register_and_login(client)

    response = await client.get("/workplaces/abc", headers=headers)

    assert response.status_code == 422
