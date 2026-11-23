from sqlalchemy.ext.asyncio import AsyncSession

from app.users.model import User
from app.workplaces.model import Workplace
from app.workplaces.services import WorkplaceServices
from app.agent.schemas import ListMyWorkplacesResponse


async def list_my_workplaces(
    user: User,
    db: AsyncSession,
) -> ListMyWorkplacesResponse:
    """
    Возвращает активные рабочие точки пользователя:
    созданные им или в которых он активный сотрудник.
    """
    workplaces: list[Workplace] = await WorkplaceServices(db).get_all_by_user(user)
    return ListMyWorkplacesResponse.model_validate(
        {"workplaces": workplaces}
    )