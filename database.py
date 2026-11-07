import os
from collections.abc import Generator
from importlib import import_module
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

load_dotenv(Path(__file__).resolve().parent / ".env")


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _create_turso_engine(database_url: str, auth_token: str) -> Engine:
    endpoint = database_url.strip()
    if "://" not in endpoint:
        endpoint = f"libsql://{endpoint}"

    parsed_url = urlsplit(endpoint)
    if (
        parsed_url.scheme != "libsql"
        or not parsed_url.netloc
        or parsed_url.username
        or parsed_url.password
        or parsed_url.path not in ("", "/")
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise RuntimeError(
            "TURSO_DATABASE_URL must be a Turso libsql:// URL or hostname."
        )

    return create_engine(
        URL.create(
            "sqlite+libsql",
            host=parsed_url.netloc,
            query={"secure": "true"},
        ),
        connect_args={"auth_token": auth_token},
        poolclass=NullPool,
    )


turso_database_url = os.getenv("TURSO_DATABASE_URL", "").strip()
turso_auth_token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
if bool(turso_database_url) != bool(turso_auth_token):
    raise RuntimeError(
        "TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must both be configured."
    )

if os.getenv("VERCEL") == "1" and not turso_database_url:
    raise RuntimeError(
        "TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are required on Vercel."
    )

if turso_database_url:
    engine = _create_turso_engine(turso_database_url, turso_auth_token)
else:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        normalized_url = _normalize_database_url(database_url)
        engine_options = {"pool_pre_ping": True}
        if normalized_url.startswith("sqlite:"):
            engine_options["connect_args"] = {"check_same_thread": False}
        engine = create_engine(normalized_url, **engine_options)
    else:
        engine = create_engine(
            URL.create(
                "sqlite",
                database=str(Path(__file__).resolve().with_name("notes.db")),
            ),
            connect_args={"check_same_thread": False},
        )

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def initialize_database() -> None:
    """Create missing application tables without modifying existing data."""
    import_module(f"{__package__}.models" if __package__ else "models")
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
