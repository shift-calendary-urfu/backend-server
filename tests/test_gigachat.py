import json

import pytest

from app.agent.sberbank_gigachat_auth import (
    get_gigachat_token,
    send_gigachat_request,
)
from app.config import Settings


@pytest.mark.asyncio
async def test_gigachat_token_and_chat_request():
    authorization_key = Settings().GIGA_API_KEY
    if not authorization_key:
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
