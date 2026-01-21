from pydantic import BaseModel, computed_field, model_validator

from agent.client.hypervisor.libvirt.models.volume.logic import (
    LogicalVolumeSizeType,
)
from agent.client.hypervisor.libvirt.models.general import StoragePoolType

PAGE_SIZE = 4096  # Система работает со страницами памяти, обычно по (4096 байт) на большинстве современных систем


class ResourceReservationVM(BaseModel):
    name: str
    cpu_core_count: int  # Сколько ядер установить в качестве резерва
    ram: int  # Какой объем RAM установить в качестве резерва(в байтах)
    storage: int  # Какой объем STORAGE установить в качестве резерва(в байтах)
    vm_pid: int


class ResourcePoolVirtualCreate(BaseModel):
    name: str
    cpu_core_limit: int  # Сколько ядер установить в качестве лимита
    ram_limit_gb: (
        int | float
    )  # Какой объем RAM установить в качестве лимита(в гигабайтах)
    ram_reservation_gb: int | float | None = (
        None  # Какой объем RAM установить в качестве лимита(в гигабайтах)
    )
    cpu_weight: int | None = None  # Веса процессорного времени
    storage_limit: int  # Какой объем STORAGE установить в качестве лимита, единица измерения в поле volume_size_type
    storage_type: StoragePoolType = (
        StoragePoolType.LOGICAL
    )  # Какой объем STORAGE установить в качестве лимита(в байтах)
    volume_size_type: LogicalVolumeSizeType = LogicalVolumeSizeType.GB
    vms: list[str] | None = None  # имена ВМ
    vm_reservation_list: list[ResourceReservationVM] | None = None

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        if self.storage_type != StoragePoolType.LOGICAL:
            raise ValueError("Отсутствует поддержка других типов хранилищ")

        if not self.name.startswith("resource_pool_"):
            raise ValueError("Имя ресурс пула должно начинаться с resource_pool_")

        return self

    @computed_field
    @property
    def ram_limit_bytes(self) -> int:
        bytes_value = int(self.ram_limit_gb * (1024**3))
        return (bytes_value // PAGE_SIZE) * PAGE_SIZE

    @computed_field
    @property
    def ram_reservation_bytes(self) -> int | None:
        if self.ram_reservation_gb is not None:
            return int(self.ram_reservation_gb * (1024**3))
        return None


class ResourcePoolVirtualEdit(BaseModel):
    name: str
    cpu_core_limit: int | None = None  # Сколько ядер установить в качестве лимита
    cpu_weight: int | None = None  # Веса процессорного времени
    ram_limit_gb: int | float | None = (
        None  # Какой объем RAM установить в качестве лимита(в гигабайтах)
    )
    vms: list[str] | str | None = None
    storage_limit: int | None = None  # Какой объем STORAGE установить в качестве лимита
    storage_type: StoragePoolType | None = (
        None  # Какой объем STORAGE установить в качестве лимита(в байтах)
    )
    volume_size_type: LogicalVolumeSizeType | None = None
    save_current_vms: bool = True  # Сохранять ли текущие ВМ ресурс пула
    vm_reservation_list: list[ResourceReservationVM] | None = None

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        if self.storage_limit is not None:
            if self.volume_size_type is None:
                raise ValueError(
                    "При указании storage_type нужно указать volume_size_type"
                )
            if self.storage_type is None:
                raise ValueError("При указании storage_type нужно указать storage_type")

        return self

    @computed_field
    @property
    def ram_limit_bytes(self) -> None | int:
        if self.ram_limit_gb:
            bytes_value = int(self.ram_limit_gb * (1024**3))
            return (bytes_value // PAGE_SIZE) * PAGE_SIZE
        return None


class ResourcePoolVirtual(BaseModel):
    name: str
    cpu_core_limit: int  # Сколько ядер установлено в качестве лимита
    cpu_core_allocated: int | float  # Сколько ядер уже используется
    cpu_core_available: int | float  # Сколько ядер свободно для использования
    cpu_weight: int  # Веса процессорного времени
    ram_limit_bytes: int  # Какой объем RAM установлено в качестве лимита(в байтах)
    ram_reservation_bytes: (
        int  # Какой объем RAM установлено в качестве резерва(в байтах)
    )
    ram_allocated: int | float  # Какой объем RAM уже используется(в байтах)
    ram_available: int | float  # Какой объем RAM свободен для использования(в байтах)
    storage_limit: int  # Какой объем STORAGE установлено в качестве лимита(в байтах)
    storage_allocated: int  # Какой объем STORAGE уже используется(в байтах)
    storage_available: int  # Какой объем STORAGE свободен для использования(в байтах)
    vms: list[str] | None = None  # Количество ВМ в ресурс пуле
    vm_reservation_list: list[ResourceReservationVM] | None = None
    storage_type: StoragePoolType
    group_volume: str | None = None
    logical_volume: str | None = None

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        if self.storage_type != StoragePoolType.LOGICAL:
            if self.group_volume or self.logical_volume:
                raise ValueError(
                    "Поля group_volume/logical_volume поддерживаются только логическими томами"
                )

        if self.cpu_core_limit == -1.0:
            # Валидно, означает "неограниченно"
            return self
        elif self.cpu_core_limit <= 0:
            raise ValueError("CPU limit must be positive or -1 for unlimited")

        if self.cpu_core_available == -1.0:
            # Валидно, означает "неограниченно"
            return self
        elif self.cpu_core_available <= 0:
            raise ValueError("CPU available must be positive or -1 for unlimited")

        if self.ram_limit_bytes == -1.0:
            # Валидно, означает "неограниченно"
            return self
        elif self.ram_limit_bytes <= 0:
            raise ValueError("RAM limit must be positive or -1 for unlimited")

        if self.ram_available == -1.0:
            # Валидно, означает "неограниченно"
            return self
        elif self.ram_available <= 0:
            raise ValueError("CPU available must be positive or -1 for unlimited")
        return self

    @computed_field
    @property
    def ram_limit_gb(self) -> float:
        return self.ram_limit_bytes / (1024**3)

    @computed_field
    @property
    def ram_allocated_gb(self) -> float:
        return self.ram_allocated / (1024**3)

    @computed_field
    @property
    def ram_available_gb(self) -> float:
        return self.ram_available / (1024**3)

    @computed_field
    @property
    def storage_limit_gb(self) -> float:
        return self.storage_limit / (1024**3)

    @computed_field
    @property
    def storage_allocated_gb(self) -> float:
        return self.storage_allocated / (1024**3)

    @computed_field
    @property
    def storage_available_gb(self) -> float:
        return self.storage_available / (1024**3)
