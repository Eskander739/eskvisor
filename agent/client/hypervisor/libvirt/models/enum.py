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


class DiskBus(str, Enum):
    """Типы шин для дисков"""
    VIRTIO = "virtio"
    SATA = "sata"
    SCSI = "scsi"
    IDE = "ide"
    USB = "usb"
    SD = "sd"
    XEN = "xen"
    NVDIMM = "nvdimm"


class DiskType(str, Enum):
    """Типы дисков"""
    FILE = "file"
    BLOCK = "block"
    DIR = "dir"
    NETWORK = "network"
    VOLUME = "volume"


class DiskFormat(str, Enum):
    """Форматы дисков"""
    QCOW2 = "qcow2"
    RAW = "raw"
    VMDK = "vmdk"
    VDI = "vdi"
    VHD = "vhd"
    VHDX = "vhdx"


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


class NetworkModel(str, Enum):
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
