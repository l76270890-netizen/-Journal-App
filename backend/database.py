
import os
from pathlib import Path
from typing import Generator

import turso_serverless
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def create_connection():
    """Connect to the remote Turso database."""
    database_url = os.getenv("TURSO_DATABASE_URL")
    auth_token = os.getenv("TURSO_AUTH_TOKEN")

    if not database_url or not auth_token:
        raise RuntimeError(
            "TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set."
        )

    return turso_serverless.connect(
        database_url,
        auth_token=auth_token,
    )


def initialize_database() -> None:
    """Create the application tables if they do not exist."""
    connection = create_connection()

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                hashed_password TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                mood TEXT NOT NULL DEFAULT 'Calm',
                tags TEXT NOT NULL DEFAULT '[]',
                date TEXT NOT NULL,
                image TEXT,
                favorite INTEGER NOT NULL DEFAULT 0,
                archived INTEGER NOT NULL DEFAULT 0,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_notes_user_id
            ON notes(user_id)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS user_app_locks (
                user_id INTEGER PRIMARY KEY,
                lock_type TEXT NOT NULL,
                hashed_secret TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        connection.commit()

    finally:
        connection.close()


def get_db() -> Generator:
    """Provide a Turso connection to a FastAPI request."""
    connection = create_connection()

    try:
        yield connection
    finally:
        connection.close()
