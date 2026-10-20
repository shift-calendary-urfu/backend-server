from fastapi import APIRouter, Depends, HTTPException, status, Query

from sqlalchemy.ext.asyncio import AsyncSession

from typing import Annotated

from app.shifts.schemas import ShiftCreate, ShiftResponse
from app.shifts.model import Shift as ShiftModel
from app.shifts.services import ShiftServices

from app.users.model import User as UserModel

from app.core.database import get_db
from app.core.security import get_owner_or_admin

from app.exceptions import EmployeeNotFoundException


router = APIRouter(
    prefix="/shifts",
    tags=["Shifts"]
)


@router.post(
    "/", 
    response_model=ShiftResponse, 
    status_code=status.HTTP_201_CREATED
)
async def create_shift(
    new_shift: ShiftCreate,
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin)
) -> ShiftResponse:
    """
    Создание смены в указанной рабочей точке.
    Доступно только администратору и владельцу.
    """
    try:
        shift_service = ShiftServices(db)
        return await shift_service.create_shift(new_shift, workplace_id)
    except EmployeeNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )
        