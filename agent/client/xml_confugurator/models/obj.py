from enum import Enum

from pydantic import BaseModel

from agent.client import CLIControl
from agent.client import XmlVCpu, XmlCpu
from agent.client import XmlDisk
from agent.client import PowerPCFeatures, ARMFeatures, X86Features
from agent.client.xml_confugurator.models.general import ProcessorArchitecture, MachineOS, TypeOS, NvramModel, \
    DomainVirtualizationType
from agent.client.xml_confugurator.models.loader import ConfigurationLoader
from agent.client.xml_confugurator.models.memory import MemoryXml, CurrentMemory
from agent.client import XmlOnPowerOff, XmlOnReboot, XmlOnCrash
from agent.client import XmlClock

cli = CLIControl()

class BootDevEnum(Enum):
    hd = "hd" # Жесткий диск
    cdrom = "cdrom" # CD/DVD привод
    network = "network" # Сетевая загрузка (PXE)
    fd = "fd" # Флоппи-диск (устаревшее)
    usb_disk = "usb-disk" # Загрузка с USB
    sd = "sd" # Загрузка с SD карты
    pci = "pci" # Загрузка с PCI устройства


class BootEnableEnum(Enum):
    yes = "yes" # Включить устройство в boot order
    no = "no" # Исключить устройство из boot order
    none = "none" # Если не указано, по умолчанию 'yes'


class BootLoadParmLoadEnum(Enum):
    linux = "LINUX"
    first = "1"
    second = "2"
    lnxboot = "LNXBOOT"


class BootLoad(BaseModel):
    dev: BootDevEnum = BootDevEnum.hd
    enable: BootEnableEnum = BootEnableEnum.yes
    loadparm: BootLoadParmLoadEnum | None = None


class BootLoadList(BaseModel):
    boot_loads: list[BootLoad] = [BootLoad()]


class ConfigurationOSType(BaseModel):
    arch: ProcessorArchitecture = ProcessorArchitecture.x86_64_bit
    machine: MachineOS = MachineOS.pc_q35_7_2.virt_7_2
    value: TypeOS = TypeOS.HVM


class BootOSConfiguration(Enum):
    dev: BootDevEnum


class XmlOS(BaseModel):
    type: ConfigurationOSType = ConfigurationOSType()
    loader: ConfigurationLoader | None = None
    nvram: NvramModel | None = None
    boot: BootLoadList | None = None


class XmlEmulator(BaseModel):
    # TODO: Добавить автоматический поиск доступных эмуляторов в системе и возможность установки дополнительных эмуляторов
    value: str = cli.default_emulator



class XmlDevices(BaseModel):
    emulator: XmlEmulator = XmlEmulator()
    disk: list[XmlDisk] = [XmlDisk()]
    # interface: list[XmlInterface] = [XmlDisk()]

class XmlObject(BaseModel):
    id: int | None = None # нельзя указать при создании, только при редактировании
    type: DomainVirtualizationType = DomainVirtualizationType.KVM

    """
    <!-- Латинские буквы, цифры, дефисы, подчеркивания -->
    <name>web-server-01</name>
    <name>db_vm_2</name>
    <name>test-machine</name>

    <!-- НЕ используйте: -->
    <!-- <name>web server</name> -->      <!-- пробелы -->
    <!-- <name>vm@prod</name> -->         <!-- специальные символы -->
    <!-- <name>.hidden</name> -->         <!-- начинается с точки -->
    <!-- <name>192.168.1.100</name> -->   <!-- похоже на IP -->
    """
    name: str
    memory: MemoryXml = MemoryXml() # максимальная память
    current_memory: CurrentMemory = CurrentMemory(value=128) # текущий выделенный объем памяти
    vcpu: XmlVCpu = XmlVCpu() # виртуальные процессоры
    os: XmlOS = XmlOS()
    features: PowerPCFeatures | ARMFeatures | X86Features | None = None
    cpu: XmlCpu | None = None
    clock: XmlClock | None = None
    on_poweroff: XmlOnPowerOff | None = None
    on_reboot: XmlOnReboot | None = None
    on_crash: XmlOnCrash | None = None
    devices: XmlDevices = XmlDevices()
