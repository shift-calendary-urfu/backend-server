from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from pydantic import SecretStr

from app.users.model import User as UserModel
from app.users.schemas import UserUpdate

from app.core.security import verify_password, hash_password

from app.exceptions import InvalidPasswordException


class UserServices:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_user(
        self, 
        new_data: UserUpdate,
        user: UserModel
    ) -> UserModel:

        update_data = new_data.model_dump(exclude_unset=True)
    
        if not update_data:
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
        
        return user


    async def update_password(
        self,
        new_password: SecretStr,
        old_passowrd_hash: SecretStr,
        user: UserModel
    ) -> UserModel:
        
        if not new_password:
            raise InvalidPasswordException(
                "New password cannot be empty."
            )

        if not old_passowrd_hash:
            raise InvalidPasswordException(
                "Old password cannot be empty."
            )

        if not verify_password(
            old_passowrd_hash.get_secret_value(), 
            user.hashed_password
        ):
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
        
        return user