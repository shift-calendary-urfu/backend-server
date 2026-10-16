from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.users.model import User as UserModel

from app.workplaces.model import Workplace as WorkplaceModel

from app.employees.model import Employee as EmployeeModel
from app.employees.schemas import EmployeeResponse, EmployeeCreate
from app.employees.services import EmployeeServices

from app.core.security import (
    get_current_user,
    get_owner_or_admin,
    get_owner_or_employees,
    check_workplace_access
)
from app.core.database import get_db

from app.exceptions import (
    WorkplaceNotFoundException,
    UserNotFoundException,
    EmployeeAlreadyInWorkPlaceExceprion,
    EmployeeNotFoundException
)

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.post(
    "/",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_employee(
    employee_data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin),
):
    """
    Создание нового пользователя в системе.
    Возвращает созданного юзера.
    Создание доступно только владельцу или администратору рабочего пространства.
    """
    try:
        employee_services = EmployeeServices(db)
        return await employee_services.create_employee(employee_data)
    except (
        WorkplaceNotFoundException, 
        UserNotFoundException, 
    ) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg,
        )
    except EmployeeAlreadyInWorkPlaceExceprion as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.msg,
        )


@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """
    Получение информации о пользователе по его ID.
    Доступно только владельцу или работнику рабочего пространства.
    """
    try: 
        services_emplpoyee = EmployeeServices(db)
        employee = await services_emplpoyee.get_employee_by_id(employee_id)
        await check_workplace_access(
            employee.workplace_id, current_user, db
        )
        return employee
    except EmployeeNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg,
        )


@router.delete(
    "/{employee_id}",
    response_model=dict,
)
async def delete_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_owner_or_admin),
):
    # 1. Ищем сотрудника
    employee = await db.scalar(
        select(EmployeeModel).where(EmployeeModel.id == employee_id)
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # 2. Проверяем, является ли текущий пользователь владельцем
    owner_id = await db.scalar(
        select(WorkplaceModel.owner_id).where(
            WorkplaceModel.id == employee.workplace_id
        )
    )

    # 3. Если не владелец, проверяем роль администратора
    if owner_id != current_user.id:
        is_admin = await db.scalar(
            select(EmployeeModel.id).where(
                EmployeeModel.workplace_id == employee.workplace_id,
                EmployeeModel.user_id == current_user.id,
                EmployeeModel.role == "admin",
                EmployeeModel.is_active.is_(True),
            )
        )

        if is_admin is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be the owner or admin of this workplace",
            )

    # 4. Деактивируем сотрудника
    employee.is_active = False

    # 5. Сохраняем изменения
    await db.commit()

    return {"message": "Employee deactivated successfully"}
