from fastapi import APIRouter, HTTPException, status, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.workplaces.model import Workplace as WorkplaceModel
from app.workplaces.schemas import WorkplaceCreate, WorkplaceResponse, WorkplaceWithEmployeesResponse
from app.workplaces.services import WorkplaceServices

from app.users.model import User as UserModel


from app.core.database import get_db
from app.core.security import get_current_user, get_owner_or_admin

from app.exceptions import WorkplaceExistsException, WorkplaceNotFoundException


router = APIRouter(
    tags=["Workplaces"],
    prefix="/workplaces"
)


@router.post(
    "/",
    response_model=WorkplaceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workplace(
    workplace_data: WorkplaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> WorkplaceModel:
    try:
        services = WorkplaceServices(db)
        workplace = await services.create_workplace(workplace_data, owner=current_user)
        return workplace
    except WorkplaceExistsException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.msg
        )


@router.get(
    "/",
    response_model=list[WorkplaceResponse]
)
async def get_all_workspaces_for_user(
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    services = WorkplaceServices(db)
    return await services.get_all_by_user(current_user)


@router.get(
    "/{workplace_id}",
    response_model=WorkplaceWithEmployeesResponse)
async def get_workplace_by_id(
    workplace_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin),
):
    try:
        services = WorkplaceServices(db)
        return await services.get_by_id(workplace_id)
    except WorkplaceNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )