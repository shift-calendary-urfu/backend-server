from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.users.model import User
from app.chats.services import ChatServices
from app.chats.schemas import ChatListItem, DirectChatCreate, DirectChatResponse
from app.exceptions import (
    ChatWithSelfException,
    CommonWorkplaceNotFoundException,
    UserNotFoundException,
)


router = APIRouter(
    prefix="/chats",
    tags=["Chats"],
)


@router.get(
    "/",
    response_model=list[ChatListItem],
)
async def get_chats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatListItem]:
    """Получение списка чатов текущего пользователя."""

    services = ChatServices(db)

    return await services.get_chats(user_id=current_user.id)


@router.post(
    "/direct",
    response_model=DirectChatResponse,
    status_code=status.HTTP_200_OK,
)
async def create_direct_chat(
    chat_data: DirectChatCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DirectChatResponse:
    """Создание или получение личного чата."""

    try:
        services = ChatServices(db)

        return await services.get_or_create_direct_chat(
            user_id=current_user.id,
            target_user_id=chat_data.target_user_id,
        )

    except ChatWithSelfException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.msg,
        )

    except CommonWorkplaceNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.msg,
        )

    except UserNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg,
        )