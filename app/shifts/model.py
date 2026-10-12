from sqlalchemy import Integer, String, Text, DateTime, Date, ForeignKey, func, Time, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, time, date

from app.core.database import Base

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
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

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