try:
    from .database import Base, engine
    from .models import Note, User
except ImportError:  # pragma: no cover - fallback when run directly from the backend dir
    from database import Base, engine
    from models import Note, User

Base.metadata.create_all(
    bind=engine,
    tables=[Note.__table__, User.__table__],
)

print("Database tables created successfully.")
