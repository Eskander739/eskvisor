import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.constants import DB_POOL_SIZE
from src.db.base import Base


class DBPool:
    def __init__(
        self,
        connection_count: int = DB_POOL_SIZE,
    ):
        self.user = os.environ.get("DB_USER")
        self.password = os.environ.get("DB_PASS")
        self.db_host = os.environ.get("DB_HOST")
        self.db_port = os.environ.get("DB_PORT")

        # Используем асинхронный драйвер asyncpg
        self.engine = create_async_engine(
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.db_host}:{self.db_port}/postgres",
            pool_size=connection_count,  # <-- РАЗМЕР ПУЛА
            max_overflow=5,  # <-- ДОПОЛНИТЕЛЬНЫЕ СОЕДИНЕНИЯ
            pool_timeout=30,  # <-- ТАЙМАУТ
            pool_recycle=3600,  # <-- ПЕРЕСОЗДАНИЕ КАЖДЫЙ ЧАС
            pool_pre_ping=True,  # <-- ПРОВЕРКА СОЕДИНЕНИЯ
            echo=True,
        )
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def create_tables(self):
        async with self.get_connection() as session:
            # Получите connection из session
            connection = await session.connection()
            await connection.run_sync(Base.metadata.create_all)
            await connection.commit()  # Явный коммит

    async def close_pool(self):
        await self.async_session().close_all()
        await self.engine.dispose()

    @asynccontextmanager
    async def get_connection(self):
        session = self.async_session()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
