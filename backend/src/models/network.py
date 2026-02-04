from datetime import datetime
from ipaddress import IPv4Network, IPv6Network

from pydantic import (
    BaseModel,
    Field,
    IPvAnyAddress,
    IPvAnyNetwork,
    field_validator,
    model_validator,
)

from src.models.enum_model import NetworkModelEnum, NetworkType


class DNSForwarder(BaseModel):
    """Модель для настройки DNS форвардера"""

    domain: str | None = None  # Домен для которого применяется форвардер (опционально)
    addr: str  # IP адрес DNS сервера

    @model_validator(mode="after")
    def validate_mode(self):
        IPvAnyNetwork(self.addr)

        return self


class DNSHost(BaseModel):
    """Модель для статических DNS записей хостов"""

    ip: str  # IP адрес
    hostnames: list[str]  # Список имен хостов для этого IP

    @model_validator(mode="after")
    def validate_mode(self):
        IPvAnyNetwork(self.ip)

        return self


class DNSTXT(BaseModel):
    """Модель для TXT записей DNS"""

    name: str  # Имя записи (например, example.com или _domainkey.example.com)
    value: str  # Значение TXT записи


# Дополнительные модели для типов сетей
class NetworkTypeInfo(BaseModel):
    """Информация о типе сети"""

    type: str  # nat, route, bridge, isolated, private, vepa, passthrough, no-forward
    is_isolated: bool = False
    has_dhcp: bool = False
    has_ipv4: bool = False
    has_ipv6: bool = False
    has_bridge: bool = False
    description: str = ""


# Модели Pydantic для валидации параметров
class NetworkDHCPRange(BaseModel):
    start: IPvAnyAddress | str = Field(..., description="Стартовый диапазон IP адресов")
    end: IPvAnyAddress | str = Field(..., description="Конечный диапазон IP адресов")

    @model_validator(mode="after")
    def validate_mode(self):
        if isinstance(self.start, str):
            IPvAnyNetwork(self.start)
        if isinstance(self.end, str):
            IPvAnyNetwork(self.end)
        return self


class NetworkDHCPHost(BaseModel):
    mac: str = Field(pattern=r"^([0-9A-Fa-f]{2}:){5}([0-9A-Fa-f]{2})$")
    ip: IPvAnyAddress
    name: str | None = None


class NetworkForward(BaseModel):
    mode: str = Field(
        default="nat", pattern="^(nat|route|bridge|private|vepa|passthrough)$"
    )
    dev: str | None = None
    interface: str | None = None

    @model_validator(mode="before")
    def validate_mode(cls, v):
        valid_modes = ["nat", "route", "bridge", "private", "vepa", "passthrough"]
        if v.get("mode") not in valid_modes:
            raise ValueError(
                f"Недопустимый режим форвардинга: {v}. Допустимые: {valid_modes}"
            )
        return v


class NetworkBridge(BaseModel):
    name: str | None = Field(
        default=None, description="Имя bridge-интерфейса на хосте (например, virbr0)"
    )
    stp: str | None = Field(
        None,
        pattern="^(on|off)$",
        description="Spanning Tree Protocol (вкл/выкл) для защиты от петель в сети",
    )  # default="on"
    delay: int | None = Field(
        None, ge=0, description="Задержка перед активацией порта bridge (секунды)"
    )  # default=0
    zone: str | None = Field(
        default=None,
        description=" Зона фаервола для bridge (например, trusted, public)",
    )


class NetworkRoute(BaseModel):
    address: IPvAnyNetwork = Field(..., description="IP адрес роутера")
    gateway: IPvAnyAddress | None = Field(
        default=None,
        description="это IP-адрес устройства (обычно роутера), через которое ваша сеть общается с внешним миром",
    )
    metric: str | None = Field(
        default=1,
        ge=1,
        description="Число от 1 до ∞, которое показывает 'стоимость' маршрута. Чем меньше метрика — тем предпочтительнее маршрут",
    )


class NetworkDNSHost(BaseModel):
    ip: IPvAnyAddress
    hostname: str | None = None

    @model_validator(mode="after")
    def validate_mode(self):
        if self.hostnames:
            for hostname in self.hostnames:
                IPvAnyNetwork(hostname)

        return self


