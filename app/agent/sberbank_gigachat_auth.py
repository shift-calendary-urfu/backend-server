import asyncio
import requests
import uuid

async def get_gigachat_token(authorization_key: str) -> str:
    """
    Получает токен для ЛЛМ GigaChat, используя ключ авторизации.
    
    Args:
        authorization_key (str): Ключ авторизации (Bearer <TOKEN>).
    
    Returns:
        str: Полученный токен.
    
    Raises:
        Exception: Если запрос не успешен.
    """
    rq_uuid = str(uuid.uuid4())
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = {"scope": "GIGACHAT_API_PERS"}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': rq_uuid,
        'Authorization': f"Basic {authorization_key}"
    }
    
    response = await asyncio.to_thread(
        requests.post,
        url,
        headers=headers,
        data=payload,
        verify=False,
    )
    
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        raise Exception(f"Ошибка при получении токена: {response.status_code} - {response.text}")


async def send_gigachat_request(
    token: str,
    messages: list[dict[str, str]],
    model: str = "GigaChat",
) -> dict:
    """
    Отправляет запрос в GigaChat с полученным OAuth-токеном.
    """
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    response = await asyncio.to_thread(
        requests.post,
        url,
        headers=headers,
        json=payload,
        timeout=30,
        verify=False,
    )

    if response.status_code == 200:
        return response.json()

    raise Exception(
        f"Ошибка при отправке запроса в GigaChat: "
        f"{response.status_code} - {response.text}"
    )
