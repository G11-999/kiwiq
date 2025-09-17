"""
Database session management module.

This module provides database session management utilities using SQLModel with
singleton threadsafe instances and configurable connection parameters.

Key Features:
- Singleton threadsafe database engines (sync and async) 
- Singleton threadsafe session factories
- Configurable connection pool parameters via configure_database()
- Thread-safe lazy initialization with proper locking
- Context managers for automatic session lifecycle management

Usage Examples:
    # Basic usage with default configuration
    session = get_sync_session()
    async_session = await get_async_session()
    
    # Configure custom SQLAlchemy connection parameters
    configure_database(pool_size=20, max_overflow=15, echo=True)
    
    # Configure psycopg worker pools for LangGraph
    configure_database(worker_pool_size=10, worker_pool_max_size=25)
    
    # Configure both SQLAlchemy and worker pools
    configure_database(
        pool_size=15, max_overflow=10,  # SQLAlchemy engines
        worker_pool_size=8, worker_pool_max_size=20  # Psycopg worker pools
    )
    
    # Use context managers for automatic cleanup
    with get_db_as_manager() as session:
        # session operations
        pass
    
    async with get_async_db_as_manager() as session:
        # async session operations  
        pass
        
    # Use configurable psycopg pools for LangGraph
    async with get_async_pool() as pool:
        # raw psycopg operations for LangGraph checkpointer
        pass

Design Decisions:
- DatabaseManager implements singleton pattern with double-checked locking
- Lazy initialization of engines and session factories for performance
- Configuration overrides reset existing instances to apply new settings
- Extensive documentation and type hints for better developer experience
"""
import asyncio
import threading
from contextlib import asynccontextmanager, contextmanager
from typing import Generator, AsyncGenerator, Optional, Dict, Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, ConnectionPool

# --- SQLModel Imports ---
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import create_engine, Engine
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
POOL_SIZE = global_settings.effective_pool_size
MAX_OVERFLOW = global_settings.effective_max_overflow
WORKER_POOL_SIZE = global_settings.WORKER_DB_POOL_SIZE
WORKER_MAX_OVERFLOW = global_settings.WORKER_DB_MAX_OVERFLOW
WORKER_POOL_MAX_SIZE = global_settings.WORKER_POOL_MAX_SIZE

# ========================================
# Singleton Engine and Session Factory Management
# ========================================

