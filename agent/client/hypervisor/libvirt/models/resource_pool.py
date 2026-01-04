from enum import Enum

from pydantic import BaseModel, Field


class ResourcePoolType(str, Enum):
    """Типы ресурсов в пуле"""
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"


class ResourcePoolCreateRequest(BaseModel):
    """Запрос на создание пула ресурсов"""
    name: str
    cpu_limit: int | None = Field(None, description="Лимит CPU (в ядрах)")
    memory_limit: int | None = Field(None, description="Лимит памяти (в МБ)")
    storage_limit: int | None = Field(None, description="Лимит хранилища (в ГБ)")
    storage_path: str | None = Field(None, description="Путь к хранилищу")
    storage_xml: str | None = Field(None, description="XML описание пула хранения")


class ResourcePoolEditRequest(BaseModel):
    """Запрос на редактирование пула ресурсов"""
    request_id: str
    name: str
    cpu_limit: int | None = Field(None, description="Новый лимит CPU (в ядрах)")
    memory_limit: int | None = Field(None, description="Новый лимит памяти (в МБ)")
    storage_limit: int | None = Field(None, description="Новый лимит хранилища (в ГБ)")
    storage_xml: str | None = Field(None, description="Новое XML описание пула хранения")


class ResourcePoolAdjustRequest(BaseModel):
    """Запрос на изменение ресурсов пула"""
    request_id: str
    name: str
    resource_type: ResourcePoolType
    value: int
    operation: str = Field(..., description="add или remove")


class ResourcePoolReservationRequest(BaseModel):
    """Запрос на установку резерва ресурсов"""
    request_id: str
    name: str
    cpu_reservation: int | None = Field(None, description="Гарантированный минимум CPU (в ядрах)")
    memory_reservation: int | None = Field(None, description="Гарантированный минимум памяти (в МБ)")


class ResourcePoolLimitRequest(BaseModel):
    """Запрос на установку лимита ресурсов"""
    request_id: str
    name: str
    cpu_limit: int | None = Field(None, description="Максимальный лимит CPU (в ядрах)")
    memory_limit: int | None = Field(None, description="Максимальный лимит памяти (в МБ)")
    storage_limit: int | None = Field(None, description="Максимальный лимит хранилища (в ГБ)")


class VMPoolAssignmentRequest(BaseModel):
    """Запрос на назначение/изъятие ВМ из пула"""
    request_id: str
    pool_name: str
    vm_name: str


class ResourcePoolDeleteRequest(BaseModel):
    """Запрос на удаление пула ресурсов"""
    request_id: str
    name: str
    force: bool = Field(False, description="Принудительное удаление даже если есть ВМ")


class ResourcePoolState(BaseModel):
    name: str
    state: str


class ResourceMetrics(BaseModel):
    limit: int | None = None
    usage: int | None = None
    available: int | None = None
    percent: int | None = None


class ResourcePoolUsageInfo(BaseModel):
    pool_name: str
    vms: list[dict[str, object]]
    vms_count: int = Field(ge=0)

    cpu: ResourceMetrics
    memory: ResourceMetrics
    storage: ResourceMetrics

    reservations: dict[str, object] = Field(default_factory=dict)
    limits: dict[str, object] = Field(default_factory=dict)
    storage_info: dict[str, object]


class ResourcePoolInfoRequest(BaseModel):
    """Запрос на получение информации о пуле"""
    request_id: str
    name: str


class ResourcePoolControlRequest(BaseModel):
    """Запрос на управление пулом (старт/стоп)"""
    request_id: str
    name: str

class AdjustResourcePool(BaseModel):
    name: str
    resource_type: str
    operation: str
    value: int
    new_limit: str


class DeleteResourcePool(BaseModel):
    name: str
    force: bool
    vms_count: int


class ResourcePoolUpdates(BaseModel):
    name: str
    limits: int | None = None
    updates: dict


class ResourcePoolReservation(BaseModel):
    name: str
    reservations: dict


class AddVMInResourcePool(BaseModel):
    name: str
    vm_name: str
    vm_cpu: int
    vm_memory: int
    total_vms: int
    resource_usage: int


class RemoveVMInResourcePool(BaseModel):
    name: str
    vm_name: str
    freed_cpu: int
    freed_memory: int
    total_vms: int
    resource_usage: int


class ResourcePool(BaseModel):
    name: str
    type: ResourcePoolType | None = None
    cpu_limit: int
    memory_limit: int
    storage_limit: int
    vms: list
    reservations: dict
    limits: dict


class ResourcePoolList(BaseModel):
    count: int
    items: list[ResourcePool]