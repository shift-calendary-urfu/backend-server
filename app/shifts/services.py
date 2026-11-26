from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update

from app.shifts.schemas import (
    ShiftCreate, 
    ShiftResponse, 
    ShiftUpdate, 
    CalendarResponse, 
    ShiftsDuplicate,
    ShiftsDuplicateResponse,
    CalendarReportResponse,
    EmployeeReportItem
)
from app.shifts.model import Shift as ShiftModel

from app.employees.model import Employee as EmployeeModel

from app.users.model import User as UserModel

from app.workplaces.model import Workplace as WorkplaceModel

from app.core.logger import get_logger
from app.core.excel_report import (
    ColumnType,
    ExcelColumn,
    ExcelFile,
    ExcelSheet,
    build_excel_report_async,
)

from app.exceptions import (
    EmployeeNotFoundException,
    ShiftNotFoundException,
    WorkplaceNotFoundException,
    InvalidReportPeriodException
)

import calendar
import datetime as dt
import re


logger=get_logger(__name__)


# ----- Константы и вспомогательные функции для отчёта -----
MINUTES_IN_DAY = 24 * 60

# Допустимый диапазон лет для отчёта
MIN_REPORT_YEAR = 2000
MAX_REPORT_YEAR = 2100


def build_schedule_dates(
    schedule: str | None,
    period: int,
    start_date: dt.date,
) -> tuple[list[dt.date], str, bool]:
    """Рассчитывает рабочие даты цикла от начальной даты включительно.

    Формат цикла — ``рабочие/выходные``. Первый день считается рабочим;
    ``period`` задаёт количество календарных дней цикла. Если расписание
    отсутствует, имеет неверный формат или содержит меньше одного рабочего дня,
    возвращается только начальная дата, а флаг показывает, что цикл не применён.

    Args:
        schedule: Строка цикла, например ``5/2`` или ``7/0``, либо ``None``.
        period: Количество календарных дней для расчёта.
        start_date: Первый день периода и первый день рабочего цикла.

    Returns:
        Список дат смен, описание эффективного графика и флаг применения цикла.
    """
    match = re.fullmatch(r"(\d+)/(\d+)", schedule.strip()) if schedule else None
    if match is None:
        return [start_date], "не задан или некорректен — одна смена", False

    work_days, off_days = (int(value) for value in match.groups())
    if work_days < 1:
        return [start_date], "некорректен — одна смена", False

    dates: list[dt.date] = []
    cycle_length = work_days + off_days
    for day_offset in range(period):
        if day_offset % cycle_length < work_days:
            dates.append(start_date + dt.timedelta(days=day_offset))

    return dates, f"{work_days}/{off_days}", True


def _to_minutes(value: dt.time) -> int:
    """
    Переводит время в количество минут от начала суток.
    """
    return value.hour * 60 + value.minute


def _shift_bounds(start_time: dt.time, end_time: dt.time) -> tuple[int, int]:
    """
    Возвращает начало и конец смены в минутах от начала дня смены.
    Сейчас API не даёт создать смену, где конец раньше начала,
    но если такие смены появятся (через полночь, 22:00–06:00),
    конец переносится на следующие сутки и часы не уходят в минус.
    """
    start = _to_minutes(start_time)
    end = _to_minutes(end_time)

    if end <= start:
        end += MINUTES_IN_DAY

    return start, end


def _minutes_to_hours(minutes: int) -> float:
    return round(minutes / 60, 2)


def _full_name(employee: EmployeeModel) -> str:
    user = employee.user
    parts = [user.second_name, user.first_name, user.third_name]
    return " ".join(part for part in parts if part)


MONTH_NAMES = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)


