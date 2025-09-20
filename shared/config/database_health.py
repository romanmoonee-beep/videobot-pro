"""
VideoBot Pro - Database Health Check and Maintenance
Модули для мониторинга и обслуживания базы данных
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .database import get_async_session, db_config
from .settings import settings

logger = structlog.get_logger(__name__)

class DatabaseHealthCheck:
    """Проверка состояния базы данных"""
    
    @staticmethod
    async def check_connection() -> Dict[str, Any]:
        """
        Проверка соединения с базой данных
        
        Returns:
            Словарь со статусом соединения
        """
        try:
            async with get_async_session() as session:
                # Простой запрос для проверки соединения
                result = await session.execute(text("SELECT 1"))
                result.fetchone()
                
                # Проверяем время отклика
                start_time = datetime.now()
                await session.execute(text("SELECT COUNT(*) FROM users"))
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                
                return {
                    "status": "healthy",
                    "response_time_ms": round(response_time, 2),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database connection check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "error_type": "SQLAlchemyError",
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Unexpected error in database check: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    async def get_database_stats() -> Dict[str, Any]:
        """
        Получение статистики базы данных
        
        Returns:
            Статистика БД
        """
        try:
            async with get_async_session() as session:
                stats = {}
                
                # Размер базы данных (PostgreSQL)
                if 'postgresql' in settings.DATABASE_URL:
                    db_size_result = await session.execute(text("""
                        SELECT pg_size_pretty(pg_database_size(current_database())) as size,
                               pg_database_size(current_database()) as size_bytes
                    """))
                    db_size_data = db_size_result.fetchone()
                    stats['database_size'] = db_size_data.size
                    stats['database_size_bytes'] = db_size_data.size_bytes
                
                # Статистика таблиц
                table_stats = await DatabaseHealthCheck._get_table_statistics(session)
                stats['tables'] = table_stats
                
                # Активные соединения
                if 'postgresql' in settings.DATABASE_URL:
                    connections_result = await session.execute(text("""
                        SELECT count(*) as active_connections
                        FROM pg_stat_activity 
                        WHERE state = 'active'
                    """))
                    connections_data = connections_result.fetchone()
                    stats['active_connections'] = connections_data.active_connections
                
                # Индексы без использования
                unused_indexes = await DatabaseHealthCheck._get_unused_indexes(session)
                stats['unused_indexes'] = unused_indexes
                
                # Блокировки
                locks_count = await DatabaseHealthCheck._get_locks_count(session)
                stats['locks_count'] = locks_count
                
                return {
                    "status": "success",
                    "stats": stats,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    async def _get_table_statistics(session) -> Dict[str, Any]:
        """Получение статистики таблиц"""
        try:
            if 'postgresql' in settings.DATABASE_URL:
                result = await session.execute(text("""
                    SELECT 
                        schemaname,
                        tablename,
                        n_tup_ins as inserts,
                        n_tup_upd as updates,
                        n_tup_del as deletes,
                        n_live_tup as live_tuples,
                        n_dead_tup as dead_tuples,
                        last_vacuum,
                        last_autovacuum,
                        last_analyze,
                        last_autoanalyze
                    FROM pg_stat_user_tables 
                    ORDER BY n_live_tup DESC
                    LIMIT 10
                """))
                
                tables = []
                for row in result.fetchall():
                    tables.append({
                        "schema": row.schemaname,
                        "table": row.tablename,
                        "inserts": row.inserts,
                        "updates": row.updates,
                        "deletes": row.deletes,
                        "live_tuples": row.live_tuples,
                        "dead_tuples": row.dead_tuples,
                        "last_vacuum": row.last_vacuum.isoformat() if row.last_vacuum else None,
                        "last_analyze": row.last_analyze.isoformat() if row.last_analyze else None
                    })
                
                return {"postgresql_tables": tables}
            
            return {"message": "Table statistics available only for PostgreSQL"}
            
        except Exception as e:
            logger.error(f"Error getting table statistics: {e}")
            return {"error": str(e)}
    
    @staticmethod
    async def _get_unused_indexes(session) -> List[Dict[str, Any]]:
        """Получение неиспользуемых индексов"""
        try:
            if 'postgresql' in settings.DATABASE_URL:
                result = await session.execute(text("""
                    SELECT 
                        schemaname,
                        tablename,
                        indexname,
                        idx_tup_read,
                        idx_tup_fetch,
                        pg_size_pretty(pg_relation_size(indexrelid)) as size
                    FROM pg_stat_user_indexes 
                    WHERE idx_tup_read = 0 
                    AND idx_tup_fetch = 0
                    ORDER BY pg_relation_size(indexrelid) DESC
                    LIMIT 10
                """))
                
                return [
                    {
                        "schema": row.schemaname,
                        "table": row.tablename,
                        "index": row.indexname,
                        "size": row.size
                    }
                    for row in result.fetchall()
                ]
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting unused indexes: {e}")
            return []
    
    @staticmethod
    async def _get_locks_count(session) -> int:
        """Получение количества блокировок"""
        try:
            if 'postgresql' in settings.DATABASE_URL:
                result = await session.execute(text("""
                    SELECT COUNT(*) as locks_count
                    FROM pg_locks
                """))
                
                locks_data = result.fetchone()
                return locks_data.locks_count
            
            return 0
            
        except Exception as e:
            logger.error(f"Error getting locks count: {e}")
            return 0
    
    @staticmethod
    async def check_slow_queries() -> Dict[str, Any]:
        """
        Проверка медленных запросов
        
        Returns:
            Информация о медленных запросах
        """
        try:
            async with get_async_session() as session:
                if 'postgresql' in settings.DATABASE_URL:
                    result = await session.execute(text("""
                        SELECT 
                            query,
                            calls,
                            total_time,
                            mean_time,
                            max_time,
                            rows
                        FROM pg_stat_statements 
                        WHERE mean_time > 1000  -- запросы дольше 1 секунды
                        ORDER BY mean_time DESC
                        LIMIT 10
                    """))
                    
                    slow_queries = []
                    for row in result.fetchall():
                        slow_queries.append({
                            "query": row.query[:200] + "..." if len(row.query) > 200 else row.query,
                            "calls": row.calls,
                            "total_time": round(row.total_time, 2),
                            "mean_time": round(row.mean_time, 2),
                            "max_time": round(row.max_time, 2),
                            "rows": row.rows
                        })
                    
                    return {
                        "status": "success",
                        "slow_queries": slow_queries,
                        "count": len(slow_queries)
                    }
                
                return {
                    "status": "not_available",
                    "message": "Slow query monitoring available only for PostgreSQL with pg_stat_statements"
                }
                
        except Exception as e:
            logger.error(f"Error checking slow queries: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

class DatabaseMaintenance:
    """Обслуживание и оптимизация базы данных"""
    
    @staticmethod
    async def vacuum_tables(analyze: bool = True, verbose: bool = False) -> Dict[str, Any]:
        """
        Выполнение VACUUM для оптимизации таблиц
        
        Args:
            analyze: Выполнить ANALYZE после VACUUM
            verbose: Подробный вывод
            
        Returns:
            Результат операции
        """
        try:
            async with get_async_session() as session:
                if 'postgresql' not in settings.DATABASE_URL:
                    return {
                        "status": "skipped",
                        "message": "VACUUM available only for PostgreSQL"
                    }
                
                # Получаем список пользовательских таблиц
                tables_result = await session.execute(text("""
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                """))
                
                tables = [row.tablename for row in tables_result.fetchall()]
                vacuumed_tables = []
                
                for table in tables:
                    try:
                        vacuum_cmd = f"VACUUM"
                        if analyze:
                            vacuum_cmd += " ANALYZE"
                        if verbose:
                            vacuum_cmd += " VERBOSE"
                        vacuum_cmd += f" {table}"
                        
                        await session.execute(text(vacuum_cmd))
                        vacuumed_tables.append(table)
                        
                        logger.info(f"VACUUM completed for table: {table}")
                        
                    except Exception as e:
                        logger.error(f"VACUUM failed for table {table}: {e}")
                
                return {
                    "status": "completed",
                    "tables_processed": len(vacuumed_tables),
                    "tables": vacuumed_tables,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"VACUUM operation failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    async def update_table_statistics() -> Dict[str, Any]:
        """
        Обновление статистики таблиц
        
        Returns:
            Результат операции
        """
        try:
            async with get_async_session() as session:
                if 'postgresql' not in settings.DATABASE_URL:
                    return {
                        "status": "skipped",
                        "message": "Table statistics update available only for PostgreSQL"
                    }
                
                # Получаем список таблиц
                tables_result = await session.execute(text("""
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                """))
                
                tables = [row.tablename for row in tables_result.fetchall()]
                analyzed_tables = []
                
                for table in tables:
                    try:
                        await session.execute(text(f"ANALYZE {table}"))
                        analyzed_tables.append(table)
                        
                    except Exception as e:
                        logger.error(f"ANALYZE failed for table {table}: {e}")
                
                return {
                    "status": "completed",
                    "tables_analyzed": len(analyzed_tables),
                    "tables": analyzed_tables
                }
                
        except Exception as e:
            logger.error(f"Statistics update failed: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    @staticmethod
    async def cleanup_old_analytics(days: int = 90) -> int:
        """
        Очистка старых аналитических данных
        
        Args:
            days: Количество дней для хранения
            
        Returns:
            Количество удаленных записей
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            deleted_count = 0
            
            async with get_async_session() as session:
                # Удаляем старые события аналитики
                analytics_result = await session.execute(text("""
                    DELETE FROM analytics_events 
                    WHERE created_at < :cutoff_date 
                    AND is_processed = true
                """), {"cutoff_date": cutoff_date})
                
                deleted_count += analytics_result.rowcount if hasattr(analytics_result, 'rowcount') else 0
                
                # Удаляем старые логи системных событий
                logs_result = await session.execute(text("""
                    DELETE FROM system_logs 
                    WHERE created_at < :cutoff_date 
                    AND level NOT IN ('ERROR', 'CRITICAL')
                """), {"cutoff_date": cutoff_date})
                
                deleted_count += logs_result.rowcount if hasattr(logs_result, 'rowcount') else 0
                
                # Очищаем старые метрики производительности
                metrics_result = await session.execute(text("""
                    DELETE FROM performance_metrics 
                    WHERE recorded_at < :cutoff_date
                """), {"cutoff_date": cutoff_date})
                
                deleted_count += metrics_result.rowcount if hasattr(metrics_result, 'rowcount') else 0
                
                await session.commit()
                
                logger.info(f"Cleaned up {deleted_count} old analytics records")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Analytics cleanup failed: {e}")
            return 0
    
    @staticmethod
    async def reindex_database() -> Dict[str, Any]:
        """
        Переиндексация базы данных
        
        Returns:
            Результат операции
        """
        try:
            async with get_async_session() as session:
                if 'postgresql' not in settings.DATABASE_URL:
                    return {
                        "status": "skipped",
                        "message": "REINDEX available only for PostgreSQL"
                    }
                
                # Получаем индексы, которые нуждаются в переиндексации
                indexes_result = await session.execute(text("""
                    SELECT 
                        schemaname,
                        tablename,
                        indexname
                    FROM pg_stat_user_indexes 
                    WHERE idx_tup_read > 0 
                    AND pg_relation_size(indexrelid) > 1024*1024  -- индексы больше 1MB
                """))
                
                indexes = indexes_result.fetchall()
                reindexed = []
                failed = []
                
                for index in indexes:
                    try:
                        await session.execute(text(f"REINDEX INDEX {index.indexname}"))
                        reindexed.append(index.indexname)
                        
                    except Exception as e:
                        logger.error(f"REINDEX failed for {index.indexname}: {e}")
                        failed.append({"index": index.indexname, "error": str(e)})
                
                return {
                    "status": "completed",
                    "reindexed_count": len(reindexed),
                    "reindexed_indexes": reindexed,
                    "failed_count": len(failed),
                    "failed_indexes": failed
                }
                
        except Exception as e:
            logger.error(f"Database reindex failed: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    @staticmethod
    async def optimize_database() -> Dict[str, Any]:
        """
        Комплексная оптимизация базы данных
        
        Returns:
            Результат операций
        """
        try:
            start_time = datetime.now()
            results = {}
            
            # 1. VACUUM ANALYZE
            vacuum_result = await DatabaseMaintenance.vacuum_tables(analyze=True)
            results['vacuum'] = vacuum_result
            
            # 2. Обновление статистики
            stats_result = await DatabaseMaintenance.update_table_statistics()
            results['statistics'] = stats_result
            
            # 3. Очистка старых данных
            cleanup_count = await DatabaseMaintenance.cleanup_old_analytics(days=90)
            results['cleanup'] = {"deleted_records": cleanup_count}
            
            # 4. Проверка фрагментации
            fragmentation = await DatabaseMaintenance._check_table_fragmentation()
            results['fragmentation'] = fragmentation
            
            # 5. Оптимизация настроек (если нужно)
            config_check = await DatabaseMaintenance._check_configuration()
            results['configuration'] = config_check
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            return {
                "status": "completed",
                "duration_seconds": round(duration, 2),
                "results": results,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Database optimization failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    @staticmethod
    async def _check_table_fragmentation() -> Dict[str, Any]:
        """Проверка фрагментации таблиц"""
        try:
            async with get_async_session() as session:
                if 'postgresql' in settings.DATABASE_URL:
                    result = await session.execute(text("""
                        SELECT 
                            schemaname,
                            tablename,
                            n_dead_tup,
                            n_live_tup,
                            CASE 
                                WHEN n_live_tup > 0 
                                THEN round(n_dead_tup * 100.0 / (n_live_tup + n_dead_tup), 2)
                                ELSE 0
                            END as fragmentation_percent
                        FROM pg_stat_user_tables
                        WHERE n_dead_tup > 1000  -- таблицы с заметной фрагментацией
                        ORDER BY fragmentation_percent DESC
                    """))
                    
                    fragmented_tables = []
                    for row in result.fetchall():
                        fragmented_tables.append({
                            "table": f"{row.schemaname}.{row.tablename}",
                            "dead_tuples": row.n_dead_tup,
                            "live_tuples": row.n_live_tup,
                            "fragmentation_percent": row.fragmentation_percent
                        })
                    
                    return {
                        "status": "success",
                        "fragmented_tables": fragmented_tables,
                        "needs_vacuum": len([t for t in fragmented_tables if t["fragmentation_percent"] > 20])
                    }
                
                return {"status": "not_available", "message": "Available only for PostgreSQL"}
                
        except Exception as e:
            logger.error(f"Error checking fragmentation: {e}")
            return {"status": "error", "error": str(e)}
    
    @staticmethod
    async def _check_configuration() -> Dict[str, Any]:
        """Проверка конфигурации БД"""
        try:
            async with get_async_session() as session:
                if 'postgresql' in settings.DATABASE_URL:
                    # Проверяем ключевые настройки PostgreSQL
                    settings_to_check = [
                        'shared_buffers',
                        'work_mem',
                        'maintenance_work_mem',
                        'effective_cache_size',
                        'checkpoint_completion_target',
                        'wal_buffers',
                        'max_connections'
                    ]
                    
                    current_settings = {}
                    for setting in settings_to_check:
                        try:
                            result = await session.execute(text(f"SHOW {setting}"))
                            value = result.fetchone()[0]
                            current_settings[setting] = value
                        except Exception:
                            current_settings[setting] = "unknown"
                    
                    return {
                        "status": "success",
                        "current_settings": current_settings,
                        "recommendations": DatabaseMaintenance._get_config_recommendations(current_settings)
                    }
                
                return {"status": "not_available"}
                
        except Exception as e:
            logger.error(f"Error checking configuration: {e}")
            return {"status": "error", "error": str(e)}
    
    @staticmethod
    def _get_config_recommendations(settings: Dict[str, str]) -> List[str]:
        """Получить рекомендации по конфигурации"""
        recommendations = []
        
        # Анализируем настройки и даем рекомендации
        try:
            # shared_buffers
            if 'shared_buffers' in settings and settings['shared_buffers']:
                if settings['shared_buffers'].endswith('MB'):
                    size = int(settings['shared_buffers'].replace('MB', ''))
                    if size < 128:
                        recommendations.append("Consider increasing shared_buffers to at least 128MB")
                elif settings['shared_buffers'].endswith('kB'):
                    recommendations.append("shared_buffers seems too small, consider increasing to 128MB or more")
            
            # work_mem
            if 'work_mem' in settings and settings['work_mem']:
                if settings['work_mem'].endswith('kB'):
                    size = int(settings['work_mem'].replace('kB', ''))
                    if size < 4096:  # 4MB
                        recommendations.append("Consider increasing work_mem to 4MB or more for better sort/hash performance")
            
            # max_connections
            if 'max_connections' in settings and settings['max_connections']:
                try:
                    max_conn = int(settings['max_connections'])
                    if max_conn > 200:
                        recommendations.append("High max_connections value might indicate connection pooling issues")
                except ValueError:
                    pass
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
        
        return recommendations

# Вспомогательные функции для мониторинга

async def get_database_health_summary() -> Dict[str, Any]:
    """
    Получить сводку состояния базы данных
    
    Returns:
        Сводная информация о здоровье БД
    """
    try:
        # Проверка соединения
        connection_health = await DatabaseHealthCheck.check_connection()
        
        # Базовая статистика
        stats = await DatabaseHealthCheck.get_database_stats()
        
        # Медленные запросы
        slow_queries = await DatabaseHealthCheck.check_slow_queries()
        
        # Определяем общий статус
        overall_status = "healthy"
        if connection_health["status"] != "healthy":
            overall_status = "unhealthy"
        elif slow_queries.get("count", 0) > 5:
            overall_status = "warning"
        elif connection_health.get("response_time_ms", 0) > 1000:
            overall_status = "warning"
        
        return {
            "overall_status": overall_status,
            "connection": connection_health,
            "statistics": stats,
            "slow_queries": slow_queries,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting database health summary: {e}")
        return {
            "overall_status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

async def schedule_maintenance() -> Dict[str, Any]:
    """
    Запланированное обслуживание БД
    
    Returns:
        Результат обслуживания
    """
    try:
        # Проверяем, нужно ли обслуживание
        health_summary = await get_database_health_summary()
        
        maintenance_needed = False
        reasons = []
        
        # Проверяем условия для обслуживания
        if health_summary["overall_status"] == "warning":
            maintenance_needed = True
            reasons.append("Database performance issues detected")
        
        if health_summary.get("slow_queries", {}).get("count", 0) > 3:
            maintenance_needed = True
            reasons.append("Multiple slow queries detected")
        
        # Проверяем фрагментацию
        fragmentation = await DatabaseMaintenance._check_table_fragmentation()
        if fragmentation.get("needs_vacuum", 0) > 2:
            maintenance_needed = True
            reasons.append("High table fragmentation detected")
        
        if maintenance_needed:
            logger.info("Automated maintenance triggered", reasons=reasons)
            optimization_result = await DatabaseMaintenance.optimize_database()
            return {
                "maintenance_performed": True,
                "reasons": reasons,
                "results": optimization_result
            }
        else:
            return {
                "maintenance_performed": False,
                "message": "No maintenance needed",
                "health_status": health_summary["overall_status"]
            }
        
    except Exception as e:
        logger.error(f"Error in scheduled maintenance: {e}")
        return {
            "maintenance_performed": False,
            "error": str(e)
        }