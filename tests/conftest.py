"""Фикстуры API-тестов.

База поднимается в отдельном файле SQLite на каждый тест.
Код приложения не меняется: сессия подменяется через dependency_overrides.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import DefaultClause

from app.core.database import Base, get_db
from app.main import app


def _make_sqlite_defaults() -> None:
    """Подменяет server_default, которые SQLite не умеет выполнить как есть.

    В моделях стоят now() и today(). В PostgreSQL now() есть, today() — нет.
    CURRENT_TIMESTAMP и CURRENT_DATE корректны и для SQLite, и для PostgreSQL.
    Меняется только метаданные в процессе тестов, файлы app/ не трогаются.
    """
    for table in Base.metadata.tables.values():
        for column in table.columns:
            server_default = column.server_default
            if server_default is None:
                continue
            arg = getattr(server_default, "arg", None)
            sql = str(arg).lower()
            if "today" in sql:
                column.server_default = DefaultClause(text("CURRENT_DATE"))
            elif "now" in sql:
                column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest_asyncio.fixture
async def session_factory():
    tmp = tempfile.TemporaryDirectory()
    db_path = Path(tmp.name) / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        poolclass=NullPool,
    )
    event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    _make_sqlite_defaults()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    try:
        yield factory
    finally:
        await engine.dispose()
        tmp.cleanup()


@pytest_asyncio.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
