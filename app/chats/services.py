from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats.models import Chat, ChatMember
from app.chats.models.chat import ChatType
from app.exceptions import (
    WorkplaceChatCreationException,
    WorkplaceChatNotFoundException,
)

from app.core.logger import get_logger

logger = get_logger(__name__)


async def ensure_workplace_chat(
    db: AsyncSession,
    workplace_id: int,
    owner_id: int,
) -> int:
    """Создаёт общий чат торговой точки и добавляет владельца."""

    stmt = (
        insert(Chat)
        .values(
            type=ChatType.WORKPLACE,
            workplace_id=workplace_id,
        )
        .on_conflict_do_nothing(
            index_elements=[Chat.workplace_id],
        )
        .returning(Chat.id)
    )

    chat_id = await db.scalar(stmt)

    if chat_id is None:
        chat_id = await db.scalar(
            select(Chat.id).where(
                Chat.workplace_id == workplace_id,
            )
        )

    if chat_id is None:
        logger.error(
            "Не удалось создать общий чат: workplace_id=%s",
            workplace_id,
        )
        raise WorkplaceChatCreationException(
            "Failed to create workplace chat"
        )

    await db.execute(
        insert(ChatMember)
        .values(
            chat_id=chat_id,
            user_id=owner_id,
        )
        .on_conflict_do_nothing(
            index_elements=[
                ChatMember.chat_id,
                ChatMember.user_id,
            ],
        )
    )

    logger.info(
        "Общий чат точки создан или найден: chat_id=%s, workplace_id=%s",
        chat_id,
        workplace_id,
    )

    return chat_id


async def add_member_to_workplace_chat(
    db: AsyncSession,
    workplace_id: int,
    user_id: int,
) -> None:
    """Добавляет пользователя в общий чат торговой точки."""

    chat_id = await db.scalar(
        select(Chat.id).where(
            Chat.workplace_id == workplace_id,
        )
    )

    if chat_id is None:
        logger.warning(
            "Общий чат не найден: workplace_id=%s",
            workplace_id,
        )
        raise WorkplaceChatNotFoundException(
            "Workplace chat not found"
        )

    await db.execute(
        insert(ChatMember)
        .values(
            chat_id=chat_id,
            user_id=user_id,
        )
        .on_conflict_do_nothing(
            index_elements=[
                ChatMember.chat_id,
                ChatMember.user_id,
            ],
        )
    )

    logger.info(
        "Пользователь добавлен в общий чат: user_id=%s, chat_id=%s",
        user_id,
        chat_id,
    )
