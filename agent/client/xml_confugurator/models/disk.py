from enum import Enum

from pydantic import Field, field_validator, BaseModel

from agent.client.xml_confugurator.models.general import EnableParam, StateOnOff, StateOpenClosed


class XmlDiskType(Enum):
    file = "file" # Диск — это файл в файловой системе (например, .qcow2, .raw). Наиболее часто используется.
    block = "block" # Блочное устройство (например, /dev/sdb, LVM-логический том). Подходит для высокой производительности.
    dir = "dir" # Каталог (используется редко, например, для 9p файловой системы).
    network = "network" # Сетевой диск (iSCSI, NBD, RBD/Ceph, GlusterFS и др.).


class XmlDiskDeviceType(Enum):
    disk = "disk" # Обычный жёсткий диск (основной системный или данных).
    cdrom = "cdrom" # Виртуальный CD/DVD-привод. Может быть пустым или указывать на .iso.
    floppy = "floppy" # Дискета (устаревшее, редко используется).
    lun = "lun" # Логический блок в SCSI-устройстве (часто для passthrough).


class XmlDiskDriverType(Enum):
    raw = "raw"
    qcow2 = "qcow2"
    qcow = "qcow"
    vmdk = "vmdk"
    vdi = "vdi"
    iso = "iso"
    host_device = "host_device"

class XmlDiskDriverIo(Enum):
    threads = "threads" # threads — эмуляция в потоках (по умолчанию)
    native = "native" # native — использовать aio=io_uring (Linux), более производительно.


class XmlDiskDriverDiscard(Enum):
    """
    Поддержка TRIM/UNMAP для SSD
    """

    unmap = "unmap" # unmap позволяет освобождать блоки.
    ignore = "ignore"


class XmlDiskDriverCache(Enum):
    none = "none"
    writethrough = "writethrough"
    writeback = "writeback"
    directsync = "directsync"
    unsafe = "unsafe"


class XmlDiskDriverErrorPolicy(Enum):
    stop = "stop"
    report = "report"
    ignore = "ignore"


class XmlDiskDriverReadErrorPolicy(Enum):
    stop = "stop"
    report = "report"
    ignore = "ignore"
    enospace = "enospace"


class XmlDriverNameEnum(Enum):
    qemu = "qemu" # основной драйвер для образов дисков
    tap = "tap" # для TAP-устройств (сетевые диски, deprecated)(основной для Xen)
    tap2 = "tap2" # улучшенная версия
    phy = "phy" #  для физических устройств (устаревший)
    lxc = "lxc" # Для LXC (type='lxc' в domain)


class XmlDiskDriver(BaseModel):
    name: XmlDriverNameEnum = XmlDriverNameEnum.qemu
    type: XmlDiskDriverType = XmlDiskDriverType.qcow2
    cache: XmlDiskDriverCache | None = None
    io: XmlDiskDriverIo | None = XmlDiskDriverIo.threads
    discard: XmlDiskDriverDiscard | None = XmlDiskDriverDiscard.ignore
    error_policy: XmlDiskDriverErrorPolicy | None = None
    rerror_policy: XmlDiskDriverReadErrorPolicy | None = None
    ioeventfd: StateOnOff | None = None
    event_idx: StateOnOff | None = None


class XmlDiskSourceFile(BaseModel):
    file: str


class XmlDiskSourcCDRome(BaseModel):
    file: str | None = None


class XmlDiskSourceBlock(BaseModel):
    dev: str


class XmlDiskSourceNetworkHost(BaseModel):
    name: str # host ip
    port: str


class XmlDiskSourceVolume(BaseModel):
    pool: str
    volume: str


class XmlDiskSourceNetwork(BaseModel):
    protocol: str
    name: str
    host: list[XmlDiskSourceNetworkHost] | XmlDiskSourceNetworkHost

class XmlDiskSourceDir(BaseModel):
    dir: str

class XmlDiskTargetDevEnum(Enum):
    vda = "vda"
    vdb = "vdb"
    sda = "sda"
    hda = "hda"
    xvda = "xvda"


class XmlDiskTargetBusEnum(Enum):
    """
    Шина, к которой подключается диск
    • virtio — самый быстрый (рекомендуется)
    • sata — если нужна совместимость
    • scsi — для множества дисков
    • ide — устаревший, медленный.
    """

    virtio = "virtio"
    ide = "ide"
    sata = "sata"
    scsi = "scsi"
    usb = "usb"


class XmlDiskTarget(BaseModel):
    """
    dev - Имя устройства в госте. Рекомендуется использовать vda, vdb при virtio.
    """

    dev: XmlDiskTargetDevEnum = XmlDiskTargetDevEnum.vda.value # имя устройства в гостевой ОС (vda, hda, sda и т.д.)
    bus: XmlDiskTargetBusEnum = XmlDiskTargetBusEnum.virtio.value #  тип шины (virtio, ide, scsi, usb и т.д.)
    removable: StateOnOff | None = None
    tray: StateOpenClosed | None = None #  только для CDROM (device='cdrom')


