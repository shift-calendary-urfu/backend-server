from datetime import date

import pytest

from app.employees.model import Employee
from app.shifts.model import Shift

from tests.helpers import (
    add_employee,
    add_shift,
    auth_header,
    create_employee,
    create_workplace,
    employee_payload,
    login,
    make_token,
    next_phone,
    register_and_login,
    set_user_active,
)

OWNER_OR_ADMIN = "You must be the owner or admin of this workplace"
OWNER_OR_EMPLOYEE = "You must be the owner or employee of this workplace"


def _assert_profile(
    body: dict,
    user: dict,
    workplace_id: int,
    role: str,
    position: str | None,
) -> None:
    assert body["id"] >= 1
    assert body["user_id"] == user["id"]
    assert body["workplace_id"] == workplace_id
    assert body["role"] == role
    assert body["position"] == position
    assert body["is_active"] is True
    assert body["hire_date"] == date.today().isoformat()
    assert body["user"] == {
        "id": user["id"],
        "first_name": user["first_name"],
        "second_name": user["second_name"],
        "third_name": user["third_name"],
        "phone": user["phone"],
    }
    assert "email" not in body
    assert "email" not in body["user"]
    assert "password" not in body
    assert "hashed_password" not in body


def _params(workplace_id: int) -> dict:
    return {"workplace_id": workplace_id}


async def _read(client, employee_id: int, workplace_id: int, headers):
    return await client.get(
        f"/employees/{employee_id}",
        params=_params(workplace_id),
        headers=headers,
    )


@pytest.mark.asyncio
async def test_employee_routes_require_token(client):
    payload = employee_payload("+79990001122")
    params = _params(1)

    create = await client.post("/employees/", params=params, json=payload)
    read = await client.get("/employees/1", params=params)
    update = await client.put(
        "/employees/1", params=params, json={"role": "admin"}
    )
    delete = await client.delete("/employees/1", params=params)

    assert create.status_code == 401
    assert read.status_code == 401
    assert update.status_code == 401
    assert delete.status_code == 401


@pytest.mark.asyncio
async def test_employee_routes_reject_bad_tokens(client, session_factory):
    _owner, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    user, _user_headers = await register_and_login(client)
    employee = await create_employee(
        client, headers, workplace["id"], user["phone"]
    )
    params = _params(workplace["id"])
    path = f"/employees/{employee['id']}"
    tokens = (await login(client, user["email"], user["password"])).json()
    expired = make_token(user["email"], user["id"], expired=True)
    inactive_user, inactive_headers = await register_and_login(client)
    await set_user_active(session_factory, inactive_user["id"], False)

    garbage = await client.get(path, params=params, headers=auth_header("not-a-jwt"))
    expired_response = await client.get(
        path, params=params, headers=auth_header(expired)
    )
    refresh = await client.get(
        path, params=params, headers=auth_header(tokens["refresh_token"])
    )
    inactive = await client.get(path, params=params, headers=inactive_headers)

    assert garbage.status_code == 401
    assert garbage.json()["detail"] == "Could not validate the provided credential"
    assert expired_response.status_code == 401
    assert expired_response.json()["detail"] == "Token expired"
    assert refresh.status_code == 401
    assert inactive.status_code == 401


