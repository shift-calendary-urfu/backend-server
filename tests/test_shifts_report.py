from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.core.excel_report import XLSX_MEDIA_TYPE

from tests.helpers import (
    add_employee,
    create_shift,
    create_workplace,
    register_and_login,
)

OWNER_OR_ADMIN = "You must be the owner or admin of this workplace"
REPORT_URL = "/shifts/reports/calendar"
EXCEL_URL = "/shifts/reports/calendar/excel"

# Строка Excel, с которой начинается таблица: 5 строк шапки + пустая строка
HEADER_ROW = 7


def _params(workplace_id: int, **extra) -> dict:
    return {"workplace_id": workplace_id, **extra}


def _table(ws) -> list[tuple]:
    """Строки таблицы без шапки отчёта: заголовок, данные, итог."""
    return list(ws.iter_rows(min_row=HEADER_ROW, values_only=True))


@pytest.mark.asyncio
async def test_excel_report_requires_token(client):
    response = await client.get(EXCEL_URL, params=_params(1, month=11, year=2026))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_excel_report_matches_json_report(client, session_factory):
    _owner, headers = await register_and_login(client)
    worker, _ = await register_and_login(
        client, first_name="Анна", second_name="Смирнова", third_name="Петровна"
    )
    idle, _ = await register_and_login(
        client, first_name="Борис", second_name="Борисов"
    )
    # Точка работает с 09:00 до 21:00 (значение по умолчанию в helpers)
    workplace = await create_workplace(client, headers, name="ПВЗ на Ленина")
    employee_id = await add_employee(
        session_factory, user_id=worker["id"], workplace_id=workplace["id"]
    )
    # Активный сотрудник без смен тоже попадает в отчёт
    await add_employee(session_factory, user_id=idle["id"], workplace_id=workplace["id"])

    # Полная смена (12 ч) и неполная (9 ч)
    await create_shift(
        client, headers, workplace["id"], employee_id,
        date="2026-11-02", start_time="09:00", end_time="21:00",
    )
    await create_shift(
        client, headers, workplace["id"], employee_id,
        date="2026-11-03", start_time="09:00", end_time="18:00",
    )
    # Удалённая смена и смена другого месяца в отчёт не попадают
    removed = await create_shift(
        client, headers, workplace["id"], employee_id, date="2026-11-04"
    )
    await client.delete(
        f"/shifts/{removed['id']}", params=_params(workplace["id"]), headers=headers
    )
    await create_shift(client, headers, workplace["id"], employee_id, date="2026-12-01")

    params = _params(workplace["id"], month=11, year=2026)
    json_report = await client.get(REPORT_URL, params=params, headers=headers)
    response = await client.get(EXCEL_URL, params=params, headers=headers)

    assert json_report.status_code == 200, json_report.text
    assert json_report.json()["total_hours"] == 21
    assert json_report.json()["total_shifts"] == 2

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == XLSX_MEDIA_TYPE
    assert response.headers["content-disposition"] == (
        f'attachment; filename="report_{workplace["id"]}_2026-11.xlsx"'
    )

    workbook = load_workbook(BytesIO(response.content))
    assert workbook.sheetnames == ["Отчёт"]
    ws = workbook["Отчёт"]
    assert ws["A1"].value == "Отчёт по сменам: ПВЗ на Ленина"
    assert ws["A3"].value == "Период: ноябрь 2026"
    assert ws["A4"].value == "Режим работы точки: 09:00–21:00"
    assert ws["A5"].value == "Всего смен за месяц: 2"

    header, idle_row, worker_row, totals = _table(ws)
    assert header == (
        "№", "Сотрудник", "Отработано часов", "Полных смен", "Часов в полных сменах"
    )
    assert idle_row == (1, "Борисов Борис Иванович", 0, 0, 0)
    assert worker_row == (2, "Смирнова Анна Петровна", 21, 1, 12)
    assert totals == (None, "Итого", 21, 1, 12)

    # Цифры в Excel совпадают с JSON-отчётом
    json_employees = {
        item["full_name"]: item for item in json_report.json()["employees"]
    }
    smirnova = json_employees["Смирнова Анна Петровна"]
    assert worker_row[2:] == (
        smirnova["hours_worked"],
        smirnova["full_shifts_count"],
        smirnova["full_shifts_hours"],
    )


@pytest.mark.asyncio
async def test_excel_report_permissions(client, session_factory):
    _owner, owner_headers = await register_and_login(client)
    admin, admin_headers = await register_and_login(client)
    worker, worker_headers = await register_and_login(client)
    _stranger, stranger_headers = await register_and_login(client)
    workplace = await create_workplace(client, owner_headers)
    await add_employee(
        session_factory, user_id=admin["id"], workplace_id=workplace["id"], role="admin"
    )
    await add_employee(session_factory, user_id=worker["id"], workplace_id=workplace["id"])

    params = _params(workplace["id"], month=11, year=2026)
    by_owner = await client.get(EXCEL_URL, params=params, headers=owner_headers)
    by_admin = await client.get(EXCEL_URL, params=params, headers=admin_headers)
    by_worker = await client.get(EXCEL_URL, params=params, headers=worker_headers)
    by_stranger = await client.get(EXCEL_URL, params=params, headers=stranger_headers)

    # Месяц без смен — файл всё равно формируется
    assert by_owner.status_code == 200
    assert by_owner.headers["content-type"] == XLSX_MEDIA_TYPE
    assert by_admin.status_code == 200
    assert by_worker.status_code == 403
    assert by_worker.json()["detail"] == OWNER_OR_ADMIN
    assert by_stranger.status_code == 403
    assert by_stranger.json()["detail"] == OWNER_OR_ADMIN


@pytest.mark.asyncio
async def test_excel_report_bad_period_and_deleted_workplace(client, session_factory):
    _owner, headers = await register_and_login(client)
    workplace = await create_workplace(client, headers)

    bad_month = await client.get(
        EXCEL_URL, params=_params(workplace["id"], month=13, year=2026), headers=headers
    )
    bad_year = await client.get(
        EXCEL_URL, params=_params(workplace["id"], month=11, year=1999), headers=headers
    )
    missing_month = await client.get(
        EXCEL_URL, params=_params(workplace["id"], year=2026), headers=headers
    )

    await client.delete(f"/workplaces/{workplace['id']}", headers=headers)
    deleted = await client.get(
        EXCEL_URL, params=_params(workplace["id"], month=11, year=2026), headers=headers
    )

    assert bad_month.status_code == 400
    assert bad_month.json()["detail"] == "Month must be between 1 and 12"
    assert bad_year.status_code == 400
    assert bad_year.json()["detail"] == "Year must be between 2000 and 2100"
    assert missing_month.status_code == 422
    assert deleted.status_code == 404
    assert deleted.json()["detail"] == "Workplace not found"
