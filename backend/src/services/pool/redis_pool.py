import os
from contextlib import asynccontextmanager
import asyncio
import redis.asyncio as redis

from src.constants import REDIS_POOL_SIZE


class RedisPoolManager:
    def __init__(
        self,
        connection_count: int = REDIS_POOL_SIZE,
    ):

        self.host = os.environ.get("REDIS_HOST")
        self.port = os.environ.get("REDIS_PORT")
        self.db = os.environ.get("REDIS_DB_NUMBER")
        self.db_for_requests = os.environ.get("REDIS_CACHE_REQUESTS_DB_NUMBER")
        # self.password = os.environ.get("REDIS_DB_PASSWORD")
        self.connection_count = connection_count
        self.__connections = asyncio.Queue()


    async def create_connections(self):
        for _ in range(self.connection_count):
            await self.__connections.put(await redis.Redis(
                host=self.host,
                port=int(self.port),
                db=self.db,
                # password=self.password,
                decode_responses=True,  # Автоматическое декодирование в строки
            ))

    async def close_all(self):
        for _ in range(self.connection_count):
            connection = await self.__connections.get()
            connection.close()

    @asynccontextmanager
    async def get_connection(self):
        connection = await self.__connections.get()
        yield connection
        await self.__connections.put(connection)

