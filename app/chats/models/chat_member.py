
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
    false
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# === type checking for SQLAlchemy models ===
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.chats.models.chat import Chat
# ===========================================


class ChatMember(Base):
    __tablename__ = "chat_members"

    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "user_id",
            name="uq_chat_members_chat_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    last_read_message_id: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    is_active_at_closure: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    chat: Mapped["Chat"] = relationship(back_populates="members")
