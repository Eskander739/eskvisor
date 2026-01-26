from enum import Enum


class Architecture(str, Enum):
    """Поддерживаемые архитектуры процессоров"""

    X86_64 = "x86_64"
    I386 = "i386"
    ARM64 = "aarch64"
    ARM = "arm"
    PPC64LE = "ppc64le"
    S390X = "s390x"
    RISCV64 = "riscv64"


class EmulatorType(str, Enum):
    """Типы эмуляторов/гипервизоров"""

    KVM = "kvm"
    QEMU = "qemu"
    XEN = "xen"
    LXC = "lxc"
    BHYVE = "bhyve"
    VMWARE = "vmware"


class OSType(str, Enum):
    """Типы операционных систем"""

    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    BSD = "bsd"
    SOLARIS = "solaris"
    GENERIC = "generic"


class NetworkType(str, Enum):
    """Типы сетевых интерфейсов"""

    BRIDGE = "bridge"
    NETWORK = "network"
    USER = "user"
    DIRECT = "direct"
    VHOSTUSER = "vhostuser"
    MCAST = "mcast"
    SERVER = "server"
    CLIENT = "client"


class NetworkModelEnum(str, Enum):
    """Модели сетевых карт"""

    VIRTIO = "virtio"
    E1000 = "e1000"
    E1000E = "e1000e"
    RTL8139 = "rtl8139"
    NE2K_PCI = "ne2k_pci"
    PCNET = "pcnet"
    SPAPR_VLAN = "spapr-vlan"
    VIRTIO_NET_PCI = "virtio-net-pci"
    VIRTIO_NET_CCW = "virtio-net-ccw"


class GraphicsType(str, Enum):
    """Типы графических адаптеров"""

    VNC = "vnc"
    SPICE = "spice"
    SDL = "sdl"
    GTK = "gtk"
    NONE = "none"


class ControllerType(str, Enum):
    """Типы контроллеров"""

    USB = "usb"
    PCI = "pci"
    SCSI = "scsi"
    IDE = "ide"
    SATA = "sata"
    VIRTIO_SERIAL = "virtio-serial"
    CCID = "ccid"
    FDC = "fdc"


class VideoModel(str, Enum):
    """
    Модели видеокарт для виртуальных машин в libvirt/QEMU.
    Использование: VideoModel.VIRTIO.value
    """

    # Паравиртуализированная модель с аппаратным ускорением (virgl)
    # Лучшая производительность для Linux гостевых ОС
    VIRTIO = "virtio"

    # Оптимизирован для Spice протокола, хорошая производительность 2D
    # Поддерживает многомониторность, живую миграцию
    QXL = "qxl"

    # Совместимость с драйверами VMware SVGA-II
    # Хороший выбор для Windows гостевых ОС
    VMWARE = "vmware"

    # Стандартная модель VGA (аналог vmware в некоторых системах)
    # Базовая совместимость, низкая производительность
    VGA = "vga"

    # Cirrus Logic GD5446, устаревшая модель
    # Обратная совместимость со старыми гостями
    CIRRUS = "cirrus"

    # Базовый дисплей Bochs для простых окружений
    # Используется в основном для UEFI/OVMF
    BOCHS = "bochs-display"

    # Паравиртуализированная модель Xen
    # Только для гипервизора Xen
    XEN = "xen"

    # RAM framebuffer - простейшая модель
    # Для загрузки до инициализации графики
    RAMFB = "ramfb"

    # UEFI Graphics Output Protocol
    # Для использования GOP в UEFI среде
    GOP = "gop"