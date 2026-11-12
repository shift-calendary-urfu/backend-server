from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from fastapi.responses import Response

from sqlalchemy.ext.asyncio import AsyncSession

from typing import Annotated

from app.shifts.schemas import (
    ShiftCreate, 
    ShiftResponse,
    ShiftUpdate, 
    CalendarResponse, 
    ShiftsDuplicate, 
    ShiftsDuplicateResponse,
    CalendarReportResponse
)
from app.shifts.services import ShiftServices

from app.users.model import User as UserModel

from app.core.database import get_db
from app.core.security import get_owner_or_admin, get_owner_or_employees
from app.core.excel_report import XLSX_MEDIA_TYPE

from app.exceptions import (
    EmployeeNotFoundException,
    ShiftNotFoundException,
    WorkplaceNotFoundException,
    InvalidReportPeriodException
)

import datetime as dt


router = APIRouter(
    prefix="/shifts",
    tags=["Shifts"]
)


@router.post(
    "/", 
    response_model=ShiftResponse, 
    status_code=status.HTTP_201_CREATED
)
async def create_shift(
    new_shift: ShiftCreate,
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin)
) -> ShiftResponse:
    """
    Создание смены в указанной рабочей точке.
    Доступно только администратору и владельцу.
    """
    try:
        shift_service = ShiftServices(db)
        return await shift_service.create_shift(new_shift, workplace_id)
    except EmployeeNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )


@router.put(
    "/{shift_id}",
    response_model=ShiftResponse,
)
async def update_shift(
    shift_id: Annotated[
        int, 
        Path(
            ge=1, 
            description="ID смены"
        )
    ],
    updated_data : ShiftUpdate,
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin)
) -> ShiftResponse:
    """
    Обновление информации о смене по её ID.
    Доступно только администратору и владельцу.
    """
    try:
        shift_service = ShiftServices(db)
        return await shift_service.update_shift(shift_id, workplace_id, updated_data)
    except ShiftNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )



@router.delete(
    "/{shift_id}",
    response_model=dict[str, str],
)
async def delete_shift_by_id(
    shift_id: Annotated[
        int, 
        Path(
            ge=1, 
            description="ID смены"
        )
    ],
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin)
) -> dict[str, str]:
    """
    Удаление смены по её ID.
    Доступно только администратору и владельцу.
    """
    try:
        shift_service = ShiftServices(db)
        await shift_service.delete_shift_by_id(shift_id, workplace_id)
        return {"message": "Смена успешно удалена"}
    except ShiftNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )


@router.delete(
    "/",
    response_model=dict[str, str],
)
async def delete_shifts_by_date(
    date: Annotated[
        dt.date, 
        Query(
            description="Дата, смены которой будут удалены (в формате YYYY-MM-DD)"
        )
    ],
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_admin)
) -> dict[str, str]:
    """
    Удаление всех смен в указанную дату.
    Доступно только администратору и владельцу.
    """
    try:
        shift_service = ShiftServices(db)
        await shift_service.delete_shifts_by_date(date, workplace_id)
        return {"message": f"Смены успешно удалены, дата {date}"}
    except ShiftNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )


@router.get(
    "/{shift_id}",
    response_model=ShiftResponse,
)
async def get_shift_by_id(
    shift_id: Annotated[
        int, 
        Path(
            ge=1, 
            description="ID смены"
        )
    ],
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_owner_or_employees)
) -> ShiftResponse:
    """
    Получение информации о смене по её ID.
    """
    try:
        shift_service = ShiftServices(db)
        return await shift_service.get_shift_by_id(shift_id, workplace_id)
    except ShiftNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )


@router.get(
    "/",
    response_model=list[ShiftResponse],
)
async def get_shifts_by_date(
    date: Annotated[
        dt.date, 
        Query(
            description="Дата, смены которой будут получены (в формате YYYY-MM-DD)"
        )
    ],
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    _: Annotated[
        UserModel, 
        Depends(get_owner_or_employees)
    ]
) -> list[ShiftResponse]:
    """
    Получение всех смен в указанную дату.
    Получение доступно владельцу и сотрудникам рабочего пространства.
    """
    try:
        shift_service = ShiftServices(db)
        return await shift_service.get_shifts_by_date(date, workplace_id)
    except ShiftNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )


