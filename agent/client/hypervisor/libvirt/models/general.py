from enum import Enum


class VMState(Enum):
    """Состояния виртуальной машины"""
    NOSTATE = 0  # Нет состояния
    RUNNING = 1  # Работает
    BLOCKED = 2  # Заблокирована
    PAUSED = 3  # Приостановлена
    SHUTDOWN = 4  # Завершается
    SHUTOFF = 5  # Выключена
    CRASHED = 6  # Аварийно завершена
    PMSUSPENDED = 7  # Приостановлена (PM)


class SnapshotState(Enum):
    """
    Состояния снапшота виртуальной машины в libvirt.
    Соответствуют значениям элемента <state> в XML снапшота.
    """

    # Основные состояния
    RUNNING = "running"
    """ВМ была запущена в момент создания снапшота"""

    PAUSED = "paused"
    """ВМ была приостановлена в момент создания снапшота"""

    SHUT_OFF = "shut off"
    """ВМ была выключена в момент создания снапшота"""

    SHUTDOWN = "shutdown"
    """ВМ находилась в процессе выключения"""

    CRASHED = "crashed"
    """ВМ завершилась аварийно"""

    PMSUSPENDED = "pmsuspended"
    """ВМ переведена в спящий режим (power management suspend)"""

    DISK_SNAPSHOT = "disk-snapshot"
    """Снапшот содержит только дисковое состояние"""

    # Дополнительные состояния (могут встречаться в разных версиях libvirt)
    BLOCKED = "blocked"
    """ВМ заблокирована (обычно ресурсом)"""

    NOSTATE = "nostate"
    """Неизвестное состояние"""


class MachineType(Enum):
    """Типы машин для эмуляции"""
    Q35 = "q35"  # Современный, поддерживает PCIe и hotplug
    PC = "pc"  # Стандартный PC (устаревший)
    PC_I440FX = "pc-i440fx"  # PC с i440FX чипсетом
    VIRT = "virt"  # Виртуальная машина (для ARM)
    PSERIES = "pseries"  # PowerPC
    S390_CCW_VIRTIO = "s390-ccw-virtio"  # IBM s390x

    # Специальные типы
    MICROVM = "microvm"  # Упрощенная ВМ
    XENPV = "xenpv"  # Xen паравиртуализация
    XENHVM = "xenhvm"  # Xen аппаратная виртуализация