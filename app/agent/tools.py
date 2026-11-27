import re
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.schemas import (
    AgentShiftItem,
    EmployeeLookupRequest,
    EmployeeLookupResponse,
    EmployeeLookupWorkplace,
    EmployeeShiftsRequest,
    EmployeeShiftsResponse,
    WorkplaceShiftsRequest,
    WorkplaceShiftsResponse,
)
from app.users.model import User
from app.employees.model import Employee
from app.workplaces.model import Workplace
from app.workplaces.services import WorkplaceServices
from app.agent.schemas import ListMyWorkplacesResponse, ShiftScheduleRequest
from app.agent.authorization import can_manage_shifts, get_workplace_access
from app.shifts.model import Shift
from app.shifts.services import ShiftServices


async def list_my_workplaces(
    user: User,
    db: AsyncSession,
) -> ListMyWorkplacesResponse:
    """
    Возвращает активные рабочие точки пользователя:
    созданные им или в которых он активный сотрудник.
    """
    workplaces: list[Workplace] = await WorkplaceServices(db).get_all_by_user(user)
    return ListMyWorkplacesResponse.model_validate(
        {"workplaces": workplaces}
    )


class EmployeeLookupToolError(ValueError):
    """Ошибка доступа при поиске сотрудника через инструмент агента."""


async def lookup_employee(
    request: EmployeeLookupRequest,
    user: User,
    db: AsyncSession,
) -> EmployeeLookupResponse:
    """Ищет активного сотрудника только в точке, где пользователь управляет сменами.

    Если точка не указана и управляемая точка одна, она выбирается автоматически.
    При нескольких точках возвращаются варианты для уточнения, без поиска по ним.
    """
    available_workplaces = await WorkplaceServices(db).get_all_by_user(user)
    manageable_workplaces = []
    for workplace in available_workplaces:
        role = await get_workplace_access(db, user, workplace.id)
        if can_manage_shifts(role):
            manageable_workplaces.append(workplace)

    if not manageable_workplaces:
        raise EmployeeLookupToolError(
            "Нет рабочей точки, где вы можете управлять графиком смен."
        )

    if request.workplace_id is not None:
        selected = next(
            (place for place in manageable_workplaces if place.id == request.workplace_id),
            None,
        )
        if selected is None:
            raise EmployeeLookupToolError(
                "Рабочая точка не найдена или у вас нет прав администратора."
            )
    elif request.workplace_name is not None:
        matching = [
            place
            for place in manageable_workplaces
            if place.name.casefold() == request.workplace_name.strip().casefold()
        ]
        if len(matching) != 1:
            choices = matching or manageable_workplaces
            return EmployeeLookupResponse(
                status="workplace_required",
                workplaces=choices,
            )
        selected = matching[0]
    elif len(manageable_workplaces) == 1:
        selected = manageable_workplaces[0]
    elif len(manageable_workplaces) > 1:
        return EmployeeLookupResponse(
            status="workplace_required",
            workplaces=manageable_workplaces,
        )

    statement = (
        select(Employee)
        .join(Employee.user)
        .options(selectinload(Employee.user))
        .where(
            Employee.workplace_id == selected.id,
            Employee.is_active,
            User.is_active,
        )
    )
    if request.full_name is not None:
        query = request.full_name.strip()
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        full_name_surname_first = (
            User.second_name
            + " "
            + User.first_name
            + " "
            + func.coalesce(User.third_name, "")
        )
        full_name_given_first = (
            User.first_name
            + " "
            + User.second_name
            + " "
            + func.coalesce(User.third_name, "")
        )
        statement = statement.where(
            or_(
                User.first_name.ilike(pattern, escape="\\"),
                User.second_name.ilike(pattern, escape="\\"),
                User.third_name.ilike(pattern, escape="\\"),
                full_name_surname_first.ilike(pattern, escape="\\"),
                full_name_given_first.ilike(pattern, escape="\\"),
            )
        )
    else:
        digits = re.sub(r"\D", "", request.phone or "")
        if len(digits) == 10:
            digits = f"7{digits}"
        if len(digits) != 11 or digits[0] not in {"7", "8"}:
            raise EmployeeLookupToolError(
                "Укажите телефон в формате +7XXXXXXXXXX или 8XXXXXXXXXX."
            )
        tail = digits[-10:]
        phone_values = {f"+7{tail}", f"8{tail}"}
        statement = statement.where(User.phone.in_(phone_values))

    result = await db.scalars(statement.order_by(Employee.id))
    employees = list(result.all())
    return EmployeeLookupResponse(
        status="matches" if employees else "not_found",
        workplace=selected,
        employees=[
            {
                "employee_id": employee.id,
                "full_name": " ".join(
                    part
                    for part in (
                        employee.user.second_name,
                        employee.user.first_name,
                        employee.user.third_name,
                    )
                    if part
                ),
            }
            for employee in employees
        ],
    )


