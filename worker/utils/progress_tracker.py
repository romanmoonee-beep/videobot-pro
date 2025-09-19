"""
VideoBot Pro - Progress Tracker
Отслеживание прогресса выполнения задач
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
import json
import time

logger = structlog.get_logger(__name__)

class ProgressTrackerError(Exception):
    """Ошибки трекера прогресса"""
    pass

class TaskStatus(Enum):
    """Статусы задач"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"

class ProgressTracker:
    """Трекер прогресса для задач worker'а"""
    
    def __init__(self, redis_client=None):
        """
        Инициализация трекера прогресса
        
        Args:
            redis_client: Redis клиент для хранения прогресса (опционально)
        """
        self.redis_client = redis_client
        self._local_storage = {}  # Локальное хранение если нет Redis
        self._callbacks = {}      # Колбэки для обновлений
        self._update_intervals = {}  # Интервалы обновления
        
    def start_task(self, task_id: str, total_steps: int = 100, 
                   task_name: str = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Начало отслеживания задачи
        
        Args:
            task_id: Уникальный ID задачи
            total_steps: Общее количество шагов
            task_name: Название задачи
            metadata: Дополнительные метаданные
            
        Returns:
            Информация о созданной задаче
        """
        try:
            task_info = {
                'task_id': task_id,
                'task_name': task_name or f"Task {task_id}",
                'status': TaskStatus.RUNNING.value,
                'progress': 0,
                'total_steps': total_steps,
                'current_step': 0,
                'message': 'Task started',
                'started_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat(),
                'completed_at': None,
                'duration_seconds': None,
                'estimated_completion': None,
                'metadata': metadata or {},
                'error': None,
                'warnings': []
            }
            
            # Сохраняем информацию
            self._save_task_info(task_id, task_info)
            
            logger.info(f"Started tracking task: {task_id}", 
                       task_name=task_name, total_steps=total_steps)
            
            return task_info
            
        except Exception as e:
            logger.error(f"Error starting task tracking: {e}")
            raise ProgressTrackerError(f"Cannot start task tracking: {e}")
    
    def update_progress(self, task_id: str, current_step: int = None, 
                       progress: float = None, message: str = None,
                       metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Обновление прогресса задачи
        
        Args:
            task_id: ID задачи
            current_step: Текущий шаг (если указан, progress рассчитается автоматически)
            progress: Прогресс в процентах (0-100)
            message: Сообщение о текущем состоянии
            metadata: Дополнительные метаданные
            
        Returns:
            Обновленная информация о задаче
        """
        try:
            task_info = self._get_task_info(task_id)
            if not task_info:
                raise ProgressTrackerError(f"Task {task_id} not found")
            
            # Проверяем что задача еще выполняется
            if task_info['status'] not in [TaskStatus.RUNNING.value, TaskStatus.PAUSED.value]:
                logger.warning(f"Cannot update progress for task in status: {task_info['status']}")
                return task_info
            
            # Обновляем прогресс
            if current_step is not None:
                task_info['current_step'] = current_step
                total_steps = task_info['total_steps']
                if total_steps > 0:
                    task_info['progress'] = min(100.0, (current_step / total_steps) * 100)
            elif progress is not None:
                task_info['progress'] = min(100.0, max(0.0, progress))
                # Обратный расчет текущего шага
                if task_info['total_steps'] > 0:
                    task_info['current_step'] = int((progress / 100.0) * task_info['total_steps'])
            
            # Обновляем сообщение
            if message:
                task_info['message'] = message
            
            # Обновляем метаданные
            if metadata:
                task_info['metadata'].update(metadata)
            
            # Обновляем времена
            now = datetime.utcnow()
            task_info['updated_at'] = now.isoformat()
            
            # Оценка времени завершения
            if task_info['progress'] > 0:
                started_at = datetime.fromisoformat(task_info['started_at'])
                elapsed_seconds = (now - started_at).total_seconds()
                estimated_total_seconds = elapsed_seconds / (task_info['progress'] / 100.0)
                estimated_completion = started_at + timedelta(seconds=estimated_total_seconds)
                task_info['estimated_completion'] = estimated_completion.isoformat()
            
            # Сохраняем обновления
            self._save_task_info(task_id, task_info)
            
            # Вызываем колбэки
            self._trigger_callbacks(task_id, task_info)
            
            logger.debug(f"Updated progress for task {task_id}: {task_info['progress']:.1f}%")
            
            return task_info
            
        except Exception as e:
            logger.error(f"Error updating task progress: {e}")
            raise ProgressTrackerError(f"Cannot update task progress: {e}")
    
    def complete_task(self, task_id: str, message: str = None, 
                     result_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Завершение задачи
        
        Args:
            task_id: ID задачи
            message: Сообщение о завершении
            result_data: Данные результата
            
        Returns:
            Информация о завершенной задаче
        """
        try:
            task_info = self._get_task_info(task_id)
            if not task_info:
                raise ProgressTrackerError(f"Task {task_id} not found")
            
            # Обновляем статус
            task_info['status'] = TaskStatus.COMPLETED.value
            task_info['progress'] = 100.0
            task_info['current_step'] = task_info['total_steps']
            task_info['message'] = message or 'Task completed successfully'
            
            # Устанавливаем время завершения
            now = datetime.utcnow()
            task_info['completed_at'] = now.isoformat()
            task_info['updated_at'] = now.isoformat()
            
            # Вычисляем длительность
            started_at = datetime.fromisoformat(task_info['started_at'])
            task_info['duration_seconds'] = (now - started_at).total_seconds()
            
            # Добавляем данные результата
            if result_data:
                task_info['metadata']['result'] = result_data
            
            # Сохраняем
            self._save_task_info(task_id, task_info)
            
            # Вызываем колбэки
            self._trigger_callbacks(task_id, task_info)
            
            logger.info(f"Task completed: {task_id}", 
                       duration=task_info['duration_seconds'])
            
            return task_info
            
        except Exception as e:
            logger.error(f"Error completing task: {e}")
            raise ProgressTrackerError(f"Cannot complete task: {e}")
    
    def fail_task(self, task_id: str, error_message: str, 
                 error_details: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Отметка задачи как неудачной
        
        Args:
            task_id: ID задачи
            error_message: Сообщение об ошибке
            error_details: Детали ошибки
            
        Returns:
            Информация о задаче с ошибкой
        """
        try:
            task_info = self._get_task_info(task_id)
            if not task_info:
                raise ProgressTrackerError(f"Task {task_id} not found")
            
            # Обновляем статус
            task_info['status'] = TaskStatus.FAILED.value
            task_info['message'] = f'Task failed: {error_message}'
            task_info['error'] = {
                'message': error_message,
                'timestamp': datetime.utcnow().isoformat(),
                'details': error_details or {}
            }
            
            # Устанавливаем время завершения
            now = datetime.utcnow()
            task_info['completed_at'] = now.isoformat()
            task_info['updated_at'] = now.isoformat()
            
            # Вычисляем длительность
            started_at = datetime.fromisoformat(task_info['started_at'])
            task_info['duration_seconds'] = (now - started_at).total_seconds()
            
            # Сохраняем
            self._save_task_info(task_id, task_info)
            
            # Вызываем колбэки
            self._trigger_callbacks(task_id, task_info)
            
            logger.error(f"Task failed: {task_id}", error_message=error_message)
            
            return task_info
            
        except Exception as e:
            logger.error(f"Error failing task: {e}")
            raise ProgressTrackerError(f"Cannot fail task: {e}")
    
    def cancel_task(self, task_id: str, reason: str = None) -> Dict[str, Any]:
        """
        Отмена задачи
        
        Args:
            task_id: ID задачи
            reason: Причина отмены
            
        Returns:
            Информация об отмененной задаче
        """
        try:
            task_info = self._get_task_info(task_id)
            if not task_info:
                raise ProgressTrackerError(f"Task {task_id} not found")
            
            # Обновляем статус
            task_info['status'] = TaskStatus.CANCELLED.value
            task_info['message'] = f'Task cancelled: {reason or "User request"}'
            
            # Устанавливаем время завершения
            now = datetime.utcnow()
            task_info['completed_at'] = now.isoformat()
            task_info['updated_at'] = now.isoformat()
            
            # Вычисляем длительность
            started_at = datetime.fromisoformat(task_info['started_at'])
            task_info['duration_seconds'] = (now - started_at).total_seconds()
            
            # Добавляем информацию об отмене
            task_info['metadata']['cancellation'] = {
                'reason': reason or "User request",
                'cancelled_at': now.isoformat()
            }
            
            # Сохраняем
            self._save_task_info(task_id, task_info)
            
            # Вызываем колбэки
            self._trigger_callbacks(task_id, task_info)
            
            logger.info(f"Task cancelled: {task_id}", reason=reason)
            
            return task_info
            
        except Exception as e:
            logger.error(f"Error cancelling task: {e}")
            raise ProgressTrackerError(f"Cannot cancel task: {e}")
    
    def pause_task(self, task_id: str) -> Dict[str, Any]:
        """
        Приостановка задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Информация о приостановленной задаче
        """
        try:
            task_info = self._get_task_info(task_id)
            if not task_info:
                raise ProgressTrackerError(f"Task {task_id} not found")
            
            if task_info['status'] != TaskStatus.RUNNING.value:
                raise ProgressTrackerError(f"Cannot pause task in status: {task_info['status']}")
            
            # Обновляем статус
            task_info['status'] = TaskStatus.PAUSED.value
            task_info['message'] = 'Task paused'
            task_info['updated_at'] = datetime.utcnow().isoformat()
            
            # Добавляем информацию о паузе
            task_info['metadata']['pause_info'] = {
                'paused_at': datetime.utcnow().isoformat(),
                'paused_at_progress': task_info['progress']
            }
            
            # Сохраняем
            self._save_task_info(task_id, task_info)
            
            # Вызываем колбэки
            self._trigger_callbacks(task_id, task_info)
            
            logger.info(f"Task paused: {task_id}")
            
            return task_info
            
        except Exception as e:
            logger.error(f"Error pausing task: {e}")
            raise ProgressTrackerError(f"Cannot pause task: {e}")
    
    def resume_task(self, task_id: str) -> Dict[str, Any]:
        """
        Возобновление приостановленной задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Информация о возобновленной задаче
        """
        try:
            task_info = self._get_task_info(task_id)
            if not task_info:
                raise ProgressTrackerError(f"Task {task_id} not found")
            
            if task_info['status'] != TaskStatus.PAUSED.value:
                raise ProgressTrackerError(f"Cannot resume task in status: {task_info['status']}")
            
            # Обновляем статус
            task_info['status'] = TaskStatus.RUNNING.value
            task_info['message'] = 'Task resumed'
            task_info['updated_at'] = datetime.utcnow().isoformat()
            
            # Добавляем информацию о возобновлении
            if 'pause_info' in task_info['metadata']:
                pause_info = task_info['metadata']['pause_info']
                paused_at = datetime.fromisoformat(pause_info['paused_at'])
                resumed_at = datetime.utcnow()
                pause_duration = (resumed_at - paused_at).total_seconds()
                
                task_info['metadata']['resume_info'] = {
                    'resumed_at': resumed_at.isoformat(),
                    'pause_duration_seconds': pause_duration
                }
            
            # Сохраняем
            self._save_task_info(task_id, task_info)
            
            # Вызываем колбэки
            self._trigger_callbacks(task_id, task_info)
            
            logger.info(f"Task resumed: {task_id}")
            
            return task_info
            
        except Exception as e:
            logger.error(f"Error resuming task: {e}")
            raise ProgressTrackerError(f"Cannot resume task: {e}")
    
    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение информации о задаче
        
        Args:
            task_id: ID задачи
            
        Returns:
            Информация о задаче или None если не найдена
        """
        return self._get_task_info(task_id)
    
    def add_warning(self, task_id: str, warning_message: str, 
                   warning_details: Dict[str, Any] = None):
        """
        Добавление предупреждения к задаче
        
        Args:
            task_id: ID задачи
            warning_message: Сообщение предупреждения
            warning_details: Детали предупреждения
        """
        try:
            task_info = self._get_task_info(task_id)
            if not task_info:
                return
            
            warning = {
                'message': warning_message,
                'timestamp': datetime.utcnow().isoformat(),
                'details': warning_details or {}
            }
            
            task_info['warnings'].append(warning)
            task_info['updated_at'] = datetime.utcnow().isoformat()
            
            self._save_task_info(task_id, task_info)
            
            logger.warning(f"Task warning: {task_id}", warning=warning_message)
            
        except Exception as e:
            logger.error(f"Error adding warning: {e}")
    
    def register_callback(self, task_id: str, callback: Callable[[str, Dict[str, Any]], None], 
                         update_interval: float = 1.0):
        """
        Регистрация колбэка для обновлений задачи
        
        Args:
            task_id: ID задачи
            callback: Функция колбэка (task_id, task_info) -> None
            update_interval: Минимальный интервал между вызовами в секундах
        """
        if task_id not in self._callbacks:
            self._callbacks[task_id] = []
            self._update_intervals[task_id] = {}
        
        self._callbacks[task_id].append(callback)
        self._update_intervals[task_id][id(callback)] = {
            'interval': update_interval,
            'last_called': 0
        }
    
    def unregister_callback(self, task_id: str, callback: Callable):
        """
        Удаление колбэка
        
        Args:
            task_id: ID задачи
            callback: Функция колбэка для удаления
        """
        if task_id in self._callbacks:
            try:
                self._callbacks[task_id].remove(callback)
                if id(callback) in self._update_intervals[task_id]:
                    del self._update_intervals[task_id][id(callback)]
            except ValueError:
                pass
    
    def list_tasks(self, status_filter: str = None) -> List[Dict[str, Any]]:
        """
        Получение списка всех задач
        
        Args:
            status_filter: Фильтр по статусу (опционально)
            
        Returns:
            Список задач
        """
        try:
            all_tasks = []
            
            if self.redis_client:
                # Получаем из Redis
                pattern = "progress:*"
                keys = self.redis_client.keys(pattern)
                for key in keys:
                    try:
                        task_data = self.redis_client.get(key)
                        if task_data:
                            task_info = json.loads(task_data)
                            if status_filter is None or task_info.get('status') == status_filter:
                                all_tasks.append(task_info)
                    except Exception as e:
                        logger.error(f"Error loading task from Redis: {e}")
                        continue
            else:
                # Получаем из локального хранения
                for task_id, task_info in self._local_storage.items():
                    if status_filter is None or task_info.get('status') == status_filter:
                        all_tasks.append(task_info)
            
            # Сортируем по времени создания (новые сначала)
            all_tasks.sort(key=lambda x: x.get('started_at', ''), reverse=True)
            
            return all_tasks
            
        except Exception as e:
            logger.error(f"Error listing tasks: {e}")
            return []
    
    def cleanup_completed_tasks(self, max_age_hours: int = 24) -> int:
        """
        Очистка завершенных задач
        
        Args:
            max_age_hours: Максимальный возраст задач в часах
            
        Returns:
            Количество удаленных задач
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            deleted_count = 0
            
            # Получаем все задачи
            all_tasks = self.list_tasks()
            
            for task_info in all_tasks:
                # Проверяем завершенные задачи
                if task_info['status'] in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
                    completed_at_str = task_info.get('completed_at')
                    if completed_at_str:
                        completed_at = datetime.fromisoformat(completed_at_str)
                        if completed_at < cutoff_time:
                            self._delete_task_info(task_info['task_id'])
                            deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old completed tasks")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up tasks: {e}")
            return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Получение статистики по всем задачам
        
        Returns:
            Статистика
        """
        try:
            all_tasks = self.list_tasks()
            
            stats = {
                'total_tasks': len(all_tasks),
                'by_status': {},
                'average_duration_seconds': 0,
                'total_completed': 0,
                'success_rate': 0,
                'active_tasks': 0
            }
            
            total_duration = 0
            completed_tasks = 0
            successful_tasks = 0
            
            # Подсчитываем статистику
            for task_info in all_tasks:
                status = task_info.get('status')
                
                # Подсчет по статусам
                if status in stats['by_status']:
                    stats['by_status'][status] += 1
                else:
                    stats['by_status'][status] = 1
                
                # Активные задачи
                if status in [TaskStatus.RUNNING.value, TaskStatus.PAUSED.value]:
                    stats['active_tasks'] += 1
                
                # Длительность для завершенных задач
                if task_info.get('duration_seconds'):
                    total_duration += task_info['duration_seconds']
                    completed_tasks += 1
                    
                    if status == TaskStatus.COMPLETED.value:
                        successful_tasks += 1
            
            # Средняя длительность
            if completed_tasks > 0:
                stats['average_duration_seconds'] = total_duration / completed_tasks
                stats['total_completed'] = completed_tasks
                stats['success_rate'] = (successful_tasks / completed_tasks) * 100
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {'error': str(e)}
    
    # Внутренние методы
    
    def _save_task_info(self, task_id: str, task_info: Dict[str, Any]):
        """Сохранение информации о задаче"""
        try:
            if self.redis_client:
                # Сохраняем в Redis с TTL 7 дней
                key = f"progress:{task_id}"
                self.redis_client.setex(key, 7 * 24 * 3600, json.dumps(task_info))
            else:
                # Сохраняем локально
                self._local_storage[task_id] = task_info
                
        except Exception as e:
            logger.error(f"Error saving task info: {e}")
    
    def _get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Получение информации о задаче"""
        try:
            if self.redis_client:
                key = f"progress:{task_id}"
                task_data = self.redis_client.get(key)
                if task_data:
                    return json.loads(task_data)
            else:
                return self._local_storage.get(task_id)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting task info: {e}")
            return None
    
    def _delete_task_info(self, task_id: str):
        """Удаление информации о задаче"""
        try:
            if self.redis_client:
                key = f"progress:{task_id}"
                self.redis_client.delete(key)
            else:
                if task_id in self._local_storage:
                    del self._local_storage[task_id]
            
            # Очищаем колбэки
            if task_id in self._callbacks:
                del self._callbacks[task_id]
            if task_id in self._update_intervals:
                del self._update_intervals[task_id]
                
        except Exception as e:
            logger.error(f"Error deleting task info: {e}")
    
    def _trigger_callbacks(self, task_id: str, task_info: Dict[str, Any]):
        """Вызов колбэков для задачи"""
        try:
            if task_id not in self._callbacks:
                return
            
            current_time = time.time()
            
            for callback in self._callbacks[task_id]:
                try:
                    callback_id = id(callback)
                    interval_info = self._update_intervals[task_id].get(callback_id)
                    
                    if interval_info:
                        # Проверяем интервал
                        if current_time - interval_info['last_called'] >= interval_info['interval']:
                            callback(task_id, task_info)
                            interval_info['last_called'] = current_time
                    else:
                        # Нет интервала - вызываем всегда
                        callback(task_id, task_info)
                        
                except Exception as e:
                    logger.error(f"Error in progress callback: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error triggering callbacks: {e}")

# Утилитарные функции для удобного использования

def create_progress_callback(progress_tracker: ProgressTracker, task_id: str):
    """
    Создает колбэк функцию для yt-dlp и других инструментов
    
    Args:
        progress_tracker: Экземпляр ProgressTracker
        task_id: ID задачи
        
    Returns:
        Функция колбэка
    """
    def progress_hook(d):
        try:
            if d['status'] == 'downloading':
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded_bytes = d.get('downloaded_bytes', 0)
                
                if total_bytes and total_bytes > 0:
                    progress = (downloaded_bytes / total_bytes) * 100
                    speed = d.get('speed', 0)
                    
                    message = f"Downloading... {progress:.1f}%"
                    if speed:
                        speed_mb = speed / (1024 * 1024)
                        message += f" ({speed_mb:.1f} MB/s)"
                    
                    progress_tracker.update_progress(
                        task_id, 
                        progress=progress,
                        message=message,
                        metadata={
                            'downloaded_bytes': downloaded_bytes,
                            'total_bytes': total_bytes,
                            'speed_bps': speed
                        }
                    )
                    
            elif d['status'] == 'finished':
                progress_tracker.update_progress(
                    task_id,
                    progress=100,
                    message="Download completed, processing..."
                )
                
            elif d['status'] == 'error':
                error_msg = d.get('error', 'Unknown download error')
                progress_tracker.add_warning(task_id, f"Download warning: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error in download progress callback: {e}")
    
    return progress_hook

class BatchProgressTracker:
    """Специальный трекер для batch операций"""
    
    def __init__(self, progress_tracker: ProgressTracker, batch_id: str, total_items: int):
        """
        Инициализация batch трекера
        
        Args:
            progress_tracker: Основной трекер прогресса
            batch_id: ID batch'а
            total_items: Общее количество элементов в batch'е
        """
        self.progress_tracker = progress_tracker
        self.batch_id = batch_id
        self.total_items = total_items
        self.completed_items = 0
        self.failed_items = 0
        
        # Начинаем отслеживание batch'а
        self.progress_tracker.start_task(
            batch_id, 
            total_steps=total_items,
            task_name=f"Batch processing ({total_items} items)",
            metadata={
                'batch_type': True,
                'total_items': total_items,
                'completed_items': 0,
                'failed_items': 0
            }
        )
    
    def item_completed(self, item_id: str = None, result_data: Dict[str, Any] = None):
        """
        Отметка об успешном завершении элемента
        
        Args:
            item_id: ID элемента (опционально)
            result_data: Данные результата
        """
        self.completed_items += 1
        self._update_progress(f"Completed item {self.completed_items}/{self.total_items}")
        
        if self.completed_items + self.failed_items >= self.total_items:
            self._complete_batch()
    
    def item_failed(self, item_id: str = None, error_message: str = None):
        """
        Отметка о неудачном завершении элемента
        
        Args:
            item_id: ID элемента (опционально)
            error_message: Сообщение об ошибке
        """
        self.failed_items += 1
        
        if error_message:
            self.progress_tracker.add_warning(
                self.batch_id, 
                f"Item failed: {error_message}",
                {'item_id': item_id}
            )
        
        self._update_progress(f"Processing items... ({self.failed_items} failed)")
        
        if self.completed_items + self.failed_items >= self.total_items:
            self._complete_batch()
    
    def _update_progress(self, message: str):
        """Обновление прогресса batch'а"""
        progress = ((self.completed_items + self.failed_items) / self.total_items) * 100
        
        self.progress_tracker.update_progress(
            self.batch_id,
            progress=progress,
            message=message,
            metadata={
                'completed_items': self.completed_items,
                'failed_items': self.failed_items,
                'remaining_items': self.total_items - self.completed_items - self.failed_items
            }
        )
    
    def _complete_batch(self):
        """Завершение batch обработки"""
        if self.failed_items == 0:
            self.progress_tracker.complete_task(
                self.batch_id,
                f"Batch completed successfully: {self.completed_items}/{self.total_items}",
                {
                    'total_items': self.total_items,
                    'completed_items': self.completed_items,
                    'failed_items': self.failed_items,
                    'success_rate': (self.completed_items / self.total_items) * 100
                }
            )
        else:
            message = f"Batch completed with errors: {self.completed_items} successful, {self.failed_items} failed"
            if self.completed_items > 0:
                self.progress_tracker.complete_task(self.batch_id, message)
            else:
                self.progress_tracker.fail_task(self.batch_id, "All batch items failed")

# Декоратор для автоматического отслеживания прогресса функций
def track_progress(progress_tracker: ProgressTracker, task_name: str = None):
    """
    Декоратор для автоматического отслеживания прогресса функций
    
    Args:
        progress_tracker: Экземпляр ProgressTracker
        task_name: Название задачи
        
    Returns:
        Декоратор функции
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            import inspect
            task_id = f"{func.__name__}_{int(time.time())}"
            
            try:
                # Начинаем отслеживание
                progress_tracker.start_task(
                    task_id,
                    task_name=task_name or func.__name__,
                    metadata={'function': func.__name__, 'args_count': len(args)}
                )
                
                # Выполняем функцию
                if inspect.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Завершаем успешно
                progress_tracker.complete_task(task_id, "Function completed successfully")
                return result
                
            except Exception as e:
                # Отмечаем как неудачную
                progress_tracker.fail_task(task_id, str(e))
                raise
        
        def sync_wrapper(*args, **kwargs):
            task_id = f"{func.__name__}_{int(time.time())}"
            
            try:
                # Начинаем отслеживание
                progress_tracker.start_task(
                    task_id,
                    task_name=task_name or func.__name__,
                    metadata={'function': func.__name__, 'args_count': len(args)}
                )
                
                # Выполняем функцию
                result = func(*args, **kwargs)
                
                # Завершаем успешно
                progress_tracker.complete_task(task_id, "Function completed successfully")
                return result
                
            except Exception as e:
                # Отмечаем как неудачную
                progress_tracker.fail_task(task_id, str(e))
                raise
        
        # Возвращаем соответствующую обертку
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator