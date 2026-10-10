from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase 

from collections.abc import AsyncGenerator

from app.config import settings


engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    expire_on_commit=False, 
    class_=AsyncSession
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


class Base(DeclarativeBase):
    pass