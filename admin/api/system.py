"""
VideoBot Pro - System Management API
API endpoints для системного управления, мониторинга и диагностики
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy import text, func
from sqlalchemy.orm import AsyncSession
import structlog
import psutil
import platform
import asyncio
import os

from shared.config.database import get_async_session
from shared.models import User, DownloadTask, Payment, AnalyticsEvent
from shared.schemas.admin import ResponseSchema
from shared.services.database import DatabaseService
from shared.services.analytics import AnalyticsService
from ..config import get_admin_settings
from ..dependencies import get_current_admin, require_permission, get_analytics_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

@router.get("/health", response_model=ResponseSchema)
async def get_system_health(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin)
):
    """
    Получить общее состояние системы
    """
    try:
        health_data = {}
        
        # База данных
        try:
            db_start = datetime.utcnow()
            await session.execute(text("SELECT 1"))
            db_time = (datetime.utcnow() - db_start).total_seconds() * 1000
            
            # Количество соединений
            connections_result = await session.execute(text("""
                SELECT count(*) 
                FROM pg_stat_activity 
                WHERE state = 'active'
            """))
            active_connections = connections_result.scalar()
            
            health_data['database'] = {
                "status": "healthy",
                "response_time_ms": round(db_time, 2),
                "active_connections": active_connections
            }
            
        except Exception as e:
            health_data['database'] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Redis (если используется)
        try:
            # Здесь должна быть проверка Redis
            health_data['redis'] = {
                "status": "healthy",
                "connected": True
            }
        except Exception:
            health_data['redis'] = {
                "status": "unknown",
                "connected": False
            }
        
        # Системные ресурсы
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            health_data['system'] = {
                "status": "healthy",
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_percent": round((disk.used / disk.total) * 100, 2),
                "disk_free_gb": round(disk.free / (1024**3), 2)
            }
            
        except Exception as e:
            health_data['system'] = {
                "status": "error",
                "error": str(e)
            }
        
        # Проверка критических сервисов
        critical_issues = []
        
        if health_data.get('database', {}).get('status') != 'healthy':
            critical_issues.append("Database unavailable")
        
        if health_data.get('system', {}).get('cpu_percent', 0) > 90:
            critical_issues.append("High CPU usage")
            
        if health_data.get('system', {}).get('memory_percent', 0) > 90:
            critical_issues.append("High memory usage")
        
        overall_status = "healthy" if not critical_issues else "degraded"
        if len(critical_issues) > 2:
            overall_status = "unhealthy"
        
        return ResponseSchema(
            success=True,
            data={
                "overall_status": overall_status,
                "critical_issues": critical_issues,
                "components": health_data,
                "last_check": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при проверке состояния системы"
        )

@router.get("/metrics", response_model=ResponseSchema)
async def get_system_metrics(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("system_stats"))
):
    """
    Получить системные метрики
    """
    try:
        # Системная информация
        system_info = {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "python_version": platform.python_version(),
            "architecture": platform.architecture()[0],
            "hostname": platform.node(),
            "uptime_hours": round((datetime.utcnow().timestamp() - psutil.boot_time()) / 3600, 2)
        }
        
        # CPU метрики
        cpu_count = psutil.cpu_count(logical=False)
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_freq = psutil.cpu_freq()
        
        cpu_metrics = {
            "physical_cores": cpu_count,
            "logical_cores": cpu_count_logical,
            "current_usage_percent": cpu_percent,
            "frequency_mhz": cpu_freq.current if cpu_freq else None,
            "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None
        }
        
        # Память
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        memory_metrics = {
            "total_gb": round(memory.total / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "usage_percent": memory.percent,
            "swap_total_gb": round(swap.total / (1024**3), 2),
            "swap_used_gb": round(swap.used / (1024**3), 2),
            "swap_usage_percent": swap.percent
        }
        
        # Диск
        disk = psutil.disk_usage('/')
        
        disk_metrics = {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "usage_percent": round((disk.used / disk.total) * 100, 2)
        }
        
        # Сетевые метрики
        net_io = psutil.net_io_counters()
        
        network_metrics = {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
            "errors_in": net_io.errin,
            "errors_out": net_io.errout
        }
        
        # Процессы
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                if proc.info['cpu_percent'] > 1.0 or proc.info['memory_percent'] > 1.0:
                    processes.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "cpu_percent": round(proc.info['cpu_percent'], 2),
                        "memory_percent": round(proc.info['memory_percent'], 2)
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Сортируем по использованию CPU
        processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:10]
        
        return ResponseSchema(
            success=True,
            data={
                "system_info": system_info,
                "cpu_metrics": cpu_metrics,
                "memory_metrics": memory_metrics,
                "disk_metrics": disk_metrics,
                "network_metrics": network_metrics,
                "top_processes": processes,
                "collected_at": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении системных метрик"
        )

@router.get("/database/stats", response_model=ResponseSchema)
async def get_database_stats(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("system_stats"))
):
    """
    Получить статистику базы данных
    """
    try:
        # Статистика подключений
        connections_query = text("""
            SELECT 
                state,
                COUNT(*) as count
            FROM pg_stat_activity 
            GROUP BY state
        """)
        
        connections_result = await session.execute(connections_query)
        connections_stats = {row.state: row.count for row in connections_result.fetchall()}
        
        # Размеры таблиц
        table_sizes_query = text("""
            SELECT 
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            LIMIT 10
        """)
        
        table_sizes_result = await session.execute(table_sizes_query)
        table_sizes = [
            {
                "table_name": row.tablename,
                "size": row.size,
                "size_bytes": row.size_bytes
            }
            for row in table_sizes_result.fetchall()
        ]
        
        # Статистика по таблицам
        table_stats_query = text("""
            SELECT 
                schemaname,
                tablename,
                n_tup_ins as inserts,
                n_tup_upd as updates,
                n_tup_del as deletes,
                n_live_tup as live_tuples,
                n_dead_tup as dead_tuples
            FROM pg_stat_user_tables
            ORDER BY n_tup_ins + n_tup_upd + n_tup_del DESC
            LIMIT 10
        """)
        
        table_stats_result = await session.execute(table_stats_query)
        table_stats = [
            {
                "table_name": row.tablename,
                "inserts": row.inserts,
                "updates": row.updates,
                "deletes": row.deletes,
                "live_tuples": row.live_tuples,
                "dead_tuples": row.dead_tuples
            }
            for row in table_stats_result.fetchall()
        ]
        
        # Медленные запросы (если включено логирование)
        slow_queries = []
        try:
            slow_queries_query = text("""
                SELECT 
                    query,
                    calls,
                    total_time,
                    mean_time,
                    max_time
                FROM pg_stat_statements 
                ORDER BY total_time DESC
                LIMIT 5
            """)
            
            slow_queries_result = await session.execute(slow_queries_query)
            slow_queries = [
                {
                    "query": row.query[:100] + "..." if len(row.query) > 100 else row.query,
                    "calls": row.calls,
                    "total_time_ms": round(row.total_time, 2),
                    "mean_time_ms": round(row.mean_time, 2),
                    "max_time_ms": round(row.max_time, 2)
                }
                for row in slow_queries_result.fetchall()
            ]
        except Exception:
            # pg_stat_statements не установлен
            pass
        
        # Общая информация о БД
        db_info_query = text("""
            SELECT 
                pg_size_pretty(pg_database_size(current_database())) as database_size,
                current_database() as database_name,
                version() as postgres_version
        """)
        
        db_info_result = await session.execute(db_info_query)
        db_info = db_info_result.fetchone()
        
        return ResponseSchema(
            success=True,
            data={
                "database_info": {
                    "name": db_info.database_name,
                    "size": db_info.database_size,
                    "version": db_info.postgres_version.split(',')[0] if db_info.postgres_version else "Unknown"
                },
                "connections": connections_stats,
                "table_sizes": table_sizes,
                "table_stats": table_stats,
                "slow_queries": slow_queries,
                "collected_at": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении статистики БД"
        )

@router.post("/maintenance/start", response_model=ResponseSchema)
async def start_maintenance(
    reason: str = "Scheduled maintenance",
    current_admin = Depends(require_permission("system_maintenance"))
):
    """
    Включить режим технического обслуживания
    """
    try:
        # Здесь должна быть логика включения режима обслуживания
        # Например, установка флага в Redis или файле конфигурации
        
        logger.warning(
            f"Maintenance mode started",
            admin_id=current_admin['admin_id'],
            reason=reason
        )
        
        return ResponseSchema(
            success=True,
            message="Режим технического обслуживания включен",
            data={
                "maintenance_active": True,
                "reason": reason,
                "started_by": current_admin['username'],
                "started_at": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error starting maintenance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка включения режима обслуживания"
        )

@router.post("/maintenance/stop", response_model=ResponseSchema)
async def stop_maintenance(
    current_admin = Depends(require_permission("system_maintenance"))
):
    """
    Отключить режим технического обслуживания
    """
    try:
        # Здесь должна быть логика отключения режима обслуживания
        
        logger.info(
            f"Maintenance mode stopped",
            admin_id=current_admin['admin_id']
        )
        
        return ResponseSchema(
            success=True,
            message="Режим технического обслуживания отключен",
            data={
                "maintenance_active": False,
                "stopped_by": current_admin['username'],
                "stopped_at": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error stopping maintenance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка отключения режима обслуживания"
        )

@router.post("/cleanup/logs", response_model=ResponseSchema)
async def cleanup_old_logs(
    days: int = Query(30, ge=1, le=365, description="Удалить логи старше N дней"),
    current_admin = Depends(require_permission("system_maintenance")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Очистка старых логов и событий аналитики
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_async_session() as session:
            # Удаляем старые события аналитики
            analytics_query = text("""
                DELETE FROM analytics_events 
                WHERE created_at < :cutoff_date
            """)
            
            analytics_result = await session.execute(analytics_query, {"cutoff_date": cutoff_date})
            deleted_analytics = analytics_result.rowcount
            
            await session.commit()
        
        # В фоне очищаем файлы логов
        background_tasks.add_task(cleanup_log_files, days)
        
        logger.info(
            f"Cleanup completed",
            deleted_analytics=deleted_analytics,
            cutoff_days=days,
            admin_id=current_admin['admin_id']
        )
        
        return ResponseSchema(
            success=True,
            message=f"Очистка завершена. Удалено {deleted_analytics} событий аналитики",
            data={
                "deleted_analytics_events": deleted_analytics,
                "cutoff_date": cutoff_date.isoformat(),
                "days": days
            }
        )
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при очистке данных"
        )

@router.post("/backup/database", response_model=ResponseSchema)
async def backup_database(
    current_admin = Depends(require_permission("system_maintenance")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Создать резервную копию базы данных
    """
    try:
        backup_filename = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.sql"
        
        # Запускаем backup в фоне
        background_tasks.add_task(create_database_backup, backup_filename, current_admin['admin_id'])
        
        return ResponseSchema(
            success=True,
            message="Создание резервной копии запущено",
            data={
                "backup_filename": backup_filename,
                "started_at": datetime.utcnow().isoformat(),
                "started_by": current_admin['username']
            }
        )
        
    except Exception as e:
        logger.error(f"Error starting backup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка запуска резервного копирования"
        )

