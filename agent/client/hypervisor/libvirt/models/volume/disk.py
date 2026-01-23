import random
from datetime import datetime
from enum import Enum
from typing import Self

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

    # Форматы QEMU/KVM
    QCOW2 = "qcow2"  # QEMU Copy-On-Write v2 (рекомендуемый)
    QCOW = "qcow"  # QEMU Copy-On-Write v1 (устаревший)
    RAW = "raw"  # Сырой образ (raw image)
    QED = "qed"  # QEMU Enhanced Disk (устаревший)
    ISO = "iso"  # Для образов
    IMG = "img"  # Для образов
    # Форматы VMware
    VMDK = "vmdk"  # VMware Virtual Machine Disk
    VDI = "vdi"  # VirtualBox Virtual Disk Image

    # Форматы Hyper-V
    VHD = "vhd"  # Microsoft Virtual Hard Disk (фиксированный)
    VHDX = "vhdx"  # Microsoft Virtual Hard Disk v2 (динамический)

    # Форматы Xen
    VHD_RAW = "vhd_raw"  # Xen VHD в raw формате

    # Форматы Parallels
    HDD = "hdd"  # Parallels Desktop Hard Disk

    # Контейнерные/архивные форматы
    TAR = "tar"  # Tar архив
    BOCHS = "bochs"  # Bochs disk image

    # Специальные форматы
    SHEEPDOG = "sheepdog"  # Sheepdog распределенное хранилище
    RBD = "rbd"  # Ceph RADOS Block Device
    ISCSI = "iscsi"  # iSCSI target
    GLUSTER = "gluster"  # GlusterFS
    HTTP = "http"  # HTTP/HTTPS образ
    HTTPS = "https"  # HTTPS образ

    # Форматы для импорта/экспорта
    VPC = "vpc"  # Microsoft Virtual PC
    VVFAT = "vvfat"  # Virtual VFAT

    # Форматы облачных провайдеров
    AMI = "ami"  # Amazon Machine Image
    VHD_AMI = "vhd-ami"  # Azure VHD
    QCOW2_OPENSTACK = "qcow2-openstack"  # OpenStack QCOW2

    # Неизвестный/неопределенный формат
    UNKNOWN = "unknown"


def disk_format_by_path(disk_path: str) -> DiskFormat:
    if disk_path.endswith(".qcow2"):
        return DiskFormat.QCOW2
    elif disk_path.endswith(".raw") or disk_path.endswith(".img"):
        return DiskFormat.RAW
    elif disk_path.endswith(".vmdk"):
        return DiskFormat.VMDK
    elif disk_path.endswith(".vdi"):
        return DiskFormat.VDI
    elif disk_path.endswith(".vhd") or disk_path.endswith(".vhdx"):
        return DiskFormat.VHDX
    elif disk_path.endswith(".iso"):
        return DiskFormat.ISO
    elif disk_path.endswith(".img"):
        return DiskFormat.IMG
    return DiskFormat.UNKNOWN


# Enum для типов шин
class BusType(Enum):
    VIRTIO = "virtio"
    IDE = "ide"
    SCSI = "scsi"
    USB = "usb"
    SATA = "sata"
    SD = "sd"
    XEN = "xen"
    NVME = "nvme"


# Enum для режимов кэширования
class CacheMode(Enum):
    WRITEBACK = "writeback"
    WRITETHROUGH = "writethrough"
    NONE = "none"
    DIRECTSYNC = "directsync"
    UNSAFE = "unsafe"


# Enum для режимов ввода-вывода
class IoMode(Enum):
    NATIVE = "native"
    THREADS = "threads"


# Enum для поддержки discard
class DiscardMode(Enum):
    UNMAP = "unmap"
    IGNORE = "ignore"


