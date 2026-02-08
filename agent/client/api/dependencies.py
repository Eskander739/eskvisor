from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from dotenv import load_dotenv

from agent.client.cli import CLIControl
from agent.client.constants import PROD_ENV
from agent.client.hypervisor.libvirt.managers.vm import VmManager
from agent.client.hypervisor.libvirt.managers.vm_stats import VMLiveMonitor
from agent.client.logger_config import DefaultLogger
from agent.client.task_manager.ctl_queue import RedisTaskManager
from agent.client.task_manager.dispatcher import TaskDispatcher
from agent.client.task_manager.ws_notification import WebSocketNotificationHandler
from agent.client.vnc.vnc_connection_manager import VNCConnectionManager

load_dotenv()
load_dotenv(PROD_ENV)


logger = DefaultLogger("TaskManagerServer")


async def get_logger() -> DefaultLogger:
    return logger


async def get_queue_manager_service() -> RedisTaskManager:
    return RedisTaskManager()


async def get_cli_service() -> CLIControl:
    return CLIControl()


async def get_task_dispatcher_service() -> TaskDispatcher:
    return TaskDispatcher(RedisTaskManager())


@asynccontextmanager
async def get_vm_manager() -> AsyncGenerator[VmManager, Any]:
    vm_manager = VmManager()
    try:
        vm_manager.connect_all()
        yield vm_manager

    finally:
        vm_manager.conn.close()


# Создаем зависимость FastAPI
async def vm_manager_dependency() -> AsyncGenerator[VmManager, None]:
    async with get_vm_manager() as vm_manager:
        yield vm_manager


async def get_ws_handler() -> WebSocketNotificationHandler:
    return WebSocketNotificationHandler(RedisTaskManager())


async def get_vm_live_monitor_service() -> type[VMLiveMonitor]:
    return VMLiveMonitor


async def get_vnc_manager() -> VNCConnectionManager:
    return VNCConnectionManager()
