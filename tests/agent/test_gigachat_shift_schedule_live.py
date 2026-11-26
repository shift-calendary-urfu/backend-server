"""Опциональные интеграционные проверки тула графика с живым GigaChat API."""

import json
import os
from datetime import time
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.agent.agent_service import CREATE_SHIFT_SCHEDULE_TOOL
from app.agent.giga_auth import get_gigachat_token
from app.agent.giga_client import send_gigachat_request
from app.agent.schemas import ShiftScheduleRequest
from app.agent.tools import prepare_shift_schedule
from app.config import settings
from app.employees.model import Employee
from app.shifts.model import Shift
from app.users.model import User
from app.workplaces.model import Workplace


@pytest.mark.asyncio
async def test_live_gigachat_calls_shift_schedule_tool(session_factory):
    """Проверяет реальный вызов тула и серверный расчёт без записи смен."""
    if os.getenv("RUN_GIGACHAT_LIVE_TESTS") != "1":
        pytest.skip("Установите RUN_GIGACHAT_LIVE_TESTS=1 для обращения к GigaChat API")
    if not settings.GIGA_API_KEY or settings.GIGA_API_KEY == "key":
        pytest.skip("GIGA_API_KEY не задан")

    async with session_factory() as db:
        owner = User(
            email=f"live-agent-{uuid4().hex}@example.com",
            hashed_password="test-hash",
            first_name="Live",
            second_name="Test",
            phone=f"+7999{uuid4().int % 10**7:07d}",
        )
        db.add(owner)
        await db.flush()

        workplace = Workplace(
            name="GigaChat live test workplace",
            address="Test address",
            workplace_type="other",
            work_start_time=time(9, 0),
            work_end_time=time(18, 0),
            owner_id=owner.id,
        )
        db.add(workplace)
        await db.flush()

        employee = Employee(
            user_id=owner.id,
            workplace_id=workplace.id,
            role="admin",
            is_active=True,
        )
        db.add(employee)
        await db.commit()

        token = await get_gigachat_token(settings.GIGA_API_KEY)
        response = await send_gigachat_request(
            token,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Используй только вызов функции create_shift_schedule. "
                        "Не отвечай обычным текстом и передай параметры из запроса "
                        "без изменений."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Подготовь график смен со следующими данными: "
                        f"рабочая точка ID {workplace.id}, сотрудник ID {employee.id}, "
                        "цикл 5 рабочих дней / 2 выходных, период 7 календарных дней."
                    ),
                }
            ],
            tools=[CREATE_SHIFT_SCHEDULE_TOOL],
            tool_choice={
                "type": "function",
                "function": {"name": "create_shift_schedule"},
            },
        )

        choices = response.get("choices")
        assert isinstance(choices, list) and choices, (
            f"GigaChat response did not contain choices: "
            f"{json.dumps(response, ensure_ascii=False)}"
        )
        message = choices[0].get("message", {})
        function_call = message.get("function_call")
        if isinstance(function_call, dict):
            function = function_call
        else:
            tool_calls = message.get("tool_calls")
            assert isinstance(tool_calls, list) and tool_calls, (
                "GigaChat did not call the required function; "
                f"finish_reason={choices[0].get('finish_reason')!r}, "
                f"message={json.dumps(message, ensure_ascii=False)}"
            )
            function = tool_calls[0].get("function", {})
        assert function.get("name") == "create_shift_schedule", (
            "GigaChat did not call the required tool; "
            f"finish_reason={choices[0].get('finish_reason')!r}, "
            f"message={json.dumps(message, ensure_ascii=False)}"
        )
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        request = ShiftScheduleRequest.model_validate(arguments)
        assert request.workplace_id == workplace.id
        assert request.employee_id == employee.id
        assert request.schedule == "5/2"
        assert request.period == 7

        plan = await prepare_shift_schedule(request, owner, db)

        assert len(plan["shifts"]) == 5
        assert all(
            shift["start_time"] == "09:00" and shift["end_time"] == "18:00"
            for shift in plan["shifts"]
        )
        assert "5/2" in plan["summary"]
        assert "новых смен: 5" in plan["summary"]
        assert await db.scalar(select(func.count()).select_from(Shift)) == 0
