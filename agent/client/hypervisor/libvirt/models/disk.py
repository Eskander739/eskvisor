from pathlib import Path

from pydantic import BaseModel, field_validator

from agent.client.hypervisor.libvirt.models.disk_storage_manager import BusType
from agent.client.hypervisor.libvirt.models.enum import DiskType, DiskFormat


class VMDisk(BaseModel):
    """Модель диска ВМ"""
    path: str | None = None
    size_gb: int | None = 1
    bus: BusType | str = BusType.VIRTIO
    disk_type: DiskType | str = DiskType.FILE
    format: DiskFormat | str = DiskFormat.ISO
    cache: str = "none"
    readonly: bool = False
    shareable: bool = False
    serial: str | None = None

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
        BusType(v)
        return v


    @field_validator("format")
    def validate_format(cls, v):
        DiskFormat(v)
        return v