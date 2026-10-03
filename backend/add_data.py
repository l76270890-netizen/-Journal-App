from sqlalchemy import select

from database import Base, SessionLocal, engine
from models import Note, User

Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    user = db.scalars(select(User).order_by(User.id)).first()
    if user is None:
        raise RuntimeError("Register a user before adding sample notes.")

    if db.scalars(select(Note).where(Note.user_id == user.id)).first() is None:
        db.add_all(
            [
                Note(
                    title="Learn SQLite",
                    body="This is my first SQLite note",
                    date="2025-07-15T10:24:00",
                    user_id=user.id,
                ),
                Note(
                    title="Learn FastAPI",
                    body="This is my second note",
                    date="2025-07-13T15:10:00",
                    user_id=user.id,
                ),
                Note(
                    title="Practice Python",
                    body="I am learning backend development",
                    date="2025-07-11T09:40:00",
                    user_id=user.id,
                ),
            ]
        )
        db.commit()

print("Sample notes added successfully.")
