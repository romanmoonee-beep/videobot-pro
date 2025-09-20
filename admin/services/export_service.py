"""
VideoBot Pro - Export Service
Сервис для экспорта данных и генерации отчетов
"""

import asyncio
import io
import zipfile
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
from enum import Enum
from pathlib import Path
import structlog

from shared.services.database import get_db_session
from shared.models import User, DownloadTask, Payment, AnalyticsEvent, BroadcastMessage, RequiredChannel
from ..utils.export import (
    export_users_to_csv, export_users_to_excel,
    export_downloads_to_csv, export_downloads_to_excel,
    export_analytics_to_csv, export_analytics_to_excel,
    generate_summary_report
)

logger = structlog.get_logger(__name__)

class ExportFormat(str, Enum):
    """Форматы экспорта"""
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    PDF = "pdf"
    ZIP = "zip"

class ExportType(str, Enum):
    """Типы экспорта"""
    USERS = "users"
    DOWNLOADS = "downloads"
    PAYMENTS = "payments"
    ANALYTICS = "analytics"
    BROADCASTS = "broadcasts"
    CHANNELS = "channels"
    FULL_BACKUP = "full_backup"
    CUSTOM_REPORT = "custom_report"

class ExportStatus(str, Enum):
    """Статусы экспорта"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"

class ExportService:
    """Сервис экспорта данных"""
    
    def __init__(self):
        self.export_jobs = {}  # Хранение информации о задачах экспорта
        self.export_dir = Path("./exports")
        self.export_dir.mkdir(exist_ok=True)
    
    async def create_export_job(
        self,
        export_type: ExportType,
        export_format: ExportFormat,
        admin_id: int,
        filters: Dict[str, Any] = None,
        options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Создать задачу экспорта"""
        
        job_id = f"export_{datetime.utcnow().timestamp()}_{admin_id}"
        
        job_info = {
            "job_id": job_id,
            "export_type": export_type.value,
            "export_format": export_format.value,
            "admin_id": admin_id,
            "filters": filters or {},
            "options": options or {},
            "status": ExportStatus.PENDING.value,
            "created_at": datetime.utcnow(),
            "started_at": None,
            "completed_at": None,
            "file_path": None,
            "file_size": None,
            "error_message": None,
            "progress": 0
        }
        
        self.export_jobs[job_id] = job_info
        
        # Запускаем экспорт в фоне
        asyncio.create_task(self._process_export_job(job_id))
        
        logger.info(f"Export job created", job_id=job_id, type=export_type.value, format=export_format.value)
        
        return {
            "success": True,
            "job_id": job_id,
            "status": ExportStatus.PENDING.value,
            "estimated_time_minutes": self._estimate_export_time(export_type, filters)
        }
    
    async def get_export_status(self, job_id: str) -> Dict[str, Any]:
        """Получить статус задачи экспорта"""
        
        if job_id not in self.export_jobs:
            return {"error": "Export job not found"}
        
        job = self.export_jobs[job_id]
        
        return {
            "job_id": job_id,
            "status": job["status"],
            "progress": job["progress"],
            "created_at": job["created_at"].isoformat(),
            "started_at": job["started_at"].isoformat() if job["started_at"] else None,
            "completed_at": job["completed_at"].isoformat() if job["completed_at"] else None,
            "file_size": job["file_size"],
            "error_message": job["error_message"]
        }
    
    async def download_export_file(self, job_id: str, admin_id: int) -> Union[Dict[str, Any], bytes]:
        """Скачать файл экспорта"""
        
        if job_id not in self.export_jobs:
            return {"error": "Export job not found"}
        
        job = self.export_jobs[job_id]
        
        # Проверяем права доступа
        if job["admin_id"] != admin_id:
            return {"error": "Access denied"}
        
        if job["status"] != ExportStatus.COMPLETED.value:
            return {"error": "Export not completed"}
        
        if not job["file_path"] or not Path(job["file_path"]).exists():
            return {"error": "Export file not found"}
        
        try:
            with open(job["file_path"], "rb") as f:
                file_content = f.read()
            
            return file_content
            
        except Exception as e:
            logger.error(f"Failed to read export file {job_id}: {e}")
            return {"error": "Failed to read file"}
    
    async def _process_export_job(self, job_id: str):
        """Обработать задачу экспорта"""
        
        job = self.export_jobs[job_id]
        
        try:
            job["status"] = ExportStatus.PROCESSING.value
            job["started_at"] = datetime.utcnow()
            
            export_type = ExportType(job["export_type"])
            export_format = ExportFormat(job["export_format"])
            
            # Выполняем экспорт в зависимости от типа
            if export_type == ExportType.USERS:
                result = await self._export_users(job)
            elif export_type == ExportType.DOWNLOADS:
                result = await self._export_downloads(job)
            elif export_type == ExportType.PAYMENTS:
                result = await self._export_payments(job)
            elif export_type == ExportType.ANALYTICS:
                result = await self._export_analytics(job)
            elif export_type == ExportType.BROADCASTS:
                result = await self._export_broadcasts(job)
            elif export_type == ExportType.CHANNELS:
                result = await self._export_channels(job)
            elif export_type == ExportType.FULL_BACKUP:
                result = await self._export_full_backup(job)
            elif export_type == ExportType.CUSTOM_REPORT:
                result = await self._export_custom_report(job)
            else:
                raise ValueError(f"Unknown export type: {export_type}")
            
            if result["success"]:
                job["status"] = ExportStatus.COMPLETED.value
                job["file_path"] = result["file_path"]
                job["file_size"] = result["file_size"]
                job["progress"] = 100
            else:
                job["status"] = ExportStatus.FAILED.value
                job["error_message"] = result["error"]
            
            job["completed_at"] = datetime.utcnow()
            
            logger.info(f"Export job completed", job_id=job_id, status=job["status"])
            
        except Exception as e:
            job["status"] = ExportStatus.FAILED.value
            job["error_message"] = str(e)
            job["completed_at"] = datetime.utcnow()
            
            logger.error(f"Export job failed {job_id}: {e}")
    
    async def _export_users(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Экспорт пользователей"""
        
        try:
            filters = job["filters"]
            export_format = ExportFormat(job["export_format"])
            
            async with get_db_session() as session:
                # Базовый запрос
                query = session.query(User).filter(User.is_deleted == False)
                
                # Применяем фильтры
                if filters.get("user_type"):
                    query = query.filter(User.user_type == filters["user_type"])
                
                if filters.get("is_premium") is not None:
                    query = query.filter(User.is_premium == filters["is_premium"])
                
                if filters.get("is_banned") is not None:
                    query = query.filter(User.is_banned == filters["is_banned"])
                
                if filters.get("date_from"):
                    date_from = datetime.fromisoformat(filters["date_from"])
                    query = query.filter(User.created_at >= date_from)
                
                if filters.get("date_to"):
                    date_to = datetime.fromisoformat(filters["date_to"])
                    query = query.filter(User.created_at <= date_to)
                
                # Обновляем прогресс
                job["progress"] = 20
                
                users = await query.all()
                
                job["progress"] = 60
                
                # Создаем файл экспорта
                if export_format == ExportFormat.CSV:
                    response = await export_users_to_csv(users)
                    file_extension = "csv"
                    content_type = "text/csv"
                elif export_format == ExportFormat.EXCEL:
                    response = await export_users_to_excel(users)
                    file_extension = "xlsx"
                    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                else:
                    return {"success": False, "error": f"Unsupported format: {export_format}"}
                
                # Сохраняем файл
                filename = f"users_export_{job['job_id']}.{file_extension}"
                file_path = self.export_dir / filename
                
                if hasattr(response, 'body'):
                    content = response.body
                else:
                    # Для StreamingResponse нужно читать содержимое
                    content = b""
                    async for chunk in response.body_iterator:
                        content += chunk
                
                with open(file_path, "wb") as f:
                    f.write(content)
                
                job["progress"] = 100
                
                return {
                    "success": True,
                    "file_path": str(file_path),
                    "file_size": file_path.stat().st_size,
                    "records_count": len(payments)
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _export_analytics(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Экспорт аналитики"""
        
        try:
            filters = job["filters"]
            export_format = ExportFormat(job["export_format"])
            
            # Собираем данные аналитики
            from ..services.analytics_service import AnalyticsService
            analytics_service = AnalyticsService()
            
            job["progress"] = 20
            
            # Получаем различные виды аналитики
            days = filters.get("days", 30)
            
            analytics_data = {
                "overview": await analytics_service.get_overview_metrics(),
                "user_stats": await analytics_service.get_user_analytics(days),
                "download_stats": await analytics_service.get_download_analytics(days),
                "revenue_stats": await analytics_service.get_revenue_analytics(days),
                "platform_analytics": await analytics_service.get_platform_analytics(days),
                "daily_trends": await analytics_service.get_daily_trends(days)
            }
            
            job["progress"] = 60
            
            # Создаем файл экспорта
            if export_format == ExportFormat.CSV:
                response = await export_analytics_to_csv(analytics_data)
                file_extension = "csv"
            elif export_format == ExportFormat.EXCEL:
                response = await export_analytics_to_excel(analytics_data)
                file_extension = "xlsx"
            elif export_format == ExportFormat.JSON:
                import json
                content = json.dumps(analytics_data, indent=2, default=str).encode('utf-8')
                file_extension = "json"
            else:
                return {"success": False, "error": f"Unsupported format: {export_format}"}
            
            # Сохраняем файл
            filename = f"analytics_export_{job['job_id']}.{file_extension}"
            file_path = self.export_dir / filename
            
            if export_format == ExportFormat.JSON:
                with open(file_path, "wb") as f:
                    f.write(content)
            else:
                # Для CSV/Excel получаем содержимое из response
                if hasattr(response, 'body'):
                    content = response.body
                else:
                    content = b""
                    async for chunk in response.body_iterator:
                        content += chunk
                
                with open(file_path, "wb") as f:
                    f.write(content)
            
            job["progress"] = 100
            
            return {
                "success": True,
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size,
                "data_period_days": days
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _export_broadcasts(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Экспорт рассылок"""
        
        try:
            filters = job["filters"]
            export_format = ExportFormat(job["export_format"])
            
            async with get_db_session() as session:
                query = session.query(BroadcastMessage)
                
                if filters.get("status"):
                    query = query.filter(BroadcastMessage.status == filters["status"])
                
                if filters.get("date_from"):
                    date_from = datetime.fromisoformat(filters["date_from"])
                    query = query.filter(BroadcastMessage.created_at >= date_from)
                
                if filters.get("date_to"):
                    date_to = datetime.fromisoformat(filters["date_to"])
                    query = query.filter(BroadcastMessage.created_at <= date_to)
                
                job["progress"] = 20
                
                broadcasts = await query.all()
                
                job["progress"] = 60
                
                # Используем функцию из utils
                from ..utils.export import export_broadcasts_to_csv
                
                if export_format == ExportFormat.CSV:
                    response = await export_broadcasts_to_csv(broadcasts)
                    file_extension = "csv"
                else:
                    return {"success": False, "error": f"Unsupported format: {export_format}"}
                
                filename = f"broadcasts_export_{job['job_id']}.{file_extension}"
                file_path = self.export_dir / filename
                
                if hasattr(response, 'body'):
                    content = response.body
                else:
                    content = b""
                    async for chunk in response.body_iterator:
                        content += chunk
                
                with open(file_path, "wb") as f:
                    f.write(content)
                
                job["progress"] = 100
                
                return {
                    "success": True,
                    "file_path": str(file_path),
                    "file_size": file_path.stat().st_size,
                    "records_count": len(broadcasts)
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _export_channels(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Экспорт каналов"""
        
        try:
            filters = job["filters"]
            export_format = ExportFormat(job["export_format"])
            
            async with get_db_session() as session:
                query = session.query(RequiredChannel)
                
                if filters.get("is_active") is not None:
                    query = query.filter(RequiredChannel.is_active == filters["is_active"])
                
                job["progress"] = 20
                
                channels = await query.all()
                
                job["progress"] = 60
                
                # Используем функцию из utils
                from ..utils.export import export_channels_to_csv
                
                if export_format == ExportFormat.CSV:
                    response = await export_channels_to_csv(channels)
                    file_extension = "csv"
                else:
                    return {"success": False, "error": f"Unsupported format: {export_format}"}
                
                filename = f"channels_export_{job['job_id']}.{file_extension}"
                file_path = self.export_dir / filename
                
                if hasattr(response, 'body'):
                    content = response.body
                else:
                    content = b""
                    async for chunk in response.body_iterator:
                        content += chunk
                
                with open(file_path, "wb") as f:
                    f.write(content)
                
                job["progress"] = 100
                
                return {
                    "success": True,
                    "file_path": str(file_path),
                    "file_size": file_path.stat().st_size,
                    "records_count": len(channels)
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _export_full_backup(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Полный экспорт всех данных"""
        
        try:
            job["progress"] = 10
            
            # Создаем временную директорию для файлов
            backup_dir = self.export_dir / f"backup_{job['job_id']}"
            backup_dir.mkdir(exist_ok=True)
            
            # Экспортируем каждый тип данных
            export_tasks = [
                self._export_table_to_csv("users", User, backup_dir, {"is_deleted": False}),
                self._export_table_to_csv("downloads", DownloadTask, backup_dir),
                self._export_table_to_csv("payments", Payment, backup_dir),
                self._export_table_to_csv("broadcasts", BroadcastMessage, backup_dir),
                self._export_table_to_csv("channels", RequiredChannel, backup_dir),
                self._export_table_to_csv("analytics_events", AnalyticsEvent, backup_dir)
            ]
            
            # Выполняем экспорт параллельно
            results = await asyncio.gather(*export_tasks, return_exceptions=True)
            
            job["progress"] = 70
            
            # Проверяем результаты
            successful_exports = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Export task {i} failed: {result}")
                else:
                    successful_exports.append(result)
            
            # Создаем ZIP архив
            zip_filename = f"full_backup_{job['job_id']}.zip"
            zip_path = self.export_dir / zip_filename
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Добавляем все CSV файлы
                for file_path in backup_dir.glob("*.csv"):
                    zipf.write(file_path, file_path.name)
                
                # Добавляем сводный отчет
                summary_data = await self._generate_backup_summary()
                summary_content = await generate_summary_report(summary_data)
                zipf.writestr("backup_summary.txt", summary_content)
                
                # Добавляем метаданные
                metadata = {
                    "backup_date": datetime.utcnow().isoformat(),
                    "admin_id": job["admin_id"],
                    "exported_tables": len(successful_exports),
                    "backup_version": "1.0"
                }
                
                import json
                zipf.writestr("metadata.json", json.dumps(metadata, indent=2))
            
            # Удаляем временную директорию
            import shutil
            shutil.rmtree(backup_dir)
            
            job["progress"] = 100
            
            return {
                "success": True,
                "file_path": str(zip_path),
                "file_size": zip_path.stat().st_size,
                "exported_tables": len(successful_exports)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _export_custom_report(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Создание кастомного отчета"""
        
        try:
            options = job["options"]
            report_type = options.get("report_type", "summary")
            
            job["progress"] = 20
            
            if report_type == "user_activity":
                report_data = await self._generate_user_activity_report(options)
            elif report_type == "financial":
                report_data = await self._generate_financial_report(options)
            elif report_type == "performance":
                report_data = await self._generate_performance_report(options)
            elif report_type == "security":
                report_data = await self._generate_security_report(options)
            else:
                report_data = await self._generate_summary_report_data(options)
            
            job["progress"] = 70
            
            # Генерируем отчет
            if job["export_format"] == ExportFormat.PDF.value:
                # TODO: Реализовать PDF генерацию
                file_content = await self._generate_pdf_report(report_data)
                file_extension = "pdf"
            else:
                file_content = await generate_summary_report(report_data)
                file_extension = "txt"
            
            # Сохраняем файл
            filename = f"custom_report_{job['job_id']}.{file_extension}"
            file_path = self.export_dir / filename
            
            with open(file_path, "w" if file_extension == "txt" else "wb") as f:
                f.write(file_content)
            
            job["progress"] = 100
            
            return {
                "success": True,
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size,
                "report_type": report_type
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _export_table_to_csv(
        self,
        table_name: str,
        model_class,
        output_dir: Path,
        filters: Dict[str, Any] = None
    ) -> str:
        """Экспорт таблицы в CSV"""
        
        try:
            async with get_db_session() as session:
                query = session.query(model_class)
                
                # Применяем фильтры
                if filters:
                    for field, value in filters.items():
                        if hasattr(model_class, field):
                            query = query.filter(getattr(model_class, field) == value)
                
                records = await query.all()
                
                # Экспортируем в CSV
                import csv
                csv_path = output_dir / f"{table_name}.csv"
                
                if records:
                    # Получаем поля из первой записи
                    first_record = records[0]
                    if hasattr(first_record, 'to_dict'):
                        fields = list(first_record.to_dict().keys())
                    else:
                        fields = [c.key for c in model_class.__table__.columns]
                    
                    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=fields)
                        writer.writeheader()
                        
                        for record in records:
                            if hasattr(record, 'to_dict'):
                                row_data = record.to_dict()
                            else:
                                row_data = {field: getattr(record, field, '') for field in fields}
                            
                            # Преобразуем даты в строки
                            for key, value in row_data.items():
                                if isinstance(value, datetime):
                                    row_data[key] = value.isoformat()
                                elif value is None:
                                    row_data[key] = ''
                            
                            writer.writerow(row_data)
                
                return str(csv_path)
                
        except Exception as e:
            logger.error(f"Failed to export table {table_name}: {e}")
            raise
    
    async def _generate_backup_summary(self) -> Dict[str, Any]:
        """Генерация сводки для backup"""
        
        try:
            async with get_db_session() as session:
                # Собираем статистику по таблицам
                stats = {}
                
                tables = [
                    ("users", User),
                    ("downloads", DownloadTask),
                    ("payments", Payment),
                    ("broadcasts", BroadcastMessage),
                    ("channels", RequiredChannel),
                    ("analytics_events", AnalyticsEvent)
                ]
                
                for table_name, model_class in tables:
                    count = await session.query(model_class).count()
                    stats[table_name] = count
                
                return {
                    "backup_date": datetime.utcnow().isoformat(),
                    "table_counts": stats,
                    "total_records": sum(stats.values())
                }
                
        except Exception as e:
            logger.error(f"Failed to generate backup summary: {e}")
            return {"error": str(e)}
    
    async def _generate_user_activity_report(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Генерация отчета по активности пользователей"""
        
        days = options.get("days", 30)
        date_from = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Активные пользователи
            active_users = await session.query(User).filter(
                User.last_active_at >= date_from,
                User.is_deleted == False
            ).count()
            
            # Новые пользователи
            new_users = await session.query(User).filter(
                User.created_at >= date_from,
                User.is_deleted == False
            ).count()
            
            # Скачивания
            downloads = await session.query(DownloadTask).filter(
                DownloadTask.created_at >= date_from
            ).count()
            
            return {
                "report_type": "user_activity",
                "period_days": days,
                "active_users": active_users,
                "new_users": new_users,
                "total_downloads": downloads,
                "generated_at": datetime.utcnow().isoformat()
            }
    
    async def _generate_financial_report(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Генерация финансового отчета"""
        
        days = options.get("days", 30)
        date_from = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Общий доход
            from sqlalchemy import func
            total_revenue = await session.query(
                func.sum(Payment.amount)
            ).filter(
                Payment.created_at >= date_from,
                Payment.status == "completed"
            ).scalar() or 0
            
            # Количество платежей
            payment_count = await session.query(Payment).filter(
                Payment.created_at >= date_from,
                Payment.status == "completed"
            ).count()
            
            return {
                "report_type": "financial",
                "period_days": days,
                "total_revenue": float(total_revenue),
                "payment_count": payment_count,
                "avg_payment": float(total_revenue / payment_count) if payment_count > 0 else 0,
                "generated_at": datetime.utcnow().isoformat()
            }
    
    async def _generate_performance_report(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Генерация отчета по производительности"""
        
        # TODO: Собрать метрики производительности
        return {
            "report_type": "performance",
            "generated_at": datetime.utcnow().isoformat(),
            "note": "Performance metrics collection not implemented yet"
        }
    
    async def _generate_security_report(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Генерация отчета по безопасности"""
        
        days = options.get("days", 30)
        date_from = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Заблокированные пользователи
            banned_users = await session.query(User).filter(
                User.is_banned == True,
                User.updated_at >= date_from
            ).count()
            
            return {
                "report_type": "security",
                "period_days": days,
                "banned_users": banned_users,
                "generated_at": datetime.utcnow().isoformat()
            }
    
    async def _generate_summary_report_data(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Генерация общего отчета"""
        
        user_report = await self._generate_user_activity_report(options)
        financial_report = await self._generate_financial_report(options)
        security_report = await self._generate_security_report(options)
        
        return {
            "report_type": "summary",
            "user_activity": user_report,
            "financial": financial_report,
            "security": security_report,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    async def _generate_pdf_report(self, report_data: Dict[str, Any]) -> bytes:
        """Генерация PDF отчета"""
        
        # TODO: Реализовать PDF генерацию с помощью reportlab
        # Пока возвращаем текстовый отчет
        text_report = await generate_summary_report(report_data)
        return text_report.encode('utf-8')
    
    def _estimate_export_time(self, export_type: ExportType, filters: Dict[str, Any] = None) -> int:
        """Оценить время экспорта в минутах"""
        
        base_times = {
            ExportType.USERS: 2,
            ExportType.DOWNLOADS: 5,
            ExportType.PAYMENTS: 3,
            ExportType.ANALYTICS: 1,
            ExportType.BROADCASTS: 1,
            ExportType.CHANNELS: 1,
            ExportType.FULL_BACKUP: 15,
            ExportType.CUSTOM_REPORT: 3
        }
        
        return base_times.get(export_type, 5)
    
    async def cleanup_old_exports(self, days: int = 7):
        """Очистка старых файлов экспорта"""
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Удаляем старые задачи
            old_jobs = [
                job_id for job_id, job in self.export_jobs.items()
                if job["created_at"] < cutoff_date
            ]
            
            for job_id in old_jobs:
                job = self.export_jobs[job_id]
                
                # Удаляем файл если существует
                if job.get("file_path") and Path(job["file_path"]).exists():
                    Path(job["file_path"]).unlink()
                
                # Удаляем задачу из памяти
                del self.export_jobs[job_id]
            
            # Удаляем старые файлы без соответствующих задач
            for file_path in self.export_dir.glob("*"):
                if file_path.is_file():
                    file_age = datetime.utcnow() - datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_age > timedelta(days=days):
                        file_path.unlink()
            
            logger.info(f"Cleaned up {len(old_jobs)} old export jobs and files")
            
            return {
                "success": True,
                "cleaned_jobs": len(old_jobs),
                "cutoff_date": cutoff_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to cleanup old exports: {e}")
            return {"success": False, "error": str(e)}

# Глобальный экземпляр сервиса
export_service = ExportService() file_path.stat().st_size,
                    "records_count": len(users)
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _export_downloads(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Экспорт скачиваний"""
        
        try:
            filters = job["filters"]
            export_format = ExportFormat(job["export_format"])
            
            async with get_db_session() as session:
                # Базовый запрос
                query = session.query(DownloadTask)
                
                # Применяем фильтры
                if filters.get("status"):
                    query = query.filter(DownloadTask.status == filters["status"])
                
                if filters.get("platform"):
                    query = query.filter(DownloadTask.platform == filters["platform"])
                
                if filters.get("user_id"):
                    query = query.filter(DownloadTask.user_id == filters["user_id"])
                
                if filters.get("date_from"):
                    date_from = datetime.fromisoformat(filters["date_from"])
                    query = query.filter(DownloadTask.created_at >= date_from)
                
                if filters.get("date_to"):
                    date_to = datetime.fromisoformat(filters["date_to"])
                    query = query.filter(DownloadTask.created_at <= date_to)
                
                # Ограничиваем количество записей для производительности
                limit = filters.get("limit", 10000)
                query = query.limit(limit)
                
                job["progress"] = 20
                
                downloads = await query.all()
                
                job["progress"] = 60
                
                # Создаем файл экспорта
                if export_format == ExportFormat.CSV:
                    response = await export_downloads_to_csv(downloads)
                    file_extension = "csv"
                elif export_format == ExportFormat.EXCEL:
                    response = await export_downloads_to_excel(downloads)
                    file_extension = "xlsx"
                else:
                    return {"success": False, "error": f"Unsupported format: {export_format}"}
                
                # Сохраняем файл
                filename = f"downloads_export_{job['job_id']}.{file_extension}"
                file_path = self.export_dir / filename
                
                # Получаем содержимое ответа
                if hasattr(response, 'body'):
                    content = response.body
                else:
                    content = b""
                    async for chunk in response.body_iterator:
                        content += chunk
                
                with open(file_path, "wb") as f:
                    f.write(content)
                
                job["progress"] = 100
                
                return {
                    "success": True,
                    "file_path": str(file_path),
                    "file_size": file_path.stat().st_size,
                    "records_count": len(downloads)
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _export_payments(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Экспорт платежей"""
        
        try:
            filters = job["filters"]
            export_format = ExportFormat(job["export_format"])
            
            async with get_db_session() as session:
                # Базовый запрос
                query = session.query(Payment)
                
                # Применяем фильтры
                if filters.get("status"):
                    query = query.filter(Payment.status == filters["status"])
                
                if filters.get("payment_method"):
                    query = query.filter(Payment.payment_method == filters["payment_method"])
                
                if filters.get("currency"):
                    query = query.filter(Payment.currency == filters["currency"])
                
                if filters.get("date_from"):
                    date_from = datetime.fromisoformat(filters["date_from"])
                    query = query.filter(Payment.created_at >= date_from)
                
                if filters.get("date_to"):
                    date_to = datetime.fromisoformat(filters["date_to"])
                    query = query.filter(Payment.created_at <= date_to)
                
                limit = filters.get("limit", 10000)
                query = query.limit(limit)
                
                job["progress"] = 20
                
                payments = await query.all()
                
                job["progress"] = 60
                
                # Создаем файл экспорта (используем функцию из utils)
                from ..utils.export import export_payments_to_csv
                
                if export_format == ExportFormat.CSV:
                    response = await export_payments_to_csv(payments)
                    file_extension = "csv"
                elif export_format == ExportFormat.EXCEL:
                    # TODO: Создать export_payments_to_excel
                    response = await export_payments_to_csv(payments)
                    file_extension = "csv"
                else:
                    return {"success": False, "error": f"Unsupported format: {export_format}"}
                
                # Сохраняем файл
                filename = f"payments_export_{job['job_id']}.{file_extension}"
                file_path = self.export_dir / filename
                
                # Получаем содержимое
                if hasattr(response, 'body'):
                    content = response.body
                else:
                    content = b""
                    async for chunk in response.body_iterator:
                        content += chunk
                
                with open(file_path, "wb") as f:
                    f.write(content)
                
                job["progress"] = 100
                
                return {
                    "success": True,
                    "file_path": str(file_path),
                    "file_size":