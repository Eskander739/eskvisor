import random
from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    computed_field,
)


class DiskFormat(Enum):
    """
    Форматы виртуальных дисков
    """

    QCOW2 = "qcow2"  # QEMU Copy-On-Write v2
    RAW = "raw"  # Сырой образ
    UNKNOWN = "unknown"


def disk_format_by_path(disk_path: str) -> DiskFormat:
    if disk_path.endswith(".qcow2"):
        return DiskFormat.QCOW2
    elif disk_path.endswith(".raw") or disk_path.endswith(".img"):
        return DiskFormat.RAW
    return DiskFormat.UNKNOWN


# Enum для режимов кэширования
class CacheMode(Enum):
    WRITEBACK = "writeback"
    WRITETHROUGH = "writethrough"
    NONE = "none"
    DIRECTSYNC = "directsync"
    UNSAFE = "unsafe"


class DiskStatus(Enum):
    ATTACHED = "attached"
    DETACHED = "detached"
    ERROR = "error"
    PENDING = "pending"


class DiskType(Enum):
    POOL_DISK = "pool_disk"  # Диск находится в пуле хранилищ
    ORPHANED = "orphaned"  # Диск найден в ФС, но не в пуле и не подключен
    SNAPSHOT = "snapshot"  # Снапшот диска
    TEMPLATE = "template"  # Шаблонный/образцовый диск
    BACKUP = "backup"  # Резервная копия диска
    CACHE = "cache"  # Кэширующий/буферный диск
    SWAP = "swap"  # Диск подкачки
    CDROM = "cdrom"  # Виртуальный CD/DVD
    NETWORK = "network"  # Сетевой/удаленный диск
    EPHEMERAL = "ephemeral"  # Временный/эфемерный диск
    PERSISTENT = "persistent"  # Постоянное хранилище
    EXTERNAL_DISK = "external_disk"  # Внешний диск


class Disk(BaseModel):
    name: str
    file_path_exists: bool
    type: DiskType
    format: DiskFormat

    # Условно обязательные поля (инициализируются None)
    capacity_bytes: int | None = Field(
        default=None, description="Размер диска в байтах", ge=0
    )
    capacity_gb: float | None = Field(
        default=None, description="Размер диска в гигабайтах", ge=0.0
    )
    allocation_gb: float | None = Field(
        default=None, description="Фактически занято гигабайт", ge=0.0
    )
    pool: str | None = Field(default=None, description="Имя пула хранилищ")
    vm_name: str | None = Field(default=None, description="Имя виртуальной машины")
    status: DiskStatus | None = Field(default=None, description="Статус подключения")
    encrypted: bool | None = Field(default=None, description="Зашифрован ли диск")
    readonly: bool | None = Field(default=None, description="Только для чтения")
    created: datetime | None = Field(default=None, description="Дата создания")
    modified: datetime | None = Field(
        default=None, description="Дата последнего изменения"
    )
    description: str | None = Field(
        default=None, description="Описание диска", max_length=500
    )

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        """Проверка условно обязательных полей в зависимости от типа"""
        disk_type = self.type

        if self.status == DiskStatus.ATTACHED:
            if not self.vm_name:
                raise ValueError("Для типа vm_attached обязательно указать vm_name")
        if not self.status:
            self.status = DiskStatus.ATTACHED

        if disk_type == DiskType.POOL_DISK:
            if not self.pool:
                raise ValueError("Для типа pool_disk обязательно указать pool")

        if self.capacity_bytes:
            if self.capacity_gb is None:
                # Автоматически вычисляем GB из bytes
                self.capacity_gb = self.capacity_bytes / (1024**3)
            elif self.capacity_gb is not None:
                capacity_gb_to_bytes = int(self.capacity_gb * 1024 * 1024 * 1024)
                if capacity_gb_to_bytes != self.capacity_bytes:
                    raise ValueError("capacity_gb не соответствует capacity_bytes")
                # Проверяем согласованность

        return self

    # Методы
    def is_attached(self) -> bool:
        """Проверка, подключен ли диск к ВМ"""
        return self.status == DiskStatus.ATTACHED

    def is_in_pool(self) -> bool:
        """Проверка, находится ли диск в пуле"""
        return self.type == DiskType.POOL_DISK and self.pool is not None

    def supports_snapshots(self) -> bool:
        """Проверка поддержки снапшотов"""
        return self.format in {
            DiskFormat.QCOW2,
            DiskFormat.RAW,
        }

    @field_validator("format")
    def validate_format(cls, v):
        DiskFormat(v)
        return v


# Дополнительная модель для создания диска (без опциональных полей)
class DiskCreate(BaseModel):
    """
    Модель для создания нового диска
    """

    name: str = Field(
        default_factory=lambda: f"disk-{random.randint(100000, 999999)}",
        min_length=1,
        max_length=255,
    )
    size_gb: float = Field(default=1, gt=0, le=65536, description="Размер в GB")
    format: DiskFormat = Field(default=DiskFormat.QCOW2)
    description: str | None = Field(
        default=None, max_length=500, description="Описание диска"
    )
    sparse: bool = Field(default=True, description="Создать разреженный диск")
    cache: str = "none"
    readonly: bool = False
    resource_pool: str | None = None

    @computed_field
    @property
    def size_bytes(self) -> int:
        return int(self.size_gb * (1024**3))


# Модель для обновления диска
class DiskUpdate(BaseModel):
    """Модель для обновления диска"""

    new_size_gb: float | None = Field(
        None, gt=0, le=65536, description="Новый размер (только увеличение)"
    )


# Модель для подключения диска к ВМ
class DiskAttach(BaseModel):
    """Модель для подключения диска к виртуальной машине"""

    vm_name: str = Field(..., description="Имя виртуальной машины")
    name: str
    format: DiskFormat
    cache_mode: CacheMode = Field(default=CacheMode.WRITEBACK)


class DiskDetach(BaseModel):
    """Модель для отключения диска от виртуальной машины"""

    vm_name: str = Field(..., description="Имя виртуальной машины")
    name: str = Field(..., description="Имя диска")


class DiskQuery(BaseModel):
    """Модель для запроса списка дисков"""

    pool: str | None = Field(None, description="Фильтр по пулу")
    vm_name: str | None = Field(None, description="Фильтр по виртуальной машине")
    search_path: list[str] | str | None = Field(
        None, description="Фильтр по директориям"
    )
    format: DiskFormat | None = Field(None, description="Фильтр по формату")
    min_size_gb: float | None = Field(None, ge=0, description="Минимальный размер")
    max_size_gb: float | None = Field(None, ge=0, description="Максимальный размер")
    attached_only: bool | None = Field(None, description="Только подключенные диски")

    model_config = ConfigDict(validate_default=True)

    @model_validator(mode="after")
    def validate_query(self):
        """Валидация запроса"""
        if self.min_size_gb is not None and self.max_size_gb is not None:
            if self.min_size_gb > self.max_size_gb:
                raise ValueError("min_size_gb не может быть больше max_size_gb")
        return self


class SnapshotDiskInfo(BaseModel):
    name: str
    snapshot: str
