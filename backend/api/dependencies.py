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
ssh_key_generator = SSHKeyGenerator()
agent_installer = AgentInstaller()
redis_service = RedisJWTManager()
jwt_service = JWTService()
hash_service = HashService()
users_db = UsersDB()
nodes_db = NodesDB()
clusters_db = ClustersDB()


async def get_redis_service() -> RedisJWTManager:
    return redis_service


async def get_jwt_service() -> JWTService:
    return jwt_service


async def get_hash_service() -> HashService:
    return hash_service


async def get_users_db() -> UsersDB:
    return users_db


async def get_nodes_db() -> NodesDB:
    return nodes_db


async def get_clusters_db() -> ClustersDB:
    return clusters_db


async def get_agent_installer() -> AgentInstaller:
    return agent_installer


async def get_logger() -> DefaultLogger:
    return logger


async def get_ssh_key_generator() -> SSHKeyGenerator:
    return ssh_key_generator
