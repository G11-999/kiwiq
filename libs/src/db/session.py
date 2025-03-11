"""
Database session management module.

This module provides database session management utilities using SQLAlchemy and SQLModel.
It handles connection pooling and session creation.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel, create_engine

from global_config.settings import settings

# Create database engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)

# Session factory for creating new database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def init_db() -> None:
    """Initialize database by creating all tables."""
    SQLModel.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Get a new database session.
    
    Returns:
        Session: A new SQLAlchemy session instance.
    """
    return SessionLocal()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for database sessions.
    
    This ensures proper handling of database sessions, including
    automatic closing and rollback on exceptions.
    
    Yields:
        Session: Database session that will be automatically closed.
    
    Example:
        ```python
        with get_db() as db:
            db.query(User).all()
        ```
    """
    db = get_session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close() 