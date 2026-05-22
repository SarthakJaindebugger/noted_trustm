from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
import os
import logging

logger = logging.getLogger(__name__)

# Database configuration
from config import settings
DATABASE_URL = os.getenv("DATABASE_URL", settings.database.url)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    future=True
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# Base class for models
Base = declarative_base()


def _ensure_session_owner_columns(sync_conn):
    existing_columns = {column["name"] for column in inspect(sync_conn).get_columns("sessions")}

    if "owner_user_id" not in existing_columns:
        sync_conn.execute(text("ALTER TABLE sessions ADD COLUMN owner_user_id VARCHAR(255)"))
    if "owner_username" not in existing_columns:
        sync_conn.execute(text("ALTER TABLE sessions ADD COLUMN owner_username VARCHAR(255)"))

    sync_conn.execute(
        text(
            """
            UPDATE sessions
            SET owner_user_id = COALESCE(owner_user_id, :owner_user_id),
                owner_username = COALESCE(owner_username, :owner_username)
            """
        ),
        {
            "owner_user_id": settings.auth.user_id,
            "owner_username": settings.auth.username,
        },
    )

async def get_db():
    """Dependency to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Initialize database tables"""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_ensure_session_owner_columns)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")
