from datetime import datetime
from ipaddress import IPv4Address

from pydantic import BaseModel, Field, model_validator

from src.models.controller import VMController
from src.models.disk import DiskCreate, DiskAttach
from src.models.enum_model import VideoModel, Architecture, OSType, GraphicsType
from src.models.general import VMState, MachineType, QemuNetdevType, CreateTask
from src.models.network import VmNetAdapter


class HostForward(BaseModel):
    protocol: str | None = None
    host_port: int = Field(..., description="Слушает запросы извне")
    host_ip: str | None = None
    guest_port: int = Field(..., description="Куда перенаправляет порты")

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        """Проверка условно обязательных полей в зависимости от типа"""
        if self.host_ip is not None:
            IPv4Address(self.host_ip)

        return self

    @property
    def hostfwd_to_string(self):
        return f'{self.protocol}:{self.host_ip if self.host_ip else ""}:{self.host_port}-:{self.guest_port}'


class NetQemuCommandline(BaseModel):
    net_dev: QemuNetdevType = QemuNetdevType.USER
    net_id: str = "net0"
    ipv4: bool = True
    ipv6: bool = False
    dns: str = "8.8.8.8"
    hostfwd: list[HostForward] = [
        HostForward(protocol="tcp", host_port=2222, host_ip=None, guest_port=22)
    ]

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        """Проверка условно обязательных полей в зависимости от типа"""
        IPv4Address(self.dns)

        return self

    @property
    def qemu_commandline_string(self):
        ipv4 = "on" if self.ipv4 else "off"
        ipv6 = "on" if self.ipv6 else "off"
        qcs = (
            f'--qemu-commandline="'
            f"-netdev {self.net_dev.value},"
            f"id={self.net_id},"
            f"ipv4={ipv4},"
            f"ipv6={ipv6},"
            f"dns={self.dns},"
        )
        hostfwd = ""
        for current_hostfwd in self.hostfwd:
            hostfwd += "hostfwd=" + current_hostfwd.hostfwd_to_string + ","
        hostfwd = hostfwd[:-1]
        return qcs + hostfwd + '"'


class VMCreateRequest(BaseModel):
    """Модель запроса на создание ВМ через virt-install"""

    # Основные параметры

    cluster_id: int
    node_id: int
    name: str
    uuid: str | None = None
    template: str | None = Field(
        default=None, description="Является ли сущность шаблоном для создания ВМ"
    )
    description: str | None = Field(
        default=None, description="Текстовое описание виртуальной машины"
    )
    architecture: Architecture = Field(
        default=Architecture.X86_64,
        description="Архитектура процессора: X86_64, AARCH64, etc",
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
    vcpus: int = Field(
        default=2, description="Количество виртуальных процессоров (начальное)"
    )
    max_vcpus: int | None = Field(
        default=4,
        description="Максимальное количество виртуальных процессоров (для hotplug)",
    )

    # Устройства
    disks: list[DiskCreate | DiskAttach] = Field(
        ..., description="Список дисковых устройств (создаваемых или подключаемых)"
    )
    net_adapters: list[VmNetAdapter] = Field(
        ..., description="Список сетевых адаптеров для подключения ВМ"
    )
    controllers: list[VMController] = Field(
        default_factory=list, description="Список контроллеров (SCSI, IDE, USB и т.д.)"
    )

    # Графика и консоль
    graphics_type: GraphicsType = Field(
        default=GraphicsType.VNC,
        description="Тип графического интерфейса: VNC, SPICE, none и т.д.",
    )
    graphics_port: int | None = Field(
        default=5921,
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
    net_qemu_commandline: NetQemuCommandline | None = Field(
        default=None, description="Дополнительные аргументы командной строки QEMU"
    )
    boot_devices: list[str] | None = Field(
        default=None,
        description="Порядок устройств для загрузки: hd (жесткий диск), cdrom, network, fd",
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

    machine_type: MachineType = Field(
        default=MachineType.Q35,
        description="Тип эмулируемой машины",
    )

    cpu_model: str = Field(default="host-model", description="Модель CPU")


class VmUpdateRequest(BaseModel):
    max_memory_mb: int | None = None
    vcpus: int | None = None
    max_vcpus: int | None = None
    cpu_model: str | None = None
    cpu_features: list[str] | None = None
    autostart: bool | None = None
    description: str | None = None
    name: str | None = None
    graphics_type: GraphicsType | None = None
    video_model: VideoModel = Field(
        default=None, description="Модель видеокарты: qxl, cirrus, vga, virtio и т.д."
    )
    machine_type: str | None = None
    os_variant: str | None = None
    boot_devices: list[str] | None = None
    features: dict[str, str] | None = None
    memballoon_model: str | None = None
    hyperv_features: dict | None = None
    qemu_agent: bool | None = None
    change_live_config: bool = (
        False  # если включена - изменяет запущенную конфигурацию, а не постоянную
    )


class VMListRequest(BaseModel):
    cluster_id: int | None = None
    node_id: int | None = None
    resource_pool_id: int | None = None
    name: str | None = None
    state: int | None = None
    infrastructure: bool | None = None
    limit: int = 100
    offset: int = 0
    sort_by: str = "created"
    sort_desc: bool = True


class VirtualMachineFromAgent(BaseModel):
    name: str
    description: str | None = None
    state: int
    id: int | None = None
    net_id: str | None = None
    hostfwd: HostForward | None = None
    uuid: str
    vcpus: int
    memory: int  # в килобайтах
    max_memory: int  # в килобайтах
    cpu_time: int | None = None  # в наносекундах


class VirtualMachine(BaseModel):
    """Информация о виртуальной машине"""

    name: str
    description: str | None = None
    state: VMState
    id: int
    node_id: int
    cluster_id: int
    template: str | None = None
    uuid: str
    vcpus: int
    max_vcpus: int
    memory_mb: float
    created: datetime
    infrastructure: bool = False
    video_memory_mb: float
    modified: datetime
    deleted: datetime
    architecture: Architecture
    os_type: OSType
    os_variant: str
    noautoconsole: bool
    graphics_type: GraphicsType
    graphics_port: bool
    graphics_listen: bool
    console_type: str
    autostart_vm: bool
    autostart: bool
    net_qemu_commandline: NetQemuCommandline | None
    boot_devices: list[str] | None = None
    video_model: VideoModel
    boot_uefi: bool
    secure_boot: bool
    machine_type: MachineType
    cpu_model: str


class VMList(BaseModel):
    items: list[VirtualMachine]
    total: int


class VMChangeStateResponse(BaseModel):
    vm: VirtualMachine
    task: CreateTask
