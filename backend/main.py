
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from pwdlib import PasswordHash

try:
    from .database import get_db, initialize_database
    from .email_service import send_welcome_email
    from .schemas import (
        AppLockSetup,
        NoteCreate,
        NoteResponse,
        NoteUpdate,
        ProfileUpdate,
        RegisterRequest,
    )
except ImportError:
    from database import get_db, initialize_database
    from email_service import send_welcome_email
    from schemas import (
        AppLockSetup,
        NoteCreate,
        NoteResponse,
        NoteUpdate,
        ProfileUpdate,
        RegisterRequest,
    )

load_dotenv(Path(__file__).resolve().parent / ".env")

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Set SECRET_KEY in backend/.env.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Notes API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,"
            "https://journal-app-laurd.vercel.app",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def row_to_dict(cursor, row):
    """Convert a database row into a dictionary."""
    if row is None:
        return None

    if isinstance(row, dict):
        return row

    return {
        column[0]: row[index]
        for index, column in enumerate(cursor.description)
    }


def fetch_one(db, query: str, parameters=()):
    cursor = db.execute(query, parameters)
    return row_to_dict(cursor, cursor.fetchone())


def fetch_all(db, query: str, parameters=()):
    cursor = db.execute(query, parameters)
    return [
        row_to_dict(cursor, row)
        for row in cursor.fetchall()
    ]


def note_to_response(note: dict) -> dict:
    note["tags"] = json.loads(note["tags"] or "[]")
    note["favorite"] = bool(note["favorite"])
    note["archived"] = bool(note["archived"])
    return note


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db=Depends(get_db),
) -> dict:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        username = payload.get("sub")

        if not isinstance(username, str) or not username:
            raise credentials_error

    except InvalidTokenError as exc:
        raise credentials_error from exc

    user = fetch_one(
        db,
        "SELECT * FROM users WHERE username = ?",
        (username,),
    )

    if user is None:
        raise credentials_error

    return user


@app.get("/")
def home():
    return {"message": "Notes API"}


@app.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
def register(
    registration: RegisterRequest,
    db=Depends(get_db),
):
    email = str(registration.email).lower()

    try:
        cursor = db.execute(
            """
            INSERT INTO users (
                username,
                email,
                name,
                hashed_password
            )
            VALUES (?, ?, ?, ?)
            RETURNING id, email, name
            """,
            (
                email,
                email,
                registration.name.strip(),
                password_hash.hash(registration.password),
            ),
        )

        user = row_to_dict(cursor, cursor.fetchone())
        db.commit()

    except Exception as exc:
        db.rollback()

        if "unique" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            ) from exc

        raise

    return user


@app.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    welcome_email: bool = False,
    db=Depends(get_db),
):
    user = fetch_one(
        db,
        "SELECT * FROM users WHERE email = ?",
        (form_data.username.lower(),),
    )

    if user is None or not password_hash.verify(
        form_data.password,
        user["hashed_password"],
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    token = jwt.encode(
        {"sub": user["username"], "exp": expires_at},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    if welcome_email:
        send_welcome_email(user["email"], user["name"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "name": user["name"],
        "email": user["email"],
    }


@app.get("/notes", response_model=list[NoteResponse])
def get_notes(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    notes = fetch_all(
        db,
        """
        SELECT * FROM notes
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (current_user["id"],),
    )

    return [note_to_response(note) for note in notes]


@app.post(
    "/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_note(
    note_data: NoteCreate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    cursor = db.execute(
        """
        INSERT INTO notes (
            title, body, mood, tags, date, image,
            favorite, archived, user_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            note_data.title,
            note_data.body,
            note_data.mood,
            json.dumps(note_data.tags),
            note_data.date,
            note_data.image,
            int(note_data.favorite),
            int(note_data.archived),
            current_user["id"],
        ),
    )

    note = row_to_dict(cursor, cursor.fetchone())
    db.commit()

    return note_to_response(note)


@app.get("/notes/{note_id}", response_model=NoteResponse)
def get_note(
    note_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    note = fetch_one(
        db,
        "SELECT * FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user["id"]),
    )

    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    return note_to_response(note)


@app.put("/notes/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: int,
    note_data: NoteUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    existing = fetch_one(
        db,
        "SELECT id FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user["id"]),
    )

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    values = note_data.model_dump()
    values["tags"] = json.dumps(values["tags"])
    values["favorite"] = int(values["favorite"])
    values["archived"] = int(values["archived"])

    db.execute(
        """
        UPDATE notes
        SET title = ?, body = ?, mood = ?, tags = ?,
            date = ?, image = ?, favorite = ?, archived = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            values["title"],
            values["body"],
            values["mood"],
            values["tags"],
            values["date"],
            values["image"],
            values["favorite"],
            values["archived"],
            note_id,
            current_user["id"],
        ),
    )
    db.commit()

    updated = fetch_one(
        db,
        "SELECT * FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user["id"]),
    )

    return note_to_response(updated)


@app.delete(
    "/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_note(
    note_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    cursor = db.execute(
        "DELETE FROM notes WHERE id = ? AND user_id = ?",
        (note_id, current_user["id"]),
    )

    if cursor.rowcount == 0:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    db.commit()


@app.put("/users/me")
def update_profile(
    profile: ProfileUpdate,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    name = profile.name.strip()

    db.execute(
        "UPDATE users SET name = ? WHERE id = ?",
        (name, current_user["id"]),
    )
    db.commit()

    return {
        "name": name,
        "email": current_user["email"],
    }


@app.get("/users/me/app-lock")
def get_app_lock(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    app_lock = fetch_one(
        db,
        "SELECT * FROM user_app_locks WHERE user_id = ?",
        (current_user["id"],),
    )

    return {
        "enabled": app_lock is not None,
        "lock_type": app_lock["lock_type"] if app_lock else None,
    }


@app.put("/users/me/app-lock")
def set_app_lock(
    setup: AppLockSetup,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    db.execute(
        """
        INSERT INTO user_app_locks (
            user_id, lock_type, hashed_secret
        )
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            lock_type = excluded.lock_type,
            hashed_secret = excluded.hashed_secret
        """,
        (
            current_user["id"],
            setup.lock_type,
            password_hash.hash(setup.secret),
        ),
    )
    db.commit()

    return {
        "enabled": True,
        "lock_type": setup.lock_type,
    }


@app.post("/users/me/app-lock/verify")
def verify_app_lock(
    attempt: AppLockSetup,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    app_lock = fetch_one(
        db,
        "SELECT * FROM user_app_locks WHERE user_id = ?",
        (current_user["id"],),
    )

    if app_lock is None or app_lock["lock_type"] != attempt.lock_type:
        return {"verified": False}

    return {
        "verified": password_hash.verify(
            attempt.secret,
            app_lock["hashed_secret"],
        )
    }


@app.delete(
    "/users/me/app-lock",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_app_lock(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    db.execute(
        "DELETE FROM user_app_locks WHERE user_id = ?",
        (current_user["id"],),
    )
    db.commit()