class ShiftScheduleToolError(ValueError):
    """Ошибка доступа при подготовке графика смен через инструмент агента."""


class ShiftViewToolError(ValueError):
    """Ошибка доступа к просмотру смен через инструмент агента."""


def _shift_period(
    date_from: date | None,
    date_to: date | None,
    default_days: int,
) -> tuple[date, date]:
    start = date_from or date.today()
    end = date_to or start + timedelta(days=default_days - 1)
    return start, end


async def _get_shift_items(
    db: AsyncSession,
    workplace_id: int,
    date_from: date,
    date_to: date,
    employee_id: int | None = None,
) -> list[AgentShiftItem]:
    statement = (
        select(
            Shift,
            User.first_name,
            User.second_name,
            User.third_name,
        )
        .join(Employee, Employee.id == Shift.employee_id)
        .join(User, User.id == Employee.user_id)
        .where(
            Shift.workplace_id == workplace_id,
            Shift.date >= date_from,
            Shift.date <= date_to,
            Shift.is_active,
        )
        .order_by(Shift.date, Shift.start_time, Employee.id)
    )
    if employee_id is not None:
        statement = statement.where(Shift.employee_id == employee_id)

    rows = (await db.execute(statement)).all()
    return [
        AgentShiftItem(
            id=shift.id,
            workplace_id=shift.workplace_id,
            employee_id=shift.employee_id,
            employee_name=" ".join(
                part for part in (second_name, first_name, third_name) if part
            ),
            date=shift.date,
            start_time=shift.start_time.strftime("%H:%M"),
            end_time=shift.end_time.strftime("%H:%M"),
            status=shift.status,
            notes=shift.notes,
        )
        for shift, first_name, second_name, third_name in rows
    ]


async def get_employee_shifts(
    request: EmployeeShiftsRequest,
    user: User,
    db: AsyncSession,
) -> EmployeeShiftsResponse:
    """Показывает свои смены либо смены сотрудника, которым можно управлять."""
    date_from, date_to = _shift_period(
        request.date_from,
        request.date_to,
        default_days=30,
    )

    statement = (
        select(Employee, Workplace.id, Workplace.name, User.first_name, User.second_name, User.third_name)
        .join(Workplace, Workplace.id == Employee.workplace_id)
        .join(User, User.id == Employee.user_id)
        .where(
            Employee.is_active,
            Workplace.is_active,
        )
    )
    if request.employee_id is not None:
        statement = statement.where(Employee.id == request.employee_id)
    else:
        statement = statement.where(Employee.user_id == user.id)
    if request.workplace_id is not None:
        statement = statement.where(Employee.workplace_id == request.workplace_id)

    rows = (await db.execute(statement)).all()
    if not rows:
        if request.employee_id is not None:
            raise ShiftViewToolError(
                "Сотрудник не найден в активной рабочей точке."
            )
        return EmployeeShiftsResponse(
            status="not_found",
            workplace=None,
            date_from=date_from,
            date_to=date_to,
        )

    if len(rows) > 1:
        workplaces = {
            workplace_id: EmployeeLookupWorkplace(id=workplace_id, name=name)
            for _, workplace_id, name, *_ in rows
        }
        return EmployeeShiftsResponse(
            status="workplace_required",
            workplaces=list(workplaces.values()),
            date_from=date_from,
            date_to=date_to,
        )

    employee, workplace_id, workplace_name, first_name, second_name, third_name = rows[0]
    if employee.user_id != user.id:
        role = await get_workplace_access(db, user, workplace_id)
        if not can_manage_shifts(role):
            raise ShiftViewToolError(
                "Просматривать смены другого сотрудника могут только владелец "
                "или администратор его рабочей точки."
            )

    employee_name = " ".join(
        part for part in (second_name, first_name, third_name) if part
    )
    shifts = await _get_shift_items(
        db,
        workplace_id,
        date_from,
        date_to,
        employee_id=employee.id,
    )
    return EmployeeShiftsResponse(
        status="shifts" if shifts else "no_shifts",
        employee_id=employee.id,
        employee_name=employee_name,
        workplace={"id": workplace_id, "name": workplace_name},
        date_from=date_from,
        date_to=date_to,
        shifts=shifts,
    )


