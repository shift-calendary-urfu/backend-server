from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.employees.model import Employee as EmployeeModel
from app.employees.schemas import EmployeeCreate

from app.users.model import User as UserModel

from app.workplaces.model import Workplace as WorkplaceModel

from app.exceptions import (
    WorkplaceNotFoundException,
    UserNotFoundException,
    EmployeeAlreadyInWorkPlaceExceprion,
    EmployeeNotFoundException
)


class EmployeeServices:
    def __init__(self, db: AsyncSession):
        self.db = db


    async def create_employee(
        self, 
        employee_data: EmployeeCreate
    ) -> EmployeeModel:

        workplace = await self.db.scalar(
            select(WorkplaceModel).where(
                WorkplaceModel.id == employee_data.workplace_id,
                WorkplaceModel.is_active
            )
        )

        if workplace is None:
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
            raise UserNotFoundException(
                "User with this phone number not found"
            )

        existing_employee = await self.db.scalar(
                select(EmployeeModel.id).where(
                    EmployeeModel.user_id == user.id,
                    EmployeeModel.workplace_id == employee_data.workplace_id,
                    EmployeeModel.is_active
                    )
                )

        if existing_employee is not None:
            raise EmployeeAlreadyInWorkPlaceExceprion(
                "Employee already exists in this workplace"
            )

        
        new_employee = EmployeeModel(
            user_id=user.id,
            **employee_data.model_dump(exclude={"phone"}) 
        )

        self.db.add(new_employee)
        await self.db.commit()

        await self.db.refresh(new_employee, attribute_names=["user"])

        return new_employee


    async def get_employee_by_id(
        self, 
        employee_id: int
    ) -> EmployeeModel:

        employee = await self.db.scalar(
                select(EmployeeModel)
                .options(selectinload(EmployeeModel.user))
                .where(
                    EmployeeModel.id == employee_id,
                    EmployeeModel.is_active
                    )
                )

        if employee is None:
            raise EmployeeNotFoundException(
                "Employee not found"
            )

        return employee