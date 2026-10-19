import pytest

from tests.helpers import (
    auth_header,
    login,
    make_token,
    next_phone,
    register_and_login,
    register_user,
    set_user_active,
)


@pytest.mark.asyncio
async def test_get_me_requires_token(client):
    response = await client.get("/users/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_rejects_invalid_token(client):
    response = await client.get("/users/me", headers=auth_header("not-a-jwt"))

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate the provided credential"


@pytest.mark.asyncio
async def test_get_me_rejects_expired_token(client):
    user, _headers = await register_and_login(client)
    token = make_token(user["email"], user["id"], expired=True)

    response = await client.get("/users/me", headers=auth_header(token))

    assert response.status_code == 401
    assert response.json()["detail"] == "Token expired"


@pytest.mark.asyncio
async def test_get_me_rejects_refresh_token(client):
    user = await register_user(client)
    tokens = (await login(client, user["email"], user["password"])).json()

    response = await client.get(
        "/users/me",
        headers=auth_header(tokens["refresh_token"]),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_returns_current_profile(client):
    user, headers = await register_and_login(client)

    response = await client.get("/users/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user["id"]
    assert body["email"] == user["email"]
    assert body["phone"] == user["phone"]
    assert body["first_name"] == "Иван"
    assert body["second_name"] == "Иванов"
    assert body["third_name"] == "Иванович"
    assert body["is_active"] is True
    assert "hashed_password" not in body
    assert "password" not in body


@pytest.mark.asyncio
async def test_get_me_rejects_inactive_user(client, session_factory):
    user, headers = await register_and_login(client)
    await set_user_active(session_factory, user["id"], False)

    response = await client.get("/users/me", headers=headers)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_me_persists_profile(client):
    _user, headers = await register_and_login(client)
    payload = {
        "first_name": "Пётр",
        "second_name": "Петров",
        "third_name": "Петрович",
        "phone": next_phone(),
    }

    response = await client.put("/users/me", json=payload, headers=headers)

    assert response.status_code == 201
    assert response.json()["first_name"] == payload["first_name"]
    assert response.json()["phone"] == payload["phone"]
    saved = (await client.get("/users/me", headers=headers)).json()
    assert saved["first_name"] == payload["first_name"]
    assert saved["second_name"] == payload["second_name"]
    assert saved["third_name"] == payload["third_name"]
    assert saved["phone"] == payload["phone"]


@pytest.mark.asyncio
async def test_update_me_partial_does_not_clear_other_fields(client):
    user, headers = await register_and_login(client)

    response = await client.put(
        "/users/me",
        json={"first_name": "Анна"},
        headers=headers,
    )

    assert response.status_code == 201
    saved = (await client.get("/users/me", headers=headers)).json()
    assert saved["first_name"] == "Анна"
    assert saved["second_name"] == user["second_name"]
    assert saved["email"] == user["email"]
    assert saved["phone"] == user["phone"]


@pytest.mark.asyncio
async def test_update_me_can_clear_third_name(client):
    _user, headers = await register_and_login(client)

    response = await client.put(
        "/users/me",
        json={"third_name": None},
        headers=headers,
    )

    assert response.status_code == 201
    saved = (await client.get("/users/me", headers=headers)).json()
    assert saved["third_name"] is None


@pytest.mark.asyncio
async def test_update_me_empty_body_keeps_profile(client):
    user, headers = await register_and_login(client)

    response = await client.put("/users/me", json={}, headers=headers)

    assert response.status_code == 201
    saved = (await client.get("/users/me", headers=headers)).json()
    assert saved["first_name"] == user["first_name"]
    assert saved["email"] == user["email"]


@pytest.mark.asyncio
async def test_update_me_rejects_invalid_phone_and_email(client):
    _user, headers = await register_and_login(client)

    phone_response = await client.put(
        "/users/me",
        json={"phone": "12345"},
        headers=headers,
    )
    email_response = await client.put(
        "/users/me",
        json={"email": "not-an-email"},
        headers=headers,
    )

    assert phone_response.status_code == 422
    assert email_response.status_code == 422


@pytest.mark.asyncio
async def test_update_me_accepts_phone_with_eight(client):
    _user, headers = await register_and_login(client)

    response = await client.put(
        "/users/me",
        json={"phone": "89991234567"},
        headers=headers,
    )

    assert response.status_code == 201
    saved = (await client.get("/users/me", headers=headers)).json()
    assert saved["phone"] == "89991234567"


@pytest.mark.asyncio
async def test_update_me_requires_token(client):
    response = await client.put("/users/me", json={"first_name": "Пётр"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_email_is_used_on_next_login(client):
    user, headers = await register_and_login(client)
    new_email = "renamed@example.com"

    response = await client.put(
        "/users/me",
        json={"email": new_email},
        headers=headers,
    )

    assert response.status_code == 201
    old_login = await login(client, user["email"], user["password"])
    new_login = await login(client, new_email, user["password"])
    assert old_login.status_code == 401
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_update_password_success(client):
    user, headers = await register_and_login(client)
    new_password = "NewPassword1"

    response = await client.put(
        "/users/me/password",
        json={"old_password": user["password"], "new_password": new_password},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Password updated"}
    assert (await login(client, user["email"], user["password"])).status_code == 401
    assert (await login(client, user["email"], new_password)).status_code == 200
    me = await client.get("/users/me", headers=headers)
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_update_password_wrong_old_password(client):
    user, headers = await register_and_login(client)

    response = await client.put(
        "/users/me/password",
        json={"old_password": "WrongPassword1", "new_password": "NewPassword1"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Current password is not matching."
    assert (await login(client, user["email"], user["password"])).status_code == 200


@pytest.mark.asyncio
async def test_update_password_rejects_short_passwords(client):
    user, headers = await register_and_login(client)

    short_new = await client.put(
        "/users/me/password",
        json={"old_password": user["password"], "new_password": "short"},
        headers=headers,
    )
    short_old = await client.put(
        "/users/me/password",
        json={"old_password": "short", "new_password": "NewPassword1"},
        headers=headers,
    )

    assert short_new.status_code == 422
    assert short_old.status_code == 422
    assert (await login(client, user["email"], user["password"])).status_code == 200


@pytest.mark.asyncio
async def test_update_password_requires_token(client):
    response = await client.put(
        "/users/me/password",
        json={"old_password": "Password1", "new_password": "NewPassword1"},
    )

    assert response.status_code == 401
