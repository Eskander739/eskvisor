from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.enum import DiskDeviceType, DiskBus

iso_disk = VMDisk(
    path="/var/lib/libvirt/images/ubuntu-22.04.iso",
    device_type=DiskDeviceType.CDROM,
    bus=DiskBus.IDE,
    boot_order=1,  # Первое устройство для загрузки
    readonly=True,  # ISO всегда только для чтения
)

# Или более простой вариант - только путь, остальное определится автоматически
simple_iso_disk = VMDisk(
    path="/var/lib/libvirt/images/windows.iso",
    boot_order=1,
)

# Пример для обычного диска
os_disk = VMDisk(
    path="/var/lib/libvirt/images/vm-os.qcow2",
    device_type=DiskDeviceType.DISK,
    bus=DiskBus.VIRTIO,
    readonly=False,
    boot_order=2,  # Второе устройство для загрузки
)

# Пример с использованием автовалидации
auto_disk = VMDisk(
    path="/path/to/install.iso",  # Автоматически станет CDROM
    boot_order=1,
)