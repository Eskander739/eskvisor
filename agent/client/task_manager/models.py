import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Типы задач для диспетчеризации"""
    STORAGE = "storage"
    VM = "vm"
    NETWORK = "network"
    SNAPSHOT = "snapshot"
    RESOURCE_POOL = "resource_pool"
    STATS = "stats"


class TaskStatus(str, Enum):
    """Статусы выполнения задач"""
    CREATED = "created" # в ожидании
    PENDING = "pending" # в ожидании
    PROCESSING = "processing" # в процессе
    COMPLETED = "completed" # выполнено
    FAILED = "failed" # ошибка
    CANCELLED = "cancelled" # отменено


class Task(BaseModel):
    """Модель задачи"""
    task_type: TaskType = Field(..., description="Тип задачи для диспетчеризации")
    action: str = Field(..., description="Действие (create, delete, update, etc.)")
    params: dict[str, Any] = Field(default_factory=dict, description="Данные задачи")
    created_at: datetime.datetime  = Field(default_factory=datetime.datetime.now)

class TaskInfo(BaseModel):
    status: TaskStatus
    result: str | None = None
    error: bool = False


class TaskResponse(BaseModel):
    """Модель ответа задачи"""

    request_id: str
    task: Task
    status: TaskStatus
    result: dict | None = None
    error: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
