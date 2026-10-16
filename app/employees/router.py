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
    Создание нового пользователя в системе или восстановление существующего.
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
        services = EmployeeServices(db)
        employee = await services.get_employee_by_id(employee_id)
        await get_owner_or_employees(
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
    current_user: UserModel = Depends(get_current_user),
):
    """
    Удаляет сотрудника из системы.
    Доступно только владельцу или администратору рабочего пространства.
    """
    try:
        services = EmployeeServices(db)
        employee = await services.get_employee_by_id(employee_id)

        await get_owner_or_admin(
            workplace_id=employee.workplace_id,
            user=current_user,
            db=db,
        )

        await services.delete_employee(employee_id)

        return {"message": "Employee deactivated successfully"}
    except EmployeeNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg,
        )
