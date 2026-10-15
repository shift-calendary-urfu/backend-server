from sqlalchemy import (
    Integer, 
    String, 
    Text, 
    DateTime, 
    Date, 
    ForeignKey, 
    func, 
    Time, 
    CheckConstraint, 
    Boolean
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, time, date as dt_date

from app.core.database import Base


# === type checking for SQLAlchemy models ===
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.workplaces.model import Workplace
    from app.employees.model import Employee
    
# ===========================================


class Shift(Base):
    __tablename__ = "shifts"

    __table_args__ = (
        #Ограничение на статус 'planned', 'completed', 'cancelled'
        CheckConstraint("status IN ('planned', 'completed', 'cancelled')",
        name='ck_shift_status'
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workplace_id: Mapped[int] = mapped_column(ForeignKey("workplaces.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    date: Mapped[dt_date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean,default=True)


    workplace: Mapped["Workplace"] = relationship("Workplace", back_populates="shifts")
    employee: Mapped["Employee"] = relationship("Employee", back_populates="shifts")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )