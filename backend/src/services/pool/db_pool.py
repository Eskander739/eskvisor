import asyncio
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
            echo=True,
        )
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.connection_count = connection_count
        self.__connections = asyncio.Queue()

    async def create_connections(self):
        for _ in range(self.connection_count):
            session = self.async_session()
            await self.__connections.put(session)

    async def create_tables(self):
        async with self.get_connection() as session:
            # Получите connection из session
            connection = await session.connection()
            await connection.run_sync(Base.metadata.create_all)
            await connection.commit()  # Явный коммит

    async def close_all(self):
        for _ in range(self.connection_count):
            connection = await self.__connections.get()
            await connection.close()

    @asynccontextmanager
    async def get_connection(self):
        connection = await self.__connections.get()
        yield connection
        await self.__connections.put(connection)
