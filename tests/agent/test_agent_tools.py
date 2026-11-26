import json
from datetime import date, time, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.tools import (
    EmployeeLookupToolError,
    ShiftViewToolError,
    get_employee_shifts,
    get_workplace_shifts,
    list_my_workplaces,
    lookup_employee,
)
from app.agent.schemas import (
    AgentAnswer,
    EmployeeLookupRequest,
    EmployeeLookupResponse,
    EmployeeShiftsRequest,
    ListMyWorkplacesRequest,
    ListMyWorkplacesResponse,
    ShiftScheduleRequest,
    WorkplaceShiftsRequest,
)
from app.agent.agent_service import AgentService
from app.employees.model import Employee
from app.shifts.model import Shift
from app.shifts.services import build_schedule_dates
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


@pytest.mark.asyncio
async def test_lookup_employee_by_name_returns_ids_and_preserves_ambiguity(session_factory):
    async with session_factory() as db:
        owner = User(
            email="lookup-owner@example.com",
            hashed_password="hash",
            first_name="Owner",
            second_name="Agent",
            phone="+79990000011",
        )
        first_user = User(
            email="lookup-first@example.com",
            hashed_password="hash",
            first_name="Иван",
            second_name="Петров",
            third_name="Иванович",
            phone="+79990000012",
        )
        second_user = User(
            email="lookup-second@example.com",
            hashed_password="hash",
            first_name="Пётр",
            second_name="Петров",
            phone="+79990000013",
        )
        db.add_all([owner, first_user, second_user])
        await db.flush()
        workplace = Workplace(
            name="Lookup point",
            address="Lookup address",
            workplace_type="other",
            work_start_time=time(9, 0),
            work_end_time=time(21, 0),
            owner_id=owner.id,
        )
        db.add(workplace)
        await db.flush()
        first_employee = Employee(
            user_id=first_user.id,
            workplace_id=workplace.id,
            role="employee",
            is_active=True,
        )
        second_employee = Employee(
            user_id=second_user.id,
            workplace_id=workplace.id,
            role="employee",
            is_active=True,
        )
        db.add_all([first_employee, second_employee])
        await db.commit()

        result = await lookup_employee(
            EmployeeLookupRequest(full_name="Петров"),
            owner,
            db,
        )

    assert result.status == "matches"
    assert result.workplace.id == workplace.id
    assert {match.employee_id for match in result.employees} == {
        first_employee.id,
        second_employee.id,
    }


@pytest.mark.asyncio
async def test_lookup_employee_requires_workplace_when_admin_has_multiple(session_factory):
    async with session_factory() as db:
        owner = User(
            email="lookup-multi-owner@example.com",
            hashed_password="hash",
            first_name="Owner",
            second_name="Agent",
            phone="+79990000021",
        )
        db.add(owner)
        await db.flush()
        workplaces = [
            Workplace(
                name=f"Lookup point {index}",
                address=f"Lookup address {index}",
                workplace_type="other",
                work_start_time=time(9, 0),
                work_end_time=time(21, 0),
                owner_id=owner.id,
            )
            for index in (1, 2)
        ]
        db.add_all(workplaces)
        await db.commit()

        result = await lookup_employee(
            EmployeeLookupRequest(full_name="Петров"),
            owner,
            db,
        )

    assert result.status == "workplace_required"
    assert {place.id for place in result.workplaces} == {
        place.id for place in workplaces
    }
    assert result.employees == []