class NetworkDNSSRV(BaseModel):
    """DNS SRV (Service) запись - указывает расположение сетевых сервисов"""

    service: str = Field(
        description="Имя сервиса без подчеркивания: ldap, kerberos, minecraft, sip"
    )
    protocol: str = Field(
        "tcp", pattern="^(tcp|udp)$", description="Транспортный протокол: tcp или udp"
    )
    target: str = Field(
        description="Полное доменное имя (FQDN) хоста, предоставляющего сервис"
    )
    port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="Номер порта сервиса (1-65535). Обязателен для большинства сервисов",
    )
    priority: int | None = Field(
        default=0,
        ge=0,
        description="Приоритет сервера (0-65535). Меньше = выше приоритет. Клиент выбирает сервер с наименьшим значением",
    )
    weight: int | None = Field(
        default=0,
        ge=0,
        description="Вес для балансировки нагрузки (0-65535). Используется при равных приоритетах для распределения трафика",
    )


class NetworkDNS(BaseModel):
    forwarders: list[IPvAnyAddress] | None = Field(
        default=None,
        description="Список пробросов сетевого трафика из виртуальной сети наружу",
    )
    hosts: list[NetworkDNSHost] | None = Field(
        default=None,
        description="Статические записи 'имя → IP' для всех ВМ в сети (как общий /etc/hosts",
    )
    txt_records: list[DNSTXT] | None = Field(
        default=None,
        description="Текстовые записи DNS для верификации, SPF-почты и метаданных",
    )
    srv_records: list[NetworkDNSSRV] | None = Field(
        default=None,
        description="Указывает, где находятся сетевые сервисы (не только IP, но и порт, протокол, приоритет)",
    )
    domain_name: str | None = Field(
        default=None,
        description="Добавляет домен к любым коротким именам (hostnames), которые разрешаются через DNS в этой виртуальной сети",
    )
    local_only: bool | None = Field(
        default=False, description="блокировка внешнего DNS (только локальные записи)"
    )


