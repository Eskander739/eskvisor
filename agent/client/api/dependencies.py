from dotenv import load_dotenv

from agent.client.constants import PROD_ENV
from agent.client.hypervisor.libvirt.managers.vm_stats import VMLiveMonitor
from agent.client.logger_config import DefaultLogger
from agent.client.task_manager.ctl_queue import RedisTaskManager
from agent.client.task_manager.dispatcher import TaskDispatcher
from agent.client.task_manager.ws_notification import WebSocketNotificationHandler
from agent.client.vnc.vnc_connection_manager import VNCConnectionManager

load_dotenv(PROD_ENV)


logger = DefaultLogger("TaskManagerServer")
queue_manager = RedisTaskManager()
task_dispatcher = TaskDispatcher(queue_manager)
ws_handler = WebSocketNotificationHandler(queue_manager)
vm_live_monitor = VMLiveMonitor
vnc_manager = VNCConnectionManager()



async def get_logger() -> DefaultLogger:
    return logger


async def get_queue_manager_service() -> RedisTaskManager:
    return queue_manager


async def get_task_dispatcher_service() -> TaskDispatcher:
    return task_dispatcher


async def get_ws_handler() -> WebSocketNotificationHandler:
    return ws_handler


async def get_vm_live_monitor_service() -> type[VMLiveMonitor]:
    return vm_live_monitor


async def get_vnc_manager() -> VNCConnectionManager:
    return vnc_manager
