from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.users.model import User as UserModel
from app.workplaces.model import Workplace as WorkplaceModel
from app.employees.model import Employee as EmployeeModel
from app.employees.schemas import EmployeeResponse, EmployeeCreate

from app.core.security import get_current_user, get_owner_or_admin, get_owner_or_employees
from app.core.database import get_db


router = APIRouter(
    prefix="/employees",
    tags=["Employees"]
)


# TODO: 
# 1. При необходимости создать схему.
# 2. Создать сервисный слой (app/employees/services.py) с бизнес-логикой.
# 3. Создать кастомную ошибку в app/exceptions.py, если необходимо.
# 4. При необхоимсти ошибки пробросить через raise и обработать в эндпоинте.
# 5. 

# Создание по номеру ТЕЛЕФОНА (User), то есть проверить существование пользователя.
# Схема создания есть. 
# Создать может только админ или владелец
@router.post(
    "/",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)

async def create_employee(
    employee_data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # 1. Проверяем существование рабочего места
    workplace = await db.scalar(
        select(WorkplaceModel).where(
            WorkplaceModel.id == employee_data.workplace_id
        )
    )

    if workplace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workplace not found",
        )

    # 2. Проверяем, что текущий пользователь —
    # владелец рабочего места или его активный администратор
    is_admin = await db.scalar(
        select(EmployeeModel.id).where(
            EmployeeModel.workplace_id == employee_data.workplace_id,
            EmployeeModel.user_id == current_user.id,
            EmployeeModel.role == "admin",
            EmployeeModel.is_active.is_(True),
        )
    )

    if (
        workplace.owner_id != current_user.id
        and is_admin is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be the owner or admin of this workplace",
        )

    # 3. Ищем пользователя по номеру телефона
    user = await db.scalar(
        select(UserModel).where(
            UserModel.phone == employee_data.phone
        )
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with this phone number not found",
        )

    # 4. Проверяем, не добавлен ли пользователь
    # в это рабочее место ранее
    existing_employee = await db.scalar(
        select(EmployeeModel.id).where(
            EmployeeModel.user_id == user.id,
            EmployeeModel.workplace_id == employee_data.workplace_id,
        )
    )

    if existing_employee is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee already exists in this workplace",
        )

    # 5. Создаём запись сотрудника
    employee = EmployeeModel(
        user_id=user.id,
        workplace_id=employee_data.workplace_id,
        role=employee_data.role,
        position=employee_data.position,
        hire_date=employee_data.hire_date,
        is_active=True,
    )

    db.add(employee)
    await db.commit()
    await db.refresh(employee)

    # 6. Загружаем пользователя для вложенного поля response_model
    await db.refresh(employee, attribute_names=["user"])

    return employee


# Получение сотрудника по ID.
# Схема ответа есть.
# Доступно владельцу или работнику
@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # 1. Ищем сотрудника по ID
    employee = await db.scalar(
        select(EmployeeModel)
        .options(selectinload(EmployeeModel.user))
        .where(EmployeeModel.id == employee_id)
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

    # 3. Если пользователь не владелец, проверяем,
    # является ли он активным сотрудником этого рабочего места
    if owner_id != current_user.id:
        is_employee = await db.scalar(
            select(EmployeeModel.id).where(
                EmployeeModel.workplace_id == employee.workplace_id,
                EmployeeModel.user_id == current_user.id,
                EmployeeModel.is_active.is_(True),
            )
        )

        if is_employee is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be the owner or an employee of this workplace",
            )

    # 4. Возвращаем найденного сотрудника
    return employee


# Мягкое удаления сотрудника (Employee.is_active = False) по ID.
# Доступ только для администратора или владельца.
@router.delete(
    "/{employee_id}",
    response_model=dict,
)
async def delete_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    # 1. Ищем сотрудника
    employee = await db.scalar(
        select(EmployeeModel).where(
            EmployeeModel.id == employee_id
        )
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