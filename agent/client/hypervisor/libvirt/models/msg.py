from enum import Enum

from pydantic import BaseModel, model_validator

from agent.client.hypervisor.libvirt.models.volume.disk import Disk
from agent.client.hypervisor.libvirt.models.network import (
    NetworkInfo,
    NetworkInterfacesInfo,
)
from agent.client.hypervisor.libvirt.models.volume.resource_pool import (
    AddVMInResourcePool,
    AdjustResourcePool,
    DeleteResourcePool,
    RemoveVMInResourcePool,
    ResourcePool,
    ResourcePoolList,
    ResourcePoolReservation,
    ResourcePoolState,
    ResourcePoolUpdates,
    ResourcePoolUsageInfo,
)
from agent.client.hypervisor.libvirt.models.snapshots import (
    ClonedSnapshot,
    CreateMultipleSnapshots,
    CreateMultipleSnapshotsError,
    CreateSnapshotChainError,
    CreateSnapshotChainSuccess,
    DeleteSnapshotInfo,
    SnapshotList,
    SnapshotRevertSuccess,
    SnapshotsChain,
    SnapshotWithParent,
)
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
    vm_successfully_add_to_cgroup = "VM successfully add to cgroup"
    vm_error_add_to_cgroup = "VM error add to cgroup"
    vm_error_remove_from_cgroup = "VM error remove from cgroup"
    vm_successfully_removed_from_cgroup = "VM successfully removed from cgroup"
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
    virtual_network_have_connected_vms = "Virtual network have connected vms"
    virtual_network_found = "Virtual network found"
    virtual_network_not_found = "Virtual network not found"
    virtual_network_interfaces_found = "Virtual network interfaces found"
    virtual_network_interface_detached = (
        "Virtual network interface successfully detached"
    )
    virtual_network_interface_detach_error = "Virtual network interface detach error"
    virtual_network_interface_not_found = "Virtual network interface not found"
    virtual_network_successfully_updated = "Virtual network successfully updated"
    virtual_network_update_error = "Virtual network updat error"
    virtual_network_successfully_started = "Virtual network successfully started"
    virtual_network_restart_error = "Virtual network restart error"

    # Ресурс пулы
    rp_success = "Resource pool operation successful"
    rp_error = "Resource pool operation error"

    rp_create_success = "Resource pool successfully created"
    rp_create_error = "Resource pool create error"
    rp_already_exists = "Resource pool with this name already exists"

    rp_delete_success = "Resource pool successfully deleted"
    rp_delete_error = "Resource pool delete error"
    rp_delete_not_empty_error = "Cannot delete non-empty resource pool"
    rp_not_found = "Resource pool not found"

    rp_edit_success = "Resource pool successfully edited"
    rp_edit_error = "Resource pool edit error"

    rp_resource_adjust_success = "Resource pool resource adjust success"
    rp_resource_adjust_error = "Resource pool resource adjust error"
    rp_insufficient_resources = "Insufficient resources in pool"
    rp_resource_in_use = "Resource cannot be reduced below current usage"

    rp_set_reservation_success = "Resource pool reservation set success"
    rp_set_reservation_error = "Resource pool reservation set error"
    rp_set_limit_success = "Resource pool limit set success"
    rp_set_limit_error = "Resource pool limit set error"

    rp_vm_add_success = "VM successfully added to resource pool"
    rp_vm_add_error = "VM add to resource pool error"
    rp_vm_remove_success = "VM successfully removed from resource pool"
    rp_vm_remove_error = "VM remove from resource pool error"
    rp_vm_not_found = "VM not found"

    rp_start_success = "Resource pool successfully started"
    rp_start_error = "Resource pool start error"
    rp_stop_success = "Resource pool successfully stopped"
    rp_stop_error = "Resource pool stop error"
    rp_already_running = "Resource pool already running"
    rp_already_stopped = "Resource pool already stopped"

    rp_usage_info_success = "Resource pool usage info retrieved"
    rp_info_success = "Resource pool info retrieved"
    rp_info_error = "Resource pool info error"
    rp_usage_info_error = "Resource pool usage info error"
    rp_list_success = "Resource pools list retrieved"
    rp_list_error = "Resource pools list error"

    # Снапшоты
    snapshot_successfully_created = "Snapshot successfully created"
    snapshot_create_error = "Snapshot create error"
    snapshot_successfully_deleted = "Snapshot successfully deleted"
    snapshot_delete_error = "Snapshot delete error"
    snapshot_revert_success = "Snapshot revert success"
    snapshot_revert_error = "Snapshot revert error"
    snapshot_update_success = "Snapshot update success"
    snapshot_update_error = "Snapshot update error"
    snapshot_found = "Snapshot found"
    snapshot_not_found = "Snapshot not found"
    snapshot_list_found = "Snapshot list found"
    snapshot_list_error = "Snapshot list error"
    snapshot_clone_success = "Snapshot clone success"
    snapshot_clone_error = "Snapshot clone error"
    snapshot_insufficient_space = "Insufficient space for snapshot"


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
    net_info: NetworkInfo | NetworkInterfacesInfo | None = None
    note: str | None = None


class RpMessage(DefaultMessage):
    """Сообщение для работы с пулами ресурсов"""

    success: bool
    rp_info: (
        ResourcePoolList
        | ResourcePool
        | AdjustResourcePool
        | AddVMInResourcePool
        | RemoveVMInResourcePool
        | ResourcePoolReservation
        | ResourcePoolUpdates
        | DeleteResourcePool
        | ResourcePoolUsageInfo
        | ResourcePoolState
        | None
    ) = None
    note: str | None = None


class SnapshotMessage(DefaultMessage):
    """Сообщение для работы с пулами ресурсов"""

    success: bool
    snapshot_info: (
        SnapshotWithParent
        | DeleteSnapshotInfo
        | SnapshotList
        | ClonedSnapshot
        | CreateSnapshotChainError
        | CreateSnapshotChainSuccess
        | CreateMultipleSnapshotsError
        | CreateMultipleSnapshots
        | SnapshotRevertSuccess
        | SnapshotsChain
        | None
    ) = None
    note: str | None = None