class NetworkParameters(BaseModel):
    name: str = Field(..., description="Имя виртуальной сети")
    uuid: str | None = Field(
        default=None, description="Индентификатор виртуальной сети"
    )
    bridge: NetworkBridge | None = Field(
        default=None,
        description="Соединяет виртуальные машины напрямую с физической сетью хоста",
    )
    forward: NetworkForward | None = Field(
        default=None, description="Проброс сетевого трафика из виртуальной сети наружу"
    )
    ipv4: bool | None = Field(default=True, description="Включен ли режим IPv4 сети")
    ipv6: bool | None = Field(default=Field(), description="Включен ли режим IPv6 сети")
    ipv4_address: IPv4Network | None = Field(default=None, description="IPv4 адрес")
    ipv6_address: IPv6Network | None = Field(default=None, description="IPv6 адрес")
    dhcp_ranges: list[NetworkDHCPRange] | None = Field(
        default=None,
        description="Доступный диапазон адресов для устройств в вирутальной сети",
    )
    dhcp_hosts: list[NetworkDHCPHost] | None = Field(
        default=None,
        description="Статическая DHCP-резервация в рамках виртуальной сети для закрепления статичных ip за конкретными сервисами в рамках DHCP",
    )
    routes: list[NetworkRoute] | None = Field(
        default=None,
        description="Статический маршрут, который автоматически добавляется всем ВМ в виртуальной сети. Он говорит: 'Трафик в такую-то подсеть отправляй через такой-то шлюз'",
    )
    dns: NetworkDNS | None = Field(
        default=None,
        description="DNS в libvirt - это локальный DNS-сервер для виртуальной сети, который: разрешает имена между ВМ, форвардит запросы наружу, хранит локальные записи",
    )
    mtu: int | None = Field(
        default=1500,
        ge=68,
        le=65535,
        description="MTU - это максимальный размер пакета данных, который может быть передан по сети за один раз",
    )
    trust_guest_rx_filters: bool | None = Field(
        default=False,
        description="Это параметр безопасности виртуальной сети в libvirt, который контролирует, доверять ли настройкам фильтрации трафика от гостевой ОС (ВМ)",
    )
    isolated: bool | None = Field(
        default=False,
        description="Полностью изолированная виртуальная сеть - ВМ могут общаться только друг с другом внутри сети, без какого-либо доступа наружу",
    )
    domain_name: str | None = Field(
        default=None,
        description="Добавляет домен к любым коротким именам (hostnames), которые разрешаются через DNS в этой виртуальной сети",
    )
    gateway: str | None = Field(
        default=None,
        description="это IP-адрес устройства (обычно роутера), через которое ваша сеть общается с внешним миром",
    )
    dns_forwarders: list[DNSForwarder] | None = Field(
        default=None,
        description="Внешние DNS-серверы, куда перенаправлять запросы из виртуальной сети",
    )
    dns_hosts: list[DNSHost] | None = Field(
        default=None, description="Локальные записи для имён в виртуальной сети"
    )
    dns_txts: list[DNSTXT] | None = Field(
        default=None,
        description="Текстовые записи DNS для верификации, SPF-почты и метаданных",
    )
    autostart: bool = Field(
        default=False,
        description="Автозапуск виртуальной сети работает только при перезагрузке самого хоста",
    )

    @model_validator(mode="after")
    def validate_mode(self):
        if isinstance(self.ipv4_address, str):
            IPvAnyNetwork(self.ipv4_address)
        if isinstance(self.ipv6_address, str):
            IPvAnyNetwork(self.ipv6_address)
        if self.forward and self.forward.dev and self.bridge and self.bridge.name:
            raise ValueError(
                "Для bridge-сети нужно указать либо <bridge name>, либо <forward dev>, но не оба одновременно"
            )
        if self.forward and self.forward.mode == "bridge":
            if (
                self.bridge.delay is not None
                or self.bridge.stp is not None
                or self.bridge.zone is not None
            ):
                raise ValueError(
                    "Параметры delay, stp, zone не поддерживаются в режиме forward mode='bridge'"
                )
        return self

    @field_validator("isolated")
    def validate_isolated(cls, v, values):
        """Валидация: изолированная сеть не может иметь forward"""
        values = values.data
        if v and "forward" in values and values["forward"]:
            raise ValueError(
                "Изолированная сеть (isolated=True) не может иметь forward параметр"
            )
        return v

    @field_validator("forward")
    def validate_forward_mode(cls, v, values):
        """Валидация режимов форвардинга"""
        values_data = values.data
        if v and values_data.get("isolated"):
            raise ValueError(
                "Сеть с forward параметром не может быть изолированной (isolated=True)"
            )
        return v

    @field_validator("bridge")
    def validate_bridge_for_routed(cls, v, values):
        """Валидация: routed сети не используют bridge"""
        values_data = values.data
        if values_data.get("forward"):
            if v and values_data.get("forward"):
                if values_data.get("forward") == "route":
                    raise ValueError(
                        "Routed сети (forward.mode='route') не используют bridge"
                    )
        return v


class NetworkInfo(BaseModel):
    name: str = Field(..., description="Имя виртуальной сети")
    uuid: str = Field(..., description="Идентификатор виртуальной сети")
    bridge_name: str | None = Field(
        default=None, description="Имя bridge-интерфейса на хосте (например, virbr0)"
    )
    active: bool = Field(
        ..., description="Сеть, которая в данный момент запущена и готова к работе."
    )
    persistent: bool = Field(
        ...,
        description="Сеть, которая сохраняется в конфигурации libvirt после перезагрузки хоста.",
    )
    autostart: bool = Field(
        ...,
        description="Автозапуск виртуальной сети работает только при перезагрузке самого хоста",
    )
    network_type: NetworkTypeInfo = Field(..., description="Тип виртуальной сети")
    xml: str = Field(..., description="XML конфигурация виртуальной сети")
    gateway: str | None = Field(
        default=None,
        description="это IP-адрес устройства (обычно роутера), через которое ваша сеть общается с внешним миром",
    )
    dns_forwarders: list[DNSForwarder] = Field(
        ...,
        description="Внешние DNS-серверы, куда перенаправлять запросы из виртуальной сети",
    )
    dns_hosts: list[DNSHost] = Field(
        ..., description="Локальные записи для имён в виртуальной сети"
    )
    dns_txts: list[DNSTXT] = Field(
        ..., description="Текстовые записи DNS для верификации, SPF-почты и метаданных"
    )
    ipv4_address: IPvAnyNetwork | None = Field(default=None, description="IPv4 адрес")
    dhcp_ranges: list[NetworkDHCPRange] | None = Field(
        default=None,
        description="Диапазоны IP адресов, например от 192.168.0.2 до 192.168.0.100",
    )


