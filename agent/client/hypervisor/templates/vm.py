# 1. Создание простой ВМ
from agent.client.hypervisor.libvirt.models.controller import VMController
from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.enum import GraphicsType, NetworkType, NetworkModel, \
    DiskBus, DiskFormat, Architecture, OSType, ControllerType
from agent.client.hypervisor.libvirt.models.network import VMNetwork
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.hypervisor.models.general import MachineType

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
    os_variant="ubuntu22.04",
    controllers=[VMController(controller_type=ControllerType.PCI, model="pci-root")],
)
simple_config_without_net = VMCreateRequest(
    name="test-vm-03",
    description="Тестовая ВМ",
    memory_mb=2048,
    vcpus=2,
    disks=[
        VMDisk(
            path="/var/lib/libvirt/images/disk-859480.qcow2",
            # path="/var/lib/libvirt/images/test-vm-01.qcow2",
            size_gb=20,
            bus=DiskBus.VIRTIO,
            format=DiskFormat.QCOW2
        )
    ],
    os_variant="ubuntu22.04",
    # controllers=[VMController(controller_type=ControllerType.PCI, model="pci-root", index=1)],
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
hotplug_vm_config = VMCreateRequest(
    name="hotplug-vm-01",
    description="ВМ с поддержкой hotplug устройств",
    memory_mb=4096,
    vcpus=4,

    # Для hotplug важно использовать архитектуру x86_64 и machine type q35
    architecture=Architecture.X86_64,
    machine_type=MachineType.Q35,  # Обязательно для hotplug!

    # Диски - системный диск создаем как обычный
    disks=[
        VMDisk(
            path="/var/lib/libvirt/images/hotplug-vm-01-system.qcow2",
            size_gb=40,
            bus=DiskBus.SATA,  # Используем SATA для системного диска (лучше для hotplug)
            format=DiskFormat.QCOW2,
            boot_order=1,
            cache="writeback"
        )
    ],

    # Сеть
    networks=[
        VMNetwork(
            network_type=NetworkType.NETWORK,
            source="default",
            model=NetworkModel.VIRTIO,
            boot_order=2
        )
    ],

    # Контроллеры для hotplug - КРИТИЧНО важно!
    controllers=[
        # Основной PCIe контроллер (обязателен для hotplug)
        VMController(
            controller_type=ControllerType.PCI,
            model="pcie-root",
            index=0
        ),

        # PCIe root ports - порты для подключения hotplug устройств
        VMController(
            controller_type=ControllerType.PCI,
            model="pcie-root-port",
            index=1,
            # Для каждого hotplug устройства нужен свой порт
            # Можно добавить несколько портов
        ),

        # SATA контроллер для hotplug дисков
        VMController(
            controller_type=ControllerType.SATA,
            model="ich9-ahci",
            index=2
        ),

        # USB контроллер для hotplug USB устройств
        VMController(
            controller_type=ControllerType.USB,
            model="qemu-xhci",
            index=3,
            ports=15  # Много портов для горячего подключения
        ),

        # SCSI контроллер для hotplug SCSI устройств
        VMController(
            controller_type=ControllerType.SCSI,
            model="virtio-scsi",
            index=4
        ),

        # Дополнительные PCIe порты (можно добавить несколько)
        VMController(
            controller_type=ControllerType.PCI,
            model="pcie-to-pci-bridge",
            index=5
        ),
    ],

    # Графика
    graphics=GraphicsType.SPICE,
    video_model="qxl",  # Поддерживает hotplug мониторов

    # Дополнительные параметры для hotplug
    os_variant="ubuntu22.04",

    # Устройства загрузки
    boot_devices=["hd", "network"],

    # Включаем возможность изменения конфигурации на лету
    memballoon_model="virtio",  # Для hotplug памяти

    # Поддержка QEMU guest agent (очень важно для hotplug!)
    qemu_agent=True,

    # Указываем, что ВМ должна поддерживать hotplug
    features={
        "acpi": "on",  # Обязательно для hotplug
        "apic": "on",
        "vmx": "on",  # Если нужна виртуализация
    },

    # Дополнительные параметры для производительности
    cpu_model="host-passthrough",  # Лучшая производительность
    cpu_features=["vmx", "svm", "invtsc"],  # Поддержка виртуализации

    # Автостарт
    autostart=False,
)

# Упрощенный шаблон для тестов
simple_hotplug_vm_config = VMCreateRequest(
    name="test-hotplug-vm-2",
    description="Тестовая ВМ с базовой поддержкой hotplug",
    memory_mb=2048,
    vcpus=2,

    # Обязательные параметры для hotplug
    architecture=Architecture.X86_64,
    machine_type=MachineType.Q35,  # Обязательно для hotplug!

    # Минимальные контроллеры для hotplug
    controllers=[
        # PCIe root (обязательно)
        VMController(
            controller_type=ControllerType.PCI,
            model="pcie-root",
            index=0
        ),
        # PCIe порты для hotplug (минимум 2-3)
        VMController(
            controller_type=ControllerType.PCI,
            model="pcie-root-port",
            index=1,
        ),
        #
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=14,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=3,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=4,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=5,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=6,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=7,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=8,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=9,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=10,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=11,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=12,
        # ),
        # VMController(
        #     controller_type=ControllerType.PCI,
        #     model="pcie-root-port",
        #     index=13,
        # ),
    ],

    # Обязательные фичи
    features={
        "acpi": "on",
        "apic": "on",
    },

    os_variant="ubuntu22.04",
    qemu_agent=True,  # Важно для корректной работы hotplug
    autostart=False
)