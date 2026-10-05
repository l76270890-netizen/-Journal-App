from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from .database import Base
except ImportError:  # pragma: no cover - fallback when run directly from the backend dir
    from database import Base


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    mood: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="Calm"
    )

    tags: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list
    )

    date: Mapped[str] = mapped_column(
        String(40),
        nullable=False
    )

    image: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    favorite: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    user: Mapped["User"] = relationship(back_populates="notes")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(254),
        unique=True,
        nullable=False,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    notes: Mapped[list[Note]] = relationship(back_populates="user")
