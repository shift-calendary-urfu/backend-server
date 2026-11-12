"""
Генератор Excel-отчётов (.xlsx) для проекта "Календарь смен".

Модуль ничего не знает о сменах, сотрудниках и базе данных: он принимает
уже подготовленные данные (листы, колонки, строки) и возвращает готовый
файл в виде байтов. Поэтому его можно переиспользовать для любых отчётов.

Создание файла — синхронная операция, нагружающая процессор. Внутри
асинхронного кода её нужно вызывать через `build_excel_report_async`,
которая выполняет работу в отдельном потоке и не блокирует event loop.

Использование:
    from app.core.excel_report import (
        ExcelColumn, ExcelSheet, ColumnType, build_excel_report_async
    )

    sheet = ExcelSheet(
        title="Смены",
        header_lines=["Отчёт по сменам", "Период: 01.11.2026 — 30.11.2026"],
        columns=[
            ExcelColumn("Дата", ColumnType.DATE, width=12),
            ExcelColumn("Сотрудник", width=30),
            ExcelColumn("Часы", ColumnType.NUMBER, width=8),
        ],
        rows=[[date(2026, 11, 2), "Иванов Иван", 9.0]],
        totals=["Итого", None, 9.0],
    )
    content: bytes = await build_excel_report_async([sheet])
"""

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from typing import Any

from fastapi.concurrency import run_in_threadpool
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, Cell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.core.logger import get_logger


logger = get_logger(__name__)


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Ограничения Excel на название листа
_SHEET_TITLE_MAX_LENGTH = 31
_SHEET_TITLE_FORBIDDEN_RE = re.compile(r"[\[\]:*?/\\]")


class ColumnType(str, Enum):
    """
    Тип данных колонки. Определяет формат отображения ячеек в Excel.
    """
    TEXT = "text"
    INTEGER = "integer"
    NUMBER = "number"
    DATE = "date"
    TIME = "time"


# Формат отображения для каждого типа колонки
_NUMBER_FORMATS: dict[ColumnType, str] = {
    ColumnType.TEXT: "@",
    ColumnType.INTEGER: "0",
    ColumnType.NUMBER: "0.0",
    ColumnType.DATE: "DD.MM.YYYY",
    ColumnType.TIME: "HH:MM",
}


@dataclass(frozen=True, slots=True)
class ExcelColumn:
    """
    Описание колонки таблицы.
    """
    title: str
    type: ColumnType = ColumnType.TEXT
    width: int = 15


@dataclass(slots=True)
class ExcelSheet:
    """
    Описание одного листа Excel.

    header_lines — строки над таблицей (название отчёта, период и т.п.).
    rows — данные; длина каждой строки должна совпадать с количеством колонок.
    totals — необязательная итоговая строка под таблицей.
    """
    title: str
    columns: Sequence[ExcelColumn]
    rows: Sequence[Sequence[Any]]
    header_lines: Sequence[str] = field(default_factory=tuple)
    totals: Sequence[Any] | None = None


@dataclass(frozen=True, slots=True)
class ExcelFile:
    """
    Готовый файл для отправки клиенту.
    """
    filename: str
    content: bytes
    media_type: str = XLSX_MEDIA_TYPE


