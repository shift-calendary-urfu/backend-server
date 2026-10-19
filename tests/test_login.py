import jwt
import pytest

from app.config import settings

from tests.helpers import login, register_and_login, register_user, set_user_active


@pytest.mark.asyncio
async def test_login_returns_access_and_refresh_tokens(client):
    user = await register_user(client)

    response = await login(client, user["email"], user["password"])

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


@pytest.mark.asyncio
async def test_login_token_payload(client):
    user = await register_user(client)

    response = await login(client, user["email"], user["password"])
    body = response.json()

    access = jwt.decode(
        body["access_token"],
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    refresh = jwt.decode(
        body["refresh_token"],
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert access["sub"] == user["email"]
    assert access["id"] == user["id"]
    assert access["token_type"] == "access"
    assert refresh["sub"] == user["email"]
    assert refresh["id"] == user["id"]
    assert refresh["token_type"] == "refresh"
    assert refresh["exp"] > access["exp"]


@pytest.mark.asyncio
async def test_login_token_opens_protected_route(client):
    user = await register_user(client)
    tokens = (await login(client, user["email"], user["password"])).json()

    response = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == user["email"]


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    user = await register_user(client)

    response = await login(client, user["email"], "WrongPassword1")

    assert response.status_code == 401
    assert response.json()["detail"] == "Неверное имя пользователя или пароль."


@pytest.mark.asyncio
async def test_login_unknown_user(client):
    response = await login(client, "missing@example.com", "Password1")

    assert response.status_code == 401
    assert response.json()["detail"] == "Неверное имя пользователя или пароль."


@pytest.mark.asyncio
async def test_login_inactive_user(client, session_factory):
    user, _headers = await register_and_login(client)
    await set_user_active(session_factory, user["id"], False)

    response = await login(client, user["email"], user["password"])

    assert response.status_code == 401
    assert response.json()["detail"] == "Неверное имя пользователя или пароль."


@pytest.mark.asyncio
async def test_login_expects_form_username_not_json_email(client):
    user = await register_user(client)

    response = await client.post(
        "/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_missing_form_fields(client):
    response = await client.post("/auth/login", data={"username": "user@example.com"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_with_phone_is_rejected(client):
    user = await register_user(client)

    response = await login(client, user["phone"], user["password"])

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_empty_password_is_rejected(client):
    user = await register_user(client)

    response = await client.post(
        "/auth/login",
        data={"username": user["email"], "password": ""},
    )

    assert response.status_code == 422