class DatabaseManager:
    """
    Threadsafe singleton manager for database engines, session factories, and connection pools.
    
    Provides unified configurable database connection management for both SQLAlchemy 
    engines/sessions and psycopg worker connection pools. Supports overriding global 
    settings for pool sizes, overflow limits, and other connection parameters.
    
    Features:
    - SQLAlchemy sync/async engines with singleton pattern
    - SQLAlchemy session factories for ORM operations  
    - Configuration support for psycopg worker pools (LangGraph checkpointer)
    - Thread-safe lazy initialization with double-checked locking
    - Runtime configuration updates that reset instances automatically
    """
    
    _instance: Optional['DatabaseManager'] = None
    _lock = threading.Lock()
    _init_lock = threading.Lock()
    
    def __new__(cls) -> 'DatabaseManager':
        """Ensure singleton instance creation with thread safety."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """
        Initialize the DatabaseManager singleton.
        
        Note: This init method is protected by _init_lock to prevent multiple
        initialization in threaded environments.
        """
        # Prevent multiple initialization of the same instance
        if hasattr(self, '_initialized'):
            return
            
        with self._init_lock:
            if hasattr(self, '_initialized'):
                return
                
            # Engine instances - will be created lazily
            self._sync_engine: Optional[Engine] = None
            self._async_engine: Optional[AsyncEngine] = None
            
            # Session factory instances - will be created lazily
            self._sync_session_factory: Optional[sessionmaker] = None
            self._async_session_factory: Optional[async_sessionmaker] = None
            
            # Configuration overrides - can be set during initialization
            self._config_overrides: Dict[str, Any] = {}
            
            # Locks for lazy initialization of engines and session factories
            self._sync_engine_lock = threading.Lock()
            self._async_engine_lock = threading.Lock()
            self._sync_session_lock = threading.Lock()
            self._async_session_lock = threading.Lock()
            
            self._initialized = True
    
    def configure(self, **overrides: Any) -> None:
        """
        Configure database connection parameters, overriding global settings.
        
        This method allows configuration of both SQLAlchemy engines and psycopg
        worker pools used throughout the application. Configuration changes take
        effect immediately by resetting existing instances.
        
        Args:
            **overrides: Configuration parameters to override. Supported keys:
                
                SQLAlchemy Engine Configuration:
                - pool_size: Size of the SQLAlchemy connection pool
                - max_overflow: Maximum overflow connections for SQLAlchemy
                - pool_timeout: Timeout waiting for connection from pool
                - pool_recycle: Connection recycle time in seconds
                - pool_pre_ping: Whether to ping connections before use
                - echo: Whether to echo SQL statements
                - echo_pool: Whether to echo pool events
                
                Psycopg Worker Pool Configuration:
                - worker_pool_size: Minimum size of psycopg worker pool
                - worker_max_overflow: Maximum overflow for psycopg worker pool
                - worker_pool_max_size: Maximum size of psycopg worker pool
        
        Examples:
            db_manager = DatabaseManager()
            
            # Configure SQLAlchemy settings
            db_manager.configure(pool_size=20, max_overflow=10)
            
            # Configure worker pool settings for LangGraph
            db_manager.configure(worker_pool_size=15, worker_pool_max_size=25)
            
            # Configure both at once
            db_manager.configure(
                pool_size=15, max_overflow=8,  # SQLAlchemy
                worker_pool_size=10, worker_pool_max_size=20  # Psycopg
            )
        """
        self._config_overrides.update(overrides)
        
        # Reset existing engines and session factories to force recreation with new config
        # Note: psycopg pools are created fresh each time via context manager, so no reset needed
        with self._sync_engine_lock:
            self._sync_engine = None
        with self._async_engine_lock:
            self._async_engine = None
        with self._sync_session_lock:
            self._sync_session_factory = None
        with self._async_session_lock:
            self._async_session_factory = None
    
    def _get_effective_config(self) -> Dict[str, Any]:
        """
        Get effective configuration by merging global settings with overrides.
        
        Returns:
            Dict containing the effective configuration parameters.
        """
        config = {
            # SQLAlchemy engine configurations
            'pool_size': POOL_SIZE,
            'max_overflow': MAX_OVERFLOW,
            'pool_timeout': 30,
            'pool_recycle': 3600,
            'pool_pre_ping': True,
            'echo': ENGINE_ECHO,
            'echo_pool': False,
            
            # Psycopg worker pool configurations (for LangGraph/raw connections)
            'worker_pool_size': WORKER_POOL_SIZE,
            'worker_max_overflow': WORKER_MAX_OVERFLOW,
            'worker_pool_max_size': WORKER_POOL_MAX_SIZE,
        }
        
        # Apply configuration overrides
        config.update(self._config_overrides)
        
        return config
    
    def get_sync_engine(self) -> Engine:
        """
        Get singleton synchronous database engine with thread safety.
        
        Returns:
            Engine: SQLAlchemy synchronous engine instance.
        """
        if self._sync_engine is None:
            with self._sync_engine_lock:
                if self._sync_engine is None:
                    config = self._get_effective_config()
                    
                    self._sync_engine = create_engine(
                        DATABASE_URL_SYNC,
                        echo=config['echo'],
                        pool_size=config['pool_size'],
                        max_overflow=config['max_overflow'],
                        pool_timeout=config['pool_timeout'],
                        pool_recycle=config['pool_recycle'],
                        pool_pre_ping=config['pool_pre_ping'],
                        echo_pool=config['echo_pool'],
                        # connect_args={
                        #     "options": "-c statement_timeout=60000",  # 60 second statement timeout (milliseconds)
                        #     "connect_timeout": 10,  # Connection establishment timeout (10 seconds)
                        # },
                    )
        
        return self._sync_engine
    
    def get_async_engine(self) -> AsyncEngine:
        """
        Get singleton asynchronous database engine with thread safety.
        
        Returns:
            AsyncEngine: SQLAlchemy asynchronous engine instance.
        """
        if self._async_engine is None:
            with self._async_engine_lock:
                if self._async_engine is None:
                    config = self._get_effective_config()
                    
                    self._async_engine = create_async_engine(
    DATABASE_URL_ASYNC,
                        echo=config['echo'],
                        pool_size=config['pool_size'],
                        max_overflow=config['max_overflow'],
                        pool_timeout=config['pool_timeout'],
                        pool_recycle=config['pool_recycle'],
                        pool_pre_ping=config['pool_pre_ping'],
                        echo_pool=config['echo_pool'],
    # connect_args={
    #     "server_settings": {"jit": "off"},  # Disable JIT for more predictable performance
    #     "command_timeout": 60,  # Individual query timeout (60 seconds)
    #     "connect_timeout": 10,  # Connection establishment timeout (10 seconds)
    # },
)

        return self._async_engine
    
    def get_sync_session_factory(self) -> sessionmaker:
        """
        Get singleton synchronous session factory with thread safety.
        
        Returns:
            sessionmaker: SQLAlchemy synchronous session factory.
        """
        if self._sync_session_factory is None:
            with self._sync_session_lock:
                if self._sync_session_factory is None:
                    self._sync_session_factory = sessionmaker(
                        self.get_sync_engine(),
                        class_=Session,  # Use SQLModel's Session
                        expire_on_commit=False,
                        autocommit=False,
                        autoflush=False,
                    )

        return self._sync_session_factory
    
    def get_async_session_factory(self) -> async_sessionmaker:
        """
        Get singleton asynchronous session factory with thread safety.
        
        Returns:
            async_sessionmaker: SQLAlchemy asynchronous session factory.
        """
        if self._async_session_factory is None:
            with self._async_session_lock:
                if self._async_session_factory is None:
                    self._async_session_factory = async_sessionmaker(
                        self.get_async_engine(),
                        class_=AsyncSession,  # Use SQLModel's AsyncSession
                        expire_on_commit=False,
                        autocommit=False,
                        autoflush=False,
                    )
        
        return self._async_session_factory


# ========================================
# Global Database Manager Instance
# ========================================

# Global singleton instance for easy access
_db_manager = DatabaseManager()


def configure_database(**overrides: Any) -> None:
    """
    Configure global database settings with optional parameter overrides.
    
    This function allows you to override global database configuration settings
    for both SQLAlchemy engines and psycopg connection pools without modifying 
    global_settings directly.
    
    Args:
        **overrides: Configuration parameters to override. Supported keys:
            
            SQLAlchemy Engine Configuration:
            - pool_size: Size of the SQLAlchemy connection pool
            - max_overflow: Maximum overflow connections for SQLAlchemy
            - pool_timeout: Timeout waiting for connection from pool
            - pool_recycle: Connection recycle time in seconds
            - pool_pre_ping: Whether to ping connections before use
            - echo: Whether to echo SQL statements
            - echo_pool: Whether to echo pool events
            
            Psycopg Worker Pool Configuration (for LangGraph/raw connections):
            - worker_pool_size: Minimum size of psycopg worker pool
            - worker_max_overflow: Maximum overflow for psycopg worker pool
            - worker_pool_max_size: Maximum size of psycopg worker pool
    
    Examples:
        # Configure SQLAlchemy for high-load environment
        configure_database(pool_size=20, max_overflow=15, pool_timeout=60)
        
        # Configure worker pools for heavy LangGraph usage
        configure_database(worker_pool_size=10, worker_pool_max_size=25)
        
        # Configure for development with SQL logging
        configure_database(echo=True, echo_pool=True)
        
        # Configure both SQLAlchemy and worker pools
        configure_database(
            pool_size=15, max_overflow=10,  # SQLAlchemy
            worker_pool_size=8, worker_pool_max_size=20  # Psycopg worker pools
        )
    """
    if "pool_tier_size" in overrides:
        pool_tier_size = overrides.pop('pool_tier_size')
    if pool_tier_size == "small":
        return
    elif pool_tier_size == "medium":
        pool_size = global_settings.WORKER_MEDIUM_POOL_SIZE
        max_overflow = global_settings.WORKER_MEDIUM_MAX_OVERFLOW
        worker_pool_max_size = global_settings.WORKER_MEDIUM_LANGGRAPH_POOL_MAX_SIZE
        worker_pool_size = global_settings.WORKER_MEDIUM_LANGGRAPH_POOL_SIZE
        overrides['worker_pool_max_size'] = worker_pool_max_size
        overrides['worker_pool_size'] = worker_pool_size
        overrides['pool_timeout'] = global_settings.WORKER_MEDIUM_POOL_TIMEOUT
    elif pool_tier_size == "large":
        pool_size = global_settings.WORKER_LARGE_POOL_SIZE
        max_overflow = global_settings.WORKER_LARGE_MAX_OVERFLOW
        worker_pool_max_size = global_settings.WORKER_LARGE_LANGGRAPH_POOL_MAX_SIZE
        worker_pool_size = global_settings.WORKER_LARGE_LANGGRAPH_POOL_SIZE
        overrides['worker_pool_max_size'] = worker_pool_max_size
        overrides['worker_pool_size'] = worker_pool_size
        overrides['pool_timeout'] = global_settings.WORKER_LARGE_POOL_TIMEOUT
    elif pool_tier_size == "xlarge":
        pool_size = global_settings.WORKER_XLARGE_POOL_SIZE
        max_overflow = global_settings.WORKER_XLARGE_MAX_OVERFLOW
        worker_pool_max_size = global_settings.WORKER_XLARGE_LANGGRAPH_POOL_MAX_SIZE
        worker_pool_size = global_settings.WORKER_XLARGE_LANGGRAPH_POOL_SIZE
        overrides['worker_pool_max_size'] = worker_pool_max_size
        overrides['worker_pool_size'] = worker_pool_size
        overrides['pool_timeout'] = global_settings.WORKER_XLARGE_POOL_TIMEOUT
    else:
        raise ValueError(f"Invalid pool tier size: {pool_tier_size}")
    overrides['pool_size'] = pool_size
    overrides['max_overflow'] = max_overflow
    
    _db_manager.configure(**overrides)


def get_sync_engine() -> Engine:
    """
    Get singleton synchronous database engine.
    
    This function returns a threadsafe singleton SQLAlchemy Engine instance
    configured with global settings and any overrides set via configure_database().
    
    Returns:
        Engine: SQLAlchemy synchronous engine instance.
        
    Example:
        engine = get_sync_engine()
        # Engine is a singleton - subsequent calls return the same instance
    """
    return _db_manager.get_sync_engine()


def get_async_engine() -> AsyncEngine:
    """
    Get singleton asynchronous database engine.
    
    This function returns a threadsafe singleton SQLAlchemy AsyncEngine instance
    configured with global settings and any overrides set via configure_database().
    
    Returns:
        AsyncEngine: SQLAlchemy asynchronous engine instance.
        
    Example:
        async_engine = get_async_engine()
        # Engine is a singleton - subsequent calls return the same instance
    """
    return _db_manager.get_async_engine()

# ========================================
# Direct Psycopg Connection Pool Setup
# ========================================

pool_connection_kwargs = {
    "autocommit": True, # Note: This is for raw psycopg connections, not ORM sessions
    "prepare_threshold": 0,
    "row_factory": dict_row,
}


@asynccontextmanager
async def get_async_pool() -> AsyncGenerator[AsyncConnectionPool, None]:
    """
    Get an asynchronous psycopg connection pool for LangGraph checkpointer.
    
    NOTE: This uses global_settings.LANGGRAPH_DATABASE_URL and is specifically
    designed for LangGraph checkpointer functionality. Pool configuration can
    be customized via configure_database() with worker_* parameters.

    Provides an AsyncConnectionPool configured for asynchronous PostgreSQL access
    using configurable worker pool settings. The pool is automatically closed 
    when the context is exited.

    Yields:
        AsyncConnectionPool: An asynchronous connection pool for PostgreSQL,
                           configured with singleton threadsafe parameters.

    Example:
        # Use with default worker pool configuration
        async with get_async_pool() as pool:
            async with pool.connection() as aconn:
                async with aconn.cursor() as acur:
                    await acur.execute("SELECT 1")
                    
        # Configure worker pool size before usage
        configure_database(worker_pool_size=15, worker_pool_max_size=30)
        async with get_async_pool() as pool:
            # pool now uses custom configuration
            pass
    """
    # Get effective configuration from singleton database manager
    config = _db_manager._get_effective_config()
    
    # Extract worker pool configuration
    worker_pool_size = config['worker_pool_size']
    worker_pool_max_size = config['worker_pool_max_size']
    pool_timeout = config['pool_timeout']
    
    # Create pool with configurable parameters
    pool = AsyncConnectionPool(
        conninfo=global_settings.LANGGRAPH_DATABASE_URL,  # Raw URL is fine for psycopg directly
        min_size=worker_pool_size,
        max_size=max(worker_pool_size, worker_pool_max_size),
        kwargs=pool_connection_kwargs,
        timeout=pool_timeout,
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

    Uses the SQLModel metadata and the singleton async engine to create tables.
    This function ensures that all database tables are created according to
    the SQLModel definitions.
    
    Example:
        await init_db()  # Creates all tables defined in SQLModel models
    """
    async_engine = get_async_engine()  # Use singleton async engine
    async with async_engine.begin() as conn:
        # SQLModel.metadata contains all tables defined using SQLModel
        await conn.run_sync(SQLModel.metadata.create_all)

