import json

import pytest

from app.agent.giga_auth import get_gigachat_token
from app.agent.giga_client import send_gigachat_request
from app.config import settings


@pytest.mark.asyncio
async def test_gigachat_request_uses_v1_function_call_format(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(
        "app.agent.giga_client.httpx.AsyncClient",
        lambda **_kwargs: FakeClient(),
    )

    await send_gigachat_request(
        "test-token",
        messages=[{"role": "user", "content": "call function"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "test_function",
                    "description": "Test function",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        tool_choice={
            "type": "function",
            "function": {"name": "test_function"},
        },
    )

    assert captured["payload"]["functions"] == [
        {
            "name": "test_function",
            "description": "Test function",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    assert captured["payload"]["function_call"] == {"name": "test_function"}
    assert "tools" not in captured["payload"]
    assert "tool_choice" not in captured["payload"]


@pytest.mark.asyncio
async def test_gigachat_token_and_chat_request():
    authorization_key = settings.GIGA_API_KEY
    if not authorization_key or authorization_key == "key":
        pytest.skip("GIGA_API_KEY не задан")

    token = await get_gigachat_token(authorization_key)
    assert token

    response = await send_gigachat_request(
        token,
        messages=[
            {
                "role": "user",
                "content": "Ответь одним словом: работает?",
            }
        ],
    )
    print("GigaChat response:")
    print(json.dumps(response, ensure_ascii=False, indent=2))

    assert response.get("choices")
    message = response["choices"][0].get("message", {})
    assert isinstance(message.get("content"), str)
    assert message["content"].strip()
    print(f"GigaChat answer: {message['content']}")
