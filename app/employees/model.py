from sqlalchemy import Integer, String, Boolean, DateTime, Date, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, date

from app.core.database import Base

class Employee(Base):
    __tablename__ = "employees"

    __table_args__ = (
        UniqueConstraint(
            #Ограничение на UNIQUE (user_id, workplace_id)
            "user_id",
            "workplace_id",
            name="uq_employee_user_workplace"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workplace_id: Mapped[int] = mapped_column(ForeignKey("workplaces.id"), nullable=False, index=True)
    role_in_workplace: Mapped[str] = mapped_column(String(20), default="employee", nullable=False)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True,)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="employees")
    workplace: Mapped["Workplace"] = relationship("Workplace", back_populates="employees")
    shifts: Mapped[list["Shift"]] = relationship("Shift", back_populates="employee")
    shift_templates: Mapped[list["ShiftTemplate"]] = relationship("ShiftTemplate", back_populates="employee")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
