from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.enum import BusType, DiskType

iso_disk = VMDisk(
    path="/var/lib/libvirt/images/ubuntu-22.04.iso",
    disk_type=DiskType.CDROM,
    bus=BusType.IDE,
    readonly=True,  # ISO всегда только для чтения
)

# Или более простой вариант - только путь, остальное определится автоматически
simple_iso_disk = VMDisk(
    path="/var/lib/libvirt/images/windows.iso",
)

# Пример для обычного диска
os_disk = VMDisk(
    path="/var/lib/libvirt/images/vm-os.qcow2",
    disk_type=DiskType.DISK,
    bus=BusType.VIRTIO,
    readonly=False,
)

# Пример с использованием автовалидации
auto_disk = VMDisk(
    path="/path/to/install.iso",  # Автоматически станет CDROM
)