# ========================================
# SQLModel Session Getters
# ========================================

def get_sync_session() -> Session:
    """
    Get a new synchronous SQLModel database session.
    
    This function uses the singleton session factory to create new session instances.
    Each call returns a new session, but the underlying engine and session factory
    are singletons for optimal resource management.

    Returns:
        Session: A new SQLModel session instance.
                 Caller is responsible for closing the session.
        
    Example:
        session = get_sync_session()
        try:
            # Use session for database operations
            result = session.exec(select(MyModel)).all()
        finally:
            session.close()
    """
    session_factory = _db_manager.get_sync_session_factory()
    return session_factory()


async def get_async_session() -> AsyncSession:
    """
    Get a new asynchronous SQLModel database session.
    
    This function uses the singleton session factory to create new session instances.
    Each call returns a new session, but the underlying engine and session factory
    are singletons for optimal resource management.

    Returns:
        AsyncSession: A new SQLModel async session instance.
                      Caller is responsible for closing the session.
        
    Example:
        session = await get_async_session()
        try:
            # Use session for database operations
            result = await session.exec(select(MyModel))
            models = result.all()
        finally:
            await session.close()
    """
    session_factory = _db_manager.get_async_session_factory()
    return session_factory()

# ========================================
# SQLModel Context Managers for Sessions
# ========================================

