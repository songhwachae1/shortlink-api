from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shortlink_api.config import settings


engine = create_async_engine(settings.DB_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
