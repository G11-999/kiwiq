"""
Database session management module.

This module provides database session management utilities using SQLAlchemy and SQLModel.
It handles connection pooling and session creation.
"""
from contextlib import asynccontextmanager, contextmanager
from typing import Generator, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import create_engine  # Added this import

from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel

from global_config.settings import settings

# import services / libs models here for migrations discovery!
# from services.linkedin_integration.models import LinkedInAccount, LinkedInPost, LinkedInComment, LinkedInReaction, LinkedInAnalytics, LinkedInPostAnalytics, EmployeeAdvocacy

# Create async database engine with connection pooling
async_engine = create_async_engine(
    settings.DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://'),
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)

# Create sync engine for migrations and sync operations
sync_engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)

# Session factories
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

SyncSessionLocal = sessionmaker(
    sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def init_db() -> None:
    """Initialize database by creating all tables."""
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

def get_sync_session() -> Session:
    """Get a new synchronous database session.
    
    Returns:
        Session: A new SQLAlchemy session instance.
    """
    return SyncSessionLocal()

async def get_async_session() -> AsyncSession:
    """Get a new asynchronous database session.
    
    Returns:
        AsyncSession: A new SQLAlchemy async session instance.
    """
    return AsyncSessionLocal()

@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for synchronous database sessions.
    
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
    db = get_sync_session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@asynccontextmanager
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions.
    
    This ensures proper handling of database sessions, including
    automatic closing and rollback on exceptions.
    
    Yields:
        AsyncSession: Database session that will be automatically closed.
    
    Example:
        ```python
        async with get_async_db() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()
        ```
    """
    db = await get_async_session()
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()
