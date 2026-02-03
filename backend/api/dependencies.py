from dotenv import load_dotenv

from src.db.clusters import ClustersDB
from src.db.node import NodesDB
from src.services.hash import HashService
from src.agent_installer import AgentInstaller
from src.constants import PROD_ENV
from src.db.users import UsersDB
from src.services.jwt import JWTService
from src.logger_config import DefaultLogger
from src.services.redis_srv import RedisJWTManager
from src.services.ssh_keygen import SSHKeyGenerator

load_dotenv()
load_dotenv(PROD_ENV)
logger = DefaultLogger("Eskvisor Backend")


async def get_redis_service() -> RedisJWTManager:
    return RedisJWTManager()


async def get_jwt_service() -> JWTService:
    return JWTService()


async def get_hash_service() -> HashService:
    return HashService()


async def get_users_db() -> UsersDB:
    return UsersDB()


async def get_nodes_db() -> NodesDB:
    return NodesDB()


async def get_clusters_db() -> ClustersDB:
    return ClustersDB()


async def get_agent_installer() -> AgentInstaller:
    return AgentInstaller()


async def get_logger() -> DefaultLogger:
    return logger


async def get_ssh_key_generator() -> SSHKeyGenerator:
    return SSHKeyGenerator()
