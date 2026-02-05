from dotenv import load_dotenv
from fastapi import Request

from src.services.hash import HashService
from src.agent_installer import AgentInstaller
from src.constants import PROD_ENV
from src.services.jwt import JWTService
from src.logger_config import DefaultLogger
from src.services.pool.task_ws_pool import TaskWebsocketPool
from src.services.ssh_keygen import SSHKeyGenerator

load_dotenv()
load_dotenv(PROD_ENV)
logger = DefaultLogger("Eskvisor Backend")


async def get_jwt_service() -> JWTService:
    logger.info("Вызов зависимости get_jwt_service")
    return JWTService()


async def get_hash_service() -> HashService:
    logger.info("Вызов зависимости get_hash_service")
    return HashService()


async def get_agent_installer() -> AgentInstaller:
    logger.info("Вызов зависимости get_agent_installer")
    return AgentInstaller()


async def get_logger() -> DefaultLogger:
    logger.info("Вызов зависимости get_logger")
    return logger


async def get_ws_task(request: Request) -> TaskWebsocketPool:
    logger.info("Вызов зависимости get_ws_task")
    return request.app.state.websocket_pool


async def get_ssh_key_generator() -> SSHKeyGenerator:
    logger.info("Вызов зависимости get_ssh_key_generator")
    return SSHKeyGenerator()
