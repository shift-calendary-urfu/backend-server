from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.users.model import User
from app.chats.services import ChatServices
from app.chats.schemas import ChatListItem


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