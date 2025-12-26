from pydantic import field_validator, BaseModel

from agent.client.hypervisor.libvirt.models.enum import ControllerType


class VMController(BaseModel):
    """Модель контроллера ВМ"""
    controller_type: ControllerType
    index: int = 0
    model: str | None = None
    ports: int | None = None

    @field_validator("model")
    def set_default_model(cls, v, values):
        """Установка модели контроллера по умолчанию"""
        if v is None:
            controller_type = values.get('controller_type')
            default_models = {
                ControllerType.USB: "qemu-xhci",
                ControllerType.SCSI: "virtio-scsi",
                ControllerType.SATA: "ahci",
                ControllerType.IDE: "piix4-ide",
                ControllerType.PCI: "pcie-root",
                ControllerType.VIRTIO_SERIAL: "virtio-serial",
            }
            return default_models.get(controller_type, None)
        return v
