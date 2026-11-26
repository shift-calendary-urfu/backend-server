from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.model import User
from app.workplaces.model import Workplace
from app.workplaces.services import WorkplaceServices
from app.agent.schemas import ListMyWorkplacesResponse
from app.agent.schemas import ShiftScheduleRequest
from app.agent.authorization import can_manage_shifts, get_workplace_access
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


class ShiftScheduleToolError(ValueError):
    """Ошибка доступа при подготовке графика смен через инструмент агента."""


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