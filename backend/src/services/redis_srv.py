import json
import os
from typing import List, Any
from src.services.pool.redis_pool import RedisPoolManager


class RedisJWTManager:
    """
    Класс для управления JWT-токенами в Redis.
    Поддерживает добавление, инвалидацию и получение токенов.
    """

    def __init__(
        self,
        redis_pool: RedisPoolManager,
        jwt_prefix: str = "jwt_",
    ):
        self.host = os.environ.get("REDIS_HOST")
        self.port = os.environ.get("REDIS_PORT")
        self.db = os.environ.get("REDIS_DB_NUMBER")
        # self.password = os.environ.get("REDIS_DB_PASSWORD")
        self.jwt_prefix = jwt_prefix
        self.redis_pool = redis_pool

    async def check_connection(self) -> bool:
        try:
            redis_connect = await self.get_redis_connection()

            # Простой ping
            pong = await redis_connect.ping()
            if pong:
                return True
            else:
                return False

        except Exception:
            return False

    async def get_redis_connection(self):
        async with self.redis_pool.get_connection as conn:
            return conn

    # _________________________________________[JWT METHODS]_________________________________________

    async def add_token(self, token: str, expire_seconds: int = 86400 * 7) -> bool:
        """
        Добавляет JWT-токен в Redis с TTL.

        :param token: JWT-токен
        :param expire_seconds: Время жизни токена в секундах (по умолчанию 24 часа * 7)
        :return: True, если токен успешно добавлен
        """
        key = f"{self.jwt_prefix}{token}"
        redis_connect = await self.get_redis_connection()
        result = await redis_connect.setex(
            key, expire_seconds, "valid"
        )  # 'valid' — метка валидности
        return bool(result)

    async def invalidate_token(self, token: str) -> bool:
        """
        Делает токен невалидным (удаляет из Redis).

        :param token: JWT-токен
        :return: True, если токен был удален
        """
        key = f"{self.jwt_prefix}{token}"
        redis_connect = await self.get_redis_connection()
        result = await redis_connect.delete(
            key
        )  # 1, если удален; 0, если не существовал
        return bool(result)

    async def get_all_tokens(self) -> List[str]:
        """
        Возвращает список всех JWT-токенов в Redis (без префикса).

        :return: Список токенов
        """
        redis_connect = await self.get_redis_connection()
        keys = await redis_connect.keys(f"{self.jwt_prefix}*")
        # Убираем префикс из ключей
        print([key[len(self.jwt_prefix) :] for key in keys])
        return [key[len(self.jwt_prefix) :] for key in keys]

    async def is_token_valid(self, token: str) -> bool:
        """
        Проверяет, валиден ли токен (есть в Redis).

        :param token: JWT-токен
        :return: True, если токен валиден
        """
        redis_connect = await self.get_redis_connection()
        key = f"{self.jwt_prefix}{token}"
        exists = await redis_connect.exists(key)
        print(exists == 1)
        return exists == 1

    # _________________________________________[CACHE REQUEST]_________________________________________

    async def get_all_requests(self) -> List[str]:
        """
        Возвращает список всех ключей запросов в Redis (без префикса).

        :return: Список токенов
        """
        redis_connect = await self.get_redis_connection()
        keys = await redis_connect.keys()
        # Убираем префикс из ключей
        print([key for key in keys])
        return [key for key in keys]

    async def add_request(
        self, cache_key: str, data: Any, expire_seconds: int = 6
    ) -> bool:
        """
        Добавляет запрос в Redis с TTL.

        :param cache_key: ключ
        :param data: информация для кэширования
        :param expire_seconds: Время жизни токена в секундах (по умолчанию 5 минут)
        """
        print("redis-request", cache_key, data)
        redis_connect = await self.get_redis_connection()
        result = await redis_connect.set(cache_key, json.dumps(data), ex=expire_seconds)
        return bool(result)

    async def get_request(self, cache_key: str):
        """
        Возвращает запрос

        :param cache_key: ключ
        """
        redis_connect = await self.get_redis_connection()
        cached_data = await redis_connect.get(cache_key)
        print(
            "redis-request",
            (
                json.loads(json.loads(json.dumps(cached_data)))
                if cached_data
                else "Данные отсутствуют"
            ),
        )
        if cached_data:
            # Исправленный код для корректной десериализации
            try:
                # Если данные уже являются строкой JSON
                if isinstance(cached_data, str):
                    return json.loads(cached_data)
                # Или используем двойную сериализацию/десериализацию
                return json.loads(json.loads(json.dumps(cached_data)))
            except (json.JSONDecodeError, TypeError):
                # В случае ошибки возвращаем как есть
                return cached_data
        return None

    async def delete_request(self, cache_key: str) -> bool:
        """
        Удаляет ключ
        """
        redis_connect = await self.get_redis_connection()
        result = await redis_connect.delete(cache_key)
        return bool(result)  # 1, если удален; 0, если не существовал
