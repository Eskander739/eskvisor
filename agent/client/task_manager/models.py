import datetime
import json
import uuid
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

    CREATED = "created"  # в ожидании
    PENDING = "pending"  # в ожидании
    PROCESSING = "processing"  # в процессе
    COMPLETED = "completed"  # выполнено
    FAILED = "failed"  # ошибка
    CANCELLED = "cancelled"  # отменено


class TaskAdd(BaseModel):
    """Модель задачи"""

    task_type: TaskType = Field(..., description="Тип задачи для диспетчеризации")
    action: str = Field(..., description="Действие (create, delete, update, etc.)")
    params: dict[str, Any] = Field(default_factory=dict, description="Данные задачи")
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)


class Task(TaskAdd):
    """Модель задачи"""

    request_id: str = Field(..., description="Идентификатор задачи")


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
    started_at: datetime.datetime
    completed_at: datetime.datetime


class WorkerModel(BaseModel):
    name: str
    alive: bool
    processing: bool
    current_task: str | None = None


class WorkerStats(BaseModel):
    total_workers: int = 0
    active_workers: int = 0
    workers: list[WorkerModel] = []


class TaskNotificationType(str, Enum):
    """Типы уведомлений о задачах"""

    STATUS_CHANGE = "status_change"
    RESULT_READY = "result_ready"
    ERROR_OCCURRED = "error_occurred"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"


class TaskNotification(BaseModel):
    """Модель уведомления о задаче"""

    notification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    notification_type: TaskNotificationType
    request_id: str
    task_type: TaskType
    status: TaskStatus
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)
    data: dict | None = Field(default=None, description="Дополнительные данные")
    error: str | None = Field(default=None, description="Сообщение об ошибке")


class TasksInfo(BaseModel):
    pending: list[Task] = []
    processing: list[Task] = []
    total_pending: int = 0
    total_processing: int = 0