# ----- Стили -----
_TITLE_FONT = Font(bold=True, size=14)
_SUBTITLE_FONT = Font(size=11)
_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill(fill_type="solid", start_color="FFD9E1F2", end_color="FFD9E1F2")
_TOTALS_FONT = Font(bold=True)
_TOTALS_FILL = PatternFill(fill_type="solid", start_color="FFF2F2F2", end_color="FFF2F2F2")
_THIN = Side(style="thin", color="FFBFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
_CELL_ALIGNMENT = Alignment(vertical="top")
_TEXT_ALIGNMENT = Alignment(vertical="top", wrap_text=True)
# -----------------


def _safe_sheet_title(title: str, used: set[str]) -> str:
    """
    Приводит название листа к требованиям Excel: без запрещённых символов,
    не длиннее 31 символа и без повторов внутри одной книги.
    """
    base = " ".join(_SHEET_TITLE_FORBIDDEN_RE.sub(" ", title).split()) or "Лист"
    base = base[:_SHEET_TITLE_MAX_LENGTH].rstrip()

    candidate = base
    counter = 2
    while candidate.lower() in used:
        suffix = f" ({counter})"
        candidate = base[: _SHEET_TITLE_MAX_LENGTH - len(suffix)] + suffix
        counter += 1

    used.add(candidate.lower())
    return candidate


def _write_value(cell: Cell, value: Any, column_type: ColumnType) -> None:
    """
    Записывает значение в ячейку и задаёт формат отображения.
    """
    if isinstance(value, str):
        # Управляющие символы openpyxl не принимает (IllegalCharacterError)
        value = ILLEGAL_CHARACTERS_RE.sub("", value)

    cell.value = value

    if isinstance(value, str):
        # Строку, начинающуюся с "=", openpyxl сохранит как формулу.
        # Пользовательский текст (имена, примечания) формулой быть не должен,
        # иначе Excel выполнит его при открытии файла.
        cell.data_type = "s"

    if value is not None and not isinstance(value, str):
        cell.number_format = _NUMBER_FORMATS[column_type]

    if column_type is ColumnType.TEXT:
        cell.alignment = _TEXT_ALIGNMENT
    else:
        cell.alignment = _CELL_ALIGNMENT


def _check_row_length(sheet: ExcelSheet, row: Sequence[Any], what: str) -> None:
    if len(row) != len(sheet.columns):
        raise ValueError(
            f"Лист '{sheet.title}': {what} содержит {len(row)} значений, "
            f"а колонок {len(sheet.columns)}"
        )


def _fill_sheet(ws: Worksheet, sheet: ExcelSheet) -> None:
    """
    Заполняет лист: шапка отчёта, заголовок таблицы, данные, итоги.
    """
    columns_count = len(sheet.columns)
    row_index = 1

    # Шапка отчёта
    for line_number, line in enumerate(sheet.header_lines):
        cell = ws.cell(row=row_index, column=1)
        _write_value(cell, line, ColumnType.TEXT)
        cell.font = _TITLE_FONT if line_number == 0 else _SUBTITLE_FONT
        cell.alignment = Alignment(vertical="center")
        if columns_count > 1:
            ws.merge_cells(
                start_row=row_index,
                start_column=1,
                end_row=row_index,
                end_column=columns_count,
            )
        row_index += 1

    if sheet.header_lines:
        # Пустая строка между шапкой и таблицей
        row_index += 1

    # Заголовок таблицы
    header_row = row_index
    for col_index, column in enumerate(sheet.columns, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=column.title)
        cell.data_type = "s"
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
        cell.alignment = _HEADER_ALIGNMENT
        ws.column_dimensions[get_column_letter(col_index)].width = column.width
    row_index += 1

    # Данные
    first_data_row = row_index
    for row in sheet.rows:
        _check_row_length(sheet, row, f"строка {row_index}")
        for col_index, (value, column) in enumerate(zip(row, sheet.columns, strict=True), start=1):
            cell = ws.cell(row=row_index, column=col_index)
            _write_value(cell, value, column.type)
            cell.border = _BORDER
        row_index += 1
    last_data_row = row_index - 1

    # Закрепляем заголовок таблицы при прокрутке
    ws.freeze_panes = ws.cell(row=first_data_row, column=1)

    # Фильтры в заголовке таблицы (только если есть данные)
    if last_data_row >= first_data_row:
        ws.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(columns_count)}{last_data_row}"
        )

    # Настройки печати: альбомная ориентация, по ширине одной страницы,
    # заголовок таблицы повторяется на каждой странице
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"

    # Итоговая строка
    if sheet.totals is not None:
        _check_row_length(sheet, sheet.totals, "итоговая строка")
        for col_index, (value, column) in enumerate(
            zip(sheet.totals, sheet.columns, strict=True), start=1
        ):
            cell = ws.cell(row=row_index, column=col_index)
            _write_value(cell, value, column.type)
            cell.font = _TOTALS_FONT
            cell.fill = _TOTALS_FILL
            cell.border = _BORDER


def build_excel_report(sheets: Sequence[ExcelSheet]) -> bytes:
    """
    Собирает книгу Excel из листов и возвращает содержимое .xlsx файла.

    Функция синхронная и нагружает процессор. Из асинхронного кода
    вызывайте `build_excel_report_async`.
    """
    if not sheets:
        raise ValueError("Отчёт должен содержать хотя бы один лист")

    workbook = Workbook()
    # Убираем пустой лист, который openpyxl создаёт по умолчанию
    workbook.remove(workbook.active)

    used_titles: set[str] = set()
    for sheet in sheets:
        ws = workbook.create_sheet(title=_safe_sheet_title(sheet.title, used_titles))
        _fill_sheet(ws, sheet)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def build_excel_report_async(sheets: Sequence[ExcelSheet]) -> bytes:
    """
    Асинхронная обёртка над `build_excel_report`.

    Файл собирается в пуле потоков, поэтому сервер продолжает обрабатывать
    другие запросы, пока строится отчёт. В `sheets` должны быть только
    обычные значения (str, int, float, date, time), а не ORM-объекты:
    сессия базы данных не потокобезопасна.
    """
    started = time.perf_counter()
    content = await run_in_threadpool(build_excel_report, sheets)
    logger.info(
        "Excel-отчёт собран: листов=%s, размер=%s байт, время=%.3f с",
        len(sheets),
        len(content),
        time.perf_counter() - started,
    )
    return content