class NetworkList(BaseModel):
    total: int
    items: list[NetworkInfo]


class VmNetAdapter(BaseModel):
    """Сетевой адаптер виртуальной машины для конфигурации подключения"""

    network_type: NetworkType = Field(
        default=NetworkType.NETWORK,
        description="Тип сетевого подключения: NETWORK (виртуальная сеть), BRIDGE (мост), DIRECT (прямой доступ) и др.",
    )
    model: NetworkModelEnum = Field(
        default=NetworkModelEnum.VIRTIO,
        description="Модель виртуального сетевого адаптера: VIRTIO (высокопроизводительный), E1000, RTL8139, VMXNET3",
    )
    mac_address: str | None = Field(
        default=None,
        description="MAC-адрес адаптера. Если не указан, будет сгенерирован автоматически",
    )
    source: str | None = Field(
        default="default",
        description="Источник подключения: имя виртуальной сети, bridge или физического интерфейса",
    )


class VmInfo(BaseModel):
    name: str
    uuid: str
    state: str
    has_guest_agent: bool


class NetworkInterfaceSourceInfo(BaseModel):
    active: int
    persistent: int
    autostart: int
    bridge: str
    uuid: str


class NetworkInterfaceSource(BaseModel):
    type: NetworkType
    name: str
    description: str
    network_info: NetworkInterfaceSourceInfo


class NetworkInterfaceDriver(BaseModel):
    name: str
    queues: str
    iommu: str
    description: str


class NetworkInterfaceLinkState(BaseModel):
    state: str
    description: str


class NetworkInterfaceRomBar(BaseModel):
    enabled: str
    description: str


class NetworkInterfaceFilter(BaseModel):
    name: str
    description: str


class NetworkInterfaceMtu(BaseModel):
    size: str
    description: str


class NetworkInterfaceCoalescing(BaseModel):
    enabled: str
    description: str


class NetworkInterface(BaseModel):
    """Сетевой интерфейс виртуальной машины"""

    interface_type: NetworkType = Field(
        description="Тип интерфейса: network (виртуальная сеть), bridge (мост), direct (прямой доступ) и др."
    )
    mac_address: str | None = Field(
        default=None,
        description="MAC-адрес интерфейса. Если не указан, генерируется автоматически",
    )
    model: str = Field(
        description="Модель виртуального сетевого адаптера: virtio, e1000, rtl8139, vmxnet3"
    )
    source: NetworkInterfaceSource = Field(
        description="Источник подключения интерфейса: имя сети, bridge или физического интерфейса"
    )
    host_interface: str = Field(
        description="Имя интерфейса на хосте (например, vnet0) для данного подключения"
    )
    driver: NetworkInterfaceDriver = Field(
        description="Настройки драйвера сетевого адаптера: имя, очереди, iommu"
    )
    link_state: NetworkInterfaceLinkState = Field(
        description="Состояние сетевого канала (up/down) и его описание"
    )
    boot_order: str | None = Field(
        default=None,
        description="Порядок загрузки для сетевой загрузки (PXE). None = не используется для загрузки",
    )
    boot_order_description: str | None = Field(
        default=None, description="Текстовое описание порядка загрузки интерфейса"
    )
    rom_bar: NetworkInterfaceRomBar = Field(
        description="Настройки ROM: включение/выключение и путь к файлу ROM"
    )
    filter: NetworkInterfaceFilter = Field(
        description="Сетевой фильтр для трафика: имя фильтра и его параметры"
    )
    mtu: NetworkInterfaceMtu = Field(
        description="Maximum Transmission Unit (максимальный размер пакета) интерфейса"
    )
    coalescing: NetworkInterfaceCoalescing = Field(
        description="Настройки коалесцирования прерываний для повышения производительности"
    )


class NetworkInterfacesList(BaseModel):
    count: int
    interfaces: list[NetworkInterface]


class NetworkInterfacesInfo(BaseModel):
    vm_info: VmInfo
    network_interfaces: NetworkInterfacesList


class NetworkBackup(BaseModel):
    name: str
    xml_config: str
    net_uuid: str
    autostart: bool
    was_active: bool
    bridge_name: str | None = Field(default=None)
    created_at: datetime
