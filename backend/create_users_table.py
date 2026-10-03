from database import Base, engine
from models import Note, User

Base.metadata.create_all(
    bind=engine,
    tables=[Note.__table__, User.__table__],
)

print("Database tables created successfully.")
