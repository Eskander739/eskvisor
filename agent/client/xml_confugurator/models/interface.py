from enum import Enum

from pydantic import BaseModel

from agent.client.xml_confugurator.models.general import StateOnOff


class XmlInterfaceSourceNetwork(BaseModel):
    """
    Подключение к виртуальной сети libvirt (например, default, NAT). Самый распространённый вариант.
    """

    network: str = "default" # default — стандартная NAT-сеть libvirt (192.168.122.0/24)


class XmlInterfaceSourceBridge(BaseModel):
    """
    Прямое подключение к мосту хоста (например, br0).
    Используется для режима “мост” (bridge), когда ВМ получает IP из той же сети, что и хост.

    Подключение к мосту br0 (должен быть создан на хосте).
    ВМ получит IP через DHCP или вручную в той же подсети, что и хост.
    """

    bridge: str # default — стандартная NAT-сеть libvirt (192.168.122.0/24)


class XmlInterfaceSourceDirectEnum(Enum):
    vepa = "vepa" #  трафик идёт через внешний коммутатор (по умолчанию)
    bridge = "private" # как виртуальный мост
    private = "private" # изоляция от других ВМ
    passthrough = "passthrough" # полный контроль


class XmlInterfaceSourceDirect(BaseModel):
    """
    Прямое подключение к физическому интерфейсу хоста (macvtap или macvlan).
    Подходит для высокой производительности и изоляции.
    """

    dev: str  = "eth0"
    mode: XmlInterfaceSourceDirectEnum | None = None


class XmlInterfaceMacAddress(BaseModel):
    address: str


class XmlInterfaceModelEnum(Enum):
    virtio = "virtio" # Самый быстрый, рекомендуется. Требует драйвера в госте (Linux — есть, Windows — нужно установить virtio-drivers).
    e1000 = "e1000" # Эмуляция Intel E1000 (поддерживается Windows XP/Vista/7, старыми ОС). Медленнее, но совместимо.
    e1000e = "e1000e" # Современная версия E1000 (для Windows 10, Linux).
    rtl8139 = "rtl8139" # Устаревшая, но универсальная (поддерживается везде).
    pcnet = "pcnet" # Очень старая, минимальная производительность.


class XmlInterfaceModel(BaseModel):
    type: XmlInterfaceModelEnum = XmlInterfaceModelEnum.virtio.value


class XmlInterfaceDriverTXMode(Enum):
    """
    Режим передачи: iothread — лучше для нагрузки.
    """
    iothread = "iothread"
    timer = "timer"
    poo = "poo"


class XmlInterfaceDriver(BaseModel):
    name: str
    txmode: XmlInterfaceDriverTXMode = XmlInterfaceDriverTXMode.iothread.value
    ioeventfd: StateOnOff = StateOnOff.on.value # Оптимизация очередей (рекомендуется on).
    queues: int = 3 # Количество очередей для multiqueue — улучшает производительность при нагрузке.
                    # Требует поддержки в госте (ethtool -l eth0).

class XmlInterfaceInBound(BaseModel):
    """
    • average — средняя скорость (Kbps)
    • peak — пиковая<br>
    • burst — кратковременный всплеск
    """

    average: str = "1500"
    peak: str = "2000"
    burst: str = "5120"


class XmlInterfaceOutBound(BaseModel):
    """
    • average — средняя скорость (Kbps)
    • peak — пиковая<br>
    • burst — кратковременный всплеск
    """

    average: str = "1000"
    peak: str = "1500"
    burst: str = "5120"



class XmlInterfaceBandWidth(BaseModel):
    """
    Ограничение скорости
    """
    inbound: XmlInterfaceInBound = XmlInterfaceInBound()
    outbound: XmlInterfaceOutBound = XmlInterfaceOutBound()


class XmlInterfaceAddress(BaseModel):
    # <address type='pci' domain='0x0000' bus='0x01' slot='0x00' function='0x0'/>
    type: str
    domain: str
    bus: str
    slot: str
    function: str


class XmlInterface(BaseModel):
    mac_address: XmlInterfaceMacAddress | None = None
    source: XmlInterfaceSourceNetwork | XmlInterfaceSourceBridge | XmlInterfaceSourceDirect
    model: XmlInterfaceModel = XmlInterfaceModel()
    driver: XmlInterfaceDriver = XmlInterfaceDriver(name="test_driver")
    address: XmlInterfaceAddress | None = None
    bandwidth: XmlInterfaceBandWidth | None = None
    # TODO: source: hostdev	Проброс физического сетевого устройства (SR-IOV или USB-сетевуха). - добавить поддержку
    # TODO: source: ethernet	Ручное управление (редко, требует внешнего скрипта). - добавить поддержку
    # TODO: source: vhostuser	Для DPDK/vhost-user (используется в NFV, OpenStack). - добавить поддержку
