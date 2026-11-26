import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.agent.agent_service import AgentServiceError
from app.agent.confirmation import cancel_pending_action
from app.agent.schemas import AgentAnswer
from app.shifts.model import Shift
from tests.helpers import (
    create_employee,
    create_shift,
    create_workplace,
    login,
    register_and_login,
    register_user,
)


@pytest.mark.asyncio
async def test_agent_query_requires_authentication(client):
    response = await client.post(
        "/agent/query",
        json={"query": "Какие у меня рабочие точки?"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_query_returns_answer_for_authenticated_user(client):
    _user, headers = await register_and_login(client)

    with patch(
        "app.agent.router.AgentService.process",
        new=AsyncMock(
            return_value=AgentAnswer(answer="У вас есть одна рабочая точка.")
        ),
    ):
        response = await client.post(
            "/agent/query",
            json={"query": "Какие у меня рабочие точки?"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json() == {"answer": "У вас есть одна рабочая точка."}


@pytest.mark.asyncio
async def test_agent_query_rejects_empty_query(client):
    _user, headers = await register_and_login(client)

    response = await client.post(
        "/agent/query",
        json={"query": "   "},
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agent_query_maps_service_error_to_bad_gateway(client):
    _user, headers = await register_and_login(client)

    with patch(
        "app.agent.router.AgentService.process",
        new=AsyncMock(side_effect=AgentServiceError("GigaChat недоступен")),
    ):
        response = await client.post(
            "/agent/query",
            json={"query": "Какие у меня рабочие точки?"},
            headers=headers,
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "GigaChat недоступен"


@pytest.mark.asyncio
async def test_agent_query_uses_real_workplace_tool_for_current_user(client):
    _user, headers = await register_and_login(client)
    workplace = await create_workplace(
        client,
        headers,
        name="Моя точка",
        address="ул. Агентов, 1",
    )

    first_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-workplaces",
                            "type": "function",
                            "function": {
                                "name": "list_my_workplaces",
                                "arguments": '{"query":"Какие у меня рабочие точки?"}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    final_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": f"У вас есть рабочая точка «{workplace['name']}».",
                }
            }
        ]
    }

    with (
        patch(
            "app.agent.agent_service.get_gigachat_token",
            new=AsyncMock(return_value="test-token"),
        ),
        patch(
            "app.agent.agent_service.send_gigachat_request",
            new=AsyncMock(side_effect=[first_response, final_response]),
        ),
    ):
        response = await client.post(
            "/agent/query",
            json={"query": "Какие у меня рабочие точки?"},
            headers=headers,
        )

    assert response.status_code == 200
    assert workplace["name"] in response.json()["answer"]


@pytest.mark.asyncio
async def test_agent_query_executes_gigachat_v1_function_call(client):
    _user, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers, name="Точка из функции")
    first_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "function_call": {
                        "name": "list_my_workplaces",
                        "arguments": {"query": "Мои рабочие точки"},
                    },
                }
            }
        ]
    }
    final_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": f"Найдена точка «{workplace['name']}».",
                }
            }
        ]
    }

    with (
        patch(
            "app.agent.agent_service.get_gigachat_token",
            new=AsyncMock(return_value="test-token"),
        ),
        patch(
            "app.agent.agent_service.send_gigachat_request",
            new=AsyncMock(side_effect=[first_response, final_response]),
        ) as send_request,
    ):
        response = await client.post(
            "/agent/query",
            json={"query": "Покажи мои рабочие точки"},
            headers=headers,
        )

    assert response.status_code == 200
    assert workplace["name"] in response.json()["answer"]
    follow_up_messages = send_request.await_args_list[1].args[1]
    assert follow_up_messages[-2]["function_call"]["name"] == "list_my_workplaces"
    assert follow_up_messages[-1]["role"] == "function"
    assert follow_up_messages[-1]["name"] == "list_my_workplaces"
    assert (
        json.loads(follow_up_messages[-1]["content"])["workplaces"][0]["id"]
        == workplace["id"]
    )


