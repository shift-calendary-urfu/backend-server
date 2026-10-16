from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from pwdlib import PasswordHash

from datetime import timedelta, datetime, timezone

from enum import Enum

from app.workplaces.model import Workplace as WorkplaceModel

from app.employees.model import Employee as EmployeeModel

from app.users.model import User as UserModel

from app.auth.schemas import RefreshTokenRequest

from app.core.database import get_db

from app.config import settings
from app.exceptions import InvalidRefreshTokenException

import jwt

# Схема для проверки Bearer Tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


class TokenType(Enum):
        ACCESS = 'access'
        REFRESH = 'refresh'

# Хэширование паролей
password_hashed = PasswordHash.recommended()

def hash_password(password: str) -> str:
    """
    Преобразует пароль в безопасный хеш.
    """
    return password_hashed.hash(password=password)


def verify_password(
    plain_password: str, 
    hashed_password: str
) -> bool:
    """
    Проверяет, соответствует ли введённый пароль сохранённому хешу.
    """
    return password_hashed.verify(
        password=plain_password, 
        hash=hashed_password
    )


class AuthTokensManager:
    """
    Класс для управления токенами.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Время жизни токенов по умолчанию
        self.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        self.REFRESH_TOKEN_EXPIRE_DAYS = 7


    def create_access_token(self, data: dict) -> str:
        """
        Создаёт JWT с payload (sub, role, id, exp).
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        to_encode.update({
            "exp": expire,
            "token_type": TokenType.ACCESS.value
        })

        return jwt.encode(
            to_encode, 
            settings.JWT_SECRET_KEY, 
            algorithm=settings.JWT_ALGORITHM,
        )


    def create_refresh_token(self, data: dict):
        """
        Создаёт refresh-токен с длительным сроком действия и token_type="refresh".
        """
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(
            days=self.REFRESH_TOKEN_EXPIRE_DAYS
        )
        to_encode.update({
            "exp": expire,
            "token_type": TokenType.REFRESH.value,
        })

        return jwt.encode(
            to_encode, 
            settings.JWT_SECRET_KEY, 
            algorithm=settings.JWT_ALGORITHM,
        )


    async def update_session_tokens(
        self,
        body: RefreshTokenRequest,
    ) -> dict[str,str]:
        """
        Обновляет access-token на основе старого refresh-tokена.
        """

        old_refresh_token = body.refresh_token
        try:

            payload = jwt.decode(
                old_refresh_token,
                settings.JWT_SECRET_KEY, 
                algorithms=settings.JWT_ALGORITHM,
            )
            email: str | None = payload.get("sub")
            token_type: str | None = payload.get("token_type")
            if email is None or token_type != TokenType.REFRESH.value:
                raise InvalidRefreshTokenException("Could not validate refresh token")

        except jwt.ExpiredSignatureError:
            # refresh-токен истёк
            raise InvalidRefreshTokenException("Could not validate refresh token")
        except jwt.PyJWTError:
            # подпись неверна или токен повреждён
            raise InvalidRefreshTokenException("Could not validate refresh token")
        
        user = await self.db.scalar(
            select(UserModel).where(
                UserModel.email == email,
                UserModel.is_active
            )
        )
        if user is None:
            raise InvalidRefreshTokenException("Could not validate refresh token")

        new_refresh_token = self.create_refresh_token(
            data={"sub": user.email, "id": user.id}
        )
        new_access_token = self.create_access_token(
            data={"sub": user.email, "id": user.id}
        )
        return {
            "refresh_token": new_refresh_token,
            "access_token": new_access_token,
            "token_type": "Bearer",
        }


# -------------------------------------------------------------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db), 
) -> UserModel:
    """
    Проверяет JWT и возвращает текущего пользователя из базы данных.
    """
    credentials_exceptions = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Could not validate the provided credential',
        headers={"WWW-Authenticate":"Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY, 
            algorithms=settings.JWT_ALGORITHM,
        )

        email: str | None = payload.get("sub")
        token_type: str | None = payload.get("token_type")
        if email is None or token_type != TokenType.ACCESS.value:
            raise credentials_exceptions

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token expired",
            headers={'WWW-Authenticate': 'Bearer'},
        )
    
    except jwt.PyJWTError:
        raise credentials_exceptions

    user = await db.scalar(
        select(UserModel).where(
            UserModel.email == email,
            UserModel.is_active
        )
    )
    if user is None:
        raise credentials_exceptions

    return user


async def get_owner_or_admin(
    workplace_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    is_owner = await db.scalar(
        select(WorkplaceModel.id).where(
            WorkplaceModel.id == workplace_id,
            WorkplaceModel.owner_id == user.id,
        )
    )

    if is_owner is not None:
        return user

    is_admin = await db.scalar(
        select(EmployeeModel.id).where(
            EmployeeModel.workplace_id == workplace_id,
            EmployeeModel.user_id == user.id,
            EmployeeModel.role == "admin",
            EmployeeModel.is_active,
        )
    )

    if is_admin is not None:
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You must be the owner or admin of this workplace",
    )


async def get_current_owner(
    workplace_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    is_owner = await db.scalar(
        select(WorkplaceModel.id).where(
            WorkplaceModel.id == workplace_id,
            WorkplaceModel.owner_id == user.id,
        )
    )

    if is_owner is not None:
        return user

    raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be the owner of this workplace",
        )


async def get_owner_or_employees(
    workplace_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    is_owner = await db.scalar(
        select(WorkplaceModel.id).where(
            WorkplaceModel.id == workplace_id,
            WorkplaceModel.owner_id == user.id,

        )
    )

    if is_owner is not None:
        return user

    is_employee = await db.scalar(
        select(EmployeeModel.id).where(
            EmployeeModel.workplace_id == workplace_id,
            EmployeeModel.user_id == user.id,
            EmployeeModel.is_active,
        )
    )

    if is_employee is not None:
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You must be the owner or employee of this workplace",
    )


async def check_workplace_access(
    workplace_id: int,
    user: UserModel,
    db: AsyncSession,
):
    await get_owner_or_employees(
        workplace_id=workplace_id,
        user=user,
        db=db,
    )