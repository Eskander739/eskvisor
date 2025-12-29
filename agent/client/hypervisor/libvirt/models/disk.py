from pathlib import Path

from pydantic import BaseModel, field_validator, Field

from agent.client.hypervisor.libvirt.models.enum import DiskBus, DiskType, DiskFormat, DiskDeviceType


class VMDisk(BaseModel):
    """Модель диска ВМ"""
    path: str | None = None
    size_gb: int | None = 1
    bus: DiskBus | str = DiskBus.VIRTIO
    device_type: DiskDeviceType | str = Field(default=DiskDeviceType.DISK, description="Тип устройства") # TODO: Добавить поддержку в методах
    disk_type: DiskType = DiskType.FILE
    format: DiskFormat | str = DiskFormat.QCOW2
    cache: str = "none"
    readonly: bool = False
    shareable: bool = False
    serial: str | None = None
    boot_order: int | None = None

    @field_validator('path')
    def validate_path(cls, v):
        """Валидация пути к диску"""
        path = Path(v)
        # Если это новый диск (есть size_gb), проверяем директорию
        # Если это существующий диск, проверяем наличие файла
        if path.exists():
            if not path.is_file():
                raise ValueError(f"Путь {v} существует, но не является файлом")
        return str(path)


    @field_validator("bus")
    def validate_bus(cls, v):
        DiskBus(v)
        return v


    @field_validator("format")
    def validate_format(cls, v):
        DiskFormat(v)
        return v