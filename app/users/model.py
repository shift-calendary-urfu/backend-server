from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, Integer, Boolean, func

from datetime import datetime

from app.core.database import Base


# === type checking for SQLAlchemy models ===
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.workplaces.model import Workplace
    from app.employees.model import Employee
    
# ===========================================


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

    employees: Mapped[list["Employee"]] = relationship("Employee", back_populates="user")
    # Рабочие точки созданные пользователем
    workplaces: Mapped[list["Workplace"]] = relationship("Workplace", back_populates="user")
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    