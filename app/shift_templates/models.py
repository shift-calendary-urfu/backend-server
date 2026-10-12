from sqlalchemy import Integer, String, Boolean, DateTime, Date, ForeignKey, func, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, time, date

from app.core.database import Base

class ShiftTemplate(Base):
    __tablename__ = "shift_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workplace_id: Mapped[int] = mapped_column(ForeignKey("workplaces.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    work_pattern: Mapped[str] = mapped_column(String(20), nullable=False)
    shift_duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    default_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    cycle_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )