"""
Database session management module.

This module provides database session management utilities using SQLModel.
It handles connection pooling and session creation.
"""
from contextlib import asynccontextmanager, contextmanager
from typing import Generator, AsyncGenerator

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, ConnectionPool

# --- SQLModel Imports ---
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session
from sqlmodel.ext.asyncio.session import AsyncSession

# --- SQLAlchemy Core Imports (used by SQLModel) ---
# We still need sessionmaker and async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import async_sessionmaker

from global_config.settings import global_settings

# import services / libs models here for migrations discovery!
# e.g., from services.my_service.models import MyModel

# ========================================
# Database URLs and Common Settings
# ========================================

DATABASE_URL_SYNC = global_settings.DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://')
DATABASE_URL_ASYNC = global_settings.DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://')
ENGINE_ECHO = global_settings.DB_ECHO
POOL_SIZE = global_settings.DB_POOL_SIZE
MAX_OVERFLOW = global_settings.DB_MAX_OVERFLOW

# ========================================
# SQLModel Engine and Session Setup
# ========================================

# Create SQLModel async database engine
async_engine = create_async_engine(
    DATABASE_URL_ASYNC,
    echo=ENGINE_ECHO,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW, 
)

# Create SQLModel sync engine
sync_engine = create_engine(
    DATABASE_URL_SYNC,
    echo=ENGINE_ECHO,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
)

# SQLModel Session Factories
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession, # Use SQLModel's AsyncSession
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

SyncSessionLocal = sessionmaker(
    sync_engine,
    class_=Session, # Use SQLModel's Session
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ========================================
# Direct Psycopg Connection Pool Setup
# ========================================

pool_connection_kwargs = {
    "autocommit": True, # Note: This is for raw psycopg connections, not ORM sessions
    "prepare_threshold": 0,
    "row_factory": dict_row,
}

@contextmanager
def get_pool() -> Generator[ConnectionPool, None, None]:
    """
    NOTE: this uses global_settings.LANGGRAPH_DATABASE_URL and meant to be used for LangGraph checkpointer
    Get a synchronous psycopg connection pool as a context manager.

    Provides a ConnectionPool configured for synchronous PostgreSQL access.
    The pool is automatically closed when the context is exited.

    Yields:
        ConnectionPool: A synchronous connection pool for PostgreSQL.

    Example:
        with get_pool() as pool:
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
    """
    pool = ConnectionPool(
        conninfo=global_settings.LANGGRAPH_DATABASE_URL, # Raw URL is fine for psycopg directly
        min_size=POOL_SIZE,
        max_size=MAX_OVERFLOW,
        kwargs=pool_connection_kwargs,
    )
    try:
        # Note: pool.open() might block, depending on implementation;
        # consider if truly needed in sync context if pool manages connections lazily.
        pool.open(wait=True)
        yield pool
    finally:
        pool.close()

@asynccontextmanager
async def get_async_pool() -> AsyncGenerator[AsyncConnectionPool, None]:
    """
    NOTE: this uses global_settings.LANGGRAPH_DATABASE_URL and meant to be used for LangGraph checkpointer
    Get an asynchronous psycopg connection pool as an async context manager.

    Provides an AsyncConnectionPool configured for asynchronous PostgreSQL access.
    The pool is automatically closed when the context is exited.

    Yields:
        AsyncConnectionPool: An asynchronous connection pool for PostgreSQL.

    Example:
        async with get_async_pool() as pool:
            async with pool.connection() as aconn:
                async with aconn.cursor() as acur:
                    await acur.execute("SELECT 1")
    """
    pool = AsyncConnectionPool(
        conninfo=global_settings.LANGGRAPH_DATABASE_URL, # Raw URL is fine for psycopg directly
        min_size=POOL_SIZE,
        max_size=MAX_OVERFLOW,
        kwargs=pool_connection_kwargs,
    )
    try:
        # Open the pool asynchronously
        await pool.open()
        yield pool
    finally:
        await pool.close()

# ========================================
# Database Initialization
# ========================================

async def init_db() -> None:
    """
    Initialize the database by creating all tables defined by SQLModel models.

    Uses the SQLModel metadata and the async engine to create tables.
    """
    async with async_engine.begin() as conn:
        # SQLModel.metadata contains all tables defined using SQLModel
        await conn.run_sync(SQLModel.metadata.create_all)

# ========================================
# SQLModel Session Getters
# ========================================

def get_sync_session() -> Session:
    """
    Get a new synchronous SQLModel database session.

    Returns:
        Session: A new SQLModel session instance.
                 Caller is responsible for closing the session.
    """
    return SyncSessionLocal()

async def get_async_session() -> AsyncSession:
    """
    Get a new asynchronous SQLModel database session.

    Returns:
        AsyncSession: A new SQLModel async session instance.
                      Caller is responsible for closing the session.
    """
    return AsyncSessionLocal()

# ========================================
# SQLModel Context Managers for Sessions
# ========================================

@contextmanager
def get_db_as_manager() -> Generator[Session, None, None]:
    """
    Context manager for synchronous SQLModel database sessions.

    Provides a SQLModel Session, managing commit, rollback, and closing.

    Yields:
        Session: SQLModel session managed by the context.

    Example:
        ```python
        with get_db() as session:
            # session is a SQLModel Session
            hero = session.get(Hero, 1)
        ```
    """
    session = get_sync_session() # Uses the SQLModel session factory
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

@asynccontextmanager
async def get_async_db_as_manager() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for asynchronous SQLModel database sessions.

    Provides a SQLModel AsyncSession, managing commit, rollback, and closing.

    Yields:
        AsyncSession: SQLModel async session managed by the context.

    Example:
        ```python
        async with get_async_db() as session:
            # session is a SQLModel AsyncSession
            results = await session.exec(select(Hero))
            heroes = results.all()
        ```
    """
    session = await get_async_session() # Uses the SQLModel async session factory
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
