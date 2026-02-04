from src.services.pool.db_pool import DBPool
from src.services.pool.redis_pool import RedisPoolManager
from src.services.pool.task_ws_pool import TaskWebsocketPool

# Глобальные экземпляры
websocket_pool_instance: TaskWebsocketPool | None = None
db_pool_instance: DBPool | None = None
redis_pool_instance: RedisPoolManager | None = None
