from fastapi.security import OAuth2PasswordRequestForm
from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession

from app.users.schemas import UserCreate, UserResponse
from app.users.model import User as UserModel

from app.auth.services import AuthServices

from app.core.database import get_db

from app.exceptions import EmailExistsException, UsernamePasswordException


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register", 
    status_code=201, 
    response_model=UserResponse
)
async def create_user(
    user: UserCreate, 
    db: AsyncSession = Depends(get_db)
) -> UserModel:
    """
    Регистрирует нового пользователя.
    """
    try:
        services = AuthServices(db)
        db_user = await services.create_user(user)
        return db_user
    except EmailExistsException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=e.msg
        )


@router.post('/login', response_model=dict)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession  = Depends(get_db)
) -> dict:
    """
    Аутентифицирует пользователя и возвращает access_token и refresh_token.
    """
    try:
        services = AuthServices(db)
        tokens = await services.get_authenticated_user(form_data)
        return tokens
    except UsernamePasswordException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail=e.msg
        )