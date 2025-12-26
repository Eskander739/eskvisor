# 1. Создание простой ВМ
from agent.client.hypervisor.libvirt.models.controller import VMController
from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.enum import GraphicsType, ControllerType, NetworkType, NetworkModel, \
    DiskBus, DiskFormat, Architecture, OSType
from agent.client.hypervisor.libvirt.models.network import VMNetwork
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest

simple_config = VMCreateRequest(
    name="test-vm-01",
    description="Тестовая ВМ",
    memory_mb=2048,
    vcpus=2,
    disks=[
        VMDisk(
            path="/var/lib/libvirt/images/test-vm-01.qcow2",
            size_gb=20,
            bus=DiskBus.VIRTIO,
            format=DiskFormat.QCOW2
        )
    ],
    networks=[
        VMNetwork(
            network_type=NetworkType.NETWORK,
            source="default",
            model=NetworkModel.VIRTIO
        )
    ],
    os_variant="ubuntu22.04"
)

# 2. Создание ВМ Windows
windows_config = VMCreateRequest(
    name="windows-vm-01",
    os_type=OSType.WINDOWS,
    os_variant="win10",
    memory_mb=4096,
    vcpus=4,
    disks=[
        VMDisk(
            path="/var/lib/libvirt/images/windows-vm-01.qcow2",
            size_gb=50,
            bus=DiskBus.SATA,
            format=DiskFormat.QCOW2
        )
    ],
    networks=[
        VMNetwork(
            network_type=NetworkType.NETWORK,
            source="default",
            model=NetworkModel.E1000,
            mac_address="52:54:00:ab:cd:ef"
        )
    ],
    controllers=[
        VMController(controller_type=ControllerType.USB, model="qemu-xhci"),
        VMController(controller_type=ControllerType.SATA, model="ahci")
    ],
    graphics=GraphicsType.SPICE,
    video_model="qxl",
    autostart=True
)

# 3. Создание ARM ВМ
arm_config = VMCreateRequest(
    name="arm-vm-01",
    architecture=Architecture.ARM64,
    memory_mb=1024,
    vcpus=2,
    disks=[
        VMDisk(
            path="/var/lib/libvirt/images/arm-vm-01.qcow2",
            size_gb=10,
            bus=DiskBus.VIRTIO,
            format=DiskFormat.QCOW2
        )
    ],
    networks=[
        VMNetwork(
            network_type=NetworkType.USER,
            model=NetworkModel.VIRTIO
        )
    ],
    os_variant="ubuntu22.04"
)

# 4. Создание ВМ с несколькими дисками
multi_disk_config = VMCreateRequest(
    name="storage-vm-01",
    memory_mb=4096,
    vcpus=4,
    disks=[
        VMDisk(
            path="/var/lib/libvirt/images/storage-vm-01-system.qcow2",
            size_gb=20,
            bus=DiskBus.VIRTIO,
            format=DiskFormat.QCOW2,
            boot_order=1
        ),
        VMDisk(
            path="/var/lib/libvirt/images/storage-vm-01-data.qcow2",
            size_gb=100,
            bus=DiskBus.SCSI,
            format=DiskFormat.QCOW2,
            cache="writeback"
        ),
        VMDisk(
            path="/var/lib/libvirt/images/storage-vm-01-backup.raw",
            size_gb=200,
            bus=DiskBus.VIRTIO,
            format=DiskFormat.RAW,
            readonly=True
        )
    ],
    networks=[
        VMNetwork(
            network_type=NetworkType.BRIDGE,
            source="br0",
            model=NetworkModel.VIRTIO,
            boot_order=2
        ),
        VMNetwork(
            network_type=NetworkType.NETWORK,
            source="management",
            model=NetworkModel.VIRTIO,
            mac_address="52:54:00:11:22:33"
        )
    ],
    controllers=[
        VMController(controller_type=ControllerType.SCSI, model="virtio-scsi"),
        VMController(controller_type=ControllerType.USB, model="qemu-xhci", ports=15)
    ],
    graphics=GraphicsType.VNC,
    graphics_port=5901,
    autostart=False,
    extra_args="console=ttyS0"
)