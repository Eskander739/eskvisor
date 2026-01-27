from ipaddress import IPv4Address
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator, computed_field

from agent.client.hypervisor.libvirt.models.controller import VMController
from agent.client.hypervisor.libvirt.models.volume.disk import (
    BusType,
    DiskCreate,
    DiskAttach,
)
from agent.client.hypervisor.libvirt.models.enum import (
    Architecture,
    ControllerType,
    EmulatorType,
    GraphicsType,
    OSType,
    VideoModel,
)
from agent.client.hypervisor.libvirt.models.general import (
    MachineType,
    VMState,
    QemuNetdevType,
)
from agent.client.hypervisor.libvirt.models.network import VmNetAdapter


class HostForward(BaseModel):
    protocol: str | None = None
    host_port: int
    host_ip: str | None = None
    guest_port: int

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        """Проверка условно обязательных полей в зависимости от типа"""
        if self.host_ip is not None:
            IPv4Address(self.host_ip)

        return self

    @property
    def hostfwd_to_string(self):
        return f'{self.protocol}:{self.host_ip if self.host_ip else ""}:{self.host_port}-:{self.guest_port}'


class VMStateInfo(BaseModel):
    vm_name: str
    state: VMState


class NetQemuCommandline(BaseModel):
    net_dev: QemuNetdevType = QemuNetdevType.USER
    net_id: str = "net0"
    ipv4: bool = True
    ipv6: bool = False
    dns: str = "8.8.8.8"
    hostfwd: HostForward = HostForward(
        protocol="tcp", host_port=2222, host_ip=None, guest_port=22
    )

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        """Проверка условно обязательных полей в зависимости от типа"""
        IPv4Address(self.dns)

        return self

    @property
    def qemu_commandline_string(self):
        ipv4 = "on" if self.ipv4 else "off"
        ipv6 = "on" if self.ipv6 else "off"
        return (
            f'--qemu-commandline="'
            f"-netdev {self.net_dev.value},"
            f"id={self.net_id},"
            f"ipv4={ipv4},"
            f"ipv6={ipv6},"
            f"dns={self.dns},"
            f'hostfwd={self.hostfwd.hostfwd_to_string}"'
        )


