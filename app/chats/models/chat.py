
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# === type checking for SQLAlchemy models ===
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.chats.models.chat_member import ChatMember
    from app.chats.models.message import Message
# ===========================================


class ChatType(str, Enum):
    WORKPLACE = "workplace"
    DIRECT = "direct"


class Chat(Base):
    __tablename__ = "chats"

    __table_args__ = (
        CheckConstraint(
            "(type = 'workplace' AND workplace_id IS NOT NULL) "
            "OR (type = 'direct' AND workplace_id IS NULL)",
            name="ck_chats_type_workplace_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    type: Mapped[ChatType] = mapped_column(
        SQLAlchemyEnum(
            ChatType,
            name="chat_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )

    workplace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workplaces.id"),
        unique=True,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    members: Mapped[list["ChatMember"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
    )
