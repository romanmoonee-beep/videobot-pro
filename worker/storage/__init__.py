"""
VideoBot Pro - Worker Storage Package
Модуль для работы с различными хранилищами файлов
"""

from .base import BaseStorage, StorageError, StorageConfig
from .wasabi import WasabiStorage
from .backblaze import BackblazeStorage
from .digitalocean import DigitalOceanStorage
from .local import LocalStorage

# Фабрика для создания экземпляров хранилищ
def create_storage(storage_type: str, config: dict) -> BaseStorage:
    """
    Фабричная функция для создания экземпляра хранилища
    
    Args:
        storage_type: Тип хранилища (wasabi, backblaze, digitalocean, local)
        config: Конфигурация хранилища
        
    Returns:
        Экземпляр хранилища
        
    Raises:
        ValueError: Если тип хранилища не поддерживается
    """
    storage_classes = {
        'wasabi': WasabiStorage,
        'backblaze': BackblazeStorage,
        'digitalocean': DigitalOceanStorage,
        'local': LocalStorage,
    }
    
    if storage_type not in storage_classes:
        raise ValueError(f"Unsupported storage type: {storage_type}")
    
    return storage_classes[storage_type](config)

__all__ = [
    'BaseStorage',
    'StorageError', 
    'StorageConfig',
    'WasabiStorage',
    'BackblazeStorage',
    'DigitalOceanStorage',
    'LocalStorage',
    'create_storage',
]