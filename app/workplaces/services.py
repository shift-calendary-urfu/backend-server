from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.users.model import User as UserModel

from app.workplaces.model import Workplace as WorkplaceModel
from app.workplaces.schemas import WorkplaceCreate

from app.exceptions import WorkplaceExistsException


class WorkplaceServices:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_workplace(
        self, 
        workplace_data: WorkplaceCreate,
        owner: UserModel
    ) -> WorkplaceModel:

        result = await self.db.scalar(
            select(WorkplaceModel)
            .where(
                WorkplaceModel.address == workplace_data.address,
                WorkplaceModel.workplace_type==workplace_data.workplace_type,
                WorkplaceModel.owner_id == owner.id
            )
        )
        if result is not None:
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

        return new_workplace