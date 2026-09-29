from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shortlink_api.config import settings
from shortlink_api.db.session import get_db

app = FastAPI(title=settings.PROJECT_NAME)


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/health")
async def health(db: Annotated[AsyncSession, Depends(get_db)]):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "up"}