import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).resolve().parent / ".env")

try:
    from .database import Base, engine, get_db
    from .models import Note, User, UserAppLock
    from .schemas import (
        AppLockSetup,
        NoteCreate,
        NoteResponse,
        NoteUpdate,
        ProfileUpdate,
        RegisterRequest,
    )
except ImportError:  # pragma: no cover - fallback for running files directly
    from database import Base, engine, get_db
    from models import Note, User, UserAppLock
    from schemas import (
        AppLockSetup,
        NoteCreate,
        NoteResponse,
        NoteUpdate,
        ProfileUpdate,
        RegisterRequest,
    )

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "Set SECRET_KEY in backend/.env before starting the API.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

app = FastAPI(title="Notes API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,"
            "https://journal-app-murex-beta.vercel.app",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
Base.metadata.create_all(bind=engine)

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not isinstance(username, str) or not username:
            raise credentials_error
    except InvalidTokenError as exc:
        raise credentials_error from exc

    user = db.scalars(select(User).where(User.username == username)).first()
    if user is None:
        raise credentials_error
    return user


@app.get("/")
def home() -> dict[str, str]:
    return {"message": "Notes API"}


@app.post("/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(
    note_data: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Note:
    note = Note(
        title=note_data.title,
        body=note_data.body,
        mood=note_data.mood,
        tags=note_data.tags,
        date=note_data.date,
        image=note_data.image,
        favorite=note_data.favorite,
        archived=note_data.archived,
        user_id=current_user.id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@app.get("/notes", response_model=list[NoteResponse])
def get_notes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Note]:
    return db.scalars(
        select(Note).where(Note.user_id ==
                           current_user.id).order_by(Note.id.desc())
    ).all()


@app.get("/notes/{note_id}", response_model=NoteResponse)
def get_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Note:
    note = db.get(Note, note_id)
    if note is None or note.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


@app.put("/notes/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: int,
    note_data: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Note:
    note = db.get(Note, note_id)
    if note is None or note.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    for field, value in note_data.model_dump().items():
        setattr(note, field, value)
    db.commit()
    db.refresh(note)
    return note


@app.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    note = db.get(Note, note_id)
    if note is None or note.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    db.delete(note)
    db.commit()


@app.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    registration: RegisterRequest,
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    user = User(
        username=registration.email.lower(),
        email=registration.email.lower(),
        name=registration.name.strip(),
        hashed_password=password_hash.hash(registration.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    db.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name}


@app.put("/users/me")
def update_profile(
    profile: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    current_user.name = profile.name.strip()
    db.commit()
    return {"name": current_user.name, "email": current_user.email}


@app.get("/users/me/app-lock")
def get_app_lock(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool | str | None]:
    app_lock = db.get(UserAppLock, current_user.id)
    return {
        "enabled": app_lock is not None,
        "lock_type": app_lock.lock_type if app_lock else None,
    }


@app.put("/users/me/app-lock")
def set_app_lock(
    setup: AppLockSetup,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool | str]:
    app_lock = db.get(UserAppLock, current_user.id)
    if app_lock is None:
        app_lock = UserAppLock(user_id=current_user.id)
        db.add(app_lock)
    app_lock.lock_type = setup.lock_type
    app_lock.hashed_secret = password_hash.hash(setup.secret)
    db.commit()
    return {"enabled": True, "lock_type": app_lock.lock_type}


@app.post("/users/me/app-lock/verify")
def verify_app_lock(
    attempt: AppLockSetup,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    app_lock = db.get(UserAppLock, current_user.id)
    if app_lock is None or app_lock.lock_type != attempt.lock_type:
        return {"verified": False}
    return {
        "verified": password_hash.verify(
            attempt.secret,
            app_lock.hashed_secret,
        )
    }


@app.delete("/users/me/app-lock", status_code=status.HTTP_204_NO_CONTENT)
def delete_app_lock(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    app_lock = db.get(UserAppLock, current_user.id)
    if app_lock is not None:
        db.delete(app_lock)
        db.commit()


@app.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = db.scalars(
        select(User).where(User.email == form_data.username.lower())
    ).first()
    if user is None or not password_hash.verify(
        form_data.password, user.hashed_password
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
    return {
        "access_token": token,
        "token_type": "bearer",
        "name": user.name,
        "email": user.email,
    }
