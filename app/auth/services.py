from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.users.schemas import UserCreate, UserResponse
from app.users.model import User as UserModel

from app.core.security import hash_password

from app.exceptions import EmailExistsException


class AuthServices:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_user(
        self,
        user: UserCreate,
    ) -> UserModel:
        """
        Регистрирует нового пользователя.
        """
        result = await self.db.scalar(
            select(UserModel).where(UserModel.email == user.email)
        )
        if result:
            raise EmailExistsException("Email уже зарегистрирован")

        db_user = UserModel(
            first_name=user.first_name,
            second_name=user.second_name,
            third_name=user.third_name,
            email=user.email,
            phone=user.phone,
            hashed_password=hash_password(user.password.get_secret_value()),
        )
        
        self.db.add(db_user)
        await self.db.commit()
        
        return db_user