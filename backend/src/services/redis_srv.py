import json
import os
from typing import List, Any
import asyncio
import redis.asyncio as redis


class RedisJWTManager:
    """
    Класс для управления JWT-токенами в Redis.
    Поддерживает добавление, инвалидацию и получение токенов.
    """

    def __init__(
            self,
            jwt_prefix: str = "jwt_",
            tech_works_key: str = "tech_works_status",
    ):
        """
        Инициализация подключения к Redis.

        :param jwt_prefix: Префикс для ключей токенов в Redis
        :param tech_works_key: Ключ для хранения статуса технических работ
        """
        self.host = os.environ.get("REDIS_HOST")
        self.port = os.environ.get("REDIS_PORT")
        self.db = os.environ.get("REDIS_DB_NUMBER")
        self.db_for_requests = os.environ.get("REDIS_CACHE_REQUESTS_DB_NUMBER")
        # self.password = os.environ.get("REDIS_DB_PASSWORD")
        self.jwt_prefix = jwt_prefix
        self.tech_works_key = tech_works_key
        self._connections = {}

    async def check_connection(self, db: int | None = None) -> bool:
        try:
            redis_connect = self.get_redis_connection(db)

            # Простой ping
            pong = await redis_connect.ping()
            if pong:
                return True
            else:
                return False

        except Exception:
            return False

    def get_redis_connection(self, db: int | None = None):
        """Создает или возвращает существующее подключение к Redis"""
        if isinstance(db, str):
            db = int(db)
        db_key = db if db is not None else self.db

        if db_key not in self._connections:
            self._connections[db_key] = redis.Redis(
                host=self.host,
                port=int(self.port),
                db=db_key,
                # password=self.password,
                decode_responses=True,  # Автоматическое декодирование в строки
            )
        return self._connections[db_key]

    async def close_connections(self):
        """Закрывает все соединения с Redis"""
        for conn in self._connections.values():
            await conn.aclose()
        self._connections.clear()

    # _________________________________________[JWT METHODS]_________________________________________

    async def add_token(self, token: str, expire_seconds: int = 86400 * 7) -> bool:
        """
        Добавляет JWT-токен в Redis с TTL.

        :param token: JWT-токен
        :param expire_seconds: Время жизни токена в секундах (по умолчанию 24 часа * 7)
        :return: True, если токен успешно добавлен
        """
        key = f"{self.jwt_prefix}{token}"
        redis_connect = self.get_redis_connection()
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
        redis_connect = self.get_redis_connection()
        result = await redis_connect.delete(key)  # 1, если удален; 0, если не существовал
        return bool(result)

    async def get_all_tokens(self) -> List[str]:
        """
        Возвращает список всех JWT-токенов в Redis (без префикса).

        :return: Список токенов
        """
        redis_connect = self.get_redis_connection()
        keys = await redis_connect.keys(f"{self.jwt_prefix}*")
        # Убираем префикс из ключей
        print([key[len(self.jwt_prefix):] for key in keys])
        return [key[len(self.jwt_prefix):] for key in keys]

    async def is_token_valid(self, token: str) -> bool:
        """
        Проверяет, валиден ли токен (есть в Redis).

        :param token: JWT-токен
        :return: True, если токен валиден
        """
        redis_connect = self.get_redis_connection()
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
        redis_connect = self.get_redis_connection(self.db_for_requests)
        keys = await redis_connect.keys()
        # Убираем префикс из ключей
        print([key for key in keys])
        return [key for key in keys]

    async def add_request(self, cache_key: str, data: Any, expire_seconds: int = 6) -> bool:
        """
        Добавляет запрос в Redis с TTL.

        :param cache_key: ключ
        :param data: информация для кэширования
        :param expire_seconds: Время жизни токена в секундах (по умолчанию 5 минут)
        """
        print("redis-request", cache_key, data)
        redis_connect = self.get_redis_connection(self.db_for_requests)
        result = await redis_connect.set(cache_key, json.dumps(data), ex=expire_seconds)
        return bool(result)

    async def get_request(self, cache_key: str):
        """
        Возвращает запрос

        :param cache_key: ключ
        """
        redis_connect = self.get_redis_connection(self.db_for_requests)
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
        redis_connect = self.get_redis_connection(self.db_for_requests)
        result = await redis_connect.delete(cache_key)
        return bool(result)  # 1, если удален; 0, если не существовал


# Пример использования новых методов
async def main():
    jwt_manager = RedisJWTManager()
    # Пример использования асинхронных методов
    await jwt_manager.add_token("test_token_123", expire_seconds=3600)
    is_valid = await jwt_manager.is_token_valid("test_token_123")
    print(f"Token is valid: {is_valid}")
    await jwt_manager.close_connections()


if __name__ == "__main__":
    asyncio.run(main())