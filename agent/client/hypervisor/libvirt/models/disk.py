from pathlib import Path

from pydantic import BaseModel, field_validator

from agent.client.hypervisor.libvirt.models.enum import DiskBus, DiskType, DiskFormat


class VMDisk(BaseModel):
    """Модель диска ВМ"""
    path: str
    size_gb: int | None = None
    bus: DiskBus = DiskBus.VIRTIO
    disk_type: DiskType = DiskType.FILE
    format: DiskFormat = DiskFormat.QCOW2
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
