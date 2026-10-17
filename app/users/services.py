from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from pydantic import SecretStr

from app.users.model import User as UserModel
from app.users.schemas import UserUpdate

from app.core.security import verify_password, hash_password
from app.core.logger import get_logger

from app.exceptions import InvalidPasswordException

logger = get_logger(__name__)


class UserServices:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_user(
        self,
        new_data: UserUpdate,
        user: UserModel
    ) -> UserModel:

        logger.info("Обновление профиля: user_id=%s", user.id)

        update_data = new_data.model_dump(exclude_unset=True)

        if not update_data:
            logger.info("Нет данных для обновления: user_id=%s", user.id)
            return user

        await self.db.execute(
            update(UserModel)
            .where(UserModel.id == user.id,
                   UserModel.email==user.email,
                   UserModel.is_active,
                   )
            .values(**update_data)
        )
        await self.db.commit()

        logger.info("Профиль обновлён: user_id=%s, поля=%s", user.id, list(update_data.keys()))

        return user


    async def update_password(
        self,
        new_password: SecretStr,
        old_passowrd_hash: SecretStr,
        user: UserModel
    ) -> UserModel:

        logger.info("Смена пароля: user_id=%s", user.id)

        if not new_password:
            logger.warning("Пустой новый пароль: user_id=%s", user.id)
            raise InvalidPasswordException(
                "New password cannot be empty."
            )

        if not old_passowrd_hash:
            logger.warning("Пустой старый пароль: user_id=%s", user.id)
            raise InvalidPasswordException(
                "Old password cannot be empty."
            )

        if not verify_password(
            old_passowrd_hash.get_secret_value(),
            user.hashed_password
        ):
            logger.warning("Неверный текущий пароль: user_id=%s", user.id)
            raise InvalidPasswordException(
                "Current password is not matching."
            )

        await self.db.execute(
            update(UserModel)
            .where(UserModel.id == user.id,
                   UserModel.email==user.email,
                   UserModel.is_active,
                   )
            .values(hashed_password=hash_password(new_password.get_secret_value()))
        )
        await self.db.commit()

        logger.info("Пароль успешно изменён: user_id=%s", user.id)

        return user
