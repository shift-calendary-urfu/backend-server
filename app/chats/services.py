from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats.models import Chat, ChatMember, Message
from app.chats.models.chat import ChatType
from app.chats.schemas import ChatListItem

from app.employees.model import Employee

from app.users.model import User

from app.workplaces.model import Workplace

from app.core.logger import get_logger

from app.exceptions import (
    WorkplaceChatCreationException,
    WorkplaceChatNotFoundException,
)


logger = get_logger(__name__)


class ChatServices:
    def __init__(self, db: AsyncSession):
        self.db = db
    async def ensure_workplace_chat(
        self,
        workplace_id: int,
        owner_id: int,
        title: str,
    ) -> int:
        """Создаёт общий чат торговой точки и добавляет владельца."""

        stmt = (
            insert(Chat)
            .values(
                type=ChatType.WORKPLACE,
                workplace_id=workplace_id,
                title=title,
            )
            .on_conflict_do_nothing(
                index_elements=[Chat.workplace_id],
            )
            .returning(Chat.id)
        )

        chat_id = await self.db.scalar(stmt)

        if chat_id is None:
            chat_id = await self.db.scalar(
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

        await self.db.execute(
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
        self,
        workplace_id: int,
        user_id: int,
    ) -> None:
        """Добавляет пользователя в общий чат торговой точки."""

        chat_id = await self.db.scalar(
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

        await self.db.execute(
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
        
    async def get_chats(
        self, 
        user_id: int
    ) -> list[ChatListItem]:
        """Возвращает список чатов пользователя."""

        other_member = aliased(ChatMember)
        other_user = aliased(User)

        # Имя второго участника личного чата
        direct_title = (
            select(
                func.concat_ws(
                    " ",
                    other_user.first_name,
                    other_user.second_name,
                    other_user.third_name,
                )
            )
            .select_from(other_member)
            .join(other_user, other_user.id == other_member.user_id)
            .where(
                other_member.chat_id == Chat.id,
                other_member.user_id != user_id,
            )
            .limit(1)
            .scalar_subquery()
        )

        # Последнее сообщение
        last_message = (
            select(Message.text)
            .where(Message.chat_id == Chat.id)
            .order_by(Message.id.desc())
            .limit(1)
            .scalar_subquery()
        )

        last_message_at = (
            select(Message.created_at)
            .where(Message.chat_id == Chat.id)
            .order_by(Message.id.desc())
            .limit(1)
            .scalar_subquery()
        )

        # Количество непрочитанных сообщений
        unread_count = (
            select(func.count(Message.id))
            .where(
                Message.chat_id == Chat.id,
                Message.id > ChatMember.last_read_message_id,
                or_(
                    Message.sender_id.is_(None),
                    Message.sender_id != user_id,
                ),
            )
            .scalar_subquery()
        )

        # Проверка активного сотрудника
        is_active_employee = exists(
            select(1).where(
                Employee.workplace_id == Chat.workplace_id,
                Employee.user_id == user_id,
                Employee.is_active.is_(True),
            )
        )

        # Проверка доступа к рабочему чату
        can_access_workplace = or_(
            and_(
                Workplace.is_active.is_(True),
                or_(
                    Workplace.owner_id == user_id,
                    is_active_employee,
                ),
            ),
            and_(
                Workplace.is_active.is_(False),
                ChatMember.is_active_at_closure.is_(True),
            ),
        )

        stmt = (
            select(
                Chat.id.label("id"),
                Chat.type.label("type"),
                Chat.workplace_id.label("workplace_id"),
                func.coalesce(
                    case(
                        (Chat.type == ChatType.WORKPLACE, Chat.title),
                        else_=direct_title,
                    ),
                    "Личный чат",
                ).label("title"),
                case(
                    (
                        and_(
                            Chat.type == ChatType.WORKPLACE,
                            Workplace.is_active.is_(False),
                        ),
                        True,
                    ),
                    else_=False,
                ).label("is_readonly"),
                unread_count.label("unread_count"),
                last_message.label("last_message_text"),
                last_message_at.label("last_message_at"),
            )
            .join(ChatMember, ChatMember.chat_id == Chat.id)
            .outerjoin(Workplace, Workplace.id == Chat.workplace_id)
            .where(
                ChatMember.user_id == user_id,
                or_(
                    Chat.type == ChatType.DIRECT,
                    and_(
                        Chat.type == ChatType.WORKPLACE,
                        can_access_workplace,
                    ),
                ),
            )
            .order_by(last_message_at.desc().nulls_last(), Chat.id.desc())
        )

        result = await self.db.execute(stmt)

        return [
            ChatListItem.model_validate(dict(row))
            for row in result.mappings().all()
        ]