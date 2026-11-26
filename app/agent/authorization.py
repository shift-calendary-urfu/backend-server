from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.employees.model import Employee
from app.workplaces.model import Workplace
from app.users.model import User


def _admin_or_owner_role(workplace: Workplace, user: User, employee: Employee | None) -> str:
    """Определяет роль пользователя для активной рабочей точки."""
    if workplace.owner_id == user.id:
        return "owner"
    if employee is not None and employee.role == "admin":
        return "admin"
    if employee is not None:
        return employee.role
    return "none"


async def get_workplace_access(
    db: AsyncSession,
    user: User,
    workplace_id: int,
) -> str:
    """Возвращает роль пользователя в активной точке или ``none`` без доступа."""
    workplace = await db.scalar(
        select(Workplace).where(
            Workplace.id == workplace_id,
            Workplace.is_active,
        )
    )
    if workplace is None:
        return "none"

    employee = await db.scalar(
        select(Employee).where(
            Employee.workplace_id == workplace_id,
            Employee.user_id == user.id,
            Employee.is_active,
        )
    )
    return _admin_or_owner_role(workplace, user, employee)


def can_mutate_workplace(role: str, action: str) -> bool:
    if action in {"update_workplace", "delete_workplace"}:
        return role == "owner"
    if action == "create_employee":
        return role in {"owner", "admin"}
    if action == "create_workplace":
        return True
    return False


def can_manage_shifts(role: str) -> bool:
    """Возвращает, может ли роль составлять смены в рабочей точке.

    Создание расписания разрешено владельцу и администратору точки; обычный
    сотрудник может просматривать смены, но не планировать и создавать их.
    """
    return role in {"owner", "admin"}