def build_calendar_report_sheets(
    report: CalendarReportResponse,
    workplace_name: str,
    workplace_address: str | None,
    work_start_time: dt.time,
    work_end_time: dt.time,
) -> list[ExcelSheet]:
    """
    Превращает отчёт за месяц (get_calendar_report) в лист Excel.
    Возвращает только простые значения, чтобы файл можно было
    безопасно собирать в отдельном потоке.
    """
    year, month = (int(part) for part in report.period.split("-"))

    rows = [
        [
            number,
            item.full_name,
            item.hours_worked,
            item.full_shifts_count,
            item.full_shifts_hours,
        ]
        for number, item in enumerate(report.employees, start=1)
    ]

    total_full_shifts = sum(item.full_shifts_count for item in report.employees)
    total_full_hours = round(
        sum(item.full_shifts_hours for item in report.employees), 2
    )

    sheet = ExcelSheet(
        title="Отчёт",
        header_lines=[
            f"Отчёт по сменам: {workplace_name}",
            f"Адрес: {workplace_address or '—'}",
            f"Период: {MONTH_NAMES[month - 1]} {year}",
            f"Режим работы точки: {work_start_time:%H:%M}–{work_end_time:%H:%M}",
            f"Всего смен за месяц: {report.total_shifts}",
        ],
        columns=[
            ExcelColumn("№", ColumnType.INTEGER, width=6),
            ExcelColumn("Сотрудник", width=36),
            ExcelColumn("Отработано часов", ColumnType.NUMBER, width=14),
            ExcelColumn("Полных смен", ColumnType.INTEGER, width=12),
            ExcelColumn("Часов в полных сменах", ColumnType.NUMBER, width=16),
        ],
        rows=rows,
        totals=[
            None,
            "Итого",
            report.total_hours,
            total_full_shifts,
            total_full_hours,
        ],
    )

    return [sheet]
# ----------------------------------------------------------