@contextmanager
def get_db_as_manager() -> Generator[Session, None, None]:
    """
    Context manager for synchronous SQLModel database sessions.

    Provides a SQLModel Session using singleton session factory, managing 
    commit, rollback, and closing automatically. This ensures proper resource
    cleanup and transaction management.

    Yields:
        Session: SQLModel session managed by the context.

    Example:
        ```python
        with get_db_as_manager() as session:
            # session is a SQLModel Session from singleton factory
            hero = session.get(Hero, 1)
            # Commit happens automatically on successful exit
        # Session is automatically closed
        ```
    """
    session = get_sync_session()  # Uses singleton session factory
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

    Provides a SQLModel AsyncSession using singleton session factory, managing 
    commit, rollback, and closing automatically. This ensures proper resource
    cleanup and transaction management in async contexts.

    Yields:
        AsyncSession: SQLModel async session managed by the context.

    Example:
        ```python
        async with get_async_db_as_manager() as session:
            # session is a SQLModel AsyncSession from singleton factory
            results = await session.exec(select(Hero))
            heroes = results.all()
            # Commit happens automatically on successful exit
        # Session is automatically closed
        ```
    """
    session = await get_async_session()  # Uses singleton session factory
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_async_db_dependency() -> AsyncGenerator[AsyncSession, None]:
    """
    Async dependency generator for FastAPI-style asynchronous SQLModel database sessions.

    Provides a SQLModel AsyncSession using singleton session factory, managing 
    commit, rollback, and closing automatically. This function is designed for
    use as a FastAPI dependency injection.

    Yields:
        AsyncSession: SQLModel async session managed by the dependency.

    Example:
        ```python
        @app.get("/heroes/")
        async def get_heroes(session: AsyncSession = Depends(get_async_db_dependency)):
            # session is a SQLModel AsyncSession from singleton factory  
            results = await session.exec(select(Hero))
            return results.all()
        # Session is automatically committed and closed after request
        ```
    """
    session = await get_async_session()  # Uses singleton session factory
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

