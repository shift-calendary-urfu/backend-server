from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from pwdlib import PasswordHash

from datetime import timedelta, datetime, timezone

from enum import Enum

from app.users.model import User as UserModel
from app.auth.schemas import RefreshTokenRequest
from app.config import settings

import jwt


class TokenType(Enum):
    ACCESS = 'access'
    REFRESH = 'refresh'

# Хэширование паролей
password_hashed = PasswordHash.recommended()

# Время жизни токенов по умолчанию
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Схема для проверки Bearer Tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="users/token")


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


def create_access_token(data: dict) -> str:
    """
    Создаёт JWT с payload (sub, role, id, exp).
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
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


def create_refresh_token(data: dict):
    """
    Создаёт refresh-токен с длительным сроком действия и token_type="refresh".
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
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
    body: RefreshTokenRequest,
    db: AsyncSession
) -> dict[str,str]:
    """
    Обновляет access-token на основе старого refresh-tokена.
    """
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
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
            raise credentials_exception

    except jwt.ExpiredSignatureError:
        # refresh-токен истёк
        raise credentials_exception
    except jwt.PyJWTError:
        # подпись неверна или токен повреждён
        raise credentials_exception
    
    user = await db.scalar(
        select(UserModel).where(
            UserModel.email == email,
            UserModel.is_active
        )
    )
    if user is None:
        raise credentials_exception

    new_refresh_token = create_refresh_token(
        data={"sub": user.email, "id": user.id}
    )
    new_access_token = create_access_token(
        data={"sub": user.email, "id": user.id}
    )
    return {
        "refresh_token": new_refresh_token,
        "access_token": new_access_token,
        "token_type": "bearer",
    }