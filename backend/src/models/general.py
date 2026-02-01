from enum import Enum
from typing import Any

from pydantic import BaseModel
from websockets import ClientConnection


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


class SystemStatRequest(BaseModel):
    cluster_id: int
    node_id: int
    object: ObjectStatEnum
    vm_name: str | None = None