@pytest.mark.asyncio
async def test_create_employee_by_owner(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(
        client,
        first_name="Мария",
        second_name="Соколова",
        third_name="Игоревна",
    )
    workplace = await create_workplace(client, headers)
    payload = employee_payload(
        person["phone"],
        role="employee",
        position="Кладовщик",
        hire_date="2020-01-01",
        is_active=False,
        user_id=person["id"],
    )

    response = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    _assert_profile(body, person, workplace["id"], "employee", "Кладовщик")
    saved = await _read(client, body["id"], workplace["id"], headers)
    assert saved.status_code == 200
    assert saved.json() == body


@pytest.mark.asyncio
async def test_create_employee_without_position_or_patronymic(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client, third_name=None)
    workplace = await create_workplace(client, headers)

    response = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json={"phone": person["phone"], "role": "admin"},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    _assert_profile(body, person, workplace["id"], "admin", None)
    assert body["user"]["third_name"] is None


@pytest.mark.asyncio
async def test_create_employee_accepts_phone_starting_with_eight(client):
    _owner, headers = await register_and_login(client)
    phone = next_phone().replace("+7", "8", 1)
    person, _person_headers = await register_and_login(client, phone=phone)
    workplace = await create_workplace(client, headers)

    body = await create_employee(
        client, headers, workplace["id"], phone, position="Оператор"
    )

    _assert_profile(body, person, workplace["id"], "employee", "Оператор")
    assert body["user"]["phone"] == phone


@pytest.mark.asyncio
async def test_create_employee_by_admin_only_in_own_workplace(client):
    _owner, owner_headers = await register_and_login(client)
    admin, admin_headers = await register_and_login(client)
    candidate, _candidate_headers = await register_and_login(client)
    _other_owner, other_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    other = await create_workplace(client, other_headers)
    await create_employee(
        client, owner_headers, workplace["id"], admin["phone"], role="admin"
    )

    created = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=employee_payload(candidate["phone"], position="Сборщик"),
        headers=admin_headers,
    )
    foreign = await client.post(
        "/employees/",
        params=_params(other["id"]),
        json=employee_payload(candidate["phone"]),
        headers=admin_headers,
    )

    assert created.status_code == 201
    _assert_profile(
        created.json(), candidate, workplace["id"], "employee", "Сборщик"
    )
    assert foreign.status_code == 403
    assert foreign.json()["detail"] == OWNER_OR_ADMIN


@pytest.mark.asyncio
async def test_create_employee_forbidden_for_employee_and_stranger(client):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    candidate, _candidate_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await create_employee(
        client, owner_headers, workplace["id"], worker["phone"], role="employee"
    )
    payload = employee_payload(candidate["phone"])

    worker_attempt = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=payload,
        headers=worker_headers,
    )
    stranger_attempt = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=payload,
        headers=stranger_headers,
    )

    assert worker_attempt.status_code == 403
    assert worker_attempt.json()["detail"] == OWNER_OR_ADMIN
    assert stranger_attempt.status_code == 403
    assert stranger_attempt.json()["detail"] == OWNER_OR_ADMIN
    listed = await client.get(
        f"/workplaces/{workplace['id']}/employees",
        headers=owner_headers,
    )
    assert [item["user_id"] for item in listed.json()] == [worker["id"]]


@pytest.mark.asyncio
async def test_employee_role_owner_does_not_grant_management(client):
    _owner, owner_headers = await register_and_login(client)
    titled, titled_headers = await register_and_login(client)
    candidate, _candidate_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    created = await create_employee(
        client, owner_headers, workplace["id"], titled["phone"], role="owner"
    )

    attempt = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=employee_payload(candidate["phone"]),
        headers=titled_headers,
    )
    readable = await _read(client, created["id"], workplace["id"], titled_headers)

    assert created["role"] == "owner"
    assert attempt.status_code == 403
    assert attempt.json()["detail"] == OWNER_OR_ADMIN
    assert readable.status_code == 200


