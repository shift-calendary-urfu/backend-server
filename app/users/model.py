from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, DateTime, Integer, Boolean, func

from datetime import datetime

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    first_name: Mapped[str] = mapped_column(String(255))
    second_name: Mapped[str] = mapped_column(String(255))
    third_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(12))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    