from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria
from sqlalchemy import select, or_, update

from app.users.model import User as UserModel

from app.workplaces.model import Workplace as WorkplaceModel
from app.workplaces.schemas import WorkplaceCreate, WorkplaceUpdate

from app.employees.model import Employee as EmployeeModel

from app.shifts.model import Shift as ShiftModel

from app.shift_templates.models import ShiftTemplate as ShiftTemplateModel

from app.core.logger import get_logger

from app.exceptions import WorkplaceExistsException, WorkplaceNotFoundException

logger = get_logger(__name__)


class WorkplaceServices:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_workplace(
        self,
        workplace_data: WorkplaceCreate,
        owner: UserModel
    ) -> WorkplaceModel:

        logger.info(
            "Создание рабочей точки: name=%s, owner_id=%s",
            workplace_data.name, owner.id
        )

        result = await self.db.scalar(
            select(WorkplaceModel)
            .where(
                WorkplaceModel.address == workplace_data.address,
                WorkplaceModel.workplace_type==workplace_data.workplace_type,
                WorkplaceModel.owner_id == owner.id,
                WorkplaceModel.is_active
            )
        )
        if result is not None:
            logger.warning(
                "Точка уже существует: address=%s, type=%s, owner_id=%s",
                workplace_data.address, workplace_data.workplace_type, owner.id
            )
            raise WorkplaceExistsException(
                "Workplace with this address and type already exists."
            )

        new_workplace=WorkplaceModel(
            name=workplace_data.name,
            address=workplace_data.address,
            phone=workplace_data.phone,
            description=workplace_data.description,
            workplace_type=workplace_data.workplace_type,
            work_start_time=workplace_data.work_start_time,
            work_end_time=workplace_data.work_end_time,
            owner_id=owner.id
        )

        self.db.add(new_workplace)
        await self.db.commit()

        logger.info("Точка создана: id=%s, name=%s", new_workplace.id, new_workplace.name)

        return new_workplace


    async def get_all_by_user(
        self,
        user: UserModel,
    ):
        logger.info("Получение всех точек пользователя: user_id=%s", user.id)

        employee_workplaces = (
        select(EmployeeModel.workplace_id)
        .where(
            EmployeeModel.user_id == user.id,
            EmployeeModel.is_active,
            )
        )

        result = await self.db.scalars(
            select(WorkplaceModel).where(
                or_(
                    WorkplaceModel.owner_id == user.id,
                    WorkplaceModel.id.in_(employee_workplaces),
                ),
                WorkplaceModel.is_active,
            )
        )

        workplaces = list(result.all())
        logger.info("Найдено точек: %d для user_id=%s", len(workplaces), user.id)

        return workplaces


    async def get_by_id(
        self,
        workplace_id: int,
    ):
        logger.info("Получение точки по ID: workplace_id=%s", workplace_id)

        result = await self.db.scalar(
            select(WorkplaceModel)
            .options(
                selectinload(WorkplaceModel.employees)
                .selectinload(EmployeeModel.user),
                with_loader_criteria(
                    EmployeeModel,
                    EmployeeModel.is_active,
                ),
            )
            .where(
                WorkplaceModel.id == workplace_id,
                WorkplaceModel.is_active
                )
        )

        if result is None:
            logger.warning("Точка не найдена: workplace_id=%s", workplace_id)
            raise WorkplaceNotFoundException(
                "Workplace not found"
            )

        logger.info("Точка найдена: id=%s, name=%s", result.id, result.name)

        return result


    async def update_workplace(
        self,
        workplace_id: int,
        workplace_data: WorkplaceUpdate,
    ):
        logger.info("Обновление точки: workplace_id=%s", workplace_id)

        result = await self.db.scalar(
            select(WorkplaceModel)
            .where(WorkplaceModel.id == workplace_id,
                   WorkplaceModel.is_active
                   )
        )

        if result is None:
            logger.warning("Точка для обновления не найдена: workplace_id=%s", workplace_id)
            raise WorkplaceNotFoundException(
                "Workplace not found"
            )

        update_data = workplace_data.model_dump(exclude_unset=True)

        await self.db.execute(
            update(WorkplaceModel)
            .where(WorkplaceModel.id == workplace_id)
            .values(**update_data)
        )

        await self.db.commit()

        logger.info(
            "Точка обновлена: workplace_id=%s, поля=%s",
            workplace_id, list(update_data.keys())
        )

        return result


    async def delete_workplace(
        self,
        workplace_id: int,
    ):
        logger.info("Удаление точки: workplace_id=%s", workplace_id)

        result = await self.db.scalar(
            select(WorkplaceModel)
            .where(
                WorkplaceModel.id == workplace_id,
                WorkplaceModel.is_active
            )
        )

        if result is None:
            logger.warning("Точка для удаления не найдена: workplace_id=%s", workplace_id)
            raise WorkplaceNotFoundException(
                "Workplace not found"
            )

        await self.db.execute(
            update(EmployeeModel)
            .where(EmployeeModel.workplace_id == workplace_id)
            .values(is_active=False)
        )

        await self.db.execute(
            update(ShiftModel)
            .where(ShiftModel.workplace_id == workplace_id)
            .values(is_active=False)
        )

        await self.db.execute(
            update(ShiftTemplateModel)
            .where(ShiftTemplateModel.workplace_id == workplace_id)
            .values(is_active=False)
        )

        result.is_active = False

        await self.db.commit()

        logger.info("Точка удалена (soft delete): workplace_id=%s", workplace_id)


    async def get_employees_by_workplace(
        self,
        workplace_id: int,
    ):
        logger.info("Получение сотрудников точки: workplace_id=%s", workplace_id)

        result = await self.db.scalars(
            select(EmployeeModel)
            .options(
                selectinload(EmployeeModel.user),
                with_loader_criteria(
                    UserModel,
                    UserModel.is_active,
                )
            )
            .where(
                EmployeeModel.workplace_id == workplace_id,
                EmployeeModel.is_active
            )
        )

        employees = list(result.all())
        logger.info(
            "Найдено сотрудников: %d для workplace_id=%s",
            len(employees), workplace_id
        )

        return employees
