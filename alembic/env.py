import asyncio  # Добавили для запуска асинхронного цикла
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
# Импортируем асинхронный движок
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.core.database import Base  # Путь к вашему Base
from app.employees.model import Employee
from app.shift_templates.models import ShiftTemplate
from app.shifts.model import Shift
from app.users.model import User
from app.workplaces.model import Workplace

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Гарантируем, что URL базы данных подставляется из настроек Pydantic
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# Новая вспомогательная функция для выполнения миграций внутри синхронного контекста SQLAlchemy
def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Получаем URL из настроек
    database_url = settings.DATABASE_URL

    # Если в .env случайно указан postgresql:// вместо postgresql+asyncpg://, исправляем на лету
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )

    # Создаем асинхронный движок
    connectable = create_async_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Запускаем online-миграции через asyncio event loop
    asyncio.run(run_migrations_online())
