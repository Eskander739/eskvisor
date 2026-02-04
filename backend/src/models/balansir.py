from pydantic import BaseModel, computed_field, model_validator, Field

from agent.client.hypervisor.libvirt.models.volume.logic import (
    LogicalVolumeSizeType,
)
from agent.client.hypervisor.libvirt.models.general import StoragePoolType


class ResourceReservationVM(BaseModel):
    name: str
    cpu_core_count: int  # Сколько ядер установить в качестве резерва
    ram: int  # Какой объем RAM установить в качестве резерва(в байтах)
    storage: int  # Какой объем STORAGE установить в качестве резерва(в байтах)
    vm_pid: int


class ResourcePoolVirtualCreate(BaseModel):
    name: str
    cpu_core_limit: int = Field(
        default=None, description="Сколько ядер установить в качестве лимита"
    )
    ram_limit_gb: int | float = Field(
        default=None, description="Какой объем RAM установить в качестве лимита"
    )
    ram_reservation_gb: int | float | None = Field(
        default=None, description="Какой объем RAM установить в качестве резерва"
    )
    cpu_weight: int | None = Field(
        default=None, description="Веса процессорного времени"
    )
    storage_limit: int = Field(
        ..., description="Какой объем STORAGE установить в качестве лимита"
    )
    volume_size_type: LogicalVolumeSizeType = Field(
        default=LogicalVolumeSizeType.GB,
        description="Единица измерения устанавливаемого значения в хранилище",
    )
    storage_type: StoragePoolType = Field(
        default=StoragePoolType.LOGICAL, description="Тип хранилища ресурс пула"
    )
    vms: list[str] | None = Field(
        default=None,
        description="Имена виртуальных машин добавляемых в ресурс пул при создании",
    )
    vm_reservation_list: list[ResourceReservationVM] | None = Field(
        default=None, description="Установка резервов для ВМ"
    )

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        if self.storage_type != StoragePoolType.LOGICAL:
            raise ValueError("Отсутствует поддержка других типов хранилищ")

        return self


class ResourcePoolVirtualEdit(BaseModel):
    name: str
    cpu_core_limit: int | None = Field(
        default=None, description="Сколько ядер установить в качестве лимита"
    )
    cpu_weight: int | None = Field(
        default=None, description="Веса процессорного времени"
    )
    ram_limit_gb: int | float | None = Field(
        default=None, description="Какой объем RAM установить в качестве лимита"
    )
    vms: list[str] | str | None = Field(
        default=None,
        description="Имена виртуальных машин добавляемых в ресурс пул при создании",
    )
    storage_limit: int | None = Field(
        default=None, description="Какой объем STORAGE установить в качестве лимита"
    )
    volume_size_type: LogicalVolumeSizeType | None = Field(
        default=None,
        description="Единица измерения устанавливаемого значения в хранилище",
    )

    # storage_type: StoragePoolType | None = (
    #     None  # Какой объем STORAGE установить в качестве лимита(в байтах)
    # )
    save_current_vms: bool = Field(
        default=True,
        description="Сохранять ли текущие ВМ ресурс пула(если False, текущий список будет заменен списком ВМ в vms)",
    )
    vm_reservation_list: list[ResourceReservationVM] | None = Field(
        default=None, description="Установка резервов для ВМ"
    )

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


class ResourcePoolVirtual(BaseModel):
    id: int
    cluster_id: int
    node_id: int
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


class ResourcePoolVMS(BaseModel):
    name: str
    connected_vms: list[str]


class ResourcePoolConnectedVMS(BaseModel):
    resource_pools: list[ResourcePoolVMS] = []
