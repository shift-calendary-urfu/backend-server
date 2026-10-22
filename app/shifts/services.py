from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.shifts.schemas import (
    ShiftCreate, 
    ShiftResponse, 
    ShiftUpdate, 
    CalendarResponse, 
    ShiftsDuplicate,
    ShiftsDuplicateResponse
)
from app.shifts.model import Shift as ShiftModel

from app.employees.model import Employee as EmployeeModel

from app.users.model import User as UserModel

from app.core.logger import get_logger

from app.exceptions import EmployeeNotFoundException, ShiftNotFoundException

import datetime as dt


logger=get_logger(__name__)


class ShiftServices:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_shift_by_id(
        self, 
        shift_id: int, 
        workplace_id: int
    ) -> ShiftResponse:
        result = await self.db.execute(
            select(
                ShiftModel,
                UserModel.first_name,
                UserModel.second_name,
                UserModel.third_name,
            )
            .join(EmployeeModel, EmployeeModel.id == ShiftModel.employee_id)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .where(
                ShiftModel.id == shift_id,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
        )

        shift, first_name, second_name, third_name = result.one()

        if not shift:
            logger.warning(
                "Смена не найдена или не активна, shift_id=%s", 
                shift_id
            )
            raise ShiftNotFoundException(
                "Shift not found or not active"
            )

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
        
        return await self.get_shift_by_id(shift.id, workplace_id)


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
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
        )

        if not shift:
            logger.warning(
                "Смена не найдена или не активна, shift_id=%s", 
                shift_id
            )
            raise ShiftNotFoundException(
                "Shift not found or not active"
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

        return await self.get_shift_by_id(shift.id, workplace_id)


    async def delete_shift_by_id(
        self,
        shift_id: int,
        workplace_id: int
    ) -> None:
        shift = await self.db.scalar(
            select(ShiftModel)
            .where(
                ShiftModel.id == shift_id,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
        )

        if not shift:
            logger.warning(
                "Смена не найдена или не активна, shift_id=%s", 
                shift_id
            )
            raise ShiftNotFoundException(
                "Shift not found or not active"
            )

        shift.is_active = False

        await self.db.commit()

        logger.info(
            "Смена удалена успешно, shift_id=%s", 
            shift.id
        )


    async def delete_shifts_by_date(
        self,
        date: dt.date,
        workplace_id: int,
    ) -> None:
        result = await self.db.execute(
            update(ShiftModel)
            .where(
                ShiftModel.date == date,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active,
            )
            .values(is_active=False)
            .returning(ShiftModel.id)
        )

        if not result.scalars().all():
            logger.warning(
                "Смены не найдены или не активны, date=%s, workplace_id=%s", 
                date, workplace_id
            )
            raise ShiftNotFoundException(
                f"Shifts not found or not active on this date={date}"
            )

        await self.db.commit()
        
        logger.info(
            "Смены удалены успешно, date=%s, workplace_id=%s", 
            date, workplace_id
        )


    async def get_shifts_by_date(
        self,
        date: dt.date,
        workplace_id: int,
    ) -> list[ShiftResponse]:
        result = await self.db.execute(
            select(
                ShiftModel,
                UserModel.first_name,
                UserModel.second_name,
                UserModel.third_name,
            )
            .join(EmployeeModel, EmployeeModel.id == ShiftModel.employee_id)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .where(
                ShiftModel.date == date,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
        )

        shifts = result.all()

        if not shifts:
            logger.warning(
                "Смены не найдены или не активны, date=%s, workplace_id=%s", 
                date, workplace_id
            )
            raise ShiftNotFoundException(
                f"Shifts not found or not active on this date={date}"
            )

        return [
            ShiftResponse(
                id=shift.id,
                workplace_id=shift.workplace_id,
                employee_id=shift.employee_id,
                date=shift.date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                notes=shift.notes,
                first_name=first_name,
                second_name=second_name,
                third_name=third_name,
            )
            for shift, first_name, second_name, third_name in shifts
        ]
        

    async def get_calendar_shifts(
        self,
        date_from: dt.date,
        date_to: dt.date,
        workplace_id: int,
    ) -> CalendarResponse:
        result = await self.db.execute(
            select(
                ShiftModel,
                UserModel.first_name,
                UserModel.second_name,
                UserModel.third_name,
            )
            .join(EmployeeModel, EmployeeModel.id == ShiftModel.employee_id)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .where(
                ShiftModel.date >= date_from,
                ShiftModel.date <= date_to,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
            .order_by(ShiftModel.date)
        )

        shifts = result.all()

        if not shifts:
            logger.warning(
                "Смены не найдены или не активны, start_date=%s, end_date=%s, workplace_id=%s", 
                date_from, date_to, workplace_id
            )
            raise ShiftNotFoundException(
                f"Shifts not found or not active between {date_from} and {date_to}"
            )

        shifts_by_date: dict[dt.date, list[ShiftResponse]] = {}
        for shift, first_name, second_name, third_name in shifts:
            shift_response = ShiftResponse(
                id=shift.id,
                workplace_id=shift.workplace_id,
                employee_id=shift.employee_id,
                date=shift.date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                notes=shift.notes,
                first_name=first_name,
                second_name=second_name,
                third_name=third_name,
            )

            shifts_by_date.setdefault(shift.date, []).append(shift_response)

        logger.info(
            "Смены получены успешно, start_date=%s, end_date=%s, workplace_id=%s", 
            date_from, date_to, workplace_id
        )

        return CalendarResponse(root=shifts_by_date)


    async def duplicate_shifts(
        self,
        duplicate_data: ShiftsDuplicate,
        workplace_id: int,
    ) -> ShiftsDuplicateResponse:
        result = await self.db.execute(
            select(ShiftModel)
            .where(
                ShiftModel.id.in_(duplicate_data.shift_ids),
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active,
            )
        )
        shifts = result.scalars().all()

        found_ids = {shift.id for shift in shifts}
        missing_ids = set(duplicate_data.shift_ids) - found_ids

        if missing_ids:
            logger.warning(
                "Смены не найдены или не активны, missing_ids=%s, workplace_id=%s",
                missing_ids,
                workplace_id,
            )
            raise ShiftNotFoundException(
                f"Shifts not found or not active: {sorted(missing_ids)}"
            )

        new_shifts = [
            ShiftModel(
                employee_id=shift.employee_id,
                workplace_id=shift.workplace_id,
                date=date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                notes=shift.notes,
            )
            for date in duplicate_data.dates
            for shift in shifts
        ]

        self.db.add_all(new_shifts)
        await self.db.flush()

        new_shift_ids = [shift.id for shift in new_shifts]

        await self.db.commit()

        start_date = min(duplicate_data.dates)
        end_date = max(duplicate_data.dates)

        logger.info(
            "Смены успешно размножены, new_shift_ids=%s, workplace_id=%s",
            new_shift_ids,
            workplace_id,
        )

        return ShiftsDuplicateResponse(
            count_duplicated_shifts_created=len(new_shifts),
            workplace_id=workplace_id,
            period={
                "start_date": start_date,
                "end_date": end_date,
            },
            message=(
                f"Смены успешно скопированы на период "
                f"с {start_date} по {end_date}"
            ),
        )