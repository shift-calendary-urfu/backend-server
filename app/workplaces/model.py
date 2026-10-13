from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, func, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, time

from app.core.database import Base


# === type checking for SQLAlchemy models ===
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.employees.model import Employee
    from app.shifts.model import Shift
    from app.shift_templates.models import ShiftTemplate
    from app.users.model import User
    
# ===========================================


class Workplace(Base):
    __tablename__ = "workplaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    workplace_type: Mapped[str] = mapped_column(String(50), nullable=False)
    work_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    work_end_time: Mapped[time] = mapped_column(Time, nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    user: Mapped["User"] = relationship("User", back_populates="workplaces")
    employees: Mapped[list["Employee"]] = relationship("Employee", back_populates="workplace")
    shifts: Mapped[list["Shift"]] = relationship("Shift", back_populates="workplace")
    shift_templates: Mapped[list["ShiftTemplate"]] = relationship("ShiftTemplate", back_populates="workplace")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )