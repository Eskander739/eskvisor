from pydantic import BaseModel, Field, IPvAnyAddress, IPvAnyNetwork, validator, field_validator, model_validator

from agent.client.hypervisor.libvirt.models.enum import NetworkType, NetworkModel


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

    @model_validator(mode="before")
    def validate_mode(cls, v):
        valid_modes = ["nat", "route", "bridge", "private", "vepa", "passthrough"]
        if v.get("mode") not in valid_modes:
            raise ValueError(f"Недопустимый режим форвардинга: {v}. Допустимые: {valid_modes}")
        return v


class NetworkBridge(BaseModel):
    name: str | None = None
    stp: str | None = Field(None, pattern="^(on|off)$")  # default="on"
    delay: int | None = Field(None, ge=0) # default=0
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
    autostart: bool = False

    @model_validator(mode="after")
    def validate_mode(cls, values):
        if values.forward and values.forward.dev and values.bridge and values.bridge.name:
            raise ValueError("Для bridge-сети нужно указать либо <bridge name>, либо <forward dev>, но не оба одновременно")
        if values.forward and values.forward.mode == "bridge":
            if values.bridge.delay is not None or values.bridge.stp is not None or values.bridge.zone is not None:
                raise ValueError("Параметры delay, stp, zone не поддерживаются в режиме forward mode='bridge'")
        return values

    @field_validator("isolated")
    def validate_isolated(cls, v, values):
        """Валидация: изолированная сеть не может иметь forward"""
        values = values.data
        if v and "forward" in values and values["forward"]:
            raise ValueError("Изолированная сеть (isolated=True) не может иметь forward параметр")
        return v

    @field_validator("forward")
    def validate_forward_mode(cls, v, values):
        """Валидация режимов форвардинга"""
        values_data = values.data
        if v and values_data.get("isolated"):
            raise ValueError("Сеть с forward параметром не может быть изолированной (isolated=True)")
        return v

    @field_validator("bridge")
    def validate_bridge_for_routed(cls, v, values):
        """Валидация: routed сети не используют bridge"""
        values_data = values.data
        if values_data.get("forward"):
            if v and values_data.get("forward"):
                if values_data.get("forward") == "route":
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

class VmNetAdapter(BaseModel):
    """
            for i, net in enumerate(config.networks):
            net_cmd = f"--network "

            net_params = []

            if net.network_type == NetworkType.BRIDGE:
                net_params.append(f"bridge={net.source}")
            elif net.network_type == NetworkType.NETWORK:
                net_params.append(f"network={net.source}")
            elif net.network_type == NetworkType.USER:
                net_params.append("user")
            elif net.network_type == NetworkType.DIRECT:
                net_params.append(f"direct={net.source}")

            if net.model:
                net_params.append(f"model={net.model.value}")

            if net.mac_address:
                net_params.append(f"mac={net.mac_address}")

            net_cmd += ",".join(net_params)
            cmd_parts.append(net_cmd)
    """
    network_type: NetworkType = NetworkType.NETWORK
    model: NetworkModel = NetworkModel.VIRTIO
    mac_address: str | None = None
    source: str | None = "default"