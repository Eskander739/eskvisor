from enum import Enum
from typing import Any

from pydantic import BaseModel


class ObjectStatEnum(Enum):
    system = "system"
    vm = "vm"


class HealthInfo(BaseModel):
    postgres_db: bool
    redis: bool


class NodeWebsocketConnection(BaseModel):
    cluster_id: int
    node_id: int
    connection: Any  # Websocket соединение


class NodeWebsocketConnections(BaseModel):
    cluster_id: int
    node_id: int
    connections_queue: Any  # Websocket соединение
    ip_address: str


class SystemStatRequest(BaseModel):
    cluster_id: int
    node_id: int
    object: ObjectStatEnum
    vm_name: str | None = None


class VMState(Enum):
    """Состояния виртуальной машины"""

    NOSTATE = 0  # Нет состояния
    RUNNING = 1  # Работает
    BLOCKED = 2  # Заблокирована
    PAUSED = 3  # Приостановлена
    SHUTDOWN = 4  # Завершается
    SHUTOFF = 5  # Выключена
    CRASHED = 6  # Аварийно завершена
    PMSUSPENDED = 7  # Приостановлена (PM)


class QemuNetdevType(str, Enum):
    USER = "user"
    TAP = "tap"
    BRIDGE = "bridge"
    SOCKET = "socket"


class MachineType(Enum):
    """Типы машин для эмуляции"""

    Q35 = "q35"  # Современный, поддерживает PCIe и hotplug
    PC_I440FX = "pc-i440fx"  # PC с i440FX чипсетом


class InstallAgentResponse(BaseModel):
    ip_address: str
    username: str
    code: str
