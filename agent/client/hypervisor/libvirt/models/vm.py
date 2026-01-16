import uuid
from ipaddress import IPv4Address
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator, computed_field

from agent.client.hypervisor.libvirt.models.controller import VMController
from agent.client.hypervisor.libvirt.models.volume.disk import BusType, DiskCreate
from agent.client.hypervisor.libvirt.models.enum import (
    Architecture,
    ControllerType,
    EmulatorType,
    GraphicsType,
    OSType,
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
    def validate_disk_type_constraints(cls, values):
        """Проверка условно обязательных полей в зависимости от типа"""
        if values.host_ip is not None:
            IPv4Address(values.host_ip)

    @property
    def hostfwd_to_string(self):
        return f'{self.protocol}:{self.host_ip if self.host_ip else ""}:{self.host_port}-:{self.guest_port}'


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
    def validate_disk_type_constraints(cls, values):
        """Проверка условно обязательных полей в зависимости от типа"""
        IPv4Address(values.dns)

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

    request_id: str = str(uuid.uuid4())
    name: str
    install_method: str | None = (
        "import"  # "import", "pxe", "boot", "cdrom", "location"
    )
    description: str | None = None
    architecture: Architecture | str = Architecture.X86_64
    emulator_type: EmulatorType = EmulatorType.KVM
    os_type: OSType | str = OSType.LINUX
    os_variant: str | None = "generic"  # ubuntu22.04, centos8, win10 и т.д.
    noautoconsole: bool = True

    # Ресурсы
    memory_mb: int = 256
    current_memory_mb: int | None = None
    vcpus: int = 2
    max_vcpus: int | None = 4
    cpu_model: str | None = None
    cpu_features: list[str] | None = None

    # Устройства
    disks: list[DiskCreate] = Field(default_factory=list)
    networks: list[VmNetAdapter] = Field(default_factory=list)
    controllers: list[VMController] = Field(default_factory=list)

    # Графика и консоль
    graphics: GraphicsType | str = GraphicsType.VNC
    graphics_port: int | None = None
    graphics_listen: str = "0.0.0.0"
    console_type: str = "pty"

    # Прочие настройки
    autostart_vm: bool = False
    autostart: bool = False
    qemu_commandline: NetQemuCommandline | None = None
    boot_devices: list[str] | None = None
    extra_args: str | None = None
    video_model: str = "qxl"

    machine_type: MachineType = Field(
        default=(
            MachineType.Q35 if architecture == Architecture.X86_64 else MachineType.VIRT
        ),
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

    cpu_features: list[str] = Field(
        default_factory=list, description="Дополнительные фичи CPU"
    )

    @model_validator(mode="after")
    def validate_disk_type_constraints(cls, values):
        """Проверка условно обязательных полей в зависимости от типа"""

        if values.boot_devices:
            for current_disk in values.disks:
                if current_disk.path is None:
                    raise ValueError(
                        "Несовместимые параметры, "
                        f"нельзя использовать boot_devices='{values.boot_devices}' и диски с path=None"
                    )

        if values.boot_devices is None and values.install_method is None:
            raise ValueError(
                "Несовместимые параметры "
                "нельзя использовать boot_devices=None и диски с install_method=None"
            )

        return values

    # Валидаторы
    @field_validator("os_variant")
    def set_default_variant(cls, v, values):
        """Установка варианта ОС по умолчанию"""
        if v is None:
            os_type = values.get("os_type")
            if os_type == OSType.WINDOWS:
                return "win10"
            elif os_type == OSType.LINUX:
                return "generic"
        return v

    @field_validator("current_memory_mb")
    def set_current_memory(cls, v, values):
        """Установка текущей памяти, если не указана"""
        if v is None:
            return values.get("memory_mb")
        return v

    @field_validator("max_vcpus")
    def set_max_vcpus(cls, v, values):
        """Установка максимального количества vCPUs"""
        if v is None:
            return values.get("vcpus")
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
        if any(disk.bus == BusType.SCSI for disk in disks):
            scsi_controller = VMController(
                controller_type=ControllerType.SCSI, index=0, model="virtio-scsi"
            )
            controllers.append(scsi_controller)

        # Добавляем SATA контроллер если есть SATA диски
        if any(disk.bus == BusType.SATA for disk in disks):
            sata_controller = VMController(
                controller_type=ControllerType.SATA, index=0, model="ahci"
            )
            controllers.append(sata_controller)

        # Добавляем IDE контроллер если есть IDE диски или CDROM
        cdrom = values.get("cdrom")
        if any(disk.bus == BusType.IDE for disk in disks) or cdrom:
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
    memory_mb: int | None = None
    vcpus: int | None = None
    max_vcpus: int | None = None
    current_memory_mb: int | None = None
    cpu_model: str | None = None
    cpu_features: list[str] | None = None
    autostart: bool | None = None
    description: str | None = None
    name: str | None = None
    graphics: dict[str, Any] | None = None
    video_model: str | None = None
    machine_type: str | None = None
    os_variant: str | None = None
    boot_devices: list[str] | None = None
    features: dict[str, str] | None = None
    memballoon_model: str | None = None
    hyperv_features: dict[str, Any] | None = None
    qemu_agent: bool | None = None
    reboot_if_needed: bool = False


class VirtualMachine(BaseModel):
    """Информация о виртуальной машине"""

    name: str
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