@pytest.mark.asyncio
async def test_agent_shift_schedule_requires_confirmation_before_creating_shifts(
    client,
    session_factory,
):
    _user, headers = await register_and_login(client)
    workplace = await create_workplace(
        client,
        headers,
        name="Точка для графика",
    )
    employee_user = await register_user(client)
    employee = await create_employee(
        client,
        headers,
        workplace["id"],
        employee_user["phone"],
    )
    await create_shift(
        client,
        headers,
        workplace["id"],
        employee["id"],
        date=date.today(),
    )

    tool_call = {
        "id": "call-schedule",
        "type": "function",
        "function": {
            "name": "create_shift_schedule",
            "arguments": json.dumps(
                {
                    "workplace_id": workplace["id"],
                    "employee_id": employee["id"],
                    "schedule": "5/2",
                    "period": 7,
                }
            ),
        },
    }
    first_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call],
                }
            }
        ]
    }
    final_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Подготовил график. Подтвердите его для создания смен.",
                }
            }
        ]
    }

    with (
        patch(
            "app.agent.agent_service.get_gigachat_token",
            new=AsyncMock(return_value="test-token"),
        ),
        patch(
            "app.agent.agent_service.send_gigachat_request",
            new=AsyncMock(side_effect=[first_response, final_response]),
        ),
    ):
        response = await client.post(
            "/agent/query",
            json={"query": "Составь график 5/2 на 7 дней для сотрудника"},
            headers=headers,
        )

    assert response.status_code == 200
    result = response.json()
    assert result["confirmation_required"] is True
    assert "новых смен: 4" in result["confirmation_summary"]
    assert result["confirmation_summary"] in result["answer"]
    assert "Подтвердите действие" in result["answer"]
    assert "Пропустить даты с существующими сменами" in result["confirmation_summary"]
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Shift)) == 1

    confirmation = await client.post(
        "/agent/confirm",
        json={"confirmation_id": result["confirmation_id"], "approved": True},
        headers=headers,
    )

    assert confirmation.status_code == 200
    assert confirmation.json()["status"] == "executed", confirmation.json()
    assert "Создано смен: 4" in confirmation.json()["answer"]
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Shift)) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("schedule", "expected_schedule"),
    [(None, "не задан или некорректен — одна смена"), ("invalid", "некорректен — одна смена")],
)
async def test_agent_shift_schedule_with_missing_or_invalid_schedule_prepares_one_shift(
    client,
    session_factory,
    schedule,
    expected_schedule,
):
    _user, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)
    employee_user = await register_user(client)
    employee = await create_employee(
        client,
        headers,
        workplace["id"],
        employee_user["phone"],
    )
    arguments = {
        "workplace_id": workplace["id"],
        "employee_id": employee["id"],
        "period": 30,
    }
    if schedule is not None:
        arguments["schedule"] = schedule

    first_response = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-partial-schedule",
                    "type": "function",
                    "function": {
                        "name": "create_shift_schedule",
                        "arguments": json.dumps(arguments),
                    },
                }],
            },
        }],
    }
    final_response = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Подготовил одну смену. Подтвердите создание.",
            },
        }],
    }
    with (
        patch(
            "app.agent.agent_service.get_gigachat_token",
            new=AsyncMock(return_value="test-token"),
        ),
        patch(
            "app.agent.agent_service.send_gigachat_request",
            new=AsyncMock(side_effect=[first_response, final_response]),
        ),
    ):
        response = await client.post(
            "/agent/query",
            json={"query": "Подготовь смену сотруднику"},
            headers=headers,
        )

    assert response.status_code == 200
    result = response.json()
    assert result["confirmation_required"] is True
    assert expected_schedule in result["confirmation_summary"]
    assert "новых смен: 1" in result["confirmation_summary"]
    assert "period=30 не применяется" in result["confirmation_summary"]
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Shift)) == 0

    assert cancel_pending_action(result["confirmation_id"], _user["id"]) is True


@pytest.mark.asyncio
async def test_regular_employee_cannot_prepare_shift_schedule(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    employee_user = await register_user(client)
    employee = await create_employee(
        client,
        owner_headers,
        workplace["id"],
        employee_user["phone"],
    )
    employee_login = await login(
        client,
        employee_user["email"],
        employee_user["password"],
    )
    employee_headers = {
        "Authorization": f"Bearer {employee_login.json()['access_token']}",
    }

    first_response = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-unauthorized-schedule",
                    "type": "function",
                    "function": {
                        "name": "create_shift_schedule",
                        "arguments": json.dumps({
                            "workplace_id": workplace["id"],
                            "employee_id": employee["id"],
                            "schedule": "5/2",
                            "period": 7,
                        }),
                    },
                }],
            },
        }],
    }
    final_response = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Составлять смены может только владелец или администратор.",
            },
        }],
    }
    with (
        patch(
            "app.agent.agent_service.get_gigachat_token",
            new=AsyncMock(return_value="test-token"),
        ),
        patch(
            "app.agent.agent_service.send_gigachat_request",
            new=AsyncMock(side_effect=[first_response, final_response]),
        ),
    ):
        response = await client.post(
            "/agent/query",
            json={"query": "Составь мой график на неделю"},
            headers=employee_headers,
        )

    assert response.status_code == 200
    result = response.json()
    assert "confirmation_required" not in result
    assert "confirmation_id" not in result
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Shift)) == 0
