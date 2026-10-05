"""9ja Jobs API: FastAPI, SQLAlchemy, signed HttpOnly-cookie sessions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, quote

import httpx
import jwt
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from jwt import PyJWKClient
from dotenv import load_dotenv
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, LargeBinary, String, Text, UniqueConstraint, create_engine, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

HOSTED_ENVIRONMENT = bool(os.getenv("VERCEL") or os.getenv("RENDER"))
ENVIRONMENT = os.getenv("ENVIRONMENT", "production" if HOSTED_ENVIRONMENT else "development").lower()
CONFIGURED_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if ENVIRONMENT == "production" and not CONFIGURED_DATABASE_URL:
    raise RuntimeError("DATABASE_URL must point to a persistent PostgreSQL database in production")
DATABASE_URL = CONFIGURED_DATABASE_URL or f"sqlite:///{(BACKEND_DIR / '9ja.db').as_posix()}"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
JWT_SECRET = os.getenv("JWT_SECRET", "development-only-change-me")
if ENVIRONMENT == "production" and (JWT_SECRET == "development-only-change-me" or len(JWT_SECRET) < 32):
    raise RuntimeError("Set a unique JWT_SECRET with at least 32 characters before production startup")
COOKIE_SECURE = ENVIRONMENT == "production" or os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_NAME = "nineja_session"
TOKEN_TTL_HOURS = 24 * 7
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "" if HOSTED_ENVIRONMENT else "http://localhost:8000").strip().rstrip("/")
FRONTEND_ORIGINS = [x.strip().rstrip("/") for x in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
if ENVIRONMENT == "production":
    if not FRONTEND_ORIGINS or any(origin == "*" or not origin.startswith("https://") for origin in FRONTEND_ORIGINS):
        raise RuntimeError("Set FRONTEND_ORIGINS to the exact HTTPS origin of your frontend")
    if not PUBLIC_API_URL.startswith("https://"):
        raise RuntimeError("Set PUBLIC_API_URL to this backend's public HTTPS URL")
else:
    # Vite may move to 5174 (or 127.0.0.1) when its default port is occupied.
    FRONTEND_ORIGINS = list(dict.fromkeys([
        *FRONTEND_ORIGINS,
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]))
# Vercel's filesystem is ephemeral. Keep uploaded file contents in the
# persistent database so resumes remain available after a function restart.
DEFAULT_UPLOAD_DIR = "/tmp/9ja-uploads" if os.getenv("VERCEL") else str(BACKEND_DIR / "uploads")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", DEFAULT_UPLOAD_DIR)).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
password_hash = PasswordHash.recommended()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="jobseeker")
    name: Mapped[str] = mapped_column(String(160), default="")
    photo_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    jobs: Mapped[list[Job]] = relationship(back_populates="employer")


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_identity"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), index=True)
    provider_user_id: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    company_name: Mapped[str] = mapped_column(String(180), index=True)
    category: Mapped[str] = mapped_column(String(100), default="")
    job_type: Mapped[str] = mapped_column(String(50), default="Full-time")
    work_mode: Mapped[str] = mapped_column(String(50), default="On-site")
    location: Mapped[str] = mapped_column(String(180), default="")
    salary_min: Mapped[int] = mapped_column(Integer, default=0)
    salary_max: Mapped[int] = mapped_column(Integer, default=0)
    experience: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    responsibilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    benefits: Mapped[list[str]] = mapped_column(JSON, default=list)
    deadline: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    employer: Mapped[User] = relationship(back_populates="jobs")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "applicant_id", name="uq_application_job_applicant"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_url: Mapped[str | None] = mapped_column(String(800), nullable=True)
    resume_file_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id", ondelete="SET NULL"), nullable=True)
    cover_letter: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="Pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SavedJob(Base):
    __tablename__ = "saved_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_saved_job"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CompanyFollow(Base):
    __tablename__ = "company_follows"
    __table_args__ = (UniqueConstraint("user_id", "company_name", name="uq_company_follow"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_name: Mapped[str] = mapped_column(String(180), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(String(500), default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    participant_one_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    participant_two_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("company_name", "author_id", name="uq_company_review_author"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(180), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    stored_name: Mapped[str] = mapped_column(String(100), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UploadedFileContent(Base):
    __tablename__ = "uploaded_file_contents"
    file_id: Mapped[int] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)


Base.metadata.create_all(bind=engine)
app = FastAPI(title="9ja Jobs API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"], allow_headers=["Content-Type"])

@app.middleware("http")
async def verify_browser_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    provider_callback = request.url.path.startswith("/api/auth/oauth/") and request.url.path.endswith("/callback")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in FRONTEND_ORIGINS and not provider_callback:
        return Response(status_code=403, content="Origin is not allowed")
    return await call_next(request)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def token_for(user: User) -> str:
    import base64, hashlib, hmac, json, time
    payload = base64.urlsafe_b64encode(json.dumps({"sub": user.id, "ver": user.token_version, "exp": int(time.time()) + TOKEN_TTL_HOURS * 3600}).encode()).decode().rstrip("=")
    signature = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return payload + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def user_from_token(token: str, db: Session) -> User | None:
    import base64, hashlib, hmac, json, time
    try:
        payload, signature = token.split(".", 1)
        expected = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected): return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] < time.time(): return None
        user = db.get(User, int(data["sub"]))
        return user if user and user.is_active and data.get("ver", -1) == user.token_version else None
    except (ValueError, KeyError, TypeError):
        return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_token(request.cookies.get(COOKIE_NAME, ""), db)
    if not user: raise HTTPException(status_code=401, detail="Please sign in to continue")
    return user

def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return user_from_token(request.cookies.get(COOKIE_NAME, ""), db)


def employer(user: User = Depends(current_user)) -> User:
    if user.role != "employer": raise HTTPException(status_code=403, detail="Employer account required")
    return user


PRIVATE_PROFILE_FIELDS = {"email", "phone", "cvUrl", "resumeUrl", "notifications", "savedJobs"}
RESERVED_PROFILE_FIELDS = PRIVATE_PROFILE_FIELDS | {"id", "uid", "role", "name", "displayName", "photoURL", "password", "passwordHash", "password_hash", "token_version", "is_active"}
PUBLIC_PROFILE_FIELDS = {
    "title", "bio", "companyName", "companySize", "industry", "location", "website",
    "companyWebsite", "companyDescription", "companyLocation", "companyLogo", "companyBanner",
    "companyBenefits", "companySocials", "bannerURL", "profileViews",
}


def public_user(user: User, *, include_private: bool = False) -> dict[str, Any]:
    profile = user.profile if isinstance(user.profile, dict) else {}
    visible_profile = {
        key: value
        for key, value in profile.items()
        if key not in RESERVED_PROFILE_FIELDS and (include_private or key in PUBLIC_PROFILE_FIELDS)
    }
    result = {**visible_profile}
    result.update({"id": user.id, "uid": str(user.id), "name": user.name, "displayName": user.name, "role": user.role, "photoURL": user.photo_url or profile.get("photoURL")})
    if include_private:
        result["email"] = user.email
        for key in PRIVATE_PROFILE_FIELDS - {"email"}:
            if key in profile:
                result[key] = profile[key]
    return result


def public_job(job: Job, db: Session) -> dict[str, Any]:
    application_count = db.scalar(select(func.count(Application.id)).where(Application.job_id == job.id)) or 0
    return {"id": str(job.id), "employerId": str(job.employer_id), "companyId": str(job.employer_id), "title": job.title, "companyName": job.company_name, "company": job.company_name, "category": job.category, "jobType": job.job_type, "type": job.job_type, "workMode": job.work_mode, "location": job.location, "salaryMin": job.salary_min, "salaryMax": job.salary_max, "salary": job.salary_max or job.salary_min, "experience": job.experience, "description": job.description, "requirements": job.requirements or [], "skills": job.requirements or [], "responsibilities": job.responsibilities or [], "benefits": job.benefits or [], "deadline": job.deadline, "status": job.status, "createdAt": job.created_at.isoformat(), "postedDate": job.created_at.isoformat(), "applicationCount": application_count}


def public_application(item: Application, job: Job, user: User) -> dict[str, Any]:
    return {"id": str(item.id), "jobId": str(job.id), "jobTitle": job.title, "company": job.company_name, "location": job.location, "employerId": str(job.employer_id), "companyId": str(job.employer_id), "userId": str(user.id), "applicantName": user.name, "userEmail": user.email, "resumeUrl": f"/api/files/{item.resume_file_id}" if item.resume_file_id else item.resume_url, "coverLetter": item.cover_letter, "status": item.status, "appliedAt": item.created_at.isoformat()}


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=160)
    role: str = "jobseeker"

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class PasswordChangeIn(BaseModel):
    currentPassword: str
    newPassword: str = Field(min_length=8, max_length=128)

class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    profile: dict[str, Any] | None = None

class JobIn(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    companyName: str = Field(min_length=2, max_length=180)
    category: str = ""
    jobType: str = "Full-time"
    workMode: str = "On-site"
    location: str = ""
    salaryMin: int = Field(default=0, ge=0)
    salaryMax: int = Field(default=0, ge=0)
    experience: str = ""
    description: str = Field(min_length=20)
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    deadline: str = ""
    status: str = "active"
    model_config = ConfigDict(extra="ignore")

class ApplicationIn(BaseModel):
    coverLetter: str = Field(default="", max_length=12000)
    resumeFileId: int | None = None

class StatusIn(BaseModel):
    status: str

class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)

class ConversationIn(BaseModel):
    otherUserId: int
    jobId: int | None = None

class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=4000)


OAUTH_PROVIDERS = {"google", "apple", "github"}


def oauth_callback_url(provider: str) -> str:
    return f"{PUBLIC_API_URL}/api/auth/oauth/{provider}/callback"


def oauth_state_cookie(provider: str) -> str:
    return f"nineja_oauth_state_{provider}"


def oauth_client(provider: str) -> tuple[str, str]:
    settings = {
        "google": (os.getenv("GOOGLE_CLIENT_ID", ""), os.getenv("GOOGLE_CLIENT_SECRET", "")),
        "github": (os.getenv("GITHUB_CLIENT_ID", ""), os.getenv("GITHUB_CLIENT_SECRET", "")),
        "apple": (os.getenv("APPLE_CLIENT_ID", ""), "apple"),
    }
    client_id, client_secret = settings[provider]
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail=f"{provider.title()} sign-in is not configured on the backend yet.")
    if provider == "apple" and not all(os.getenv(key) for key in ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY")):
        raise HTTPException(status_code=503, detail="Apple sign-in is missing its team ID, key ID, or private key.")
    return client_id, client_secret


def make_oauth_state(provider: str, role: str) -> tuple[str, str]:
    nonce = secrets.token_urlsafe(32)
    payload = {"provider": provider, "role": role, "nonce": nonce, "issued": int(time.time())}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(JWT_SECRET.encode(), encoded.encode(), hashlib.sha256).digest()
    state = encoded + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")
    verifier = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), ("oauth-pkce:" + nonce).encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return state, verifier


def read_oauth_state(state: str, provider: str) -> tuple[dict[str, Any], str]:
    try:
        encoded, signature = state.split(".", 1)
        expected = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), encoded.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected): raise ValueError("Invalid sign-in state")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload.get("provider") != provider or payload.get("role") not in {"jobseeker", "employer"}:
            raise ValueError("Invalid sign-in state")
        if int(time.time()) - int(payload.get("issued", 0)) > 600:
            raise ValueError("Sign-in attempt expired. Please try again.")
        verifier = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), ("oauth-pkce:" + payload["nonce"]).encode(), hashlib.sha256).digest()).decode().rstrip("=")
        return payload, verifier
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired sign-in request. Please try again.") from exc


def apple_client_secret() -> str:
    key = os.getenv("APPLE_PRIVATE_KEY", "").replace("\\n", "\n")
    now = int(time.time())
    return jwt.encode(
        {"iss": os.environ["APPLE_TEAM_ID"], "iat": now, "exp": now + 300, "aud": "https://appleid.apple.com", "sub": os.environ["APPLE_CLIENT_ID"]},
        key,
        algorithm="ES256",
        headers={"kid": os.environ["APPLE_KEY_ID"]},
    )


def provider_id_token(token: str, provider: str, client_id: str) -> dict[str, Any]:
    jwks_url = "https://appleid.apple.com/auth/keys" if provider == "apple" else "https://www.googleapis.com/oauth2/v3/certs"
    signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
    issuer = "https://appleid.apple.com" if provider == "apple" else ["https://accounts.google.com", "accounts.google.com"]
    return jwt.decode(token, signing_key.key, algorithms=["ES256"] if provider == "apple" else ["RS256"], audience=client_id, issuer=issuer, options={"require": ["sub", "email"]})


async def fetch_provider_profile(provider: str, code: str, verifier: str) -> dict[str, Any]:
    client_id, client_secret = oauth_client(provider)
    redirect_uri = oauth_callback_url(provider)
    async with httpx.AsyncClient(timeout=15) as client:
        if provider == "google":
            token_response = await client.post("https://oauth2.googleapis.com/token", data={
                "client_id": client_id, "client_secret": client_secret, "code": code,
                "code_verifier": verifier, "grant_type": "authorization_code", "redirect_uri": redirect_uri,
            })
            token_response.raise_for_status()
            claims = provider_id_token(token_response.json()["id_token"], provider, client_id)
            if claims.get("email_verified") is not True:
                raise ValueError("Google did not return a verified email address.")
            return {"id": str(claims["sub"]), "email": claims["email"], "name": claims.get("name") or "", "photo": claims.get("picture")}

        if provider == "github":
            token_response = await client.post("https://github.com/login/oauth/access_token", json={
                "client_id": client_id, "client_secret": client_secret, "code": code,
                "redirect_uri": redirect_uri, "code_verifier": verifier,
            }, headers={"Accept": "application/json"})
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not access_token: raise ValueError("GitHub did not return an access token.")
            headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
            user_response = await client.get("https://api.github.com/user", headers=headers)
            user_response.raise_for_status()
            profile = user_response.json()
            email_response = await client.get("https://api.github.com/user/emails", headers=headers)
            email_response.raise_for_status()
            verified = [item for item in email_response.json() if item.get("primary") and item.get("verified")]
            if not verified: raise ValueError("Your GitHub account needs a verified email address to sign in.")
            return {"id": str(profile["id"]), "email": verified[0]["email"], "name": profile.get("name") or profile.get("login") or "", "photo": profile.get("avatar_url")}

        token_response = await client.post("https://appleid.apple.com/auth/token", data={
            "client_id": client_id, "client_secret": apple_client_secret(), "code": code,
            "grant_type": "authorization_code", "redirect_uri": redirect_uri,
        })
        token_response.raise_for_status()
        claims = provider_id_token(token_response.json()["id_token"], provider, client_id)
        if str(claims.get("email_verified", "")).lower() != "true":
            raise ValueError("Apple did not return a verified email address.")
        return {"id": str(claims["sub"]), "email": claims["email"], "name": "", "photo": None}


def finish_oauth_login(provider: str, profile: dict[str, Any], role: str, db: Session) -> User:
    identity = db.scalar(select(OAuthIdentity).where(OAuthIdentity.provider == provider, OAuthIdentity.provider_user_id == profile["id"]))
    if identity:
        user = db.get(User, identity.user_id)
        if not user or not user.is_active: raise ValueError("This account is not active.")
        return user
    email = profile["email"].strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(email=email, password_hash=password_hash.hash(secrets.token_urlsafe(48)), role=role, name=profile.get("name") or email.split("@", 1)[0], photo_url=profile.get("photo"))
        db.add(user)
        db.flush()
    elif profile.get("photo") and not user.photo_url:
        user.photo_url = profile["photo"]
    db.add(OAuthIdentity(provider=provider, provider_user_id=profile["id"], user_id=user.id, email=email))
    db.commit()
    db.refresh(user)
    return user


def oauth_error_redirect(message: str, provider: str | None = None) -> RedirectResponse:
    target = f"{FRONTEND_ORIGINS[0].rstrip('/')}/login?oauth_error={quote(message[:180])}"
    response = RedirectResponse(target, status_code=303)
    if provider in OAUTH_PROVIDERS:
        response.delete_cookie(oauth_state_cookie(provider), path="/api/auth/oauth")
    return response


@app.get("/api/auth/oauth/{provider}/start")
def start_oauth(provider: str, role: str = Query(default="jobseeker")):
    if provider not in OAUTH_PROVIDERS: raise HTTPException(status_code=404, detail="That sign-in provider is not supported.")
    client_id, _ = oauth_client(provider)
    if role not in {"jobseeker", "employer"}: raise HTTPException(status_code=422, detail="Choose a valid account type.")
    state, verifier = make_oauth_state(provider, role)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    callback = oauth_callback_url(provider)
    common = {"client_id": client_id, "redirect_uri": callback, "response_type": "code", "state": state}
    if provider == "google":
        params = {**common, "scope": "openid email profile", "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account"}
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    elif provider == "github":
        params = {**common, "scope": "read:user user:email", "code_challenge": challenge, "code_challenge_method": "S256", "allow_signup": "true"}
        url = "https://github.com/login/oauth/authorize?" + urlencode(params)
    else:
        params = {**common, "scope": "name email", "response_mode": "form_post"}
        url = "https://appleid.apple.com/auth/authorize?" + urlencode(params)
    # Start OAuth as a top-level navigation so browsers accept the state cookie
    # even when the frontend and API are hosted on different sites.
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(oauth_state_cookie(provider), state, httponly=True, secure=COOKIE_SECURE, samesite="none" if COOKIE_SECURE else "lax", max_age=600, path="/api/auth/oauth")
    return response


@app.api_route("/api/auth/oauth/{provider}/callback", methods=["GET", "POST"])
async def oauth_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    if provider not in OAUTH_PROVIDERS: return oauth_error_redirect("That sign-in provider is not supported.")
    if request.method == "POST":
        form = await request.form()
        code, state = str(form.get("code") or ""), str(form.get("state") or "")
        provider_error = str(form.get("error_description") or form.get("error") or "")
        apple_user = form.get("user")
    else:
        code, state = request.query_params.get("code", ""), request.query_params.get("state", "")
        provider_error = request.query_params.get("error_description") or request.query_params.get("error") or ""
        apple_user = None
    try:
        if not state or not hmac.compare_digest(request.cookies.get(oauth_state_cookie(provider), ""), state):
            raise ValueError("Your sign-in session expired. Please try again.")
        state_data, verifier = read_oauth_state(state, provider)
    except ValueError as exc:
        return oauth_error_redirect(str(exc), provider)
    if provider_error: return oauth_error_redirect("Sign-in was cancelled or declined.", provider)
    try:
        if not code: raise ValueError("The provider returned an incomplete sign-in response.")
        profile = await fetch_provider_profile(provider, code, verifier)
        if provider == "apple" and apple_user:
            if isinstance(apple_user, str):
                try: apple_user = json.loads(apple_user)
                except json.JSONDecodeError: apple_user = {}
            name = apple_user.get("name") if isinstance(apple_user, dict) else None
            if isinstance(name, dict): profile["name"] = " ".join(x for x in (name.get("firstName"), name.get("lastName")) if x)
        user = finish_oauth_login(provider, profile, state_data["role"], db)
        response = RedirectResponse(FRONTEND_ORIGINS[0], status_code=303)
        response.set_cookie(COOKIE_NAME, token_for(user), httponly=True, secure=COOKIE_SECURE, samesite="none" if COOKIE_SECURE else "lax", max_age=TOKEN_TTL_HOURS * 3600, path="/")
        response.delete_cookie(oauth_state_cookie(provider), path="/api/auth/oauth")
        return response
    except ValueError as exc:
        db.rollback()
        return oauth_error_redirect(str(exc), provider)
    except Exception:
        db.rollback()
        return oauth_error_redirect("Could not finish sign-in. Check the provider app settings and try again.", provider)


@app.get("/api/health")
def health(): return {"status": "ok", "service": "9ja-jobs-api"}

@app.post("/api/auth/signup", status_code=201)
def signup(data: SignupIn, response: Response, db: Session = Depends(get_db)):
    if data.role not in {"jobseeker", "employer"}: raise HTTPException(422, "Choose a valid account type")
    email = data.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)): raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, password_hash=password_hash.hash(data.password), role=data.role, name=data.name.strip())
    db.add(user); db.commit(); db.refresh(user)
    response.set_cookie(COOKIE_NAME, token_for(user), httponly=True, secure=COOKIE_SECURE, samesite="none" if COOKIE_SECURE else "lax", max_age=TOKEN_TTL_HOURS * 3600, path="/")
    return public_user(user, include_private=True)

@app.post("/api/auth/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower().strip()))
    if not user or not password_hash.verify(data.password, user.password_hash): raise HTTPException(401, "Email or password is incorrect")
    response.set_cookie(COOKIE_NAME, token_for(user), httponly=True, secure=COOKIE_SECURE, samesite="none" if COOKIE_SECURE else "lax", max_age=TOKEN_TTL_HOURS * 3600, path="/")
    return public_user(user, include_private=True)

@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    # Logout should remain idempotent: clear the browser cookie even if it has
    # expired, is malformed, or the database is temporarily unavailable.
    try:
        user = user_from_token(request.cookies.get(COOKIE_NAME, ""), db)
        if user:
            user.token_version += 1
            db.commit()
    except SQLAlchemyError:
        db.rollback()
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="none" if COOKIE_SECURE else "lax",
        max_age=0,
    )

@app.patch("/api/auth/password")
def change_password(data: PasswordChangeIn, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not password_hash.verify(data.currentPassword, user.password_hash): raise HTTPException(400, "Current password is incorrect")
    if password_hash.verify(data.newPassword, user.password_hash): raise HTTPException(400, "Choose a password you have not used before")
    user.password_hash = password_hash.hash(data.newPassword)
    user.token_version += 1
    db.commit(); db.refresh(user)
    response.set_cookie(COOKIE_NAME, token_for(user), httponly=True, secure=COOKIE_SECURE, samesite="none" if COOKIE_SECURE else "lax", max_age=TOKEN_TTL_HOURS * 3600, path="/")
    return public_user(user, include_private=True)

@app.get("/api/auth/me")
def me(user: User = Depends(current_user)): return public_user(user, include_private=True)

@app.get("/api/users/{user_id}")
def get_public_user(user_id: int, db: Session = Depends(get_db), viewer: User = Depends(current_user)):
    user = db.get(User, user_id)
    if not user: raise HTTPException(404, "User not found")
    result = public_user(user, include_private=viewer.id == user.id)
    if viewer.id == user.id:
        result["savedJobs"] = [str(x) for x in db.scalars(select(SavedJob.job_id).where(SavedJob.user_id == user.id)).all()]
    else:
        result.pop("email", None)
    return result

@app.post("/api/users/{user_id}/profile-view", status_code=204)
def profile_view(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user: raise HTTPException(404, "User not found")
    profile = dict(user.profile or {}); profile["profileViews"] = int(profile.get("profileViews", 0)) + 1
    user.profile = profile; db.commit()

@app.patch("/api/users/me")
def update_profile(data: ProfileIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.name is not None: user.name = data.name.strip()
    if data.profile is not None:
        user.profile = {**(user.profile or {}), **data.profile}
        if "photoURL" in data.profile: user.photo_url = data.profile["photoURL"]
    db.commit(); db.refresh(user); return public_user(user, include_private=True)

@app.post("/api/users/me/upload", status_code=201)
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    suffix = Path(file.filename or "").suffix.lower()
    allowed = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".webp"}
    if suffix not in allowed: raise HTTPException(415, "Upload a PDF, DOC, DOCX, JPG, PNG, or WEBP file")
    contents = await file.read(8 * 1024 * 1024 + 1)
    if len(contents) > 8 * 1024 * 1024: raise HTTPException(413, "File must be 8 MB or smaller")
    expected_mime = {".pdf": "application/pdf", ".doc": "application/msword", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = expected_mime[suffix]
    if suffix == ".pdf" and not contents.startswith(b"%PDF-"): raise HTTPException(415, "This file is not a valid PDF")
    if suffix in {".jpg", ".jpeg"} and not contents.startswith(b"\xff\xd8\xff"): raise HTTPException(415, "This file is not a valid JPEG")
    if suffix == ".png" and not contents.startswith(b"\x89PNG\r\n\x1a\n"): raise HTTPException(415, "This file is not a valid PNG")
    if suffix == ".webp" and not (contents.startswith(b"RIFF") and contents[8:12] == b"WEBP"): raise HTTPException(415, "This file is not a valid WEBP image")
    if suffix == ".doc" and not (contents.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or contents.startswith(b"PK\x03\x04")): raise HTTPException(415, "This file is not a valid DOC file")
    if suffix == ".docx" and not contents.startswith(b"PK\x03\x04"): raise HTTPException(415, "This file is not a valid DOCX file")
    name = f"{secrets.token_hex(20)}{suffix}"
    original_name = Path((file.filename or name).replace("\\", "/")).name
    record = UploadedFile(owner_id=user.id, stored_name=name, original_name=original_name[:255], mime_type=mime_type)
    db.add(record); db.flush()
    db.add(UploadedFileContent(file_id=record.id, content=contents))
    db.commit(); db.refresh(record)
    return {"id": record.id, "url": f"/api/files/{record.id}", "filename": record.original_name}

@app.get("/api/files/{file_id}")
def download_file(file_id: int, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    record = db.get(UploadedFile, file_id)
    if not record: raise HTTPException(404, "File not found")
    public_image = record.mime_type.startswith("image/")
    permitted = public_image or bool(user and record.owner_id == user.id)
    if not permitted and user and user.role == "employer":
        application = db.scalar(select(Application).where(Application.resume_file_id == file_id))
        job = db.get(Job, application.job_id) if application else None
        permitted = bool(job and job.employer_id == user.id)
    if not permitted: raise HTTPException(403, "You cannot access this file")
    stored_content = db.get(UploadedFileContent, record.id)
    if stored_content:
        filename = quote(record.original_name, safe="")
        return Response(stored_content.content, media_type=record.mime_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}", "X-Content-Type-Options": "nosniff"})
    path = UPLOAD_DIR / record.stored_name
    if not path.is_file(): raise HTTPException(404, "File not found")
    return FileResponse(path, media_type=record.mime_type, filename=record.original_name, headers={"X-Content-Type-Options": "nosniff"})

@app.get("/api/jobs")
def list_jobs(search: str | None = None, location: str | None = None, category: str | None = None, job_type: str | None = Query(default=None, alias="jobType"), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    q = select(Job).where(Job.status == "active")
    if search: q = q.where(or_(Job.title.ilike(f"%{search}%"), Job.company_name.ilike(f"%{search}%"), Job.description.ilike(f"%{search}%")))
    if location: q = q.where(Job.location.ilike(f"%{location}%"))
    if category: q = q.where(Job.category.ilike(f"%{category}%"))
    if job_type: q = q.where(Job.job_type == job_type)
    jobs = db.scalars(q.order_by(Job.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [public_job(job, db) for job in jobs], "total": db.scalar(select(func.count()).select_from(q.subquery())) or 0, "limit": limit, "offset": offset}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    job = db.get(Job, job_id)
    if not job or job.status == "deleted" or (job.status != "active" and (not user or user.id != job.employer_id)): raise HTTPException(404, "Job not found")
    return public_job(job, db)

@app.get("/api/applications/{application_id:int}")
def get_application(application_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(Application, application_id)
    if not item: raise HTTPException(404, "Application not found")
    job = db.get(Job, item.job_id)
    if user.id != item.applicant_id and user.id != job.employer_id: raise HTTPException(403, "You cannot view this application")
    return public_application(item, job, db.get(User, item.applicant_id))

@app.post("/api/jobs", status_code=201)
def create_job(data: JobIn, db: Session = Depends(get_db), user: User = Depends(employer)):
    job = Job(employer_id=user.id, title=data.title, company_name=data.companyName, category=data.category, job_type=data.jobType, work_mode=data.workMode, location=data.location, salary_min=data.salaryMin, salary_max=data.salaryMax, experience=data.experience, description=data.description, requirements=data.requirements, responsibilities=data.responsibilities, benefits=data.benefits, deadline=data.deadline, status=data.status if data.status in {"active", "draft"} else "active")
    db.add(job); db.commit(); db.refresh(job); return public_job(job, db)

@app.get("/api/employer/jobs")
def employer_jobs(db: Session = Depends(get_db), user: User = Depends(employer)):
    return [public_job(job, db) for job in db.scalars(select(Job).where(Job.employer_id == user.id).order_by(Job.created_at.desc())).all()]

@app.patch("/api/jobs/{job_id}")
def update_job(job_id: int, data: JobIn, db: Session = Depends(get_db), user: User = Depends(employer)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    if job.employer_id != user.id: raise HTTPException(403, "You cannot edit this job")
    if data.status not in {"active", "draft", "closed"}: raise HTTPException(422, "Invalid job status")
    for key, val in {"title": data.title, "company_name": data.companyName, "category": data.category, "job_type": data.jobType, "work_mode": data.workMode, "location": data.location, "salary_min": data.salaryMin, "salary_max": data.salaryMax, "experience": data.experience, "description": data.description, "requirements": data.requirements, "responsibilities": data.responsibilities, "benefits": data.benefits, "deadline": data.deadline, "status": data.status}.items(): setattr(job, key, val)
    db.commit(); db.refresh(job); return public_job(job, db)

@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(employer)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    if job.employer_id != user.id: raise HTTPException(403, "You cannot delete this job")
    job.status = "deleted"; db.commit()

@app.post("/api/jobs/{job_id}/applications", status_code=201)
def apply(job_id: int, data: ApplicationIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role != "jobseeker": raise HTTPException(403, "Only jobseekers can apply")
    job = db.get(Job, job_id)
    if not job or job.status != "active": raise HTTPException(404, "Job is no longer available")
    if db.scalar(select(Application).where(Application.job_id == job.id, Application.applicant_id == user.id)): raise HTTPException(409, "You have already applied")
    if data.resumeFileId:
        resume = db.get(UploadedFile, data.resumeFileId)
        if not resume or resume.owner_id != user.id: raise HTTPException(403, "Resume file does not belong to your account")
    application = Application(job_id=job.id, applicant_id=user.id, resume_file_id=data.resumeFileId, cover_letter=data.coverLetter)
    db.add(application); db.flush()
    db.add(Notification(user_id=job.employer_id, title="New application", message=f"{user.name} applied for {job.title}", link=f"/employer/applicants/{job.id}")); db.commit(); db.refresh(application)
    return public_application(application, job, user)

@app.get("/api/applications/me")
def my_applications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.execute(select(Application, Job).join(Job).where(Application.applicant_id == user.id).order_by(Application.created_at.desc())).all()
    return [public_application(apply, job, user) for apply, job in rows]

@app.get("/api/jobs/{job_id}/applications")
def job_applications(job_id: int, db: Session = Depends(get_db), user: User = Depends(employer)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    if job.employer_id != user.id: raise HTTPException(403, "You cannot view these applicants")
    rows = db.execute(select(Application, User).join(User, Application.applicant_id == User.id).where(Application.job_id == job_id).order_by(Application.created_at.desc())).all()
    return [public_application(application, job, applicant) for application, applicant in rows]

@app.patch("/api/applications/{application_id}")
def update_application(application_id: int, data: StatusIn, db: Session = Depends(get_db), user: User = Depends(employer)):
    application = db.get(Application, application_id)
    if not application: raise HTTPException(404, "Application not found")
    job = db.get(Job, application.job_id)
    if job.employer_id != user.id: raise HTTPException(403, "You cannot update this application")
    status_value = data.status.title()
    if status_value not in {"Pending", "Reviewed", "Shortlisted", "Accepted", "Rejected"}: raise HTTPException(422, "Invalid application status")
    application.status = status_value
    db.add(Notification(user_id=application.applicant_id, title="Application update", message=f"Your application for {job.title} is now {data.status}.", link="/my-applications")); db.commit()
    return {"id": application.id, "status": application.status}

@app.get("/api/saved-jobs")
def saved_jobs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    jobs = db.scalars(select(Job).join(SavedJob, SavedJob.job_id == Job.id).where(SavedJob.user_id == user.id).order_by(SavedJob.created_at.desc())).all()
    return [public_job(job, db) for job in jobs]

@app.put("/api/saved-jobs/{job_id}", status_code=204)
def save_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not db.get(Job, job_id): raise HTTPException(404, "Job not found")
    if not db.scalar(select(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id)): db.add(SavedJob(user_id=user.id, job_id=job_id)); db.commit()

@app.delete("/api/saved-jobs/{job_id}", status_code=204)
def unsave_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    saved = db.scalar(select(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id))
    if saved: db.delete(saved); db.commit()

@app.post("/api/notifications", status_code=201)
def create_notification(data: dict[str, Any], db: Session = Depends(get_db), user: User = Depends(current_user)):
    recipient_id = int(data.get("userId", user.id))
    if recipient_id != user.id:
        job_id = data.get("jobId")
        job = db.get(Job, int(job_id)) if job_id else None
        if user.role != "employer" or not job or job.employer_id != user.id: raise HTTPException(403, "You cannot send this notification")
    item = Notification(user_id=recipient_id, title=str(data.get("title", "Update"))[:180], message=str(data.get("message", ""))[:4000], link=str(data.get("link", ""))[:500])
    db.add(item); db.commit(); db.refresh(item)
    return {"id": item.id, "title": item.title, "message": item.message, "link": item.link, "read": item.read, "createdAt": item.created_at.isoformat()}

@app.get("/api/notifications")
def notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)).all()
    return [{"id": x.id, "userId": str(x.user_id), "title": x.title, "message": x.message, "link": x.link, "read": x.read, "createdAt": x.created_at.isoformat()} for x in items]

@app.patch("/api/notifications/{notification_id}/read", status_code=204)
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(Notification, notification_id)
    if not item or item.user_id != user.id: raise HTTPException(404, "Notification not found")
    item.read = True; db.commit()

@app.get("/api/companies")
def companies(db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.status == "active").order_by(Job.created_at.desc())).all()
    result = {}
    for job in jobs:
        company = result.setdefault(job.company_name, {"name": job.company_name, "employerId": str(job.employer_id), "jobs": 0, "openJobs": 0, "logo": None})
        company["jobs"] += 1; company["openJobs"] += 1
    return list(result.values())

@app.get("/api/companies/{company_name}/jobs")
def company_jobs(company_name: str, db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.company_name.ilike(company_name), Job.status == "active").order_by(Job.created_at.desc())).all()
    return [public_job(job, db) for job in jobs]

@app.get("/api/companies/{company_name}/reviews")
def company_reviews(company_name: str, db: Session = Depends(get_db)):
    reviews = db.scalars(select(Review).where(Review.company_name.ilike(company_name)).order_by(Review.created_at.desc())).all()
    return [{"id": x.id, "companyName": x.company_name, "rating": x.rating, "comment": x.comment, "createdAt": x.created_at.isoformat(), "userId": x.author_id} for x in reviews]

@app.get("/api/companies/{company_name}/follow")
def is_following(company_name: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.scalar(select(CompanyFollow).where(CompanyFollow.user_id == user.id, CompanyFollow.company_name.ilike(company_name)))
    return {"companyName": company_name, "following": bool(item)}

@app.put("/api/companies/{company_name}/follow", status_code=204)
def follow_company(company_name: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not db.scalar(select(CompanyFollow).where(CompanyFollow.user_id == user.id, CompanyFollow.company_name.ilike(company_name))): db.add(CompanyFollow(user_id=user.id, company_name=company_name)); db.commit()

@app.delete("/api/companies/{company_name}/follow", status_code=204)
def unfollow_company(company_name: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.scalar(select(CompanyFollow).where(CompanyFollow.user_id == user.id, CompanyFollow.company_name.ilike(company_name)))
    if item: db.delete(item); db.commit()

@app.post("/api/companies/{company_name}/reviews", status_code=201)
def create_review(company_name: str, data: ReviewIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    review = Review(company_name=company_name, author_id=user.id, rating=data.rating, comment=data.comment)
    db.add(review)
    try: db.commit()
    except Exception: db.rollback(); raise HTTPException(409, "You have already reviewed this company")
    db.refresh(review); return {"id": review.id, "companyName": review.company_name, "rating": review.rating, "comment": review.comment}

@app.post("/api/conversations", status_code=201)
def start_conversation(data: ConversationIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.otherUserId == user.id or not db.get(User, data.otherUserId): raise HTTPException(404, "Recipient not found")
    query = select(Conversation).where(or_(Conversation.participant_one_id == user.id, Conversation.participant_one_id == data.otherUserId), or_(Conversation.participant_two_id == data.otherUserId, Conversation.participant_two_id == user.id))
    conversation = db.scalar(query)
    if not conversation:
        conversation = Conversation(participant_one_id=user.id, participant_two_id=data.otherUserId, job_id=data.jobId); db.add(conversation); db.commit(); db.refresh(conversation)
    return {"id": conversation.id, "otherUserId": data.otherUserId}

@app.get("/api/conversations")
def conversations(db: Session = Depends(get_db), user: User = Depends(current_user)):
    items = db.scalars(select(Conversation).where(or_(Conversation.participant_one_id == user.id, Conversation.participant_two_id == user.id)).order_by(Conversation.updated_at.desc())).all()
    result = []
    for item in items:
        other_id = item.participant_two_id if item.participant_one_id == user.id else item.participant_one_id
        other = db.get(User, other_id); last = db.scalar(select(Message).where(Message.conversation_id == item.id).order_by(Message.created_at.desc()).limit(1))
        result.append({"id": item.id, "otherUser": public_user(other), "participants": [str(item.participant_one_id), str(item.participant_two_id)], "jobId": str(item.job_id) if item.job_id else None, "lastMessage": last.body if last else "", "lastMessageAt": item.updated_at.isoformat(), "updatedAt": item.updated_at.isoformat()})
    return result

@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(Conversation, conversation_id)
    if not item or user.id not in {item.participant_one_id, item.participant_two_id}: raise HTTPException(404, "Conversation not found")
    other_id = item.participant_two_id if item.participant_one_id == user.id else item.participant_one_id
    last = db.scalar(select(Message).where(Message.conversation_id == item.id).order_by(Message.created_at.desc()).limit(1))
    return {"id": item.id, "participants": [str(item.participant_one_id), str(item.participant_two_id)], "jobId": str(item.job_id) if item.job_id else None, "otherUser": public_user(db.get(User, other_id)), "lastMessage": last.body if last else "", "lastMessageAt": item.updated_at.isoformat()}

@app.patch("/api/conversations/{conversation_id}")
def update_conversation(conversation_id: int, data: dict[str, Any], db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(Conversation, conversation_id)
    if not item or user.id not in {item.participant_one_id, item.participant_two_id}: raise HTTPException(404, "Conversation not found")
    item.updated_at = datetime.now(timezone.utc); db.commit()
    return get_conversation(conversation_id, db, user)

@app.get("/api/conversations/{conversation_id}/messages")
def get_messages(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or user.id not in {conversation.participant_one_id, conversation.participant_two_id}: raise HTTPException(404, "Conversation not found")
    messages = db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)).all()
    return [{"id": m.id, "senderId": m.sender_id, "body": m.body, "text": m.body, "read": m.read, "createdAt": m.created_at.isoformat()} for m in messages]

@app.patch("/api/conversations/{conversation_id}/messages/{message_id}/read", status_code=204)
def mark_message_read(conversation_id: int, message_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    conversation = db.get(Conversation, conversation_id)
    item = db.get(Message, message_id)
    if not conversation or user.id not in {conversation.participant_one_id, conversation.participant_two_id} or not item or item.conversation_id != conversation_id: raise HTTPException(404, "Message not found")
    if item.sender_id != user.id: item.read = True; db.commit()

@app.post("/api/conversations/{conversation_id}/messages", status_code=201)
def send_message(conversation_id: int, data: MessageIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or user.id not in {conversation.participant_one_id, conversation.participant_two_id}: raise HTTPException(404, "Conversation not found")
    message = Message(conversation_id=conversation_id, sender_id=user.id, body=data.body.strip())
    conversation.updated_at = datetime.now(timezone.utc); db.add(message); db.commit(); db.refresh(message)
    recipient = conversation.participant_two_id if conversation.participant_one_id == user.id else conversation.participant_one_id
    db.add(Notification(user_id=recipient, title="New message", message=f"{user.name} sent you a message", link=f"/messages/{conversation_id}")); db.commit()
    return {"id": message.id, "senderId": message.sender_id, "body": message.body, "text": message.body, "createdAt": message.created_at.isoformat()}
