#!/usr/bin/env python3
"""
VideoBot Pro - Database Migration Script (Fixed Version)
Создание и применение миграций базы данных с правильным управлением асинхронными подключениями
"""

import os
import sys
import asyncio
from pathlib import Path

# Добавляем корневую директорию в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Импорты
try:
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    import asyncpg
except ImportError as e:
    print(f"❌ Missing required dependency: {e}")
    print("Please install: pip install alembic asyncpg")
    sys.exit(1)

try:
    from shared.config.settings import settings
    from shared.models import Base
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're in the project root directory")
    sys.exit(1)


def create_database_if_not_exists():
    """Создать базу данных если не существует (синхронно)"""
    try:
        # Подключаемся к PostgreSQL без указания БД
        db_url = settings.get_database_url(async_driver=False)
        admin_url = db_url.replace('/videobot', '/postgres')
        
        engine = create_engine(admin_url)
        
        # Проверяем существует ли БД
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'videobot'"))
            exists = result.fetchone() is not None
            
            if not exists:
                print("Creating database 'videobot'...")
                conn.execute(text("COMMIT"))
                conn.execute(text("CREATE DATABASE videobot"))
                print("Database 'videobot' created successfully!")
            else:
                print("Database 'videobot' already exists.")
                
        engine.dispose()
        return True
        
    except OperationalError as e:
        print(f"Error creating database: {e}")
        print("Please ensure PostgreSQL is running and accessible.")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False


async def create_tables_async():
    """Создать таблицы асинхронно"""
    print("Creating tables directly (async)...")
    
    try:
        # Получаем параметры подключения
        db_url = settings.get_database_url()
        
        # Парсим URL для asyncpg
        if db_url.startswith('postgresql+asyncpg://'):
            db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
        
        print(f"Connecting to: {db_url}")
        
        # Подключаемся к базе данных
        conn = await asyncpg.connect(db_url)
        print("✅ Connected to database")
        
        # Получаем DDL команды для создания таблиц
        from sqlalchemy import create_engine
        from sqlalchemy.schema import CreateTable
        
        # Создаем временный синхронный движок для генерации DDL
        temp_engine = create_engine(settings.get_database_url(async_driver=False))
        
        # Создаем таблицы
        tables_created = []
        for table_name, table in Base.metadata.tables.items():
            try:
                # Генерируем CREATE TABLE команду
                create_ddl = str(CreateTable(table).compile(temp_engine))
                
                # Выполняем команду
                await conn.execute(create_ddl)
                tables_created.append(table_name)
                print(f"✅ Created table: {table_name}")
                
            except asyncpg.exceptions.DuplicateTableError:
                print(f"⚠️  Table {table_name} already exists, skipping")
            except Exception as e:
                print(f"❌ Error creating table {table_name}: {e}")
        
        temp_engine.dispose()
        
        # Закрываем соединение
        await conn.close()
        print(f"✅ Database setup completed! Created {len(tables_created)} tables.")
        return True
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_tables_sync():
    """Создать таблицы синхронно"""
    print("Creating tables directly (sync)...")
    
    try:
        # Создаем синхронный движок
        db_url = settings.get_database_url(async_driver=False)
        engine = create_engine(db_url, echo=True)
        
        # Создаем все таблицы
        Base.metadata.create_all(engine)
        
        # Проверяем созданные таблицы
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """))
            tables = [row[0] for row in result.fetchall()]
            
        engine.dispose()
        
        print(f"✅ Database setup completed! Tables: {', '.join(tables)}")
        return True
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        import traceback
        traceback.print_exc()
        return False


def init_alembic():
    """Инициализировать Alembic"""
    migrations_dir = project_root / "migrations"
    
    if not migrations_dir.exists():
        print("Initializing Alembic...")
        alembic_cfg = Config("alembic.ini")
        command.init(alembic_cfg, "migrations")
        print("Alembic initialized!")


def create_initial_migration():
    """Создать начальную миграцию"""
    alembic_cfg = Config("alembic.ini")
    
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


def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description="VideoBot Pro Database Migration Tool (Fixed)")
    parser.add_argument(
        "--mode", 
        choices=["full", "direct", "sync", "async", "migrate-only"], 
        default="sync",
        help="Migration mode: sync (recommended), async, full, direct, migrate-only"
    )
    
    args = parser.parse_args()
    
    print("🚀 VideoBot Pro - Database Setup (Fixed)")
    print("=" * 50)
    
    # 1. Создаем БД если не существует
    if not create_database_if_not_exists():
        print("❌ Failed to create database. Exiting.")
        sys.exit(1)
    
    success = False
    
    if args.mode == "sync":
        # Синхронное создание таблиц (рекомендуется)
        success = create_tables_sync()
        
    elif args.mode == "async":
        # Асинхронное создание таблиц
        success = asyncio.run(create_tables_async())
        
    elif args.mode == "direct":
        # Пробуем синхронно, затем асинхронно
        success = create_tables_sync()
        if not success:
            print("Trying async method...")
            success = asyncio.run(create_tables_async())
            
    elif args.mode == "full":
        # Полная настройка с миграциями
        try:
            init_alembic()
            create_initial_migration()
            apply_migrations()
            success = True
            print("✅ Database setup completed (full mode)!")
            
        except Exception as e:
            print(f"❌ Error during migration setup: {e}")
            print("Trying direct table creation...")
            success = create_tables_sync()
    
    elif args.mode == "migrate-only":
        # Только применение миграций
        try:
            apply_migrations()
            success = True
            print("✅ Migrations applied successfully!")
        except Exception as e:
            print(f"❌ Error applying migrations: {e}")
            sys.exit(1)
    
    if success:
        print("\n📋 Next steps:")
        print("1. Configure your .env file with bot token and settings")
        print("2. Run: python -m bot.main")
        print("3. Start using VideoBot Pro!")
    else:
        print("❌ Database setup failed. Check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()