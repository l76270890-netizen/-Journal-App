import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = ""
    mood: str = Field(default="Calm", max_length=30)
    tags: list[str] = Field(default_factory=list)
    date: str = Field(min_length=1, max_length=40)
    image: str | None = None
    favorite: bool = False
    archived: bool = False


class NoteUpdate(NoteCreate):
    pass


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AppLockSetup(BaseModel):
    lock_type: Literal["pin", "pattern"]
    secret: str = Field(min_length=4, max_length=9)

    @field_validator("secret")
    @classmethod
    def validate_lock_secret(cls, secret: str, info) -> str:
        lock_type = info.data.get("lock_type")
        if lock_type == "pin" and not re.fullmatch(r"\d{4,8}", secret):
            raise ValueError("A PIN must contain 4 to 8 digits.")
        if lock_type == "pattern" and (
            not re.fullmatch(r"[0-8]{4,9}", secret)
            or len(set(secret)) < 4
            or len(set(secret)) != len(secret)
        ):
            raise ValueError("A pattern must connect at least 4 different dots.")
        return secret


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    mood: str
    tags: list[str]
    date: str
    image: str | None
    favorite: bool
    archived: bool
