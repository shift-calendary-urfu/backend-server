from fastapi import APIRouter, Depends, status, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user

from app.users.model import User as UserModel
from app.users.schemas import UserResponse, UserUpdate, UserUpdatePassword
from app.users.services import UserServices

from app.exceptions import InvalidPasswordException


router = APIRouter(
    tags=["Users"],
    prefix="/users"
)


@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_info_user(
    current_user: UserModel = Depends(get_current_user)
):
    return current_user


@router.put(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
async def update_info_user(
    new_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    user_service = UserServices(db)
    updated_user = await user_service.update_user(new_data=new_data, user=current_user)
    return updated_user

@router.put(
    "/me/password",
)
async def update_password_user(
    body: UserUpdatePassword,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
) -> dict:
    try:
        user_service = UserServices(db)
        await user_service.update_password(body.new_password, body.old_password, user=current_user)
        return {"message": "Password updated"}
    except InvalidPasswordException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.msg
        )