from pydantic import BaseModel, field_validator

from agent.client.hypervisor.libvirt.models.enum import NetworkType, NetworkModel


class VMNetwork(BaseModel):
    """Модель сетевого интерфейса ВМ"""
    network_type: NetworkType | str = NetworkType.NETWORK
    source: str = "default"
    model: NetworkModel | str = NetworkModel.VIRTIO
    mac_address: str | None = None
    boot_order: int | None = None

    @field_validator('mac_address')
    def validate_mac(cls, v):
        """Валидация MAC адреса"""
        if v is None:
            return v
        if len(v) != 17 or v.count(':') != 5:
            raise ValueError("Неверный формат MAC адреса (должен быть XX:XX:XX:XX:XX:XX)")
        return v


    @field_validator("network_type")
    def validate_network_type(cls, v):
        NetworkType(v)
        return v


    @field_validator("model")
    def validate_model(cls, v):
        NetworkModel(v)
        return v
