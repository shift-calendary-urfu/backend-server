from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.shifts.schemas import ShiftCreate, ShiftResponse, ShiftUpdate
from app.shifts.model import Shift as ShiftModel

from app.employees.model import Employee as EmployeeModel

from app.users.model import User as UserModel

from app.core.logger import get_logger

from app.exceptions import EmployeeNotFoundException


logger=get_logger(__name__)


class ShiftServices:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_shift_by_id(self, shift_id: int) -> ShiftResponse:
        result = await self.db.execute(
            select(
                ShiftModel,
                UserModel.first_name,
                UserModel.second_name,
                UserModel.third_name,
            )
            .join(EmployeeModel, EmployeeModel.id == ShiftModel.employee_id)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .where(ShiftModel.id == shift_id)
        )

        shift, first_name, second_name, third_name = result.one()

        return ShiftResponse(
            id=shift.id,
            employee_id=shift.employee_id,
            workplace_id=shift.workplace_id,
            date=shift.date,
            start_time=shift.start_time,
            end_time=shift.end_time,
            notes=shift.notes,
            first_name=first_name,
            second_name=second_name,
            third_name=third_name
        )

    async def create_shift(
        self, 
        new_shift: ShiftCreate,
        workplace_id: int,
    ) -> ShiftResponse:
        employee = await self.db.scalar(
            select(EmployeeModel)
            .where(
                EmployeeModel.id == new_shift.employee_id,
                EmployeeModel.workplace_id == workplace_id,
                EmployeeModel.is_active
                )
            )
        
        if not employee:
            logger.warning(
                "Работник не найден или не активен, employee_id=%s, workplace_id=%s", 
                new_shift.employee_id, 
                workplace_id
            )
            raise EmployeeNotFoundException(
                "Employee not found or not active"
            )

        shift = ShiftModel(
            workplace_id=workplace_id,
            **new_shift.model_dump(exclude_unset=True)
        )

        self.db.add(shift)
        await self.db.commit()

        logger.info(
            "Смена создана успешно, shift_id=%s, workplace_id=%s", 
            shift.id, workplace_id
        )

        return await self.get_shift_by_id(shift.id)


    async def update_shift(
        self,
        shift_id: int,
        workplace_id: int,
        update_shift: ShiftUpdate,
    ) -> ShiftResponse:
        shift = await self.db.scalar(
            select(ShiftModel)
            .where(
                ShiftModel.id == shift_id,
                ShiftModel.workplace_id == workplace_id
            )
        )

        if not shift:
            logger.warning(
                "Смена не найдена, shift_id=%s", 
                shift_id
            )
            raise EmployeeNotFoundException(
                "Shift not found"
            )

        await self.db.execute(
            update(ShiftModel)
            .where(
                ShiftModel.id == shift_id,
                ShiftModel.workplace_id == shift.workplace_id,
                ShiftModel.is_active
            )
            .values(**update_shift.model_dump())
        )

        await self.db.commit()

        logger.info(
            "Смена обновлена успешно, shift_id=%s", 
            shift.id
        )

        return await self.get_shift_by_id(shift.id)