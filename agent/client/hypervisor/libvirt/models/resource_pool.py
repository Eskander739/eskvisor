from enum import Enum

from pydantic import BaseModel, Field, computed_field


class ResourcePoolType(str, Enum):
    """Типы ресурсов в пуле"""
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"


class StoragePoolType(str, Enum):
    """Типы пулов хранения в libvirt"""

    DIR = "dir"  # Директория в файловой системе
    FS = "fs"  # Предварительно отформатированный раздел файловой системы
    LOGICAL = "logical"  # Группа LVM логических томов
    DISK = "disk"  # Физический диск или раздел
    ISCSI = "iscsi"  # iSCSI целевое устройство
    SCSI = "scsi"  # SCSI устройства
    MPATH = "mpath"  # Multipath устройства
    RBD = "rbd"  # RADOS Block Device (Ceph)
    SHEEPDOG = "sheepdog"  # Sheepdog распределенное хранилище
    GLUSTER = "gluster"  # GlusterFS том
    ZFS = "zfs"  # ZFS пул
    VSTORAGE = "vstorage"  # Virtuozzo Storage
    NETFS = "netfs"  # Сетевая файловая система (NFS)
    VXHS = "vxhs"  # Veritas HyperScale Storage
    ISCSI_DIRECT = "iscsi-direct"  # Прямой доступ к iSCSI
    UNKNOWN = "unknown"

POOL_TYPE_DESCRIPTIONS = {
    StoragePoolType.DIR: "Директория в локальной файловой системе",
    StoragePoolType.FS: "Форматированный раздел файловой системы",
    StoragePoolType.LOGICAL: "Группа LVM логических томов",
    StoragePoolType.DISK: "Физический диск или раздел",
    StoragePoolType.ISCSI: "iSCSI целевое устройство по сети",
    StoragePoolType.SCSI: "SCSI устройства",
    StoragePoolType.MPATH: "Устройства с multipath",
    StoragePoolType.RBD: "RADOS Block Device (Ceph)",
    StoragePoolType.SHEEPDOG: "Sheepdog распределенное хранилище",
    StoragePoolType.GLUSTER: "GlusterFS сетевой том",
    StoragePoolType.ZFS: "ZFS пул",
    StoragePoolType.VSTORAGE: "Virtuozzo Storage",
    StoragePoolType.NETFS: "Сетевая файловая система (NFS)",
    StoragePoolType.VXHS: "Veritas HyperScale Storage",
    StoragePoolType.ISCSI_DIRECT: "Прямой доступ к iSCSI",
}

POOL_STATE = {0: "inactive", 1: "building", 2: "running", 3: "degraded"}

class PoolState(Enum):
    INACTIVE = "inactive"
    BUILDING = "building"
    RUNNING = "running"
    DEGRADED = "degraded"


class ResourcePoolCreateRequest(BaseModel):
    """Запрос на создание пула ресурсов"""
    name: str
    cpu_limit: int | None = Field(None, description="Лимит CPU (в ядрах)")
    memory_limit: int | None = Field(None, description="Лимит памяти (в МБ)")
    storage_limit: int | None = Field(None, description="Лимит хранилища (в ГБ)")
    storage_path: str | None = Field(None, description="Путь к хранилищу")
    storage_xml: str | None = Field(None, description="XML описание пула хранения")
    pool_type: StoragePoolType = StoragePoolType.DIR

    @computed_field
    @property
    def storage_limit_bytes(self) -> int | None:
        """Лимит хранилища в байтах"""
        if self.storage_limit is None:
            return None
        return int(self.storage_limit * 1024 * 1024 * 1024)  # ГБ -> байты


    class Config:
        use_enum_values = True  # Для сериализации Enum в их значения


class ResourcePoolEditRequest(BaseModel):
    """Запрос на редактирование пула ресурсов"""
    request_id: str
    name: str
    cpu_limit: int | None = Field(None, description="Новый лимит CPU (в ядрах)")
    memory_limit: int | None = Field(None, description="Новый лимит памяти (в МБ)")
    storage_limit: int | None = Field(None, description="Новый лимит хранилища (в ГБ)")
    storage_xml: str | None = Field(None, description="Новое XML описание пула хранения")


    @computed_field
    @property
    def storage_limit_bytes(self) -> int | None:
        """Лимит хранилища в байтах"""
        if self.storage_limit is None:
            return None
        return int(self.storage_limit * 1024 * 1024 * 1024)  # ГБ -> байты


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


