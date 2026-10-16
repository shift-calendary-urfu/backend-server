from fastapi import APIRouter, Depends, HTTPException, status

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

# TODO: Создание по номеру ТЕЛЕФОНА (User), то есть проверить существование пользователя. 
# Схема создания есть. 
# Создать может только админ или владелец
@router.post(
    '/',
    response_model=EmployeeResponse,
)
async def create_employee():
    pass


# TODO: Получение сотрудника по ID. 
# Схема ответа есть.
# Доступно владельцу или работнику
@router.get(
    '/{employee_id}',
    response_model=EmployeeResponse,
)
async def get_employee():
    pass


# TODO: мягкое удаления сотрудника (Employee.is_active = False) по ID.
# Доступ только для администратора или владельца.
@router.delete(
    '/{employee_id}',
    response_model=dict,
)
async def delete_employee():
    pass