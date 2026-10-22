from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from datetime import date

from app.employees.model import Employee as EmployeeModel
from app.employees.schemas import EmployeeCreate, EmployeeUpdate

from app.users.model import User as UserModel

from app.workplaces.model import Workplace as WorkplaceModel

from app.core.logger import get_logger

from app.exceptions import (
    WorkplaceNotFoundException,
    UserNotFoundException,
    EmployeeAlreadyInWorkPlaceExceprion,
    EmployeeNotFoundException
)

logger = get_logger(__name__)


class EmployeeServices:
    def __init__(self, db: AsyncSession):
        self.db = db


    async def create_employee(
        self,
        employee_data: EmployeeCreate,
        workplace_id: int
    ) -> EmployeeModel:

        logger.info(
            "Добавление сотрудника: workplace_id=%s",
            workplace_id
        )

        workplace = await self.db.scalar(
            select(WorkplaceModel).where(
                WorkplaceModel.id == workplace_id,
                WorkplaceModel.is_active
            )
        )

        if workplace is None:
            logger.warning("Точка не найдена: workplace_id=%s", workplace_id)
            raise WorkplaceNotFoundException(
                "Workplace not found"
            )

        user = await self.db.scalar(
                select(UserModel).where(
                    UserModel.phone == employee_data.phone,
                    UserModel.is_active
                    )
                )

        if user is None:
            logger.warning(
                "Пользователь с указанным телефоном не найден",
            )
            raise UserNotFoundException(
                "User with this phone number not found"
            )

        existing_employee = await self.db.scalar(
                select(EmployeeModel).where(
                    EmployeeModel.user_id == user.id,
                    EmployeeModel.workplace_id == workplace_id,
                    )
                )

        if existing_employee is not None:
            if existing_employee.is_active:
                logger.warning(
                    "Сотрудник уже работает: user_id=%s, workplace_id=%s",
                    user.id, workplace_id
                )
                raise EmployeeAlreadyInWorkPlaceExceprion(
                    "Employee already exists in this workplace"
                )

            logger.info(
                "Восстановление сотрудника: employee_id=%s, workplace_id=%s",
                existing_employee.id, workplace_id
            )

            await self.db.execute(
                update(EmployeeModel)
                .where(EmployeeModel.id == existing_employee.id)
                .values(
                    **employee_data.model_dump(
                        exclude={"phone"}
                    ),
                    is_active=True,
                    hire_date=date.today(),
                )
            )


            await self.db.commit()
            await self.db.refresh(existing_employee, attribute_names=["user"])

            logger.info("Сотрудник восстановлен: employee_id=%s", existing_employee.id)

            return existing_employee


        new_employee = EmployeeModel(
            user_id=user.id,
            workplace_id=workplace_id,
            **employee_data.model_dump(exclude={"phone"})
        )

        self.db.add(new_employee)
        await self.db.commit()

        await self.db.refresh(new_employee, attribute_names=["user"])

        logger.info(
            "Сотрудник добавлен: employee_id=%s, user_id=%s, workplace_id=%s",
            new_employee.id, user.id, workplace_id
        )

        return new_employee


    async def get_employee_by_id(
        self,
        employee_id: int,
        workplace_id: int
    ) -> EmployeeModel:

        logger.info(
            "Получение сотрудника: employee_id=%s, workplace_id=%s",
            employee_id, workplace_id
        )

        employee = await self.db.scalar(
                select(EmployeeModel)
                .options(selectinload(EmployeeModel.user))
                .where(
                    EmployeeModel.id == employee_id,
                    EmployeeModel.workplace_id==workplace_id,
                    EmployeeModel.is_active
                    )
                )

        if employee is None:
            logger.warning(
                "Сотрудник не найден: employee_id=%s, workplace_id=%s",
                employee_id, workplace_id
            )
            raise EmployeeNotFoundException(
                "Employee not found"
            )

        logger.info("Сотрудник найден: employee_id=%s", employee.id)

        return employee


    async def delete_employee(
        self,
        employee_id: int,
        workplace_id: int
    ) -> None:

        logger.info(
            "Деактивация сотрудника: employee_id=%s, workplace_id=%s",
            employee_id, workplace_id
        )

        employee = await self.db.scalar(
                select(EmployeeModel).where(
                    EmployeeModel.id == employee_id,
                    EmployeeModel.workplace_id == workplace_id,
                    EmployeeModel.is_active
                    )
                )

        if employee is None:
            logger.warning(
                "Сотрудник для деактивации не найден: employee_id=%s, workplace_id=%s",
                employee_id, workplace_id
            )
            raise EmployeeNotFoundException(
                "Employee not found"
            )

        employee.is_active = False

        await self.db.commit()

        logger.info("Сотрудник деактивирован: employee_id=%s", employee_id)


    async def update_employee(
        self,
        employee_id: int,
        employee_data: EmployeeUpdate,
        workplace_id: int,
    ) -> EmployeeModel:

        logger.info(
            "Обновление сотрудника: employee_id=%s, workplace_id=%s",
            employee_id, workplace_id
        )

        employee = await self.db.scalar(
                select(EmployeeModel).where(
                    EmployeeModel.id == employee_id,
                    EmployeeModel.workplace_id == workplace_id,
                    EmployeeModel.is_active
                    )
                )

        if employee is None:
            logger.warning(
                "Сотрудник для обновления не найден: employee_id=%s, workplace_id=%s",
                employee_id, workplace_id
            )
            raise EmployeeNotFoundException(
                "Employee not found"
            )

        await self.db.execute(
            update(EmployeeModel)
            .where(
                EmployeeModel.id == employee.id,
                EmployeeModel.workplace_id == workplace_id,
                EmployeeModel.is_active
            )
            .values(**employee_data.model_dump(exclude_unset=True))
        )
        

        await self.db.commit()
        await self.db.refresh(employee, attribute_names=["user"])

        logger.info(
            "Сотрудник обновлен: employee_id=%s, workplace_id=%s", 
            employee.id, workplace_id
        )

        return employee