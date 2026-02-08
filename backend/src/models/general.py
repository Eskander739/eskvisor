import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskAction:
    # Общие манипуляции
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    DELETE_ALL = "delete_all"
    LIST = "list"
    INFO = "info"
    CLONE = "CLONE"
    DETACH = "detach"
    ATTACH = "attach"
    START = "start"
    SHUTOFF = "shutoff"
    RESTART = "restart"

    # Манипуляции для ВМ
    STATE = "state"
    SUSPEND = "suspend"
    RESUME = "resume"
    MIGRATE = "migrate"

    # Манипуляции для хранилищ
    VM_DISKS_INFO = "vm_disks_info"
    VM_DISKS_USED_INFO = "vm_disks_used_info"
    EXTEND = "EXTEND"

    # Манипуляции для снапшотов
    REVERT = "revert"

    # Манипуляции для виртуальных сетей
    BACKUP = "backup"
    VM_NETWORK_INFO = "vm_network_info"
    AUTOSTART = "autostart"

    # Манипуляции для ресурс пулов(Балансиръ)

    DELETE_VMS = "delete_vms"
    SYNC = "sync"

    # Манипуляции для задач
    VM_STATS = "vm_stats"
    MONITOR = "monitor"


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

    STARTING = "STARTING"  # Запуск
    RUNNING = "RUNNING"  # Работает
    BLOCKED = "BLOCKED"  # Заблокирована
    PAUSING = "PAUSING"  # Приостановка
    PAUSED = "PAUSED"  # Приостановлена
    RESUMING = "RESUMING"  # Возобновление
    REBOOT = "REBOOT"  # Перезагрузка
    SHUTDOWN = "SHUTDOWN"  # Завершается
    SHUTOFF = "SHUTOFF"  # Выключена
    CRASHED = "CRASHED"  # Аварийно завершена
    PMSUSPENDED = "PMSUSPENDED"  # Приостановлена (PM)
    CLONING = "CLONING"  # Клонируется
    DELETING = "DELETING"  # Удаление
    DELETED = "DELETED"  # Удален
    NOT_AVAILABLE = (
        "NOT_AVAILABLE"  # Не доступен(когда не найдена ВМ со стороны агента)
    )


class QemuNetdevType(str, Enum):
    USER = "user"
    TAP = "tap"
    BRIDGE = "bridge"
    SOCKET = "socket"


class MachineType(Enum):
    """Типы машин для эмуляции"""

    Q35 = "q35"  # Современный, поддерживает PCIe и hotplug
    PC_I440FX = "pc-i440fx"  # PC с i440FX чипсетом


class AgentResponse(BaseModel):
    ip_address: str
    username: str
    code: str


class TaskType(Enum):
    """Типы задач для диспетчеризации"""

    STORAGE = "storage"
    VM = "vm"
    NETWORK = "network"
    SNAPSHOT = "snapshot"
    RESOURCE_POOL = "resource_pool"
    STATS = "stats"


class CreateTask(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: TaskType = Field(..., description="Тип задачи для диспетчеризации")
    action: str = Field(..., description="Действие (create, delete, update, etc.)")
    params: str | None = Field(..., description="Данные задачи")
