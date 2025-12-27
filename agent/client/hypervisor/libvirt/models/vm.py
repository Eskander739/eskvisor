from pydantic import field_validator, BaseModel, Field

from agent.client.hypervisor.libvirt.models.controller import VMController
from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.enum import Architecture, EmulatorType, OSType, GraphicsType, DiskBus, \
    ControllerType
from agent.client.hypervisor.libvirt.models.network import VMNetwork
from agent.client.hypervisor.models.general import MachineType


class VMCreateRequest(BaseModel):
    """Модель запроса на создание ВМ через virt-install"""
    # Основные параметры
    name: str
    install_method: str | None = "import"  # "import", "pxe", "boot", "cdrom", "location"
    description: str | None = None
    architecture: Architecture | str = Architecture.X86_64
    emulator_type: EmulatorType = EmulatorType.KVM
    os_type: OSType | str = OSType.LINUX
    os_variant: str | None = None  # ubuntu22.04, centos8, win10 и т.д.

    # Ресурсы
    memory_mb: int = 1024
    current_memory_mb: int | None = None
    vcpus: int = 2
    max_vcpus: int | None = None
    cpu_model: str | None = None
    cpu_features: list[str] | None = None

    # Устройства
    disks: list[VMDisk] = Field(default_factory=list)
    networks: list[VMNetwork] = Field(default_factory=list)
    controllers: list[VMController] = Field(default_factory=list)

    # Графика и консоль
    graphics: GraphicsType | str = GraphicsType.VNC
    graphics_port: int | None = None
    graphics_listen: str = "0.0.0.0"
    console_type: str = "pty"

    # Прочие настройки
    autostart: bool = False
    boot_devices: list[str] = Field(default_factory=lambda: ["hd"])
    extra_args: str | None = None
    location: str | None = None  # Путь к ISO для установки
    cdrom: str | None = None
    video_model: str = "qxl"

    machine_type: MachineType = Field(
        default=MachineType.Q35 if architecture == Architecture.X86_64 else MachineType.VIRT,
        description="Тип эмулируемой машины"
    )

    features: dict[str, str] = Field(
        default_factory=lambda: {"acpi": "on", "apic": "on"},
        description="Включенные фичи ВМ"
    )

    qemu_agent: bool = Field(
        default=False,
        description="Включить QEMU guest agent"
    )

    memballoon_model: str = Field(
        default="virtio",
        description="Модель баллона памяти"
    )

    hyperv_features: dict[str, str] = Field(
        default_factory=dict,
        description="Hyper-V фичи (для Windows)"
    )

    cpu_model: str = Field(
        default="host-model",
        description="Модель CPU"
    )

    cpu_features: list[str] = Field(
        default_factory=list,
        description="Дополнительные фичи CPU"
    )

    # Валидаторы
    @field_validator("os_variant")
    def set_default_variant(cls, v, values):
        """Установка варианта ОС по умолчанию"""
        if v is None:
            os_type = values.get('os_type')
            if os_type == OSType.WINDOWS:
                return "win10"
            elif os_type == OSType.LINUX:
                return "generic"
        return v

    @field_validator("current_memory_mb")
    def set_current_memory(cls, v, values):
        """Установка текущей памяти, если не указана"""
        if v is None:
            return values.get('memory_mb')
        return v

    @field_validator("max_vcpus")
    def set_max_vcpus(cls, v, values):
        """Установка максимального количества vCPUs"""
        if v is None:
            return values.get('vcpus')
        return v

    @field_validator("controllers")
    def add_default_controllers(cls, v, values):
        """Добавление контроллеров по умолчанию"""
        controllers = list(v)
        values = values.data
        # architecture = values.get("architecture", Architecture.X86_64)
        # emulator_type = values.get("emulator_type", EmulatorType.KVM)

        # Для KVM/QEMU x86_64 добавляем PCI контроллер
        # if emulator_type in [EmulatorType.KVM, EmulatorType.QEMU] and architecture == Architecture.X86_64:
        #     print("controllers: ", controllers)
            # for controller in controllers:
            #     if controller.controller_type == ControllerType.PCI:
            #         break
            # else:
            #     pci_controller = VMController(
            #         controller_type=ControllerType.PCI,
            #         index=0,
            #         model="pcie-root"
            #     )
            #     controllers.insert(0, pci_controller)
            # for controller in controllers:
            #     if controller.controller_type == ControllerType.USB:
            #         break
            # else:
            #     usb_controller = VMController(
            #         controller_type=ControllerType.USB,
            #         index=0,
            #         model="qemu-xhci",
            #         ports=15
            #     )
            #     controllers.append(usb_controller)

        # Добавляем SCSI контроллер если есть SCSI диски
        disks = values.get('disks', [])
        if any(disk.bus == DiskBus.SCSI for disk in disks):
            scsi_controller = VMController(
                controller_type=ControllerType.SCSI,
                index=0,
                model="virtio-scsi"
            )
            controllers.append(scsi_controller)

        # Добавляем SATA контроллер если есть SATA диски
        if any(disk.bus == DiskBus.SATA for disk in disks):
            sata_controller = VMController(
                controller_type=ControllerType.SATA,
                index=0,
                model="ahci"
            )
            controllers.append(sata_controller)

        # Добавляем IDE контроллер если есть IDE диски или CDROM
        cdrom = values.get("cdrom")
        if any(disk.bus == DiskBus.IDE for disk in disks) or cdrom:
            ide_controller = VMController(
                controller_type=ControllerType.IDE,
                index=0,
                model="piix4-ide"
            )
            controllers.append(ide_controller)

        return controllers

    @field_validator("disks")
    def validate_disks(cls, v):
        """Валидация дисков"""
        if not v:
            raise ValueError("Хотя бы один диск должен быть указан")

        # Проверяем уникальность boot_order
        boot_orders = [d.boot_order for d in v if d.boot_order is not None]
        if len(boot_orders) != len(set(boot_orders)):
            raise ValueError("Boot order должен быть уникальным для каждого диска")

        return v


    @field_validator("graphics")
    def validate_graphics(cls, v):
        GraphicsType(v)
        return v


    @field_validator("os_type")
    def validate_os_type(cls, v):
        OSType(v)
        return v


    @field_validator("architecture")
    def validate_architecture(cls, v):
        Architecture(v)
        return v