class VMCreateRequest(BaseModel):
    """Модель запроса на создание ВМ через virt-install"""

    # Основные параметры

    name: str
    install_method: str | None = (
        "import"  # "import", "pxe", "boot", "cdrom", "location"
    )
    description: str | None = Field(
        default=None, description="Текстовое описание виртуальной машины"
    )
    architecture: Architecture = Field(
        default=Architecture.X86_64,
        description="Архитектура процессора: X86_64, AARCH64, etc",
    )
    emulator_type: EmulatorType = Field(
        default=EmulatorType.KVM, description="Тип эмулятора: KVM, QEMU, etc"
    )
    os_type: OSType = Field(
        default=OSType.LINUX,
        description="Тип операционной системы: LINUX, WINDOWS, etc",
    )
    os_variant: str | None = Field(
        default="generic",
        description="Вариант ОС для оптимизации настроек (ubuntu22.04, centos8, win10)",
    )
    noautoconsole: bool = Field(
        default=True,
        description="Не подключаться к консоли автоматически после создания ВМ",
    )

    # Ресурсы
    memory_mb: int = Field(
        default=256,
        description="Объем оперативной памяти в МБ(значение memory_mb всегда равно maxmemory при live режиме)",
    )
    max_memory_mb: int | None = Field(
        default=None,
        description="Максимальный объем оперативной памяти в МБ (для hotplug)",
    )
    vcpus: int = Field(
        default=2, description="Количество виртуальных процессоров (начальное)"
    )
    max_vcpus: int | None = Field(
        default=4,
        description="Максимальное количество виртуальных процессоров (для hotplug)",
    )
    cpu_features: list[str] | None = Field(
        default=None,
        description="Список дополнительных функций процессора (например, 'vmx', 'svm')",
    )

    # Устройства
    disks: list[DiskCreate | DiskAttach] = Field(
        default_factory=list,
        description="Список дисковых устройств (создаваемых или подключаемых)",
    )
    networks: list[VmNetAdapter] = Field(
        default_factory=list, description="Список сетевых адаптеров для подключения ВМ"
    )
    controllers: list[VMController] = Field(
        default_factory=list, description="Список контроллеров (SCSI, IDE, USB и т.д.)"
    )

    # Графика и консоль
    graphics: GraphicsType = Field(
        default=GraphicsType.VNC,
        description="Тип графического интерфейса: VNC, SPICE, none и т.д.",
    )
    graphics_port: int | None = Field(
        default=None,
        description="Порт для графического интерфейса (если не указан, выбирается автоматически)",
    )
    graphics_listen: str = Field(
        default="0.0.0.0",
        description="IP-адрес, на котором слушает графический интерфейс",
    )
    console_type: str = Field(
        default="pty", description="Тип консоли: pty, tcp, file и т.д."
    )

    # Прочие настройки
    autostart_vm: bool = Field(
        default=False, description="Автоматически запускать ВМ при старте хоста"
    )
    autostart: bool = Field(
        default=False, description="Автоматически запускать ВМ при перезагрузке хоста"
    )
    qemu_commandline: NetQemuCommandline | None = Field(
        default=None, description="Дополнительные аргументы командной строки QEMU"
    )
    boot_devices: list[str] | None = Field(
        default=None,
        description="Порядок устройств для загрузки: hd (жесткий диск), cdrom, network, fd",
    )
    # boot_devices: list[str] | None = ["hd", "cdrom", "network", "fd"]
    extra_args: str | None = Field(
        default=None,
        description="Дополнительные аргументы для командной строки установки",
    )
    video_model: VideoModel = Field(
        default=VideoModel.QXL,
        description="Модель видеокарты: qxl, cirrus, vga, virtio и т.д.",
    )
    boot_uefi: bool = Field(
        default=False, description="Использовать UEFI вместо BIOS для загрузки"
    )
    secure_boot: bool = Field(
        default=False,
        description="Включить Secure Boot (требует UEFI и соответствующего загрузчика)",
    )
    secure_boot_loader: str | None = Field(
        default=None,
        description="Путь к загрузчику Secure Boot (например, /usr/share/OVMF/OVMF_CODE_MS.fd)",
    )

    machine_type: MachineType = Field(
        default=MachineType.Q35,
        description="Тип эмулируемой машины",
    )

    features: dict[str, str] = Field(
        default_factory=lambda: {"acpi": "on", "apic": "on"},
        description="Включенные фичи ВМ",
    )

    qemu_agent: bool = Field(default=False, description="Включить QEMU guest agent")

    memballoon_model: str = Field(default="virtio", description="Модель баллона памяти")

    hyperv_features: dict[str, str] = Field(
        default_factory=dict, description="Hyper-V фичи (для Windows)"
    )
    cpu_model: str = Field(default="host-model", description="Модель CPU")

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        """Проверка условно обязательных полей в зависимости от типа"""

        if (
            self.secure_boot
            and not self.boot_uefi
            or self.secure_boot_loader
            and not self.boot_uefi
        ):
            raise ValueError(
                "Secure Boot требует включения UEFI загрузки, включите boot_uefi или отключите secure_boot"
            )
        if not self.secure_boot and self.secure_boot_loader:
            raise ValueError(
                "Secure Boot Loader требует включения Secure Boot загрузки, включите Secure Boot или отключите Secure Boot Loader"
            )

        if self.boot_devices:
            for current_disk in self.disks:
                if current_disk.path is None:
                    raise ValueError(
                        "Несовместимые параметры, "
                        f"нельзя использовать boot_devices='{self.boot_devices}' и диски с path=None"
                    )

        if self.boot_devices is None and self.install_method is None:
            raise ValueError(
                "Несовместимые параметры "
                "нельзя использовать boot_devices=None и диски с install_method=None"
            )

        return self

    # Валидаторы
    @field_validator("os_variant")
    def set_default_variant(cls, v, values):
        """Установка варианта ОС по умолчанию"""
        if v is None:
            os_type = (
                values.data.get("os_type")
                if not isinstance(values, dict)
                else values.get("os_type")
            )
            if os_type == OSType.WINDOWS:
                return "win10"
            elif os_type == OSType.LINUX:
                return "generic"
        return v

    @field_validator("max_vcpus")
    def set_max_vcpus(cls, v, values):
        """Установка максимального количества vCPUs"""
        if v is None:
            return (
                values.data.get("vcpus")
                if not isinstance(values, dict)
                else values.get("vcpus")
            )
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
        disks = values.get("disks", [])
        if any(disk.bus_type == BusType.SCSI for disk in disks):
            scsi_controller = VMController(
                controller_type=ControllerType.SCSI, index=0, model="virtio-scsi"
            )
            controllers.append(scsi_controller)

        # Добавляем SATA контроллер если есть SATA диски
        if any(disk.bus_type == BusType.SATA for disk in disks):
            sata_controller = VMController(
                controller_type=ControllerType.SATA, index=0, model="ahci"
            )
            controllers.append(sata_controller)

        # Добавляем IDE контроллер если есть IDE диски или CDROM
        cdrom = values.get("cdrom")
        if any(disk.bus_type == BusType.IDE for disk in disks) or cdrom:
            ide_controller = VMController(
                controller_type=ControllerType.IDE, index=0, model="piix4-ide"
            )
            controllers.append(ide_controller)

        return controllers

    @field_validator("disks")
    def validate_disks(cls, v):
        """Валидация дисков"""
        if not v:
            raise ValueError("Хотя бы один диск должен быть указан")
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


class VmUpdateRequest(BaseModel):
    max_memory_mb: int | None = None
    vcpus: int | None = None
    max_vcpus: int | None = None
    current_memory_mb: int | None = None
    cpu_model: str | None = None
    cpu_features: list[str] | None = None
    autostart: bool | None = None
    description: str | None = None
    name: str | None = None
    graphics: dict[str, Any] | None = None
    video_model: VideoModel = Field(
        default=None, description="Модель видеокарты: qxl, cirrus, vga, virtio и т.д."
    )
    machine_type: str | None = None
    os_variant: str | None = None
    boot_devices: list[str] | None = None
    features: dict[str, str] | None = None
    memballoon_model: str | None = None
    hyperv_features: dict[str, Any] | None = None
    qemu_agent: bool | None = None
    change_live_config: bool = (
        False  # если включена - изменяет запущенную конфигурацию, а не постоянную
    )


class VirtualMachine(BaseModel):
    """Информация о виртуальной машине"""

    name: str
    description: str | None = None
    state: VMState
    id: int | None = None
    net_id: str | None = None
    hostfwd: HostForward | None = None
    uuid: str
    vcpus: int
    memory: int  # в килобайтах
    max_memory: int  # в килобайтах
    cpu_time: int | None = None  # в наносекундах

    @computed_field
    @property
    def memory_bytes(self) -> float:
        return int(self.memory * 1024)

    @computed_field
    @property
    def max_memory_bytes(self) -> float:
        return int(self.max_memory * 1024)


class VirtualMachinesList(BaseModel):
    total: int
    items: list[VirtualMachine]


class SecureBootVM(BaseModel):
    vm_name: str
    has_uefi: bool = False
    has_secure_boot: bool = False
    secure_boot_loader: str | None = None
    loader_type: str | None = None
    errors: list[str] = []
