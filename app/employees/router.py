from fastapi import APIRouter, Depends, HTTPException, status, Query

from sqlalchemy.ext.asyncio import AsyncSession

from typing import Annotated

from app.users.model import User as UserModel


from app.employees.model import Employee as EmployeeModel
from app.employees.schemas import (
    EmployeeResponse, 
    EmployeeCreate, 
    EmployeeUpdate
)
from app.employees.services import EmployeeServices

from app.core.security import (
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

router = APIRouter(
    prefix="/employees", 
    tags=["Employees"]
)


@router.post(
    "/",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_employee(
    employee_data: EmployeeCreate,
    workplace_id: Annotated[int, Query(
            description="ID рабочего пространства"
    )],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin),
) -> EmployeeModel:
    """
    Создание нового пользователя в системе или восстановление существующего.
    Возвращает созданного юзера.
    Создание доступно только владельцу или администратору рабочего пространства.
    """
    try:
        employee_services = EmployeeServices(db)
        
        return await employee_services.create_employee(employee_data, workplace_id)
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
    workplace_id: Annotated[int, Query(
        description="ID рабочего пространства"
    )],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_employees),
) -> EmployeeModel:
    """
    Получение информации о пользователе по его ID.
    Доступно только владельцу или работнику рабочего пространства.
    """
    try: 
        services = EmployeeServices(db)

        return await services.get_employee_by_id(employee_id, workplace_id)
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
    workplace_id: Annotated[int, Query(
        description="ID рабочего пространства"
    )],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin),
) -> dict:
    """
    Удаляет сотрудника из системы.
    Доступно только владельцу или администратору рабочего пространства.
    """
    try:
        services = EmployeeServices(db)
        await services.delete_employee(employee_id, workplace_id)

        return {"message": "Employee deactivated successfully"}
    except EmployeeNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg,
        )


@router.put(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
async def update_employee(
    employee_id: int,
    employee_data: EmployeeUpdate,
    workplace_id: Annotated[int, Query(
        description="ID рабочего пространства"
    )],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin),
) -> EmployeeModel:
    """
    Обновляет информацию о сотруднике.
    Доступно только владельцу или администратору рабочего пространства.
    """
    try:
        services = EmployeeServices(db)
        return await services.update_employee(employee_id, employee_data, workplace_id)
    except EmployeeNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg,
        )
