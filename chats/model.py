from sqlalchemy import (
    Integer,
    String,
    DateTime,
    ForeignKey,
    func,
    CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.core.database import Base


class Chat(Base):
    __tablename__ = "chats"
    __table_args__ = (
        # Ограничение на type чата 'business_chat', 'workplace_chat', 'personal_chat'
        CheckConstraint(
            "type IN ('business_chat', 'workplace_chat', 'personal_chat')",
            name='ck_chat_type'
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    workplace_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('workplaces.id'), nullable=True)
    type: Mapped[str] = mapped_column(String(20), default="workplace_chat", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
