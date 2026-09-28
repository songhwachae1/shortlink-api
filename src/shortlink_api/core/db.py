from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from shortlink_api.config import settings


engine = create_async_engine(settings.DB_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session