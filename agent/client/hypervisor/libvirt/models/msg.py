from enum import Enum

from pydantic import BaseModel, model_validator

from agent.client.hypervisor.libvirt.models.disk import Disk
from agent.client.hypervisor.libvirt.models.network import NetworkInfo
from agent.client.hypervisor.libvirt.models.vm import VirtualMachine


class CommandMessagesEnum(Enum):
    vm_with_name_already_exists = "VM with name already exists"
    vm_created_but_not_found_in_libvirt = "VM created but not found in libvirt"
    vm_successfully_created = "VM successfully created"
    vm_successfully_deleted = "VM successfully deleted"
    vm_delete_error = "VM delete error"
    vm_create_error = "VM create error"
    vm_start_error = "VM start error"
    vm_stop_error = "VM stop error"
    vm_restart_error = "VM restart error"
    vm_shutdown_error = "VM shutdown error"
    vm_resume_error = "VM resumed error"
    vm_successfully_resumed = "VM successfully resumed"
    vm_successfully_shutdowned = "VM successfully shutdown"
    vm_successfully_started = "VM successfully started"
    vm_successfully_found = "VM successfully found"
    vm_found_error = "VM found error"
    vm_successfully_stopped = "VM successfully stopped"
    vm_successfully_restarted = "VM successfully restarted"
    vm_create_unexpected_error = "VM create unexpected error"
    vm_create_subprocess_timeout_error = "VM create subprocess timeout error"
    disk_convert_error = "Disk convert error"
    disk_not_found = "Disk not found"
    disk_founded = "Disk founded"
    disk_not_found_unexpected_error = "Disk not found unexpected error"
    disk_not_found_libvirt_error = "Disk not found libvirt error"
    disk_create_error = "Disk create error"
    disk_successfully_created = "Disk successfully created"
    disk_successfully_attached = "Disk successfully attached"
    disk_attach_error = "Disk attach error"
    disk_already_attached_error = "Disk already attached error"
    disk_already_created = "Disk already created"
    disk_attach_libvirt_error = "Disk attach libvirt error"
    disk_attach_unexpected_error = "Disk attach unexpected error"
    disk_convert_successfully = "Disk convert successfully"
    disk_not_found_by_target_dev = "Disk not found by target_dev"
    disk_founded_by_target_dev = "Disk founded by target_dev"
    vm_edit_success = "VM successfully edited"
    vm_edit_error = "VM edit error"
    vm_edit_xml_error = "VM edit XML error"
    vm_edit_unexpected_error = "VM edit unexpected error"
    virtual_network_successfully_created = "Virtual network successfully created"
    virtual_network_create_error = "Virtual network create error"
    virtual_network_successfully_deleted = "Virtual network successfully deleted"
    virtual_network_delete_error = "Virtual network delete error"
    virtual_network_founded = "Virtual network founded"
    virtual_network_not_found = "Virtual network not found"


class DefaultMessage(BaseModel):
    request_id: str
    message: CommandMessagesEnum | str
    code: CommandMessagesEnum | str

    @model_validator(mode="after")
    def validate_disk_type_constraints(cls, values):
        """
        Проверка условно обязательных полей в зависимости от типа
        """
        CommandMessagesEnum(values.message)

        for key, value in CommandMessagesEnum.__dict__.items():
            if values.code in key or values.code == key:
                break
        else:
            raise ValueError(f"Некорректный code: {values.code}")

        return values

class VmError(DefaultMessage):
    pass

class VmMessage(DefaultMessage):
    success: bool
    command: str | None = None
    vm_info: None | VirtualMachine = None
    stdout: str | None = None
    stderr: str | None = None
    note: str | None = None

class StorageMessage(DefaultMessage):
    target_path: str | None = None
    note: str | None = None
    disk_info: Disk | None = None
    stdout: str | None = None
    stderr: str | None = None

class NetworkMessage(DefaultMessage):
    success: bool
    net_info: NetworkInfo | None = None
    note: str | None = None