class XmlDiskAddress(BaseModel):
    """
    привязка к шине PCI (опционально)

    Если не указано — libvirt назначит автоматически.
    """
    type: str
    domain: str
    bus: str
    slot: str
    function: str

class XmlDiskBoot(BaseModel):
    order: str = "N"


class XmlDiskAlias(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)

    @field_validator('name', mode='before')
    @classmethod
    def add_ua_prefix(cls, v: str) -> str:
        """Автоматически добавляет префикс ua- если его нет"""
        if isinstance(v, str):
            v = v.strip()
            if not v.startswith('ua-'):
                # Убираем возможные лишние префиксы и добавляем ua-
                v = v.lstrip('dev-').lstrip('virt-').lstrip('libvirt-')
                v = f"ua-{v}"

            # Убедимся, что после ua- есть ещё символы
            if len(v) <= 3:  # только "ua-"
                raise ValueError("Имя алиаса слишком короткое после добавления префикса")

            # Проверяем допустимые символы (буквы, цифры, дефисы, подчёркивания)
            suffix = v[3:]  # часть после ua-
            if not all(c.isalnum() or c in '-_' for c in suffix):
                raise ValueError(
                    f"Алиас может содержать только буквы, цифры, дефисы и подчёркивания. "
                    f"Получено: {v}"
                )

            # Рекомендуем строчные буквы для консистентности
            v = v.lower()

        return v

    @field_validator('name', mode='after')
    @classmethod
    def validate_alias_format(cls, v: str) -> str:
        """Дополнительная валидация формата"""
        # Гарантируем, что префикс есть
        if not v.startswith('ua-'):
            raise ValueError(f"Алиас должен начинаться с 'ua-'. Получено: {v}")

        # Проверяем длину
        if len(v) > 50:
            raise ValueError(f"Алиас слишком длинный (макс. 50 символов). Получено: {v}")

        return v

    def __str__(self) -> str:
        return self.name


class XmlDiskGeometry(BaseModel):
    cyls: int
    heads: int
    secs: int
    trans: str


class XmlDiskBlockIo(BaseModel):
    logical_block_size: int = 512
    physical_block_size: int = 4096

    total_bytes_sec: int | None = 10485760 # <!-- 10 MB/s -->
    read_bytes_sec: int | None = 5242880 # <!-- 5 MB/s чтение -->
    write_bytes_sec: int | None = 5242880 #  <!-- 5 MB/s запись -->
    total_iops_sec: int | None = 1000 # <!-- 1000 IOPS всего -->
    read_iops_sec: int | None = 500 # <!-- 500 IOPS чтение -->
    write_iops_sec: int | None = 500 # <!-- 500 IOPS чтение -->

class XmlDiskIoTune(BaseModel):
    """
    Вложенные разметки воспринимаются как параметры - поэтому не создаем для них отдельные классы так как это избыточно
    """
    total_bytes_sec: int | None = 10485760 # <!-- 10 MB/s -->
    read_bytes_sec: int | None = 5242880 # <!-- 5 MB/s чтение -->
    write_bytes_sec: int | None = 5242880 #  <!-- 5 MB/s запись -->
    total_iops_sec: int | None = 1000 # <!-- 1000 IOPS всего -->
    read_iops_sec: int | None = 500 # <!-- 500 IOPS чтение -->
    write_iops_sec: int | None = 500 # <!-- 500 IOPS чтение -->
    size_iops_sec: int | None = 4294967295 # <!-- макс IOPS при burst -->


class XmlDiskSerial(BaseModel):
    value: str

class XmlDisk(BaseModel):
    type: XmlDiskType = XmlDiskType.file
    device: XmlDiskDeviceType = XmlDiskDeviceType.disk
    driver: XmlDiskDriver | None = None # XmlDiskDriver(name="test") - для тестирования
    source: XmlDiskSourceFile | XmlDiskSourceBlock | XmlDiskSourceNetwork | XmlDiskSourceDir | XmlDiskSourceVolume | XmlDiskSourcCDRome = XmlDiskSourceFile(file="/var/lib/libvirt/images/vm-root.qcow2")
    target: XmlDiskTarget = XmlDiskTarget()
    address: XmlDiskAddress | None = None
    readonly: EnableParam | None = None # Диск только для чтения (полезно для ISO).
    shareable: EnableParam | None = None # Диск может быть подключён к нескольким ВМ одновременно (только для block или network).
    serial: XmlDiskSerial | None = None
    boot: XmlDiskBoot | None = None
    alias: XmlDiskAlias | None = None
    geometry: XmlDiskGeometry | None = None # Устаревшее: задаёт геометрию диска (обычно не нужно).
    blockio: XmlDiskBlockIo | None = None # Для точной настройки блоков (редко).
    iotune: XmlDiskIoTune | None = None # Ограничение I/O (полезно в мультитенантных средах)

    """
    <target dev='DEV' bus='BUS'/>
  <address .../>
  <readonly/> или <shareable/>
  <boot order='N'/>
  """