# Enum для обнаружения нулей
class DetectZeroesMode(Enum):
    ON = "on"
    OFF = "off"
    UNMAP = "unmap"


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
    path: str
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
    allocation_bytes: int | None = Field(
        default=None, description="Фактически занято байт", ge=0
    )
    allocation_gb: float | None = Field(
        default=None, description="Фактически занято гигабайт", ge=0.0
    )
    pool: str | None = Field(default=None, description="Имя пула хранилищ")
    vm_name: str | None = Field(default=None, description="Имя виртуальной машины")
    status: DiskStatus | None = Field(default=None, description="Статус подключения")

    # Опциональные поля
    uuid: str | None = Field(
        default=None,
        description="UUID диска",
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    )
    backing_file: str | None = Field(
        default=None, description="Базовый образ (для QCOW2)"
    )
    encrypted: bool | None = Field(default=None, description="Зашифрован ли диск")
    readonly: bool | None = Field(default=None, description="Только для чтения")
    created: datetime | None = Field(default=None, description="Дата создания")
    modified: datetime | None = Field(
        default=None, description="Дата последнего изменения"
    )
    description: str | None = Field(
        default=None, description="Описание диска", max_length=500
    )
    owner: str | None = Field(default=None, description="Владелец диска")
    permissions: str | None = Field(
        default=None,
        description="Права доступа в восьмеричном формате",
        pattern=r"^0[0-7]{3}$",
    )
    cluster_size: int | None = Field(
        default=None, description="Размер кластера в байтах", ge=512
    )
    compat: str | None = Field(default=None, description="Версия совместимости")
    lazy_refcounts: bool | None = Field(
        default=None, description="Ленивые счетчики ссылок"
    )
    refcount_bits: int | None = Field(
        default=None, description="Бит счетчика ссылок", ge=1, le=64
    )
    snapshot_count: int | None = Field(
        default=None, description="Количество снапшотов", ge=0
    )
    virtual_size: int | None = Field(
        default=None, description="Виртуальный размер в байтах", ge=0
    )
    disk_size: int | None = Field(
        default=None, description="Размер на диске в байтах", ge=0
    )
    bus_type: BusType | None = Field(default=None, description="Тип шины подключения")
    target_dev: str | None = Field(
        default=None, description="Устройство в виртуальной машине"
    )
    cache_mode: CacheMode | None = Field(default=None, description="Режим кэширования")
    io_mode: IoMode | None = Field(default=None, description="Режим ввода-вывода")
    discard: DiscardMode | None = Field(default=None, description="Поддержка discard")
    detect_zeroes: DetectZeroesMode | None = Field(
        default=None, description="Обнаружение нулей"
    )
    shareable: bool = False  # TODO: Не реализовано
    serial: str | None = None

    @field_validator("allocation_gb")
    def validate_allocation_gb(cls, v, values):
        """Автоматически вычислять allocation_gb если указан allocation_bytes"""
        if values.data.get("allocation_bytes"):
            allocation_bytes = values.data.get("allocation_bytes")
            if v is None:
                return round(allocation_bytes / (1024**3), 2)
            elif abs(v * (1024**3) - allocation_bytes) > 1024:
                raise ValueError("allocation_gb не соответствует allocation_bytes")
        return v

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

    @field_validator("target_dev")
    def validate_target_dev_format(cls, v):
        """Валидация формата целевого устройства"""

        return v

    # Методы
    def is_attached(self) -> bool:
        """Проверка, подключен ли диск к ВМ"""
        return self.status == DiskStatus.ATTACHED

    def is_in_pool(self) -> bool:
        """Проверка, находится ли диск в пуле"""
        return self.type == DiskType.POOL_DISK and self.pool is not None

    def get_effective_size_gb(self) -> float:
        """Получить размер в GB (вычисляет если не указан)"""
        if self.capacity_gb is not None:
            return self.capacity_gb
        elif self.capacity_bytes is not None:
            return round(self.capacity_bytes / (1024**3), 2)
        return 0.0

    def get_allocation_percentage(self) -> float:
        """Получить процент использования диска"""
        if self.capacity_bytes and self.allocation_bytes:
            if self.capacity_bytes > 0:
                return round((self.allocation_bytes / self.capacity_bytes) * 100, 1)
        return 0.0

    def supports_snapshots(self) -> bool:
        """Проверка поддержки снапшотов"""
        return self.format in {
            DiskFormat.QCOW2,
            DiskFormat.QCOW,
            DiskFormat.VHDX,
            DiskFormat.VDI,
        }

    def is_sparse(self) -> bool:
        """Проверка, является ли диск разреженным"""
        if self.allocation_bytes and self.capacity_bytes:
            return self.allocation_bytes < self.capacity_bytes
        return False

    @field_validator("bus_type")
    def validate_bus(cls, v):
        BusType(v)
        return v

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
    path: str | None = None
    size_gb: float = Field(default=1, gt=0, le=65536, description="Размер в GB")
    format: DiskFormat = Field(default=DiskFormat.QCOW2)
    description: str | None = Field(
        default=None, max_length=500, description="Описание диска"
    )
    sparse: bool = Field(
        default=True, description="Создать разреженный диск"
    )  # Если False = занимает сразу все указанное место
    disk_type: DiskType = DiskType.EXTERNAL_DISK
    bus_type: BusType | None = Field(default=None, description="Тип шины подключения")
    cache: str = "none"
    readonly: bool = False
    shareable: bool = False
    serial: str | None = None
    resource_pool: str | None = None
    # RAW с sparse=True - должен создавать разреженный файл (sparse file)
    # RAW с sparse=False - должен создавать полный файл, заполненный нулями

    @computed_field
    @property
    def size_bytes(self) -> int:
        return int(self.size_gb * (1024**3))


# Модель для обновления диска
class DiskUpdate(BaseModel):
    """Модель для обновления диска"""

    # name: str | None = Field(None, min_length=1, max_length=255)
    # description: str | None = Field(None, max_length=500)
    new_size_gb: float | None = Field(
        None, gt=0, le=65536, description="Новый размер (только увеличение)"
    )


# Модель для подключения диска к ВМ
class DiskAttach(BaseModel):
    """Модель для подключения диска к виртуальной машине"""

    vm_name: str = Field(..., description="Имя виртуальной машины")
    path: str
    name: str
    format: DiskFormat
    disk_type: DiskType = DiskType.EXTERNAL_DISK
    target_dev: str = Field(default="vdb")
    bus_type: BusType = Field(default=BusType.VIRTIO)
    cache_mode: CacheMode = Field(default=CacheMode.WRITEBACK)


class DiskDetach(BaseModel):
    """Модель для отключения диска от виртуальной машины"""

    vm_name: str = Field(..., description="Имя виртуальной машины")
    target_dev: str = Field(..., description="Устройство для отключения")

    model_config = ConfigDict(validate_default=True)


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
    def validate_query(self) -> Self:
        """Валидация запроса"""
        if self.min_size_gb is not None and self.max_size_gb is not None:
            if self.min_size_gb > self.max_size_gb:
                raise ValueError("min_size_gb не может быть больше max_size_gb")
        return self


class SnapshotDiskInfo(BaseModel):
    name: str
    snapshot: str
