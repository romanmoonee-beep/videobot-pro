#!/usr/bin/env python3
"""
Диагностика базы данных VideoBot Pro
"""

import sys
import asyncio
from pathlib import Path

# Добавляем корневую директорию в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from shared.config.settings import settings
    from shared.models import Base
    from sqlalchemy import create_engine, text, inspect
    import asyncpg
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


def check_database_sync():
    """Проверка базы данных синхронно"""
    print("🔍 Checking database (sync)...")
    
    try:
        db_url = settings.get_database_url(async_driver=False)
        print(f"Database URL: {db_url}")
        
        engine = create_engine(db_url)
        
        with engine.connect() as conn:
            # Проверяем подключение
            version = conn.execute(text("SELECT version()")).fetchone()[0]
            print(f"✅ Connected to: {version[:50]}...")
            
            # Проверяем существующие таблицы
            tables = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)).fetchall()
            
            print(f"📊 Existing tables: {len(tables)}")
            for table in tables:
                print(f"  - {table[0]}")
            
            # Показываем что должно быть создано
            print(f"📋 Expected tables from models: {len(Base.metadata.tables)}")
            for table_name in Base.metadata.tables.keys():
                print(f"  - {table_name}")
        
        engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Database check failed: {e}")
        return False


async def check_database_async():
    """Проверка базы данных асинхронно"""
    print("🔍 Checking database (async)...")
    
    try:
        db_url = settings.get_database_url()
        if db_url.startswith('postgresql+asyncpg://'):
            db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
        
        print(f"Database URL: {db_url}")
        
        conn = await asyncpg.connect(db_url)
        
        # Проверяем подключение
        version = await conn.fetchval("SELECT version()")
        print(f"✅ Connected to: {version[:50]}...")
        
        # Проверяем существующие таблицы
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        print(f"📊 Existing tables: {len(tables)}")
        for table in tables:
            print(f"  - {table['table_name']}")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Async database check failed: {e}")
        return False


def create_tables_manual():
    """Ручное создание таблиц с детальным логированием"""
    print("🛠️ Creating tables manually...")
    
    try:
        db_url = settings.get_database_url(async_driver=False)
        engine = create_engine(db_url, echo=False)  # Отключаем echo для чистоты
        
        print("📋 Tables to create:")
        for table_name, table in Base.metadata.tables.items():
            print(f"  - {table_name}: {len(table.columns)} columns")
        
        print("\n🔨 Creating tables...")
        
        # Создаем по одной таблице
        for table_name, table in Base.metadata.tables.items():
            try:
                table.create(engine, checkfirst=True)
                print(f"✅ Created: {table_name}")
            except Exception as e:
                print(f"❌ Failed to create {table_name}: {e}")
        
        # Проверяем результат
        with engine.connect() as conn:
            tables = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)).fetchall()
            
            print(f"\n📊 Result: {len(tables)} tables created")
            for table in tables:
                print(f"  ✅ {table[0]}")
        
        engine.dispose()
        return True
        
    except Exception as e:
        print(f"❌ Manual table creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_model_info():
    """Показать информацию о моделях"""
    print("📋 Model Information:")
    print(f"Total models: {len(Base.metadata.tables)}")
    
    for table_name, table in Base.metadata.tables.items():
        print(f"\n🔹 {table_name}:")
        for column in table.columns:
            print(f"  - {column.name}: {column.type}")


async def main():
    """Главная функция диагностики"""
    print("🚀 VideoBot Pro - Database Diagnostic")
    print("=" * 50)
    
    # 1. Показать информацию о моделях
    show_model_info()
    
    print("\n" + "=" * 50)
    
    # 2. Проверить подключение синхронно
    sync_ok = check_database_sync()
    
    print("\n" + "=" * 50)
    
    # 3. Проверить подключение асинхронно
    async_ok = await check_database_async()
    
    print("\n" + "=" * 50)
    
    # 4. Попробовать создать таблицы вручную
    if sync_ok:
        success = create_tables_manual()
        if success:
            print("\n✅ Database setup completed successfully!")
        else:
            print("\n❌ Database setup failed!")
    else:
        print("\n❌ Cannot create tables - database connection failed!")


if __name__ == "__main__":
    asyncio.run(main())