#!/usr/bin/env python3
"""
VideoBot Pro - Database Migration Script
Создание и применение миграций базы данных
"""

import os
import sys
import asyncio
from pathlib import Path

# Добавляем корневую директорию в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from shared.config.settings import settings
from shared.models import Base
from shared.models import get_models_in_dependency_order

def create_database_if_not_exists():
    """Создать базу данных если не существует"""
    try:
        # Подключаемся к PostgreSQL без указания БД
        db_url = settings.get_database_url(async_driver=False)
        # Заменяем название БД на postgres для подключения к серверу
        admin_url = db_url.replace('/videobot', '/postgres')
        
        engine = create_engine(admin_url)
        
        # Проверяем существует ли БД
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'videobot'"))
            exists = result.fetchone() is not None
            
            if not exists:
                print("Creating database 'videobot'...")
                conn.execute(text("COMMIT"))  # Закрываем текущую транзакцию
                conn.execute(text("CREATE DATABASE videobot"))
                print("Database 'videobot' created successfully!")
            else:
                print("Database 'videobot' already exists.")
                
        engine.dispose()
        
    except OperationalError as e:
        print(f"Error creating database: {e}")
        print("Please ensure PostgreSQL is running and accessible.")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False
    
    return True


def init_alembic():
    """Инициализировать Alembic если не инициализирован"""
    migrations_dir = project_root / "migrations"
    
    if not migrations_dir.exists():
        print("Initializing Alembic...")
        alembic_cfg = Config("alembic.ini")
        command.init(alembic_cfg, "migrations")
        print("Alembic initialized!")
        
        # Создаем env.py с правильной конфигурацией
        env_py_content = '''from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared.models import Base
from shared.config.settings import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

def get_url():
    return settings.get_database_url(async_driver=False)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''
        
        env_py_path = migrations_dir / "env.py"
        with open(env_py_path, 'w', encoding='utf-8') as f:
            f.write(env_py_content)
            
        print("Created migrations/env.py")


def create_initial_migration():
    """Создать начальную миграцию"""
    alembic_cfg = Config("alembic.ini")
    
    # Проверяем есть ли уже миграции
    versions_dir = project_root / "migrations" / "versions"
    if versions_dir.exists() and any(versions_dir.glob("*.py")):
        print("Migrations already exist. Skipping initial migration creation.")
        return
    
    print("Creating initial migration...")
    command.revision(alembic_cfg, autogenerate=True, message="Initial migration")
    print("Initial migration created!")


def apply_migrations():
    """Применить миграции"""
    print("Applying migrations...")
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    print("Migrations applied successfully!")


def create_tables_directly():
    """Создать таблицы напрямую без миграций (для быстрого старта)"""
    print("Creating tables directly...")
    try:
        from shared.config.database import init_database, close_database
        
        # Инициализируем подключение
        asyncio.run(init_database())
        
        # Создаем таблицы
        from shared.config.database import db_config
        asyncio.run(db_config.create_all_tables())
        
        # Закрываем подключение
        asyncio.run(close_database())
        
        print("All tables created successfully!")
        return True
        
    except Exception as e:
        print(f"Error creating tables: {e}")
        return False


def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description="VideoBot Pro Database Migration Tool")
    parser.add_argument(
        "--mode", 
        choices=["full", "direct", "migrate-only"], 
        default="full",
        help="Migration mode: full (recommended), direct (quick), migrate-only"
    )
    
    args = parser.parse_args()
    
    print("🚀 VideoBot Pro - Database Setup")
    print("=" * 40)
    
    # 1. Создаем БД если не существует
    if not create_database_if_not_exists():
        print("❌ Failed to create database. Exiting.")
        sys.exit(1)
    
    if args.mode == "direct":
        # Быстрое создание таблиц без миграций
        if create_tables_directly():
            print("✅ Database setup completed (direct mode)!")
        else:
            print("❌ Failed to create tables directly.")
            sys.exit(1)
            
    elif args.mode == "full":
        # Полная настройка с миграциями
        try:
            # 2. Инициализируем Alembic
            init_alembic()
            
            # 3. Создаем начальную миграцию
            create_initial_migration()
            
            # 4. Применяем миграции
            apply_migrations()
            
            print("✅ Database setup completed (full mode)!")
            
        except Exception as e:
            print(f"❌ Error during migration setup: {e}")
            print("Trying direct table creation as fallback...")
            if create_tables_directly():
                print("✅ Database setup completed (fallback mode)!")
            else:
                print("❌ All setup methods failed.")
                sys.exit(1)
    
    elif args.mode == "migrate-only":
        # Только применение миграций (если уже настроены)
        try:
            apply_migrations()
            print("✅ Migrations applied successfully!")
        except Exception as e:
            print(f"❌ Error applying migrations: {e}")
            sys.exit(1)
    
    print("\n📋 Next steps:")
    print("1. Configure your .env file with bot token and settings")
    print("2. Run: python -m bot.main")
    print("3. Start using VideoBot Pro!")


if __name__ == "__main__":
    main()