@pytest.mark.asyncio
async def test_lookup_employee_by_phone_accepts_eight_prefix(session_factory):
    async with session_factory() as db:
        owner = User(
            email="lookup-phone-owner@example.com",
            hashed_password="hash",
            first_name="Owner",
            second_name="Agent",
            phone="+79990000041",
        )
        employee_user = User(
            email="lookup-phone-employee@example.com",
            hashed_password="hash",
            first_name="Иван",
            second_name="Петров",
            phone="+79990000042",
        )
        db.add_all([owner, employee_user])
        await db.flush()
        workplace = Workplace(
            name="Phone lookup point",
            address="Phone lookup address",
            workplace_type="other",
            work_start_time=time(9, 0),
            work_end_time=time(21, 0),
            owner_id=owner.id,
        )
        db.add(workplace)
        await db.flush()
        employee = Employee(
            user_id=employee_user.id,
            workplace_id=workplace.id,
            role="employee",
            is_active=True,
        )
        db.add(employee)
        await db.commit()

        result = await lookup_employee(
            EmployeeLookupRequest(phone="8 (999) 000-00-42"),
            owner,
            db,
        )

    assert result.status == "matches"
    assert [match.employee_id for match in result.employees] == [employee.id]


@pytest.mark.asyncio
async def test_lookup_employee_rejects_non_admin_users(session_factory):
    async with session_factory() as db:
        owner = User(
            email="lookup-owner-role@example.com",
            hashed_password="hash",
            first_name="Owner",
            second_name="Agent",
            phone="+79990000031",
        )
        employee_user = User(
            email="lookup-employee-role@example.com",
            hashed_password="hash",
            first_name="Employee",
            second_name="Agent",
            phone="+79990000032",
        )
        db.add_all([owner, employee_user])
        await db.flush()
        workplace = Workplace(
            name="Lookup restricted point",
            address="Lookup restricted address",
            workplace_type="other",
            work_start_time=time(9, 0),
            work_end_time=time(21, 0),
            owner_id=owner.id,
        )
        db.add(workplace)
        await db.flush()
        db.add(
            Employee(
                user_id=employee_user.id,
                workplace_id=workplace.id,
                role="employee",
                is_active=True,
            )
        )
        await db.commit()

        with pytest.raises(EmployeeLookupToolError):
            await lookup_employee(
                EmployeeLookupRequest(
                    full_name="Петров",
                    workplace_id=workplace.id,
                ),
                employee_user,
                db,
            )


@pytest.mark.asyncio
async def test_employee_can_view_own_shifts_without_employee_id(session_factory):
    async with session_factory() as db:
        owner = User(
            email="self-shifts-owner@example.com",
            hashed_password="hash",
            first_name="Owner",
            second_name="Agent",
            phone="+79990000101",
        )
        employee_user = User(
            email="self-shifts-employee@example.com",
            hashed_password="hash",
            first_name="Иван",
            second_name="Петров",
            phone="+79990000102",
        )
        db.add_all([owner, employee_user])
        await db.flush()
        workplace = Workplace(
            name="Self shifts point",
            address="Address",
            workplace_type="other",
            work_start_time=time(9, 0),
            work_end_time=time(21, 0),
            owner_id=owner.id,
        )
        db.add(workplace)
        await db.flush()
        employee = Employee(
            user_id=employee_user.id,
            workplace_id=workplace.id,
            role="employee",
            is_active=True,
        )
        db.add(employee)
        await db.flush()
        shift = Shift(
            employee_id=employee.id,
            workplace_id=workplace.id,
            date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        db.add(shift)
        await db.commit()

        result = await get_employee_shifts(
            EmployeeShiftsRequest(),
            employee_user,
            db,
        )

    assert result.status == "shifts"
    assert result.employee_id == employee.id
    assert result.workplace.id == workplace.id
    assert [item.id for item in result.shifts] == [shift.id]
    assert result.shifts[0].employee_name == "Петров Иван"


@pytest.mark.asyncio
async def test_owner_can_view_all_workplace_shifts_and_employee_cannot(session_factory):
    async with session_factory() as db:
        owner = User(
            email="workplace-shifts-owner@example.com",
            hashed_password="hash",
            first_name="Owner",
            second_name="Agent",
            phone="+79990000111",
        )
        employee_user = User(
            email="workplace-shifts-employee@example.com",
            hashed_password="hash",
            first_name="Иван",
            second_name="Петров",
            phone="+79990000112",
        )
        other_user = User(
            email="workplace-shifts-other@example.com",
            hashed_password="hash",
            first_name="Пётр",
            second_name="Иванов",
            phone="+79990000113",
        )
        db.add_all([owner, employee_user, other_user])
        await db.flush()
        workplace = Workplace(
            name="All shifts point",
            address="Address",
            workplace_type="other",
            work_start_time=time(9, 0),
            work_end_time=time(21, 0),
            owner_id=owner.id,
        )
        db.add(workplace)
        await db.flush()
        employee = Employee(
            user_id=employee_user.id,
            workplace_id=workplace.id,
            role="employee",
            is_active=True,
        )
        other_employee = Employee(
            user_id=other_user.id,
            workplace_id=workplace.id,
            role="employee",
            is_active=True,
        )
        db.add_all([employee, other_employee])
        await db.flush()
        shift = Shift(
            employee_id=employee.id,
            workplace_id=workplace.id,
            date=date.today(),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        db.add(shift)
        await db.commit()

        result = await get_workplace_shifts(
            WorkplaceShiftsRequest(),
            owner,
            db,
        )
        with pytest.raises(ShiftViewToolError):
            await get_workplace_shifts(
                WorkplaceShiftsRequest(workplace_id=workplace.id),
                employee_user,
                db,
            )
        with pytest.raises(ShiftViewToolError):
            await get_employee_shifts(
                EmployeeShiftsRequest(employee_id=other_employee.id),
                employee_user,
                db,
            )

    assert result.status == "shifts"
    assert result.workplace.id == workplace.id
    assert [item.id for item in result.shifts] == [shift.id]


def test_shift_view_requests_enforce_inclusive_period_limits():
    start = date(2026, 1, 1)
    assert EmployeeShiftsRequest(
        date_from=start,
        date_to=start + timedelta(days=89),
    )
    assert WorkplaceShiftsRequest(
        date_from=start,
        date_to=start + timedelta(days=29),
    )

    with pytest.raises(ValueError):
        EmployeeShiftsRequest(
            date_from=start,
            date_to=start + timedelta(days=90),
        )
    with pytest.raises(ValueError):
        WorkplaceShiftsRequest(
            date_from=start,
            date_to=start + timedelta(days=30),
        )


@pytest.mark.asyncio
async def test_agent_looks_up_named_employee_before_preparing_schedule(session_factory):
    async with session_factory() as db:
        owner = User(
            email="lookup-flow-owner@example.com",
            hashed_password="hash",
            first_name="Owner",
            second_name="Agent",
            phone="+79990000051",
        )
        employee_user = User(
            email="lookup-flow-employee@example.com",
            hashed_password="hash",
            first_name="Иван",
            second_name="Петров",
            phone="+79990000052",
        )
        db.add_all([owner, employee_user])
        await db.flush()
        workplace = Workplace(
            name="Schedule lookup point",
            address="Schedule lookup address",
            workplace_type="other",
            work_start_time=time(9, 0),
            work_end_time=time(21, 0),
            owner_id=owner.id,
        )
        db.add(workplace)
        await db.flush()
        employee = Employee(
            user_id=employee_user.id,
            workplace_id=workplace.id,
            role="employee",
            is_active=True,
        )
        db.add(employee)
        await db.commit()

        lookup_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-lookup",
                                "type": "function",
                                "function": {
                                    "name": "lookup_employee_by_full_name",
                                    "arguments": '{"full_name":"Петров"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
        schedule_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-schedule-after-lookup",
                                "type": "function",
                                "function": {
                                    "name": "create_shift_schedule",
                                    "arguments": (
                                        '{"workplace_id":'
                                        f'{workplace.id},"employee_id":{employee.id},'
                                        '"schedule":"2/2","period":30}'
                                    ),
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
                        "content": "Подготовил график смен.",
                    }
                }
            ]
        }

        with (
            patch(
                "app.agent.agent_service.get_gigachat_token",
                new=AsyncMock(return_value="token"),
            ),
            patch(
                "app.agent.agent_service.send_gigachat_request",
                new=AsyncMock(
                    side_effect=[
                        lookup_response,
                        schedule_response,
                        final_response,
                    ]
                ),
            ) as send_request,
        ):
            answer = await AgentService(db=db, user=owner).process(
                "Составь график 2/2 на месяц для Петрова"
            )

    assert answer.confirmation_required is True
    assert answer.confirmation_id
    assert send_request.await_count == 3
    first_tool_names = {
        tool["function"]["name"]
        for tool in send_request.await_args_list[0].kwargs["tools"]
    }
    assert "lookup_employee_by_full_name" in first_tool_names
    assert "lookup_employee_by_phone" in first_tool_names
    lookup_message = next(
        message
        for message in send_request.await_args_list[1].args[1]
        if message.get("tool_call_id") == "call-lookup"
    )
    lookup_result = json.loads(lookup_message["content"])
    assert lookup_result["status"] == "matches", lookup_result
    assert lookup_result["employees"] == [
        {"employee_id": employee.id, "full_name": "Петров Иван"}
    ]