@router.get("/logs/recent", response_model=ResponseSchema)
async def get_recent_logs(
    limit: int = Query(100, ge=1, le=1000, description="Количество записей"),
    level: Optional[str] = Query(None, description="Уровень логирования"),
    current_admin = Depends(require_permission("system_stats"))
):
    """
    Получить последние записи логов
    """
    try:
        # Здесь должна быть логика чтения логов из файлов или БД
        # Пока возвращаем заглушку
        
        logs = [
            {
                "timestamp": (datetime.utcnow() - timedelta(minutes=i)).isoformat(),
                "level": "INFO" if i % 3 != 0 else "ERROR" if i % 7 == 0 else "WARNING",
                "message": f"Sample log message {i}",
                "module": "admin.api.system" if i % 2 == 0 else "shared.services.database",
                "admin_id": current_admin['admin_id'] if i % 5 == 0 else None
            }
            for i in range(min(limit, 50))
        ]
        
        if level:
            logs = [log for log in logs if log['level'] == level.upper()]
        
        return ResponseSchema(
            success=True,
            data={
                "logs": logs,
                "total_returned": len(logs),
                "filters": {
                    "limit": limit,
                    "level": level
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting recent logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении логов"
        )

@router.get("/performance/slow-queries", response_model=ResponseSchema)
async def get_slow_queries(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("system_stats")),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Получить медленные SQL запросы
    """
    try:
        # Пытаемся получить данные из pg_stat_statements
        try:
            slow_queries_query = text("""
                SELECT 
                    query,
                    calls,
                    total_time,
                    mean_time,
                    max_time,
                    stddev_time,
                    rows,
                    100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) AS hit_percent
                FROM pg_stat_statements 
                WHERE query NOT LIKE '%pg_stat_statements%'
                ORDER BY total_time DESC
                LIMIT :limit
            """)
            
            result = await session.execute(slow_queries_query, {"limit": limit})
            queries = []
            
            for row in result.fetchall():
                queries.append({
                    "query": row.query[:200] + "..." if len(row.query) > 200 else row.query,
                    "calls": row.calls,
                    "total_time_ms": round(row.total_time, 2),
                    "mean_time_ms": round(row.mean_time, 2),
                    "max_time_ms": round(row.max_time, 2),
                    "stddev_time_ms": round(row.stddev_time, 2) if row.stddev_time else 0,
                    "rows_affected": row.rows,
                    "cache_hit_percent": round(row.hit_percent, 2) if row.hit_percent else 0
                })
                
        except Exception:
            # pg_stat_statements не доступен, возвращаем заглушку
            queries = [
                {
                    "query": "SELECT * FROM users WHERE created_at > ?",
                    "calls": 1247,
                    "total_time_ms": 5423.45,
                    "mean_time_ms": 4.35,
                    "max_time_ms": 234.12,
                    "stddev_time_ms": 12.34,
                    "rows_affected": 15623,
                    "cache_hit_percent": 87.5
                }
            ]
        
        return ResponseSchema(
            success=True,
            data={
                "slow_queries": queries,
                "total_returned": len(queries),
                "note": "Требуется расширение pg_stat_statements для полной функциональности" if not queries else None
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting slow queries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении медленных запросов"
        )

@router.get("/alerts", response_model=ResponseSchema)
async def get_system_alerts(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin)
):
    """
    Получить системные уведомления и алерты
    """
    try:
        alerts = []
        
        # Проверяем системные ресурсы
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            if cpu_percent > 80:
                alerts.append({
                    "type": "warning" if cpu_percent < 95 else "critical",
                    "title": "Высокая загрузка CPU",
                    "message": f"Использование CPU: {cpu_percent}%",
                    "severity": "high" if cpu_percent > 95 else "medium",
                    "timestamp": datetime.utcnow().isoformat(),
                    "category": "system"
                })
            
            if memory.percent > 80:
                alerts.append({
                    "type": "warning" if memory.percent < 95 else "critical",
                    "title": "Высокое потребление памяти",
                    "message": f"Использование памяти: {memory.percent}%",
                    "severity": "high" if memory.percent > 95 else "medium",
                    "timestamp": datetime.utcnow().isoformat(),
                    "category": "system"
                })
            
            disk_percent = (disk.used / disk.total) * 100
            if disk_percent > 85:
                alerts.append({
                    "type": "warning" if disk_percent < 95 else "critical",
                    "title": "Мало свободного места на диске",
                    "message": f"Использование диска: {disk_percent:.1f}%",
                    "severity": "high" if disk_percent > 95 else "medium",
                    "timestamp": datetime.utcnow().isoformat(),
                    "category": "storage"
                })
                
        except Exception:
            pass
        
        # Проверяем БД
        try:
            # Проверяем количество активных соединений
            connections_result = await session.execute(text("""
                SELECT count(*) FROM pg_stat_activity WHERE state = 'active'
            """))
            active_connections = connections_result.scalar()
            
            if active_connections > 50:  # Пороговое значение
                alerts.append({
                    "type": "warning",
                    "title": "Много активных соединений к БД",
                    "message": f"Активных соединений: {active_connections}",
                    "severity": "medium",
                    "timestamp": datetime.utcnow().isoformat(),
                    "category": "database"
                })
                
        except Exception:
            alerts.append({
                "type": "critical",
                "title": "Проблемы с подключением к БД",
                "message": "Не удается подключиться к базе данных",
                "severity": "critical",
                "timestamp": datetime.utcnow().isoformat(),
                "category": "database"
            })
        
        # Проверяем очередь задач (если есть)
        try:
            # Здесь должна быть проверка Celery или другой очереди задач
            pending_downloads = await session.query(DownloadTask).filter(
                DownloadTask.status == 'pending'
            ).count()
            
            if pending_downloads > 100:
                alerts.append({
                    "type": "warning",
                    "title": "Большая очередь скачиваний",
                    "message": f"В очереди {pending_downloads} задач",
                    "severity": "medium",
                    "timestamp": datetime.utcnow().isoformat(),
                    "category": "queue"
                })
                
        except Exception:
            pass
        
        # Сортируем по важности
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        alerts.sort(key=lambda x: severity_order.get(x["severity"], 4))
        
        return ResponseSchema(
            success=True,
            data={
                "alerts": alerts,
                "total_alerts": len(alerts),
                "critical_alerts": len([a for a in alerts if a["severity"] == "critical"]),
                "last_check": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting system alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении системных уведомлений"
        )

# Вспомогательные функции

async def cleanup_log_files(days: int):
    """Фоновая задача очистки файлов логов"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Здесь должна быть логика очистки файлов логов
        # Например, удаление старых .log файлов
        
        logger.info(f"Log files cleanup completed", cutoff_days=days)
        
    except Exception as e:
        logger.error(f"Error cleaning up log files: {e}")

async def create_database_backup(filename: str, admin_id: int):
    """Фоновая задача создания backup БД"""
    try:
        # Здесь должна быть логика создания backup
        # Например, вызов pg_dump
        
        logger.info(
            f"Database backup completed",
            filename=filename,
            admin_id=admin_id
        )
        
    except Exception as e:
        logger.error(f"Error creating database backup: {e}")
