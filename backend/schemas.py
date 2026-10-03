from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