@pytest.mark.asyncio
async def test_agent_looks_up_employee_before_showing_their_shifts(session_factory):
    async with session_factory() as db:
        owner = User(
            email="view-flow-owner@example.com",
            hashed_password="hash",
            first_name="Owner",
            second_name="Agent",
            phone="+79990000201",
        )
        employee_user = User(
            email="view-flow-employee@example.com",
            hashed_password="hash",
            first_name="Иван",
            second_name="Петров",
            phone="+79990000202",
        )
        db.add_all([owner, employee_user])
        await db.flush()
        workplace = Workplace(
            name="View flow point",
            address="Address",
            workplace_type="other",
            work_start_time=time(9, 0),
            work_end_time=time(21, 0),
            owner_id=owner.id,
        )
        db.add(workplace)
        await db.flush()
        employee = Employee(
            user_id=employee_user.id,
            workplace_id=workplace.id,
            role="employee",
            is_active=True,
        )
        db.add(employee)
        await db.flush()
        shift = Shift(
            employee_id=employee.id,
            workplace_id=workplace.id,
            date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        db.add(shift)
        await db.commit()

        lookup_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-view-lookup",
                                "type": "function",
                                "function": {
                                    "name": "lookup_employee_by_full_name",
                                    "arguments": '{"full_name":"Петров"}',
                                },
                            }
                        ],
                    }
                }
            ]
        }
        view_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-view-shifts",
                                "type": "function",
                                "function": {
                                    "name": "get_employee_shifts",
                                    "arguments": (
                                        '{"employee_id":'
                                        f'{employee.id},"workplace_id":{workplace.id}'
                                        '}'
                                    ),
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
                        "content": "У Петрова есть смена завтра.",
                    }
                }
            ]
        }

        with (
            patch(
                "app.agent.agent_service.get_gigachat_token",
                new=AsyncMock(return_value="token"),
            ),
            patch(
                "app.agent.agent_service.send_gigachat_request",
                new=AsyncMock(
                    side_effect=[
                        lookup_response,
                        view_response,
                        final_response,
                    ]
                ),
            ) as send_request,
        ):
            answer = await AgentService(db=db, user=owner).process(
                "Покажи смены Петрова на ближайшие дни"
            )

    assert answer.answer == "У Петрова есть смена завтра."
    follow_up_tools = {
        tool["function"]["name"]
        for tool in send_request.await_args_list[1].kwargs["tools"]
    }
    assert "get_employee_shifts" in follow_up_tools
    result_message = next(
        message
        for message in send_request.await_args_list[2].args[1]
        if message.get("tool_call_id") == "call-view-shifts"
    )
    result = json.loads(result_message["content"])
    assert result["status"] == "shifts"
    assert result["shifts"][0]["id"] == shift.id


@pytest.mark.asyncio
async def test_agent_refuses_schedule_when_name_lookup_is_ambiguous():
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-ambiguous-lookup",
                                "function": {
                                    "name": "lookup_employee_by_full_name",
                                    "arguments": '{"full_name":"Петров"}',
                                },
                            },
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-ambiguous-schedule",
                                "function": {
                                    "name": "create_shift_schedule",
                                    "arguments": (
                                        '{"workplace_id":1,"employee_id":10,'
                                        '"schedule":"2/2","period":30}'
                                    ),
                                },
                            },
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Уточните, какого сотрудника вы имеете в виду.",
                    }
                }
            ]
        },
    ]
    ambiguous_result = EmployeeLookupResponse(
        status="matches",
        workplace={"id": 1, "name": "Точка"},
        employees=[
            {"employee_id": 10, "full_name": "Петров Иван"},
            {"employee_id": 11, "full_name": "Петров Пётр"},
        ],
    )

    with (
        patch(
            "app.agent.agent_service.get_gigachat_token",
            new=AsyncMock(return_value="token"),
        ),
        patch(
            "app.agent.agent_service.send_gigachat_request",
            new=AsyncMock(side_effect=responses),
        ) as send_request,
        patch(
            "app.agent.agent_service.lookup_employee",
            new=AsyncMock(return_value=ambiguous_result),
        ),
        patch(
            "app.agent.agent_service.prepare_shift_schedule"
        ) as prepare_schedule,
    ):
        answer = await AgentService(
            db=object(),
            user=User(id=1, email="agent@example.com", hashed_password="hash"),
        ).process("Составь график для Петрова")

    assert answer.confirmation_required is False
    prepare_schedule.assert_not_called()
    schedule_result_message = next(
        message
        for message in send_request.await_args_list[2].args[1]
        if message.get("tool_call_id") == "call-ambiguous-schedule"
    )
    schedule_result = json.loads(schedule_result_message["content"])
    assert "ровно одного сотрудника" in schedule_result["error"]


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


def test_shift_schedule_dates_follow_cycle_and_fallback_rules():
    start = date(2026, 11, 26)

    dates, schedule_name, schedule_applied = build_schedule_dates("5/2", 10, start)
    assert dates == [
        start + timedelta(days=offset)
        for offset in (0, 1, 2, 3, 4, 7, 8, 9)
    ]
    assert schedule_name == "5/2"
    assert schedule_applied is True

    dates, schedule_name, schedule_applied = build_schedule_dates("2/1", 6, start)
    assert dates == [
        start,
        start + timedelta(days=1),
        start + timedelta(days=3),
        start + timedelta(days=4),
    ]
    assert schedule_applied is True

    dates, schedule_name, schedule_applied = build_schedule_dates("0/2", 30, start)
    assert dates == [start]
    assert schedule_name == "некорректен — одна смена"
    assert schedule_applied is False

    dates, _, schedule_applied = build_schedule_dates("bad", 30, start)
    assert dates == [start]
    assert schedule_applied is False


def test_shift_schedule_request_requires_paired_time_overrides():
    request = ShiftScheduleRequest(
        workplace_id=1,
        employee_id=2,
        period=30,
        schedule="5/2",
    )
    assert request.start_time is None

    with pytest.raises(ValueError):
        ShiftScheduleRequest(
            workplace_id=1,
            employee_id=2,
            period=30,
            start_time="09:00",
        )

    for start_time, end_time in (("09:15", "18:00"), ("18:00", "09:00")):
        with pytest.raises(ValueError):
            ShiftScheduleRequest(
                workplace_id=1,
                employee_id=2,
                period=30,
                start_time=start_time,
                end_time=end_time,
            )

    assert all(
        field.description
        for field in ShiftScheduleRequest.model_fields.values()
    )


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
    tool_names = {
        tool["function"]["name"]
        for tool in send.await_args_list[0].kwargs["tools"]
    }
    assert "get_employee_shifts" in tool_names
    assert "get_workplace_shifts" in tool_names
    system_prompt = send.await_args_list[0].args[1][0]["content"]
    assert "обязательно вызови подходящий tool" in system_prompt
    assert "get_workplace_shifts" in system_prompt
    assert "перечисли все даты смен из результата инструмента" in system_prompt
    assert "график нельзя достоверно определить, не угадывай" in system_prompt
