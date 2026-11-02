import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .database import get_db, initialize_database
    from .email_service import send_welcome_email
    from .models import Note, User, UserAppLock
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
    from models import Note, User, UserAppLock
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
    raise RuntimeError("SECRET_KEY must be configured.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")
DbSession = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
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


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
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

    user = db.scalar(select(User).where(User.username == username))
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
    db: DbSession,
):
    email = str(registration.email).lower()
    user = User(
        username=email,
        email=email,
        name=registration.name.strip(),
        hashed_password=password_hash.hash(registration.password),
    )
    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
    }


@app.post("/login")
def login(
    db: DbSession,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    welcome_email: bool = False,
):
    user = db.scalar(
        select(User).where(User.email == form_data.username.lower())
    )

    if user is None or not password_hash.verify(
        form_data.password,
        user.hashed_password,
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
        {"sub": user.username, "exp": expires_at},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    if welcome_email:
        send_welcome_email(user.email, user.name)

    return {
        "access_token": token,
        "token_type": "bearer",
        "name": user.name,
        "email": user.email,
    }


@app.get("/notes", response_model=list[NoteResponse])
def get_notes(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    return db.scalars(
        select(Note)
        .where(Note.user_id == current_user.id)
        .order_by(Note.id.desc())
    ).all()


@app.post(
    "/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_note(
    note_data: NoteCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    note = Note(**note_data.model_dump(), user_id=current_user.id)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@app.get("/notes/{note_id}", response_model=NoteResponse)
def get_note(
    note_id: int,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    note = db.scalar(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == current_user.id,
        )
    )

    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    return note


@app.put("/notes/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: int,
    note_data: NoteUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    note = db.scalar(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == current_user.id,
        )
    )

    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    for field, value in note_data.model_dump().items():
        setattr(note, field, value)

    db.commit()
    db.refresh(note)
    return note


@app.delete(
    "/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_note(
    note_id: int,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    note = db.scalar(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == current_user.id,
        )
    )

    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    db.delete(note)
    db.commit()


@app.put("/users/me")
def update_profile(
    profile: ProfileUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    current_user.name = profile.name.strip()
    db.commit()

    return {
        "name": current_user.name,
        "email": current_user.email,
    }


@app.get("/users/me/app-lock")
def get_app_lock(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    app_lock = db.get(UserAppLock, current_user.id)
    return {
        "enabled": app_lock is not None,
        "lock_type": app_lock.lock_type if app_lock else None,
    }


@app.put("/users/me/app-lock")
def set_app_lock(
    setup: AppLockSetup,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    app_lock = db.get(UserAppLock, current_user.id)
    if app_lock is None:
        app_lock = UserAppLock(
            user_id=current_user.id,
            lock_type=setup.lock_type,
            hashed_secret=password_hash.hash(setup.secret),
        )
        db.add(app_lock)
    else:
        app_lock.lock_type = setup.lock_type
        app_lock.hashed_secret = password_hash.hash(setup.secret)

    db.commit()
    return {
        "enabled": True,
        "lock_type": setup.lock_type,
    }


@app.post("/users/me/app-lock/verify")
def verify_app_lock(
    attempt: AppLockSetup,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    app_lock = db.get(UserAppLock, current_user.id)
    if app_lock is None or app_lock.lock_type != attempt.lock_type:
        return {"verified": False}

    return {
        "verified": password_hash.verify(
            attempt.secret,
            app_lock.hashed_secret,
        )
    }


@app.delete(
    "/users/me/app-lock",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_app_lock(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
):
    app_lock = db.get(UserAppLock, current_user.id)
    if app_lock is not None:
        db.delete(app_lock)
        db.commit()
