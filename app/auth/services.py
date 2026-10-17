from fastapi.security import OAuth2PasswordRequestForm

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.users.schemas import UserCreate
from app.users.model import User as UserModel

from app.core.security import hash_password, verify_password, AuthTokensManager
from app.core.logger import get_logger

from app.auth.schemas import RefreshTokenRequest

from app.exceptions import (
    EmailExistsException,
    UsernamePasswordException,
    InvalidRefreshTokenException
)

logger = get_logger(__name__)


class AuthServices:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.auth_manager = AuthTokensManager(db=db)

    async def create_user(
        self,
        user: UserCreate,
    ) -> UserModel:
        """
        Регистрирует нового пользователя.
        """
        logger.info("Попытка регистрации пользователя: email=%s", user.email)

        result = await self.db.scalar(
            select(UserModel).where(UserModel.email == user.email)
        )
        if result:
            logger.warning("Регистрация отклонена: email=%s уже существует", user.email)
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

        logger.info("Пользователь зарегистрирован: email=%s, id=%s", db_user.email, db_user.id)

        return db_user


    async def get_authenticated_user(
        self,
        form_data: OAuth2PasswordRequestForm
    ):
        """
        Авторизует существующего юзера, проверяя его учетные данные и возвращая токены.
        """
        logger.info("Попытка входа: username=%s", form_data.username)

        user = await self.db.scalar(
                select(UserModel).where(
                    UserModel.email == form_data.username,
                    UserModel.is_active
                )
            )
        if user is None or not verify_password(
            form_data.password,
            user.hashed_password
        ):
            logger.warning("Неудачная попытка входа: username=%s", form_data.username)
            raise UsernamePasswordException("Неверное имя пользователя или пароль.")

        access_token = self.auth_manager.create_access_token(
            data={'sub':user.email, 'id': user.id}
        )
        refresh_token = self.auth_manager.create_refresh_token(
            data={'sub':user.email, 'id': user.id}
        )

        logger.info("Успешный вход: user_id=%s, email=%s", user.id, user.email)

        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "Bearer"}


    async def update_tokens(
        self,
        body: RefreshTokenRequest
    ) -> dict:
        """
        Обновляет access_token и refresh_token для пользователя.
        """
        logger.info("Запрос на обновление токенов")
        try:
            tokens = await self.auth_manager.update_session_tokens(body)
            logger.info("Токены успешно обновлены")
            return tokens
        except InvalidRefreshTokenException as e:
            logger.warning("Ошибка обновления токенов: %s", e.msg)
            raise InvalidRefreshTokenException(e.msg)
