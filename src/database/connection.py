import os
from sqlmodel import SQLModel, create_engine, Session

# Get database URL from environment or default to a local SQLite file
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///aegis_guard.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# Initialize the structural engine
engine = create_engine(DATABASE_URL, echo=True, connect_args=connect_args)

def init_db():
    """Triggers the creation of all tables defined in the metadata blueprint."""
    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI dependency provider to yield thread-safe database sessions."""
    with Session(engine) as session:
        yield session