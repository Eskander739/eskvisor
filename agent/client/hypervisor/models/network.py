from pydantic import BaseModel, Field, IPvAnyAddress, IPvAnyNetwork, validator, field_validator, model_validator


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
    start: IPvAnyAddress
    end: IPvAnyAddress


class NetworkDHCPHost(BaseModel):
    mac: str = Field(pattern=r"^([0-9A-Fa-f]{2}:){5}([0-9A-Fa-f]{2})$")
    ip: IPvAnyAddress
    name: str | None = None


class NetworkForward(BaseModel):
    mode: str = Field(default="nat", pattern="^(nat|route|bridge|private|vepa|passthrough)$")
    dev: str | None = None
    interface: str | None = None

    @model_validator(mode="after")
    def validate_mode(cls, v):
        valid_modes = ["nat", "route", "bridge", "private", "vepa", "passthrough"]
        if v not in valid_modes:
            raise ValueError(f"Недопустимый режим форвардинга: {v}. Допустимые: {valid_modes}")
        return v


class NetworkBridge(BaseModel):
    name: str | None = None
    stp: str | None = Field(default="on", pattern="^(on|off)$")
    delay: str | None = Field(default=0.0, ge=0.0)
    zone: str | None = None


class NetworkRoute(BaseModel):
    address: IPvAnyNetwork
    gateway: IPvAnyAddress | None = None
    metric: str | None = Field(default=1, ge=1)


class NetworkDNSHost(BaseModel):
    ip: IPvAnyAddress
    hostnames: list[str] | None = None


class NetworkDNSTXT(BaseModel):
    name: str
    value: str


class NetworkDNSSRV(BaseModel):
    service: str
    protocol: str = Field(pattern="^(tcp|udp)$")
    target: str
    port: int | None = Field(default=None, ge=1, le=65535)
    priority: int | None = Field(default=0, ge=0)
    weight: int | None = Field(default=0, ge=0)


class NetworkDNS(BaseModel):
    forwarders: list[IPvAnyAddress] | None = None
    hosts: list[NetworkDNSHost] | None = None
    txt_records: list[NetworkDNSTXT] | None = None
    srv_records: list[NetworkDNSSRV] | None = None
    domain: str | None = None
    local_only: bool | None = False


class NetworkParameters(BaseModel):
    name: str
    uuid: str | None = None
    bridge: NetworkBridge | None = None
    forward: NetworkForward | None = None
    ipv4: bool | None = True
    ipv6: bool | None = False
    ipv4_address: IPvAnyNetwork | None = None
    ipv6_address: IPvAnyNetwork | None = None
    dhcp_ranges: list[NetworkDHCPRange] | None = None
    dhcp_hosts: list[NetworkDHCPHost] | None = None
    routes: list[NetworkRoute] | None = None
    dns: NetworkDNS | None = None
    mtu: int | None = Field(default=1500, ge=68, le=65535)
    trust_guest_rx_filters: bool | None = False
    isolated: bool | None = False
    domain_name: str | None = None

    @field_validator("isolated")
    def validate_isolated(cls, v, values):
        """Валидация: изолированная сеть не может иметь forward"""
        if v and "forward" in values and values["forward"]:
            raise ValueError("Изолированная сеть (isolated=True) не может иметь forward параметр")
        return v

    @field_validator("forward")
    def validate_forward_mode(cls, v, values):
        """Валидация режимов форвардинга"""
        if v and "isolated" in values and values["isolated"]:
            raise ValueError("Сеть с forward параметром не может быть изолированной (isolated=True)")
        return v

    @field_validator("bridge")
    def validate_bridge_for_routed(cls, v, values):
        """Валидация: routed сети не используют bridge"""
        if v and "forward" in values and values["forward"]:
            if values["forward"].mode == "route":
                raise ValueError("Routed сети (forward.mode='route') не используют bridge")
        return v


class NetworkInfo(BaseModel):
    name: str
    uuid: str
    bridge_name: str | None = None
    active: bool
    persistent: bool
    autostart: bool
    network_type: NetworkTypeInfo
    xml: str
