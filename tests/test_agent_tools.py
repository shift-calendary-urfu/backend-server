from datetime import time
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.tools import list_my_workplaces
from app.agent.schemas import (
    AgentAnswer,
    ListMyWorkplacesRequest,
    ListMyWorkplacesResponse,
)
from app.agent.agent_service import AgentService
from app.employees.model import Employee
from app.users.model import User
from app.workplaces.model import Workplace


@pytest.mark.asyncio
async def test_list_my_workplaces_returns_owned_and_employee_workplaces(session_factory):
    async with session_factory() as db:
        owner = User(
            email="owner-agent@example.com",
            hashed_password="hash",
            first_name="Owner",
            second_name="Agent",
            phone="+79990000001",
        )
        employee = User(
            email="employee-agent@example.com",
            hashed_password="hash",
            first_name="Employee",
            second_name="Agent",
            phone="+79990000002",
        )
        other = User(
            email="other-agent@example.com",
            hashed_password="hash",
            first_name="Other",
            second_name="Agent",
            phone="+79990000003",
        )
        db.add_all([owner, employee, other])
        await db.flush()

        owned = Workplace(
            name="Owned point",
            address="Address 1",
            workplace_type="ozon",
            work_start_time=time(9, 0),
            work_end_time=time(21, 0),
            owner_id=owner.id,
        )
        assigned = Workplace(
            name="Employee point",
            address="Address 2",
            workplace_type="other",
            work_start_time=time(8, 0),
            work_end_time=time(20, 0),
            owner_id=other.id,
        )
        db.add_all([owned, assigned])
        await db.flush()

        db.add(
            Employee(
                user_id=owner.id,
                workplace_id=assigned.id,
                role="employee",
                is_active=True,
            )
        )
        await db.commit()

        workplaces = await list_my_workplaces(owner, db)

    assert {workplace.id for workplace in workplaces.workplaces} == {owned.id, assigned.id}


def test_agent_workplace_schemas_validate_request_and_orm_summary():
    request = ListMyWorkplacesRequest(query="  Какие у меня рабочие точки?  ")
    assert request.query == "Какие у меня рабочие точки?"

    response = ListMyWorkplacesResponse.model_validate(
        {
            "workplaces": [
                {
                    "id": 1,
                    "name": "ПВЗ",
                    "address": "ул. Мира, 1",
                    "description": "Основная точка",
                    "workplace_type": "ozon",
                    "work_start_time": time(9, 0),
                    "work_end_time": time(21, 0),
                }
            ]
        }
    )

    assert response.count == 1
    assert response.workplaces[0].work_start_time == "09:00"
    assert response.workplaces[0].work_end_time == "21:00"


def test_agent_workplace_request_rejects_empty_query():
    with pytest.raises(ValueError):
        ListMyWorkplacesRequest(query="   ")


@pytest.mark.asyncio
async def test_agent_service_executes_list_workplaces_tool():
    first_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
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
                    "content": "У вас есть две рабочие точки.",
                }
            }
        ]
    }
    tool_result = ListMyWorkplacesResponse(
        workplaces=[
            {
                "id": 1,
                "name": "ПВЗ",
                "address": "ул. Мира, 1",
                "description": None,
                "workplace_type": "ozon",
                "work_start_time": "09:00",
                "work_end_time": "21:00",
            }
        ]
    )
    user = User(id=1, email="agent@example.com", hashed_password="hash")

    with (
        patch(
            "app.agent.agent_service.get_gigachat_token",
            new=AsyncMock(return_value="token"),
        ),
        patch(
            "app.agent.agent_service.send_gigachat_request",
            new=AsyncMock(side_effect=[first_response, final_response]),
        ) as send,
        patch(
            "app.agent.agent_service.list_my_workplaces",
            new=AsyncMock(return_value=tool_result),
        ),
    ):
        answer = await AgentService(db=object(), user=user).process(
            "Какие у меня рабочие точки?"
        )

    assert isinstance(answer, AgentAnswer)
    assert answer.answer == "У вас есть две рабочие точки."
    assert send.await_count == 2
    assert send.await_args_list[0].kwargs["tools"][0]["function"]["name"] == (
        "list_my_workplaces"
    )
