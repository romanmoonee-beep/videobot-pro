"""
VideoBot Pro - Database Service
Управление подключениями к базе данных и транзакциями
"""

import asyncio
import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Dict, Any, List
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine, text, event
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError, DisconnectionError

from shared.config.database import db_config, get_async_session
from shared.config.settings import settings
from shared.models import Base, User, DownloadTask, DownloadBatch, get_models_in_dependency_order

logger = structlog.get_logger(__name__)

class DatabaseService:
    """Сервис управления базой данных"""
    
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.sync_engine = None
        self.session_factory: Optional[async_sessionmaker] = None
        self.sync_session_factory = None
        self._initialized = False
        self._health_status = False
        
        # Метрики
        self.connection_count = 0
        self.query_count = 0
        self.error_count = 0
        self.last_health_check = None
        
    async def initialize(self):
        """Инициализация сервиса базы данных"""
        if self._initialized:
            return
            
        try:
            logger.info("Initializing database service...")
            
            # Используем конфигурацию из db_config
            await db_config.initialize()
            
            self.engine = db_config.async_engine
            self.sync_engine = db_config.sync_engine
            self.session_factory = db_config.async_session_factory
            self.sync_session_factory = db_config.sync_session_factory
            
            # Настраиваем метрики
            self._setup_metrics()
            
            # Проверяем подключение
            await self.health_check()
            
            self._initialized = True
            logger.info("Database service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database service: {e}")
            raise
    
    def _setup_metrics(self):
        """Настройка метрик для мониторинга"""
        
        @event.listens_for(self.engine.sync_engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            self.connection_count += 1
            
        @event.listens_for(self.engine.sync_engine, "before_cursor_execute") 
        def on_before_execute(conn, cursor, statement, parameters, context, executemany):
            self.query_count += 1
            
        @event.listens_for(self.engine.sync_engine, "handle_error")
        def on_error(exception_context):
            self.error_count += 1
            logger.error(f"Database error: {exception_context.original_exception}")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Получить асинхронную сессию базы данных"""
        if not self._initialized:
            await self.initialize()
            
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            finally:
                await session.close()
    
    @asynccontextmanager
    async def get_sync_session(self) -> Session:
        """Получить синхронную сессию базы данных"""
        session = self.sync_session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Sync database session error: {e}")
            raise
        finally:
            session.close()
    
    async def health_check(self) -> Dict[str, Any]:
        """Проверка состояния базы данных"""
        try:
            start_time = asyncio.get_event_loop().time()
            
            async with self.get_session() as session:
                # Простой запрос для проверки соединения
                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1
                
                # Проверка количества подключений
                connections_result = await session.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
                )
                active_connections = connections_result.scalar()
            
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            self._health_status = True
            self.last_health_check = datetime.utcnow()
            
            return {
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "active_connections": active_connections,
                "pool_size": settings.DATABASE_POOL_SIZE,
                "total_connections": self.connection_count,
                "total_queries": self.query_count,
                "total_errors": self.error_count,
                "last_check": self.last_health_check.isoformat()
            }
            
        except Exception as e:
            self._health_status = False
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }
    
    def is_healthy(self) -> bool:
        """Проверить состояние сервиса"""
        return self._health_status and self._initialized
    
    async def create_tables(self):
        """Создание всех таблиц"""
        if not self._initialized:
            await self.initialize()
            
        logger.info("Creating database tables...")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    
    async def drop_tables(self):
        """Удаление всех таблиц"""
        if not self._initialized:
            await self.initialize()
            
        logger.warning("Dropping all database tables...")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All database tables dropped")
    
    async def migrate_database(self):
        """Выполнение миграций базы данных"""
        try:
            logger.info("Starting database migration...")
            
            # Здесь можно добавить логику миграций
            # Например, проверка версии схемы и выполнение необходимых изменений
            
            async with self.get_session() as session:
                # Проверяем существование таблиц
                result = await session.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
                )
                existing_tables = {row[0] for row in result.fetchall()}
                
                models = get_models_in_dependency_order()
                required_tables = {model.__tablename__ for model in models}
                
                missing_tables = required_tables - existing_tables
                if missing_tables:
                    logger.info(f"Missing tables detected: {missing_tables}")
                    await self.create_tables()
                else:
                    logger.info("All required tables exist")
            
            logger.info("Database migration completed")
            
        except Exception as e:
            logger.error(f"Database migration failed: {e}")
            raise
    
    async def backup_database(self, backup_path: str = None) -> str:
        """Создание резервной копии базы данных"""
        import subprocess
        import tempfile
        from pathlib import Path
        
        if not backup_path:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_path = f"/tmp/videobot_backup_{timestamp}.sql"
        
        try:
            # Извлекаем параметры подключения из DATABASE_URL
            db_url = settings.DATABASE_URL
            # Простой парсинг URL (в продакшене лучше использовать sqlalchemy.engine.url.make_url)
            
            logger.info(f"Creating database backup: {backup_path}")
            
            # Выполняем pg_dump
            result = subprocess.run([
                "pg_dump",
                db_url.replace("postgresql://", "").replace("postgresql+asyncpg://", ""),
                "-f", backup_path,
                "--verbose"
            ], capture_output=True, text=True, check=True)
            
            logger.info(f"Database backup created successfully: {backup_path}")
            return backup_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Database backup failed: {e.stderr}")
            raise
        except Exception as e:
            logger.error(f"Backup process failed: {e}")
            raise
    
    async def vacuum_analyze(self):
        """Выполнение VACUUM ANALYZE для оптимизации"""
        try:
            logger.info("Starting database vacuum analyze...")
            
            # Используем синхронную сессию для VACUUM
            with self.sync_engine.connect() as conn:
                conn.execute(text("VACUUM ANALYZE"))
            
            logger.info("Database vacuum analyze completed")
            
        except Exception as e:
            logger.error(f"Vacuum analyze failed: {e}")
            raise
    
    async def cleanup_old_data(self):
        """Очистка старых данных"""
        try:
            logger.info("Starting old data cleanup...")
            
            async with self.get_session() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=90)
                
                # Очистка старых аналитических событий
                result = await session.execute(
                    text("DELETE FROM analytics_events WHERE created_at < :cutoff AND is_processed = true"),
                    {"cutoff": cutoff_date}
                )
                deleted_events = result.rowcount
                
                # Очистка старых завершенных задач
                task_cutoff = datetime.utcnow() - timedelta(days=7)
                result = await session.execute(
                    text("DELETE FROM download_tasks WHERE created_at < :cutoff AND status IN ('completed', 'failed')"),
                    {"cutoff": task_cutoff}
                )
                deleted_tasks = result.rowcount
                
                await session.commit()
                
                logger.info(f"Cleanup completed: {deleted_events} events, {deleted_tasks} tasks deleted")
                
        except Exception as e:
            logger.error(f"Data cleanup failed: {e}")
            raise
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Получение статистики базы данных"""
        try:
            async with self.get_session() as session:
                # Размер базы данных
                db_size_result = await session.execute(
                    text("SELECT pg_size_pretty(pg_database_size(current_database()))")
                )
                db_size = db_size_result.scalar()
                
                # Статистика по таблицам
                tables_stats = await session.execute(text("""
                    SELECT 
                        schemaname,
                        tablename,
                        n_tup_ins as inserts,
                        n_tup_upd as updates,
                        n_tup_del as deletes,
                        n_live_tup as live_rows,
                        n_dead_tup as dead_rows
                    FROM pg_stat_user_tables
                    ORDER BY n_live_tup DESC
                """))
                
                tables_data = []
                for row in tables_stats.fetchall():
                    tables_data.append({
                        "schema": row.schemaname,
                        "table": row.tablename,
                        "inserts": row.inserts,
                        "updates": row.updates,  
                        "deletes": row.deletes,
                        "live_rows": row.live_rows,
                        "dead_rows": row.dead_rows
                    })
                
                # Активные подключения
                connections_result = await session.execute(text("""
                    SELECT 
                        count(*) as total_connections,
                        count(*) FILTER (WHERE state = 'active') as active_connections,
                        count(*) FILTER (WHERE state = 'idle') as idle_connections
                    FROM pg_stat_activity
                """))
                
                conn_stats = connections_result.fetchone()
                
                return {
                    "database_size": db_size,
                    "tables": tables_data,
                    "connections": {
                        "total": conn_stats.total_connections,
                        "active": conn_stats.active_connections,
                        "idle": conn_stats.idle_connections
                    },
                    "service_metrics": {
                        "total_connections": self.connection_count,
                        "total_queries": self.query_count,
                        "total_errors": self.error_count,
                        "pool_size": settings.DATABASE_POOL_SIZE
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {"error": str(e)}
    
    async def execute_raw_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict]:
        """Выполнение сырого SQL запроса"""
        try:
            async with self.get_session() as session:
                result = await session.execute(text(query), params or {})
                
                # Конвертируем результат в список словарей
                columns = result.keys()
                rows = result.fetchall()
                
                return [dict(zip(columns, row)) for row in rows]
                
        except Exception as e:
            logger.error(f"Raw query execution failed: {e}")
            raise
    
    async def shutdown(self):
        """Корректное завершение работы сервиса"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Async database engine disposed")
            
        if self.sync_engine:
            self.sync_engine.dispose()
            logger.info("Sync database engine disposed")
            
        self._initialized = False
        self._health_status = False
        logger.info("Database service shutdown completed")

# Глобальный экземпляр сервиса
_database_service = DatabaseService()

# Удобные функции для использования в других модулях
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Получить сессию базы данных"""
    async with _database_service.get_session() as session:
        yield session

async def health_check() -> Dict[str, Any]:
    """Проверить состояние базы данных"""
    return await _database_service.health_check()

# Декоратор для автоматического управления транзакциями
def with_db_transaction(func):
    """Декоратор для автоматического управления транзакциями"""
    async def wrapper(*args, **kwargs):
        async with _database_service.get_session() as session:
            try:
                # Добавляем сессию в kwargs
                kwargs['session'] = session
                result = await func(*args, **kwargs)
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()
                raise
    return wrapper

class DatabaseManager:
    """Менеджер для выполнения административных задач БД"""
    
    def __init__(self, service: DatabaseService):
        self.service = service
    
    async def maintenance_routine(self):
        """Регулярное обслуживание базы данных"""
        logger.info("Starting database maintenance routine...")
        
        try:
            # Очистка старых данных
            await self.service.cleanup_old_data()
            
            # Vacuum analyze для оптимизации
            await self.service.vacuum_analyze()
            
            # Проверка здоровья
            health = await self.service.health_check()
            if health['status'] != 'healthy':
                logger.warning(f"Database health check failed: {health}")
            
            logger.info("Database maintenance routine completed")
            
        except Exception as e:
            logger.error(f"Database maintenance failed: {e}")
            raise
    
    async def create_backup_schedule(self, interval_hours: int = 24):
        """Запуск регулярного создания резервных копий"""
        while True:
            try:
                backup_path = await self.service.backup_database()
                logger.info(f"Scheduled backup created: {backup_path}")
                
                await asyncio.sleep(interval_hours * 3600)  # Конвертируем часы в секунды
                
            except Exception as e:
                logger.error(f"Scheduled backup failed: {e}")
                await asyncio.sleep(3600)  # Повторить через час при ошибке