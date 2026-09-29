from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, func, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shortlink_api.db.base import Base

if TYPE_CHECKING:
    from shortlink_api.models.user import User


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # base62 of id; the app fills it in after the insert
    code: Mapped[str] = mapped_column(String(16), unique=True)
    long_url: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    deactivated_at: Mapped[datetime | None]
    click_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    last_clicked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped[User | None] = relationship(back_populates="links")

    __table_args__ = (
        Index("ix_links_user_id", "user_id", postgresql_where=text("user_id IS NOT NULL")),
        Index(
            "ix_links_purge_candidates",
            "last_clicked_at",
            "created_at",
            postgresql_where=text("is_active = true"),
        ),
    )
