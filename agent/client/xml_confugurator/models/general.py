from enum import Enum

from pydantic import BaseModel


class EnableParam(Enum):
    """
    Применяется для обозначения наличия разметки в XML, когда само наличие разметки и является параметром
    """
    enable = "enable"


class StateOnOff(Enum):
    on = "on"
    off = "off"

class IoApic(Enum):
    qemu = "qemu"
    kvm = "kvm"


class StateYesNo(Enum):
    no = "no"
    yes = "yes"


class StateOpenClosed(Enum):
    open = "open"
    closed = "closed"



class NvramModel(BaseModel):
    """
    Файл для хранения переменных UEFI NVRAM (настройки BIOS/UEFI, boot order, secure boot keys и т.д.).

    <!-- Автоматический путь (libvirt создаст сам) -->
    <nvram>/var/lib/libvirt/qemu/nvram/vm-name_VARS.fd</nvram>

    <!-- Пользовательский путь -->
    <nvram>/path/to/custom/nvram.fd</nvram>

    <!-- Шаблонный NVRAM (read-only копия) -->
    <nvram template='/usr/share/OVMF/OVMF_VARS.fd'>
      /var/lib/libvirt/qemu/nvram/vm-name_VARS.fd
    </nvram>

    <!-- Без NVRAM (только для readonly) -->
    <nvram></nvram>
    """

    template: str | None = "/opt/template/path" # Шаблонный NVRAM (read-only копия)
    value: str = "/var/lib/libvirt/qemu/nvram/vm-name_VARS.fd"


class DomainVirtualizationType(Enum):
    """
    Особенности типа kvm:
        Требует поддержки аппаратной виртуализации (Intel VT-x/AMD-V)
        Требует загруженных модулей ядра: kvm, kvm_intel или kvm_amd
        Самый быстрый вариант для Linux хост-систем
        Не работает без прав root или членства в группе kvm
    """
    KVM = "kvm" # KVM (аппаратная виртуализация на Linux)
    QEMU = "qemu" # QEMU (полная программная эмуляция)
    XEN = "xen" # Xen (para-виртуализация)
    LXC = "lxc" # LXC (контейнеры)
    VZ = "vz" # VZ (OpenVZ контейнеры)
    VMWARE = "vmware" # VMware (работа с ESX)
    HYPERV = "hyperv" # Hyper-V
    VBOX = "vbox" # VirtualBox


class ProcessorArchitecture(Enum):
    """
    Определяет архитектуру процессора
    """

    x86_64_bit = "x86_64" # x86 64-bit
    x86_32_bit = "i686" # x86 32-bit
    arm_64_bit = "aarch64" # ARM 64-bit
    ibm_power = "ppc64" # IBM Power
    ibm_z = "s390x" # IBM Z

class MachineOS(Enum):
    """
    Определяет тип виртуального оборудования (эмуляцию железа)
    """

    pc_q35_7_2 = "pc-q35-7.2" # Современный PC с UEFI
    pc_i440fx_7_2 = "pc-i440fx-7.2" # Устаревший PC с BIOS
    virt_7_2 = "virt-7.2" # Для ARM
    pseries = "pseries" # Для POWER


class TypeOS(Enum):
    """
    Определяет режим виртуализации

                     Полная виртуализация
    ┌─────────────────────────────────────────────────────────┐
    │                    Гостевая ОС                          │
    │    (Не модифицированная, например, Windows, Ubuntu)     │
    ├─────────────────────────────────────────────────────────┤
    │            Виртуальное железо (Virtual Hardware)        │
    │    CPU (эмулированный), RAM, HDD, Network, GPU и т.д.   │
    ├─────────────────────────────────────────────────────────┤
    │                Гипервизор (Hypervisor)                  │
    │                    Тип 1 или Тип 2                      │
    ├─────────────────────────────────────────────────────────┤
    │                Физическое железо                        │
    │          Реальный CPU, RAM, HDD, Network, GPU           │
    └─────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │                    Гостевая ОС                          │
    │     (Модифицированная с паравиртуализационными          │
    │           драйверами, например, Xen PV guest)           │
    ├─────────────────────────────────────────────────────────┤
    │              Паравиртуализационные API                  │
    │          Прямые вызовы гипервизору (hypercalls)         │
    ├─────────────────────────────────────────────────────────┤
    │                Гипервизор (Hypervisor)                  │
    │              (Xen, KVM с virtio, VMware)                │
    ├─────────────────────────────────────────────────────────┤
    │                Физическое железо                        │
    │          Реальный CPU, RAM, HDD, Network, GPU           │
    └─────────────────────────────────────────────────────────┘
    """

    HVM = "hvm" # Полная виртуализация (Hardware Virtual Machine)
    XEN = "xen" # Para-виртуализация Xen
    LINUX = "linux" # Para-виртуализация KVM (устаревшее)