@pytest.mark.asyncio
async def test_create_employee_rejects_invalid_body(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    params = _params(workplace["id"])

    bad_phone = await client.post(
        "/employees/",
        params=params,
        json=employee_payload("79991234567"),
        headers=headers,
    )
    short_phone = await client.post(
        "/employees/",
        params=params,
        json=employee_payload("+7999"),
        headers=headers,
    )
    bad_role = await client.post(
        "/employees/",
        params=params,
        json=employee_payload(person["phone"], role="manager"),
        headers=headers,
    )
    missing_role = await client.post(
        "/employees/",
        params=params,
        json={"phone": person["phone"]},
        headers=headers,
    )
    missing_phone = await client.post(
        "/employees/",
        params=params,
        json={"role": "employee"},
        headers=headers,
    )
    missing_workplace = await client.post(
        "/employees/",
        json=employee_payload(person["phone"]),
        headers=headers,
    )
    bad_workplace = await client.post(
        "/employees/",
        params={"workplace_id": "abc"},
        json=employee_payload(person["phone"]),
        headers=headers,
    )

    assert bad_phone.status_code == 422
    assert short_phone.status_code == 422
    assert bad_role.status_code == 422
    assert missing_role.status_code == 422
    assert missing_phone.status_code == 422
    assert missing_workplace.status_code == 422
    assert bad_workplace.status_code == 422


@pytest.mark.asyncio
async def test_create_employee_unknown_or_inactive_user(client, session_factory):
    _owner, headers = await register_and_login(client)
    inactive, _inactive_headers = await register_and_login(client)
    await set_user_active(session_factory, inactive["id"], False)
    workplace = await create_workplace(client, headers)

    unknown = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=employee_payload("+70000000000"),
        headers=headers,
    )
    disabled = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=employee_payload(inactive["phone"]),
        headers=headers,
    )

    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "User with this phone number not found"
    assert disabled.status_code == 404
    assert disabled.json()["detail"] == "User with this phone number not found"


