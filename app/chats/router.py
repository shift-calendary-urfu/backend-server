from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user

from app.users.model import User

from app.chats.services import ChatServices
from app.chats.schemas import (
    ChatReadResponse,
    ChatListItem, 
    DirectChatCreate, 
    DirectChatResponse,
    MessageHistoryResponse,
)
from app.exceptions import (
    ChatNotFoundException,
    ChatWithSelfException,
    CommonWorkplaceNotFoundException,
    UserNotFoundException,
)

from typing import Annotated


router = APIRouter(
    prefix="/chats",
    tags=["Chats"],
)


@router.get(
    "/",
    response_model=list[ChatListItem],
)
async def get_chats(
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    current_user: Annotated[
        User, 
        Depends(get_current_user)
    ],
) -> list[ChatListItem]:
    """Получение списка чатов текущего пользователя."""

    services = ChatServices(db)

    return await services.get_chats(user_id=current_user.id)


@router.post(
    "/direct",
    response_model=DirectChatResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_direct_chat(
    chat_data: DirectChatCreate,
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    current_user: Annotated[
        User, 
        Depends(get_current_user)
    ],
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


@router.get(
    "/{chat_id}",
    response_model=ChatListItem,
)
async def get_chat(
    chat_id: Annotated[
        int, 
        Path(
            gt=1,
            description='Идентификатор чата'
    )],
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    current_user: Annotated[
        User, 
        Depends(get_current_user)
    ],
) -> ChatListItem:
    """Получение конкретного чата."""
    try:
        services = ChatServices(db)
        return await services.get_chat(
            chat_id=chat_id,
            user_id=current_user.id,
        )
    except ChatNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg,
        )


@router.get(
    "/{chat_id}/messages",
    response_model=MessageHistoryResponse,
)
async def get_messages(
    chat_id: Annotated[
        int, 
        Path(
            gt=1,
            description='Идентификатор чата'
    )],
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    current_user: Annotated[
        User, 
        Depends(get_current_user)
    ],
    limit: Annotated[int, Query(
        ge=1, le=100,
        description="Количество возвращаемых записей",
    )] = 50,
    before_id: Annotated[
        int | None, 
        Query(gt=0,
              description=f"Возвращать сообщения до указанного ID (не включая)"
    )] = None,
) -> MessageHistoryResponse:
    """Получение истории сообщений чата."""
    try:
        services = ChatServices(db)
        return await services.get_messages(
            chat_id=chat_id,
            user_id=current_user.id,
            limit=limit,
            before_id=before_id,
        )
    except ChatNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg,
        )


@router.post(
    "/{chat_id}/mark",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatReadResponse,
)
async def mark_chat_as_read(
    chat_id: Annotated[
        int, 
        Path(
            gt=1,
            description='Идентификатор чата'
    )],
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    current_user: Annotated[
        User, 
        Depends(get_current_user)
    ],
) -> ChatReadResponse:
    """Отметка сообщений чата как прочитанных."""
    try:
        services = ChatServices(db)
        return await services.mark_as_read(
            chat_id=chat_id,
            user_id=current_user.id,
        )
    except ChatNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg,
        )