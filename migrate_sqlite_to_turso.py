import argparse
import json
import sqlite3
from pathlib import Path

from sqlalchemy import func, select

try:
    from .database import SessionLocal, initialize_database
    from .models import Note, User, UserAppLock
except ImportError:  # pragma: no cover - direct execution from backend directory
    from database import SessionLocal, initialize_database
    from models import Note, User, UserAppLock


DEFAULT_SOURCE = Path(__file__).resolve().parent.parent / "notes.db"


def _read_source(
    source_path: Path,
) -> tuple[list[User], list[Note], list[UserAppLock]]:
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source database not found: {source_path}")

    source_uri = f"{source_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing_tables = {"users", "notes"} - tables
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise RuntimeError(f"SQLite source is missing required tables: {missing}")

        users = [
            User(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                name=row["name"],
                hashed_password=row["hashed_password"],
            )
            for row in connection.execute(
                "SELECT id, username, email, name, hashed_password "
                "FROM users ORDER BY id"
            )
        ]
        notes = [
            Note(
                id=row["id"],
                title=row["title"],
                body=row["body"],
                mood=row["mood"],
                tags=json.loads(row["tags"]),
                date=row["date"],
                image=row["image"],
                favorite=bool(row["favorite"]),
                archived=bool(row["archived"]),
                user_id=row["user_id"],
            )
            for row in connection.execute(
                "SELECT id, title, body, mood, tags, date, image, favorite, "
                "archived, user_id FROM notes ORDER BY id"
            )
        ]

        locks = []
        if "user_app_locks" in tables:
            locks = [
                UserAppLock(
                    user_id=row["user_id"],
                    lock_type=row["lock_type"],
                    hashed_secret=row["hashed_secret"],
                )
                for row in connection.execute(
                    "SELECT user_id, lock_type, hashed_secret "
                    "FROM user_app_locks ORDER BY user_id"
                )
            ]

    return users, notes, locks


def migrate(source_path: Path) -> tuple[int, int, int]:
    users, notes, locks = _read_source(source_path)
    initialize_database()

    with SessionLocal.begin() as db:
        existing_counts = (
            db.scalar(select(func.count()).select_from(User)) or 0,
            db.scalar(select(func.count()).select_from(Note)) or 0,
            db.scalar(select(func.count()).select_from(UserAppLock)) or 0,
        )
        if any(existing_counts):
            raise RuntimeError(
                "Turso target must be empty; no rows were copied or overwritten."
            )

        db.add_all(users + notes + locks)

    return len(users), len(notes), len(locks)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy existing SQLite journal data into the configured database."
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"source SQLite file (default: {DEFAULT_SOURCE})",
    )
    args = parser.parse_args()

    counts = migrate(args.source)
    print(
        "Copied records without changing the source database: "
        f"{counts[0]} users, {counts[1]} notes, {counts[2]} app locks."
    )


if __name__ == "__main__":
    main()
