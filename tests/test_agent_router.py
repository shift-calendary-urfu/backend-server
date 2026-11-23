from unittest.mock import AsyncMock, patch

import pytest

from app.agent.agent_service import AgentServiceError
from app.agent.schemas import AgentAnswer
from tests.helpers import create_workplace, register_and_login


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