@router.get(
    '/calendar/',
    response_model=CalendarResponse,
)
async def get_calendar_shifts(
    date_from: Annotated[
        dt.date, 
        Query(
            description="Дата начала периода (в формате YYYY-MM-DD)"
        )
    ],
    date_to: Annotated[
        dt.date, 
        Query(
            description="Дата окончания периода (в формате YYYY-MM-DD)"
        )
    ],
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    _: Annotated[
        UserModel, 
        Depends(get_owner_or_employees)
    ]
) -> CalendarResponse:
    """
    Получение всех смен в указанном периоде.
    Получение доступно владельцу и сотрудникам рабочего пространства.
    """
    try:
        shift_service = ShiftServices(db)
        return await shift_service.get_calendar_shifts(date_from, date_to, workplace_id)
    except ShiftNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )


@router.post(
    "/duplicate/",
    response_model=ShiftsDuplicateResponse,
)
async def duplicate_shifts(
    duplicate_data: ShiftsDuplicate,
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    _: Annotated[
        UserModel, 
        Depends(get_owner_or_admin)
    ]
) -> ShiftsDuplicateResponse:
    """
    Размножение смен на указанные даты.
    Доступно только администратору и владельцу.
    """
    try:
        shift_service = ShiftServices(db)
        return await shift_service.duplicate_shifts(duplicate_data, workplace_id)
    except ShiftNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )


@router.get(
    "/reports/calendar",
    response_model=CalendarReportResponse,
)
async def get_calendar_report(
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    month: Annotated[
        int, 
        Query(
            description="Месяц отчёта (1–12)"
        )
    ],
    year: Annotated[
        int, 
        Query(
            description="Год отчёта (например, 2026)"
        )
    ],
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    _: Annotated[
        UserModel, 
        Depends(get_owner_or_admin)
    ]
) -> CalendarReportResponse:
    """
    Отчёт по рабочей точке за месяц: период, общее количество часов и смен,
    а для каждого работника — отработанные часы, количество полных смен
    и часы полных смен.
    Доступно только администратору и владельцу.
    """
    try:
        shift_service = ShiftServices(db)
        return await shift_service.get_calendar_report(workplace_id, month, year)
    except InvalidReportPeriodException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.msg
        )
    except WorkplaceNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )


@router.get(
    "/reports/calendar/excel",
    response_class=Response,
    responses={
        200: {
            "content": {XLSX_MEDIA_TYPE: {}},
            "description": "Excel-файл (.xlsx) с отчётом за месяц",
        },
        400: {"description": "Некорректный месяц или год"},
        404: {"description": "Рабочая точка не найдена"},
    },
)
async def get_calendar_report_excel(
    workplace_id: Annotated[
        int, 
        Query(
            ge=1, 
            description="ID рабочего пространства"
        )
    ],
    month: Annotated[
        int, 
        Query(
            description="Месяц отчёта (1–12)"
        )
    ],
    year: Annotated[
        int, 
        Query(
            description="Год отчёта (например, 2026)"
        )
    ],
    db: Annotated[
        AsyncSession, 
        Depends(get_db)
    ],
    _: Annotated[
        UserModel, 
        Depends(get_owner_or_admin)
    ]
) -> Response:
    """
    Скачивание отчёта по рабочей точке за месяц в формате Excel (.xlsx).
    Содержимое совпадает с GET /shifts/reports/calendar.
    Доступно только администратору и владельцу.
    """
    try:
        shift_service = ShiftServices(db)
        report_file = await shift_service.get_calendar_report_excel(
            workplace_id, month, year
        )
    except InvalidReportPeriodException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.msg
        )
    except WorkplaceNotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.msg
        )

    return Response(
        content=report_file.content,
        media_type=report_file.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{report_file.filename}"',
        },
    )
