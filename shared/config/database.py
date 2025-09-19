"""
VideoBot Pro - Database Configuration (Production Ready)
Асинхронная и синхронная работа, retry, FastAPI middleware, очистка и vacuum.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Callable, Awaitable
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import DisconnectionError, OperationalError
import structlog
from datetime import datetime, timedelta

# ИСПРАВЛЕНО: добавляем правильный импорт
from ..models import Base, TABLES, AnalyticsEvent

logger = structlog.get_logger(__name__)

class DatabaseConfig:
    """Конфигурация базы данных"""

    def __init__(self):
        self.async_engine: Optional[AsyncEngine] = None
        self.sync_engine = None
        self.async_session_factory: Optional[async_sessionmaker] = None
        self.sync_session_factory: Optional[sessionmaker] = None
        self._initialized = False

    async def initialize(self):
        """Инициализация подключения"""
        if self._initialized:
            return

        logger.info("Initializing database connections...")
        
        # ИСПРАВЛЕНО: добавляем lazy import для избежания циклических импортов
        from .settings import settings

        # Асинхронный движок
        self.async_engine = create_async_engine(
            settings.get_database_url(async_driver=True),
            echo=settings.DATABASE_ECHO,
            pool_pre_ping=True,
            connect_args={},  # asyncpg использует свои аргументы
            execution_options={"isolation_level": "READ_COMMITTED", "autocommit": False},
        )

        # Синхронный движок
        self.sync_engine = create_engine(
            settings.get_database_url(async_driver=False),
            echo=settings.DATABASE_ECHO,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            poolclass=QueuePool,
        )

        self.async_session_factory = async_sessionmaker(
            self.async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=True, autocommit=False
        )

        self.sync_session_factory = sessionmaker(
            self.sync_engine, class_=Session, expire_on_commit=False, autoflush=True, autocommit=False
        )

        await self._test_connection()
        self._initialized = True
        logger.info("Database connections initialized successfully")

    async def _test_connection(self):
        try:
            async with self.async_engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
            logger.info("Database connection test successful")
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            raise

    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        if not self._initialized:
            await self.initialize()
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Async DB session error: {e}")
                raise

    @asynccontextmanager 
    async def get_sync_session(self) -> AsyncGenerator[Session, None]:
        if not self._initialized:
            await self.initialize()
        with self.sync_session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"Sync DB session error: {e}")
                raise

    def get_sync_session_context(self):
        """Контекстный менеджер для синхронных вызовов внутри async теста"""
        return self.sync_session_factory()

    async def close(self):
        if self.async_engine:
            await self.async_engine.dispose()
            logger.info("Async database engine disposed")
        if self.sync_engine:
            self.sync_engine.dispose()
            logger.info("Sync database engine disposed")
        self._initialized = False

    async def with_retry(self, operation: Callable[[], Awaitable], max_retries: int = 3, delay: float = 1.0):
        last_exception = None
        for attempt in range(max_retries):
            try:
                return await operation()
            except (DisconnectionError, OperationalError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(f"Retry DB operation in {delay}s (attempt {attempt+1})")
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f"DB operation failed after {max_retries} attempts")
            except Exception as e:
                logger.error(f"Non-retryable DB error: {e}")
                raise
        raise last_exception

    # --- Maintenance utilities ---
    async def create_all_tables(self):
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("All tables created")

    async def drop_all_tables(self):
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All tables dropped")

    async def vacuum_tables(self):
        async with self.get_async_session() as session:
            for table in TABLES:
                await session.execute(text(f"VACUUM ANALYZE {table}"))
                logger.info(f"Vacuumed table {table}")
        logger.info("Database vacuum completed")

    async def cleanup_old_analytics(self, days: int = 90):
        cutoff = datetime.utcnow() - timedelta(days=days)
        async with self.get_async_session() as session:
            result = await session.execute(
                text(f"DELETE FROM analytics_events WHERE created_at < '{cutoff.isoformat()}' AND is_processed = true")
            )
            logger.info(f"Deleted {result.rowcount} old analytics events")

# Global instance
db_config = DatabaseConfig()

class DatabaseHealthCheck:
    """Проверка состояния базы данных"""

    @staticmethod
    async def check_connection() -> dict:
        try:
            start_time = asyncio.get_event_loop().time()
            async with get_async_session() as session:
                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            return {"status": "healthy", "response_time_ms": round(response_time, 2)}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

class DatabaseMaintenance:
    """Утилиты для обслуживания базы данных"""

    @staticmethod
    async def vacuum_tables():
        await db_config.vacuum_tables()

    @staticmethod
    async def cleanup_old_analytics(days: int = 90):
        await db_config.cleanup_old_analytics(days)


# --- Helper functions ---
async def init_database():
    await db_config.initialize()

async def close_database():
    await db_config.close()

@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_config.get_async_session() as session:
        yield session

@asynccontextmanager
async def get_sync_session() -> AsyncGenerator[Session, None]:  # ИСПРАВЛЕНО
    async with db_config.get_sync_session() as session:
        yield session

# --- Retry wrapper ---
async def with_retry(operation, max_retries: int = 3, delay: float = 1.0):
    return await db_config.with_retry(operation, max_retries, delay)

# --- Maintenance ---
class DatabaseMaintenance:
    @staticmethod
    async def vacuum_tables():
        await db_config.vacuum_tables()

    @staticmethod
    async def cleanup_old_analytics(days: int = 90):
        await db_config.cleanup_old_analytics(days)

# --- FastAPI middleware ---
class DatabaseMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not db_config._initialized:
            await db_config.initialize()
        await self.app(scope, receive, send)