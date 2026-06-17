from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.config import get_database_url

engine = create_engine(get_database_url(), pool_pre_ping=True)
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)