class ResourcePoolState(BaseModel):
    name: str
    state: str


class ResourceMetrics(BaseModel):
    limit: int | None = None
    usage: int | None = None
    available: int | None = None
    percent: int | None = None

class UsageInfo(BaseModel):
    cpu: int
    memory: int
    storage: int


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
    state: PoolState

    # Основные метрики в байтах (сырые данные из libvirt)
    capacity_bytes: int = Field(..., description="Общая емкость в байтах")
    allocation_bytes: int = Field(..., description="Использованное пространство в байтах")
    available_bytes: int = Field(..., description="Доступное пространство в байтах")

    autostart: bool
    is_active: bool
    type: StoragePoolType

    # Лимиты ресурсов (в соответствующих единицах)
    cpu_limit: int | None = Field(None, description="Лимит CPU в ядрах")
    memory_limit: float | None = Field(None, description="Лимит памяти в гигабайтах")

    vms: list[str] = Field(default_factory=list)
    reservations: dict | None = None
    usage: UsageInfo | None = None

    # ========== ВЫЧИСЛЯЕМЫЕ ПОЛЯ для удобства ==========

    @computed_field
    @property
    def memory_limit_gb(self) -> float:
        """Общая емкость в гигабайтах"""
        return self.memory_limit / (1024 ** 3)

    @computed_field
    @property
    def capacity_gb(self) -> float:
        """Общая емкость в гигабайтах"""
        return self.capacity_bytes / (1024 ** 3)

    @computed_field
    @property
    def allocation_gb(self) -> float:
        """Использованное пространство в гигабайтах"""
        return self.allocation_bytes / (1024 ** 3)

    @computed_field
    @property
    def available_gb(self) -> float:
        """Доступное пространство в гигабайтах"""
        return self.available_bytes / (1024 ** 3)

    @computed_field
    @property
    def usage_percent(self) -> float:
        """Процент использования хранилища"""
        if self.capacity_bytes == 0:
            return 0.0
        return (self.allocation_bytes / self.capacity_bytes) * 100

    @computed_field
    @property
    def free_percent(self) -> float:
        """Процент свободного места"""
        if self.capacity_bytes == 0:
            return 0.0
        return (self.available_bytes / self.capacity_bytes) * 100

    @computed_field
    @property
    def capacity_tb(self) -> float:
        """Общая емкость в терабайтах"""
        return self.capacity_bytes / (1024 ** 4)

    @computed_field
    @property
    def allocation_tb(self) -> float:
        """Использованное пространство в терабайтах"""
        return self.allocation_bytes / (1024 ** 4)

    @computed_field
    @property
    def available_tb(self) -> float:
        """Доступное пространство в терабайтах"""
        return self.available_bytes / (1024 ** 4)

    # ========== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ==========

    def get_human_readable_size(self, size_bytes: int) -> str:
        """Конвертирует размер в байтах в человекочитаемый формат"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    @property
    def capacity_human(self) -> str:
        """Общая емкость в человекочитаемом формате"""
        return self.get_human_readable_size(self.capacity_bytes)

    @property
    def allocation_human(self) -> str:
        """Использованное пространство в человекочитаемом формате"""
        return self.get_human_readable_size(self.allocation_bytes)

    @property
    def available_human(self) -> str:
        """Доступное пространство в человекочитаемом формате"""
        return self.get_human_readable_size(self.available_bytes)

    @property
    def summary(self) -> dict[str, str]:
        """Краткая сводка информации о пуле"""
        return {
            "name": self.name,
            "state": self.state.value,
            "capacity": self.capacity_human,
            "used": self.allocation_human,
            "available": self.available_human,
            "usage_percent": f"{self.usage_percent:.1f}%",
            "type": self.type.value if self.type else "unknown",
            "vms_count": len(self.vms)
        }


class ResourcePoolList(BaseModel):
    count: int
    items: list[ResourcePool]