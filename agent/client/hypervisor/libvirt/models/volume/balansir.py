from pydantic import BaseModel, computed_field, model_validator

from agent.client.hypervisor.libvirt.models.volume.logic_volume import (
    LogicalVolumeSizeType,
)
from agent.client.hypervisor.libvirt.models.general import StoragePoolType


class ResourceReservationVM(BaseModel):
    cpu_core_count: int  # Сколько ядер установить в качестве резерва
    ram: int  # Какой объем RAM установить в качестве резерва(в байтах)
    storage: int  # Какой объем STORAGE установить в качестве резерва(в байтах)
    vm_uuid: str


class ResourcePoolVirtualCreate(BaseModel):
    name: str
    cpu_core_limit: int  # Сколько ядер установить в качестве лимита
    ram_limit: int  # Какой объем RAM установить в качестве лимита(в байтах)
    storage_limit: int  # Какой объем STORAGE установить в качестве лимита
    storage_type: StoragePoolType = (
        StoragePoolType.LOGICAL
    )  # Какой объем STORAGE установить в качестве лимита(в байтах)
    volume_size_type: LogicalVolumeSizeType = LogicalVolumeSizeType.GB
    vm_uuid_list: list[str] | None = None
    vm_reservation_list: list[ResourceReservationVM] | None = None

    @model_validator(mode="after")
    def validate_disk_type_constraints(cls, values):
        if values.storage_type != StoragePoolType.LOGICAL:
            raise ValueError("Отсутствует поддержка других типов хранилищ")

        return values


class ResourcePoolVirtualEdit(BaseModel):
    name: str
    cpu_core_limit: int | None = None  # Сколько ядер установить в качестве лимита
    ram_limit: int | None = (
        None  # Какой объем RAM установить в качестве лимита(в байтах)
    )
    vm_uuid_list: list[str] | str | None = None
    storage_limit: int | None = None  # Какой объем STORAGE установить в качестве лимита
    storage_type: StoragePoolType | None = (
        None  # Какой объем STORAGE установить в качестве лимита(в байтах)
    )
    volume_size_type: LogicalVolumeSizeType | None = None
    save_current_vms: bool = True  # Сохранять ли текущие ВМ ресурс пула
    vm_reservation_list: list[ResourceReservationVM] | None = None

    @model_validator(mode="after")
    def validate_disk_type_constraints(cls, values):
        if values.storage_limit is not None:
            if values.volume_size_type is None:
                raise ValueError(
                    "При указании storage_type нужно указать volume_size_type"
                )
            if values.storage_type is None:
                raise ValueError("При указании storage_type нужно указать storage_type")

        return values


class ResourcePoolVirtual(BaseModel):
    name: str
    cpu_core_limit: int  # Сколько ядер установлено в качестве лимита
    cpu_core_allocated: int  # Сколько ядер уже используется
    cpu_core_available: int  # Сколько ядер свободно для использования
    ram_limit: int  # Какой объем RAM установлено в качестве лимита(в байтах)
    ram_allocated: int  # Какой объем RAM уже используется(в байтах)
    ram_available: int  # Какой объем RAM свободен для использования(в байтах)
    storage_limit: int  # Какой объем STORAGE установлено в качестве лимита(в байтах)
    storage_allocated: int  # Какой объем STORAGE уже используется(в байтах)
    storage_available: int  # Какой объем STORAGE свободен для использования(в байтах)
    vm_uuid_list: list[str] | None = None  # Количество ВМ в ресурс пуле
    vm_reservation_list: list[ResourceReservationVM] | None = None
    storage_type: StoragePoolType
    group_volume: str | None = None
    logical_volume: str | None = None

    @model_validator(mode="after")
    def validate_disk_type_constraints(cls, values):
        if values.storage_type != StoragePoolType.LOGICAL:
            if values.group_volume or values.logical_volume:
                raise ValueError(
                    "Поля group_volume/logical_volume поддерживаются только логическими томами"
                )

        return values

    @computed_field
    @property
    def ram_limit_gb(self) -> float:
        return self.ram_limit / (1024**3)

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
