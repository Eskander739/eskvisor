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


class StoragePoolType(str, Enum):
    """Типы пулов хранения в libvirt"""

    DIR = "dir"  # Директория в файловой системе
    FS = "fs"  # Предварительно отформатированный раздел файловой системы
    LOGICAL = "logical"  # Группа LVM логических томов
    DISK = "disk"  # Физический диск или раздел
    ISCSI = "iscsi"  # iSCSI целевое устройство
    SCSI = "scsi"  # SCSI устройства
    MPATH = "mpath"  # Multipath устройства
    RBD = "rbd"  # RADOS Block Device (Ceph)
    SHEEPDOG = "sheepdog"  # Sheepdog распределенное хранилище
    GLUSTER = "gluster"  # GlusterFS том
    ZFS = "zfs"  # ZFS пул
    VSTORAGE = "vstorage"  # Virtuozzo Storage
    NETFS = "netfs"  # Сетевая файловая система (NFS)
    VXHS = "vxhs"  # Veritas HyperScale Storage
    ISCSI_DIRECT = "iscsi-direct"  # Прямой доступ к iSCSI
    UNKNOWN = "unknown"


POOL_TYPE_DESCRIPTIONS = {
    StoragePoolType.DIR: "Директория в локальной файловой системе",
    StoragePoolType.FS: "Форматированный раздел файловой системы",
    StoragePoolType.LOGICAL: "Группа LVM логических томов",
    StoragePoolType.DISK: "Физический диск или раздел",
    StoragePoolType.ISCSI: "iSCSI целевое устройство по сети",
    StoragePoolType.SCSI: "SCSI устройства",
    StoragePoolType.MPATH: "Устройства с multipath",
    StoragePoolType.RBD: "RADOS Block Device (Ceph)",
    StoragePoolType.SHEEPDOG: "Sheepdog распределенное хранилище",
    StoragePoolType.GLUSTER: "GlusterFS сетевой том",
    StoragePoolType.ZFS: "ZFS пул",
    StoragePoolType.VSTORAGE: "Virtuozzo Storage",
    StoragePoolType.NETFS: "Сетевая файловая система (NFS)",
    StoragePoolType.VXHS: "Veritas HyperScale Storage",
    StoragePoolType.ISCSI_DIRECT: "Прямой доступ к iSCSI",
}