class ShiftServices:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_shift_by_id(
        self, 
        shift_id: int, 
        workplace_id: int
    ) -> ShiftResponse:
        result = await self.db.execute(
            select(
                ShiftModel,
                UserModel.first_name,
                UserModel.second_name,
                UserModel.third_name,
            )
            .join(EmployeeModel, EmployeeModel.id == ShiftModel.employee_id)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .where(
                ShiftModel.id == shift_id,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
        )

        shift, first_name, second_name, third_name = result.one()

        if not shift:
            logger.warning(
                "Смена не найдена или не активна, shift_id=%s", 
                shift_id
            )
            raise ShiftNotFoundException(
                "Shift not found or not active"
            )

        return ShiftResponse(
            id=shift.id,
            employee_id=shift.employee_id,
            workplace_id=shift.workplace_id,
            date=shift.date,
            start_time=shift.start_time,
            end_time=shift.end_time,
            notes=shift.notes,
            first_name=first_name,
            second_name=second_name,
            third_name=third_name
        )
    

    async def create_shift(
        self, 
        new_shift: ShiftCreate,
        workplace_id: int,
    ) -> ShiftResponse:
        employee = await self.db.scalar(
            select(EmployeeModel)
            .where(
                EmployeeModel.id == new_shift.employee_id,
                EmployeeModel.workplace_id == workplace_id,
                EmployeeModel.is_active
                )
            )
        
        if not employee:
            logger.warning(
                "Работник не найден или не активен, employee_id=%s, workplace_id=%s", 
                new_shift.employee_id, 
                workplace_id
            )
            raise EmployeeNotFoundException(
                "Employee not found or not active"
            )

        shift = ShiftModel(
            workplace_id=workplace_id,
            **new_shift.model_dump(exclude_unset=True)
        )

        self.db.add(shift)
        await self.db.commit()

        logger.info(
            "Смена создана успешно, shift_id=%s, workplace_id=%s", 
            shift.id, workplace_id
        )
        
        return await self.get_shift_by_id(shift.id, workplace_id)


    async def prepare_schedule(
        self,
        workplace_id: int,
        employee_id: int,
        schedule: str | None,
        period: int,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict:
        """Готовит проверенный план смен, не записывая его в базу данных.

        Использует даты из ``build_schedule_dates`` и часы рабочей точки, если
        оба переопределения времени не переданы. Существующие активные смены
        выбранного сотрудника на планируемые даты исключаются из плана. В
        возвращаемом ``summary`` указываются сотрудник, точка, фактический
        период, эффективный цикл, время и число смен; этот текст предназначен
        для показа до подтверждения пользователя.

        Args:
            workplace_id: Идентификатор активной рабочей точки.
            employee_id: Идентификатор активного сотрудника этой точки.
            schedule: Цикл рабочих и выходных дней; некорректное значение
                приводит к плану из одной смены на сегодня.
            period: Количество календарных дней цикла (1–90 проверяется схемой).
            start_time: Необязательное время начала; по умолчанию открытие точки.
            end_time: Необязательное время окончания; по умолчанию закрытие точки.

        Returns:
            Словарь с ``workplace_id``, ``employee_id``, сериализованным списком
            ``shifts``, ``skipped_dates`` и человекочитаемым ``summary``.

        Raises:
            WorkplaceNotFoundException: Если точка отсутствует или неактивна.
            EmployeeNotFoundException: Если сотрудник отсутствует, неактивен
                или не относится к этой точке.
            ValidationError: Если время смен не проходит проверки ``ShiftCreate``.
        """
        workplace = await self.db.scalar(
            select(WorkplaceModel).where(
                WorkplaceModel.id == workplace_id,
                WorkplaceModel.is_active,
            )
        )
        if workplace is None:
            raise WorkplaceNotFoundException("Workplace not found or not active")

        employee_result = await self.db.execute(
            select(
                EmployeeModel,
                UserModel.first_name,
                UserModel.second_name,
                UserModel.third_name,
            )
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .where(
                EmployeeModel.id == employee_id,
                EmployeeModel.workplace_id == workplace_id,
                EmployeeModel.is_active,
            )
        )
        employee_row = employee_result.one_or_none()
        if employee_row is None:
            raise EmployeeNotFoundException("Employee not found or not active")

        employee, first_name, second_name, third_name = employee_row
        dates, effective_schedule, schedule_applied = build_schedule_dates(
            schedule,
            period,
            dt.date.today(),
        )
        shift_start = start_time or workplace.work_start_time.strftime("%H:%M")
        shift_end = end_time or workplace.work_end_time.strftime("%H:%M")
        shifts = []
        for shift_date in dates:
            shift = ShiftCreate(
                employee_id=employee_id,
                date=shift_date,
                start_time=shift_start,
                end_time=shift_end,
            )
            shifts.append(
                {
                    "employee_id": employee_id,
                    "date": shift.date.isoformat(),
                    "start_time": shift.start_time.strftime("%H:%M"),
                    "end_time": shift.end_time.strftime("%H:%M"),
                    "notes": shift.notes,
                }
            )

        existing_dates = set(
            (
                await self.db.scalars(
                    select(ShiftModel.date).where(
                        ShiftModel.workplace_id == workplace_id,
                        ShiftModel.employee_id == employee_id,
                        ShiftModel.date.in_(dates),
                        ShiftModel.is_active,
                        ShiftModel.status != "cancelled",
                    )
                )
            ).all()
        )
        skipped_dates = sorted(existing_dates)
        planned_shifts = [
            shift for shift in shifts
            if dt.date.fromisoformat(shift["date"]) not in existing_dates
        ]

        employee_name = " ".join(
            part for part in (first_name, second_name, third_name) if part
        )
        period_end = (
            dates[0] + dt.timedelta(days=period - 1)
            if schedule_applied
            else dates[0]
        )
        period_description = (
            f"{period} календарных дней ({dates[0]:%d.%m.%Y}–{period_end:%d.%m.%Y})"
            if schedule_applied
            else (
                f"1 день ({dates[0]:%d.%m.%Y}; запрошенный period={period} "
                "не применяется без корректного schedule)"
            )
        )
        summary = (
            f"Сотрудник: {employee_name} (ID {employee_id}); "
            f"рабочая точка: «{workplace.name}» (ID {workplace_id}); "
            f"период: {period_description}; "
            f"график: {effective_schedule}; "
            f"время смен: {shift_start}–{shift_end}; "
            f"новых смен: {len(planned_shifts)}."
        )
        if skipped_dates:
            skipped = ", ".join(date.strftime("%d.%m.%Y") for date in skipped_dates)
            summary += f" Пропустить даты с существующими сменами: {skipped}."

        return {
            "workplace_id": workplace_id,
            "employee_id": employee.id,
            "shifts": planned_shifts,
            "skipped_dates": [date.isoformat() for date in skipped_dates],
            "summary": summary,
        }


    async def create_scheduled_shifts(
        self,
        workplace_id: int,
        employee_id: int,
        shifts: list[ShiftCreate],
    ) -> tuple[int, list[dt.date]]:
        """Создаёт подтверждённые смены, пропуская даты с уже активными сменами.

        Перед записью повторно проверяет активность рабочей точки и сотрудника,
        блокирует запись сотрудника на время операции и повторно ищет конфликты,
        чтобы учесть смены, появившиеся после подготовки плана. Все новые смены
        добавляются и фиксируются одним commit; при пустом списке запрос ничего
        не записывает.

        Args:
            workplace_id: Идентификатор рабочей точки для создаваемых смен.
            employee_id: Активный сотрудник этой рабочей точки.
            shifts: Подтверждённые и предварительно провалидированные данные смен.

        Returns:
            Количество созданных смен и отсортированные даты, пропущенные из-за
            существующих активных смен.

        Raises:
            WorkplaceNotFoundException: Если рабочая точка отсутствует или неактивна.
            EmployeeNotFoundException: Если сотрудник отсутствует, неактивен
                или относится к другой точке.
        """
        workplace_exists = await self.db.scalar(
            select(WorkplaceModel.id).where(
                WorkplaceModel.id == workplace_id,
                WorkplaceModel.is_active,
            )
        )
        if workplace_exists is None:
            raise WorkplaceNotFoundException("Workplace not found or not active")

        employee = await self.db.scalar(
            select(EmployeeModel)
            .where(
                EmployeeModel.id == employee_id,
                EmployeeModel.workplace_id == workplace_id,
                EmployeeModel.is_active,
            )
            .with_for_update()
        )
        if employee is None:
            raise EmployeeNotFoundException("Employee not found or not active")

        dates = [shift.date for shift in shifts]
        existing_dates: set[dt.date] = set()
        if dates:
            existing_dates = set(
                (
                    await self.db.scalars(
                        select(ShiftModel.date).where(
                            ShiftModel.workplace_id == workplace_id,
                            ShiftModel.employee_id == employee_id,
                            ShiftModel.date.in_(dates),
                            ShiftModel.is_active,
                            ShiftModel.status != "cancelled",
                        )
                    )
                ).all()
            )

        new_shifts = [
            ShiftModel(
                workplace_id=workplace_id,
                **shift.model_dump(),
            )
            for shift in shifts
            if shift.date not in existing_dates
        ]
        if new_shifts:
            self.db.add_all(new_shifts)
            await self.db.commit()

        return len(new_shifts), sorted(existing_dates)


    async def update_shift(
        self,
        shift_id: int,
        workplace_id: int,
        update_shift: ShiftUpdate,
    ) -> ShiftResponse:
        shift = await self.db.scalar(
            select(ShiftModel)
            .where(
                ShiftModel.id == shift_id,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
        )

        if not shift:
            logger.warning(
                "Смена не найдена или не активна, shift_id=%s", 
                shift_id
            )
            raise ShiftNotFoundException(
                "Shift not found or not active"
            )

        await self.db.execute(
            update(ShiftModel)
            .where(
                ShiftModel.id == shift_id,
                ShiftModel.workplace_id == shift.workplace_id,
                ShiftModel.is_active
            )
            .values(**update_shift.model_dump())
        )

        await self.db.commit()

        logger.info(
            "Смена обновлена успешно, shift_id=%s", 
            shift.id
        )

        return await self.get_shift_by_id(shift.id, workplace_id)


    async def delete_shift_by_id(
        self,
        shift_id: int,
        workplace_id: int
    ) -> None:
        shift = await self.db.scalar(
            select(ShiftModel)
            .where(
                ShiftModel.id == shift_id,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
        )

        if not shift:
            logger.warning(
                "Смена не найдена или не активна, shift_id=%s", 
                shift_id
            )
            raise ShiftNotFoundException(
                "Shift not found or not active"
            )

        shift.is_active = False

        await self.db.commit()

        logger.info(
            "Смена удалена успешно, shift_id=%s", 
            shift.id
        )


    async def delete_shifts_by_date(
        self,
        date: dt.date,
        workplace_id: int,
    ) -> None:
        result = await self.db.execute(
            update(ShiftModel)
            .where(
                ShiftModel.date == date,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active,
            )
            .values(is_active=False)
            .returning(ShiftModel.id)
        )

        if not result.scalars().all():
            logger.warning(
                "Смены не найдены или не активны, date=%s, workplace_id=%s", 
                date, workplace_id
            )
            raise ShiftNotFoundException(
                f"Shifts not found or not active on this date={date}"
            )

        await self.db.commit()
        
        logger.info(
            "Смены удалены успешно, date=%s, workplace_id=%s", 
            date, workplace_id
        )


    async def get_shifts_by_date(
        self,
        date: dt.date,
        workplace_id: int,
    ) -> list[ShiftResponse]:
        result = await self.db.execute(
            select(
                ShiftModel,
                UserModel.first_name,
                UserModel.second_name,
                UserModel.third_name,
            )
            .join(EmployeeModel, EmployeeModel.id == ShiftModel.employee_id)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .where(
                ShiftModel.date == date,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
        )

        shifts = result.all()

        if not shifts:
            logger.warning(
                "Смены не найдены или не активны, date=%s, workplace_id=%s", 
                date, workplace_id
            )
            raise ShiftNotFoundException(
                f"Shifts not found or not active on this date={date}"
            )

        return [
            ShiftResponse(
                id=shift.id,
                workplace_id=shift.workplace_id,
                employee_id=shift.employee_id,
                date=shift.date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                notes=shift.notes,
                first_name=first_name,
                second_name=second_name,
                third_name=third_name,
            )
            for shift, first_name, second_name, third_name in shifts
        ]
        

    async def get_calendar_shifts(
        self,
        date_from: dt.date,
        date_to: dt.date,
        workplace_id: int,
    ) -> CalendarResponse:
        result = await self.db.execute(
            select(
                ShiftModel,
                UserModel.first_name,
                UserModel.second_name,
                UserModel.third_name,
            )
            .join(EmployeeModel, EmployeeModel.id == ShiftModel.employee_id)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .where(
                ShiftModel.date >= date_from,
                ShiftModel.date <= date_to,
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active
            )
            .order_by(ShiftModel.date)
        )

        shifts = result.all()

        if not shifts:
            logger.warning(
                "Смены не найдены или не активны, start_date=%s, end_date=%s, workplace_id=%s", 
                date_from, date_to, workplace_id
            )
            raise ShiftNotFoundException(
                f"Shifts not found or not active between {date_from} and {date_to}"
            )

        shifts_by_date: dict[dt.date, list[ShiftResponse]] = {}
        for shift, first_name, second_name, third_name in shifts:
            shift_response = ShiftResponse(
                id=shift.id,
                workplace_id=shift.workplace_id,
                employee_id=shift.employee_id,
                date=shift.date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                notes=shift.notes,
                first_name=first_name,
                second_name=second_name,
                third_name=third_name,
            )

            shifts_by_date.setdefault(shift.date, []).append(shift_response)

        logger.info(
            "Смены получены успешно, start_date=%s, end_date=%s, workplace_id=%s", 
            date_from, date_to, workplace_id
        )

        return CalendarResponse(root=shifts_by_date)


    async def duplicate_shifts(
        self,
        duplicate_data: ShiftsDuplicate,
        workplace_id: int,
    ) -> ShiftsDuplicateResponse:
        result = await self.db.execute(
            select(ShiftModel)
            .where(
                ShiftModel.id.in_(duplicate_data.shift_ids),
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.is_active,
            )
        )
        shifts = result.scalars().all()

        found_ids = {shift.id for shift in shifts}
        missing_ids = set(duplicate_data.shift_ids) - found_ids

        if missing_ids:
            logger.warning(
                "Смены не найдены или не активны, missing_ids=%s, workplace_id=%s",
                missing_ids,
                workplace_id,
            )
            raise ShiftNotFoundException(
                f"Shifts not found or not active: {sorted(missing_ids)}"
            )

        new_shifts = [
            ShiftModel(
                employee_id=shift.employee_id,
                workplace_id=shift.workplace_id,
                date=date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                notes=shift.notes,
            )
            for date in duplicate_data.dates
            for shift in shifts
        ]

        self.db.add_all(new_shifts)
        await self.db.flush()

        new_shift_ids = [shift.id for shift in new_shifts]

        await self.db.commit()

        start_date = min(duplicate_data.dates)
        end_date = max(duplicate_data.dates)

        logger.info(
            "Смены успешно размножены, new_shift_ids=%s, workplace_id=%s",
            new_shift_ids,
            workplace_id,
        )

        return ShiftsDuplicateResponse(
            count_duplicated_shifts_created=len(new_shifts),
            workplace_id=workplace_id,
            period={
                "start_date": start_date,
                "end_date": end_date,
            },
            message=(
                f"Смены успешно скопированы на период "
                f"с {start_date} по {end_date}"
            ),
        )


    async def get_calendar_report(
        self,
        workplace_id: int,
        month: int,
        year: int,
    ) -> CalendarReportResponse:
        """
        Составляет отчёт по рабочей точке за месяц.

        Учитываются активные смены, отменённые (status='cancelled') не учитываются
        (план = факт, см. docs/backend-endpoints-spec.md).

        Полная смена — смена, которая покрывает весь график точки
        (начинается не позже открытия и заканчивается не раньше закрытия).
        Если смена длиннее графика, она считается полной, а в часы идёт её фактическая длительность.
        """
        logger.info(
            "Составление отчёта: workplace_id=%s, month=%s, year=%s",
            workplace_id, month, year
        )

        if not 1 <= month <= 12:
            logger.warning("Некорректный месяц для отчёта: month=%s", month)
            raise InvalidReportPeriodException(
                "Month must be between 1 and 12"
            )

        if not MIN_REPORT_YEAR <= year <= MAX_REPORT_YEAR:
            logger.warning("Некорректный год для отчёта: year=%s", year)
            raise InvalidReportPeriodException(
                f"Year must be between {MIN_REPORT_YEAR} and {MAX_REPORT_YEAR}"
            )

        workplace = await self.db.scalar(
            select(WorkplaceModel)
            .where(
                WorkplaceModel.id == workplace_id,
                WorkplaceModel.is_active
            )
        )

        if workplace is None:
            logger.warning(
                "Рабочая точка для отчёта не найдена или не активна, workplace_id=%s",
                workplace_id
            )
            raise WorkplaceNotFoundException(
                "Workplace not found"
            )

        period_start = dt.date(year, month, 1)
        period_end = dt.date(year, month, calendar.monthrange(year, month)[1])

        shifts = (await self.db.scalars(
            select(ShiftModel)
            .options(
                selectinload(ShiftModel.employee)
                .selectinload(EmployeeModel.user)
            )
            .where(
                ShiftModel.workplace_id == workplace_id,
                ShiftModel.date >= period_start,
                ShiftModel.date <= period_end,
                ShiftModel.status != "cancelled",
                ShiftModel.is_active,
            )
        )).all()

        # Активные работники точки попадают в отчёт, даже если у них нет смен за месяц
        active_employees = (await self.db.scalars(
            select(EmployeeModel)
            .options(selectinload(EmployeeModel.user))
            .where(
                EmployeeModel.workplace_id == workplace_id,
                EmployeeModel.is_active
            )
        )).all()

        workplace_start = _to_minutes(workplace.work_start_time)
        workplace_end = _to_minutes(workplace.work_end_time)

        stats: dict[int, dict] = {}

        def get_employee_stats(employee: EmployeeModel) -> dict:
            if employee.id not in stats:
                stats[employee.id] = {
                    "employee": employee,
                    "minutes_worked": 0,
                    "full_shifts_count": 0,
                    "full_shifts_minutes": 0,
                }
            return stats[employee.id]

        for employee in active_employees:
            get_employee_stats(employee)

        total_minutes = 0

        for shift in shifts:
            # Работник мог быть уволен после смены — его смены за месяц всё равно учитываются
            employee_stats = get_employee_stats(shift.employee)

            start, end = _shift_bounds(shift.start_time, shift.end_time)
            duration = end - start

            employee_stats["minutes_worked"] += duration
            total_minutes += duration

            if start <= workplace_start and end >= workplace_end:
                employee_stats["full_shifts_count"] += 1
                employee_stats["full_shifts_minutes"] += duration

        employees_report = [
            EmployeeReportItem(
                employee_id=employee_id,
                full_name=_full_name(item["employee"]),
                hours_worked=_minutes_to_hours(item["minutes_worked"]),
                full_shifts_count=item["full_shifts_count"],
                full_shifts_hours=_minutes_to_hours(item["full_shifts_minutes"]),
            )
            for employee_id, item in stats.items()
        ]
        employees_report.sort(key=lambda item: (item.full_name, item.employee_id))

        report = CalendarReportResponse(
            workplace_id=workplace_id,
            period=f"{year:04d}-{month:02d}",
            total_hours=_minutes_to_hours(total_minutes),
            total_shifts=len(shifts),
            employees=employees_report,
        )

        logger.info(
            "Отчёт составлен успешно, workplace_id=%s, period=%s, смен=%s, часов=%s, работников=%s",
            workplace_id, report.period, report.total_shifts,
            report.total_hours, len(employees_report)
        )

        return report


    async def get_calendar_report_excel(
        self,
        workplace_id: int,
        month: int,
        year: int,
    ) -> ExcelFile:
        """
        Отчёт по рабочей точке за месяц в виде Excel-файла (.xlsx).

        Данные берутся из get_calendar_report, поэтому цифры в файле
        всегда совпадают с JSON-отчётом. Сам файл собирается в отдельном
        потоке (build_excel_report_async) и не блокирует сервер.
        """
        # Проверяет месяц, год и точку; при ошибке выбрасывает исключение
        report = await self.get_calendar_report(workplace_id, month, year)

        workplace = (await self.db.execute(
            select(
                WorkplaceModel.name,
                WorkplaceModel.address,
                WorkplaceModel.work_start_time,
                WorkplaceModel.work_end_time,
            )
            .where(
                WorkplaceModel.id == workplace_id,
                WorkplaceModel.is_active
            )
        )).one_or_none()

        if workplace is None:
            logger.warning(
                "Рабочая точка для Excel-отчёта не найдена или не активна, workplace_id=%s",
                workplace_id
            )
            raise WorkplaceNotFoundException(
                "Workplace not found"
            )

        sheets = build_calendar_report_sheets(
            report=report,
            workplace_name=workplace.name,
            workplace_address=workplace.address,
            work_start_time=workplace.work_start_time,
            work_end_time=workplace.work_end_time,
        )

        content = await build_excel_report_async(sheets)

        logger.info(
            "Excel-отчёт сформирован, workplace_id=%s, period=%s, размер=%s байт",
            workplace_id, report.period, len(content)
        )

        return ExcelFile(
            filename=f"report_{workplace_id}_{report.period}.xlsx",
            content=content,
        )