async def get_workplace_shifts(
    request: WorkplaceShiftsRequest,
    user: User,
    db: AsyncSession,
) -> WorkplaceShiftsResponse:
    """Показывает календарь всех сотрудников точки только менеджерам смен."""
    date_from, date_to = _shift_period(
        request.date_from,
        request.date_to,
        default_days=30,
    )
    available_workplaces = await WorkplaceServices(db).get_all_by_user(user)
    manageable = []
    for workplace in available_workplaces:
        role = await get_workplace_access(db, user, workplace.id)
        if can_manage_shifts(role):
            manageable.append(workplace)

    if not manageable:
        raise ShiftViewToolError(
            "Просматривать смены всей рабочей точки могут только её владелец "
            "или администратор."
        )

    selected = None
    if request.workplace_id is not None:
        selected = next(
            (place for place in manageable if place.id == request.workplace_id),
            None,
        )
        if selected is None:
            raise ShiftViewToolError(
                "Рабочая точка не найдена или у вас нет прав администратора."
            )
    elif request.workplace_name is not None:
        matches = [
            place
            for place in manageable
            if place.name.casefold() == request.workplace_name.strip().casefold()
        ]
        if len(matches) == 1:
            selected = matches[0]
        else:
            return WorkplaceShiftsResponse(
                status="workplace_required",
                workplaces=[
                    EmployeeLookupWorkplace(id=place.id, name=place.name)
                    for place in manageable
                ],
                date_from=date_from,
                date_to=date_to,
            )
    elif len(manageable) == 1:
        selected = manageable[0]
    else:
        return WorkplaceShiftsResponse(
            status="workplace_required",
            workplaces=[
                EmployeeLookupWorkplace(id=place.id, name=place.name)
                for place in manageable
            ],
            date_from=date_from,
            date_to=date_to,
        )

    shifts = await _get_shift_items(
        db,
        selected.id,
        date_from,
        date_to,
    )
    return WorkplaceShiftsResponse(
        status="shifts" if shifts else "no_shifts",
        workplace={"id": selected.id, "name": selected.name},
        date_from=date_from,
        date_to=date_to,
        shifts=shifts,
    )


async def prepare_shift_schedule(
    request: ShiftScheduleRequest,
    user: User,
    db: AsyncSession,
) -> dict:
    """Проверяет права и готовит предварительный план смен без записи в базу.

    Создавать график могут только владелец или администратор указанной точки.
    Расчёт дат и времени делегируется ``ShiftServices``; результат возвращается
    вызывающему коду для показа пользователю и последующего подтверждения.

    Args:
        request: Рабочая точка, сотрудник, цикл графика, период и необязательные
            переопределения времени.
        user: Аутентифицированный пользователь, запрашивающий план.
        db: Сессия базы данных для проверки доступа и подготовки плана.

    Returns:
        Словарь с данными рабочей точки и сотрудника, сменами для создания,
        пропускаемыми датами и человекочитаемым описанием плана.

    Raises:
        ShiftScheduleToolError: Если пользователь не владелец или администратор
            рабочей точки.
        EmployeeNotFoundException: Если сотрудник не найден, неактивен или
            относится к другой рабочей точке.
        WorkplaceNotFoundException: Если рабочая точка отсутствует или неактивна.
        ValidationError: Если параметры графика или времени не проходят проверку.
    """
    role = await get_workplace_access(db, user, request.workplace_id)
    if not can_manage_shifts(role):
        raise ShiftScheduleToolError(
            "Составлять смены могут только владелец или администратор рабочей точки."
        )

    return await ShiftServices(db).prepare_schedule(
        workplace_id=request.workplace_id,
        employee_id=request.employee_id,
        schedule=request.schedule,
        period=request.period,
        start_time=request.start_time,
        end_time=request.end_time,
    )