@pytest.mark.asyncio
async def test_create_employee_inactive_workplace(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    await client.delete(f"/workplaces/{workplace['id']}", headers=headers)

    response = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=employee_payload(person["phone"]),
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workplace not found"


@pytest.mark.asyncio
async def test_create_employee_duplicate_is_conflict(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    await create_employee(client, headers, workplace["id"], person["phone"])

    response = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=employee_payload(person["phone"], role="admin"),
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Employee already exists in this workplace"


@pytest.mark.asyncio
async def test_same_user_can_be_employee_of_two_workplaces(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    first = await create_workplace(client, headers, name="Первая")
    second = await create_workplace(client, headers, name="Вторая")

    first_employee = await create_employee(
        client, headers, first["id"], person["phone"], position="Кассир"
    )
    second_employee = await create_employee(
        client, headers, second["id"], person["phone"], role="admin", position=None
    )

    assert first_employee["id"] != second_employee["id"]
    assert first_employee["workplace_id"] == first["id"]
    assert second_employee["workplace_id"] == second["id"]
    assert second_employee["role"] == "admin"
    assert second_employee["position"] is None


@pytest.mark.asyncio
async def test_owner_can_add_own_phone(client):
    owner, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)

    body = await create_employee(
        client, headers, workplace["id"], owner["phone"], position="Владелец смены"
    )

    _assert_profile(body, owner, workplace["id"], "employee", "Владелец смены")


@pytest.mark.asyncio
async def test_create_employee_restores_inactive_record(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    created = await create_employee(
        client,
        headers,
        workplace["id"],
        person["phone"],
        role="employee",
        position="Кассир",
    )
    deleted = await client.delete(
        f"/employees/{created['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )

    restored = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=employee_payload(
            person["phone"], role="admin", position="Управляющий"
        ),
        headers=headers,
    )
    saved = await _read(client, created["id"], workplace["id"], headers)
    duplicate = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=employee_payload(person["phone"], role="employee"),
        headers=headers,
    )

    assert deleted.status_code == 200
    assert restored.status_code == 201
    assert restored.json()["id"] == created["id"]
    assert saved.status_code == 200
    _assert_profile(
        saved.json(), person, workplace["id"], "admin", "Управляющий"
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_restore_without_position_clears_it(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    created = await create_employee(
        client, headers, workplace["id"], person["phone"], position="Кассир"
    )
    await client.delete(
        f"/employees/{created['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )

    restored = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json={"phone": person["phone"], "role": "employee"},
        headers=headers,
    )
    saved = await _read(client, created["id"], workplace["id"], headers)

    assert restored.status_code == 201
    assert saved.status_code == 200
    assert saved.json()["id"] == created["id"]
    assert saved.json()["position"] is None
    assert saved.json()["role"] == "employee"
    assert saved.json()["is_active"] is True


@pytest.mark.asyncio
async def test_restore_rejected_when_user_inactive(client, session_factory):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    created = await create_employee(
        client, headers, workplace["id"], person["phone"]
    )
    await client.delete(
        f"/employees/{created['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )
    await set_user_active(session_factory, person["id"], False)

    response = await client.post(
        "/employees/",
        params=_params(workplace["id"]),
        json=employee_payload(person["phone"]),
        headers=headers,
    )
    hidden = await _read(client, created["id"], workplace["id"], headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "User with this phone number not found"
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_get_employee_for_owner_admin_and_colleague(client):
    _owner, owner_headers = await register_and_login(client)
    admin, admin_headers = await register_and_login(client)
    person, person_headers = await register_and_login(
        client, first_name="Олег", second_name="Орлов", third_name=None
    )
    colleague, colleague_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await create_employee(
        client, owner_headers, workplace["id"], admin["phone"], role="admin"
    )
    employee = await create_employee(
        client, owner_headers, workplace["id"], person["phone"], position="Кассир"
    )
    await create_employee(
        client, owner_headers, workplace["id"], colleague["phone"]
    )

    owner_response = await _read(
        client, employee["id"], workplace["id"], owner_headers
    )
    admin_response = await _read(
        client, employee["id"], workplace["id"], admin_headers
    )
    self_response = await _read(
        client, employee["id"], workplace["id"], person_headers
    )
    colleague_response = await _read(
        client, employee["id"], workplace["id"], colleague_headers
    )

    assert owner_response.status_code == 200
    assert admin_response.status_code == 200
    assert self_response.status_code == 200
    assert colleague_response.status_code == 200
    _assert_profile(
        colleague_response.json(), person, workplace["id"], "employee", "Кассир"
    )
    assert colleague_response.json()["user"]["third_name"] is None


@pytest.mark.asyncio
async def test_get_employee_not_found(client, session_factory):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    hidden, _hidden_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers, name="Своя")
    other = await create_workplace(client, headers, name="Другая")
    employee = await create_employee(
        client, headers, workplace["id"], person["phone"]
    )
    inactive_id = await add_employee(
        session_factory,
        user_id=hidden["id"],
        workplace_id=workplace["id"],
        is_active=False,
    )

    missing = await _read(client, 999999, workplace["id"], headers)
    other_workplace = await _read(client, employee["id"], other["id"], headers)
    inactive = await _read(client, inactive_id, workplace["id"], headers)
    bad_id = await client.get(
        "/employees/abc",
        params=_params(workplace["id"]),
        headers=headers,
    )

    assert missing.status_code == 404
    assert missing.json()["detail"] == "Employee not found"
    assert other_workplace.status_code == 404
    assert other_workplace.json()["detail"] == "Employee not found"
    assert inactive.status_code == 404
    assert inactive.json()["detail"] == "Employee not found"
    assert bad_id.status_code == 422


@pytest.mark.asyncio
async def test_get_employee_forbidden(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    outsider, outsider_headers = await register_and_login(client)
    _other_owner, other_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    other = await create_workplace(client, other_headers)
    employee = await create_employee(
        client, owner_headers, workplace["id"], worker["phone"]
    )
    await add_employee(
        session_factory,
        user_id=outsider["id"],
        workplace_id=workplace["id"],
        is_active=False,
    )

    stranger = await _read(
        client, employee["id"], workplace["id"], outsider_headers
    )
    wrong_scope = await _read(
        client, employee["id"], other["id"], worker_headers
    )

    assert stranger.status_code == 403
    assert stranger.json()["detail"] == OWNER_OR_EMPLOYEE
    assert wrong_scope.status_code == 403
    assert wrong_scope.json()["detail"] == OWNER_OR_EMPLOYEE


@pytest.mark.asyncio
async def test_update_employee_persists_role_and_position(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee = await create_employee(
        client, headers, workplace["id"], person["phone"], position="Кассир"
    )

    response = await client.put(
        f"/employees/{employee['id']}",
        params=_params(workplace["id"]),
        json={"role": "admin", "position": "Старший смены", "phone": "+70000000000"},
        headers=headers,
    )
    saved = await _read(client, employee["id"], workplace["id"], headers)

    assert response.status_code == 200
    assert response.json()["id"] == employee["id"]
    assert response.json()["user"]["phone"] == person["phone"]
    assert saved.status_code == 200
    assert saved.json()["role"] == "admin"
    assert saved.json()["position"] == "Старший смены"
    assert saved.json()["user"]["phone"] == person["phone"]
    assert saved.json()["hire_date"] == employee["hire_date"]


@pytest.mark.asyncio
async def test_update_employee_partial_and_clear_position(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee = await create_employee(
        client,
        headers,
        workplace["id"],
        person["phone"],
        role="employee",
        position="Кассир",
    )

    only_role = await client.put(
        f"/employees/{employee['id']}",
        params=_params(workplace["id"]),
        json={"role": "admin"},
        headers=headers,
    )
    after_role = await _read(client, employee["id"], workplace["id"], headers)
    clear_position = await client.put(
        f"/employees/{employee['id']}",
        params=_params(workplace["id"]),
        json={"position": None},
        headers=headers,
    )
    saved = await _read(client, employee["id"], workplace["id"], headers)

    assert only_role.status_code == 200
    assert after_role.json()["role"] == "admin"
    assert after_role.json()["position"] == "Кассир"
    assert clear_position.status_code == 200
    assert saved.json()["role"] == "admin"
    assert saved.json()["position"] is None


@pytest.mark.asyncio
async def test_promoted_admin_can_manage_until_demoted(client):
    _owner, owner_headers = await register_and_login(client)
    person, person_headers = await register_and_login(client)
    candidate, _candidate_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    employee = await create_employee(
        client, owner_headers, workplace["id"], person["phone"], role="employee"
    )
    params = _params(workplace["id"])
    payload = employee_payload(candidate["phone"])

    before = await client.post(
        "/employees/", params=params, json=payload, headers=person_headers
    )
    await client.put(
        f"/employees/{employee['id']}",
        params=params,
        json={"role": "admin"},
        headers=owner_headers,
    )
    promoted = await client.post(
        "/employees/", params=params, json=payload, headers=person_headers
    )
    await client.put(
        f"/employees/{employee['id']}",
        params=params,
        json={"role": "employee"},
        headers=owner_headers,
    )
    demoted = await client.put(
        f"/employees/{promoted.json()['id']}",
        params=params,
        json={"position": "Новая"},
        headers=person_headers,
    )
    saved = await _read(client, employee["id"], workplace["id"], owner_headers)

    assert before.status_code == 403
    assert promoted.status_code == 201
    assert demoted.status_code == 403
    assert demoted.json()["detail"] == OWNER_OR_ADMIN
    assert saved.json()["role"] == "employee"


@pytest.mark.asyncio
async def test_update_employee_forbidden_invalid_and_missing(client):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    other = await create_workplace(client, owner_headers, name="Вторая")
    employee = await create_employee(
        client, owner_headers, workplace["id"], worker["phone"], position="Кассир"
    )
    params = _params(workplace["id"])
    path = f"/employees/{employee['id']}"

    worker_attempt = await client.put(
        path, params=params, json={"role": "admin"}, headers=worker_headers
    )
    stranger_attempt = await client.put(
        path, params=params, json={"role": "admin"}, headers=stranger_headers
    )
    invalid = await client.put(
        path, params=params, json={"role": "boss"}, headers=owner_headers
    )
    missing = await client.put(
        "/employees/999999",
        params=params,
        json={"position": "Нет"},
        headers=owner_headers,
    )
    wrong_workplace = await client.put(
        path,
        params=_params(other["id"]),
        json={"position": "Чужая"},
        headers=owner_headers,
    )
    saved = await _read(client, employee["id"], workplace["id"], owner_headers)

    assert worker_attempt.status_code == 403
    assert worker_attempt.json()["detail"] == OWNER_OR_ADMIN
    assert stranger_attempt.status_code == 403
    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Employee not found"
    assert wrong_workplace.status_code == 404
    assert wrong_workplace.json()["detail"] == "Employee not found"
    assert saved.json()["role"] == "employee"
    assert saved.json()["position"] == "Кассир"


@pytest.mark.asyncio
async def test_delete_employee_is_soft_and_keeps_shifts(client, session_factory):
    _owner, headers = await register_and_login(client)
    person, person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee = await create_employee(
        client, headers, workplace["id"], person["phone"]
    )
    shift_id = await add_shift(
        session_factory,
        workplace_id=workplace["id"],
        employee_id=employee["id"],
    )
    params = _params(workplace["id"])

    response = await client.delete(
        f"/employees/{employee['id']}", params=params, headers=headers
    )
    again = await client.delete(
        f"/employees/{employee['id']}", params=params, headers=headers
    )
    hidden = await _read(client, employee["id"], workplace["id"], headers)
    locked = await _read(client, employee["id"], workplace["id"], person_headers)

    assert response.status_code == 200
    assert response.json() == {"message": "Employee deactivated successfully"}
    assert again.status_code == 404
    assert again.json()["detail"] == "Employee not found"
    assert hidden.status_code == 404
    assert locked.status_code == 403
    assert locked.json()["detail"] == OWNER_OR_EMPLOYEE

    async with session_factory() as session:
        stored_employee = await session.get(Employee, employee["id"])
        stored_shift = await session.get(Shift, shift_id)
        assert stored_employee.is_active is False
        assert stored_employee.user_id == person["id"]
        assert stored_shift.is_active is True
        assert stored_shift.employee_id == employee["id"]


@pytest.mark.asyncio
async def test_admin_can_delete_employee(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    admin, admin_headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await create_employee(
        client, owner_headers, workplace["id"], admin["phone"], role="admin"
    )
    employee = await create_employee(
        client, owner_headers, workplace["id"], person["phone"]
    )

    response = await client.delete(
        f"/employees/{employee['id']}",
        params=_params(workplace["id"]),
        headers=admin_headers,
    )

    assert response.status_code == 200
    async with session_factory() as session:
        stored = await session.get(Employee, employee["id"])
        assert stored.is_active is False


@pytest.mark.asyncio
async def test_delete_employee_forbidden_leaves_record(client):
    _owner, owner_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    other = await create_workplace(client, owner_headers, name="Вторая")
    employee = await create_employee(
        client, owner_headers, workplace["id"], worker["phone"], position="Кассир"
    )
    path = f"/employees/{employee['id']}"

    worker_attempt = await client.delete(
        path, params=_params(workplace["id"]), headers=worker_headers
    )
    stranger_attempt = await client.delete(
        path, params=_params(workplace["id"]), headers=stranger_headers
    )
    wrong_workplace = await client.delete(
        path, params=_params(other["id"]), headers=owner_headers
    )
    saved = await _read(client, employee["id"], workplace["id"], owner_headers)

    assert worker_attempt.status_code == 403
    assert worker_attempt.json()["detail"] == OWNER_OR_ADMIN
    assert stranger_attempt.status_code == 403
    assert wrong_workplace.status_code == 404
    assert wrong_workplace.json()["detail"] == "Employee not found"
    assert saved.status_code == 200
    assert saved.json()["is_active"] is True
    assert saved.json()["position"] == "Кассир"


@pytest.mark.asyncio
async def test_update_inactive_employee_is_not_found(client):
    _owner, headers = await register_and_login(client)
    person, _person_headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee = await create_employee(
        client, headers, workplace["id"], person["phone"], position="Кассир"
    )
    await client.delete(
        f"/employees/{employee['id']}",
        params=_params(workplace["id"]),
        headers=headers,
    )

    response = await client.put(
        f"/employees/{employee['id']}",
        params=_params(workplace["id"]),
        json={"position": "Снова"},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Employee not found"
