from enum import Enum

from pydantic import BaseModel

from agent.client.hypervisor.libvirt.models.volume.disk import Disk, VMStorageUsedInfo
from agent.client.hypervisor.libvirt.models.network import (
    NetworkInfo,
    NetworkInterfacesInfo,
    NetworkList, NetworkBackup,
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
from agent.client.hypervisor.libvirt.models.vm import (
    VirtualMachine,
    VirtualMachinesList,
)
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtual, ResourcePoolVMS, ResourcePoolConnectedVMS,
)
from agent.client.hypervisor.libvirt.models.volume.logic import LogicVolume


class CommandMessagesEnum(Enum):
    # Виртуальные машины
    vm_storage_used_info = "VM storage used info"
    vm_storage_used_info_error = "VM storage used info error"
    vm_with_name_already_exists = "VM with name already exists"
    vm_successfully_deleted_from_virtual_resource_pool = (
        "VM successfully deleted from virtual resource pool"
    )
    vm_delete_error_from_virtual_resource_pool = (
        "VM delete error from virtual resource pool"
    )
    vm_created_but_not_found_in_libvirt = "VM created but not found in libvirt"
    vm_successfully_created = "VM successfully created"
    vm_delete_error_from_rp_config = "VM delete error from resource pool config"
    vm_successfully_deleted = "VM successfully deleted"
    vm_delete_error = "VM delete error"
    vm_successfully_cloned = "VM successfully cloned"
    vm_clone_error = "VM clone error"
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

    # Виртуальные диски
    disk_convert_error = "Disk convert error"
    disk_not_found = "Disk not found"
    disk_list_founded = "Disk list founded"
    disk_list_error = "Disk list error"
    disk_founded = "Disk founded"
    disk_not_found_unexpected_error = "Disk not found unexpected error"
    disk_not_found_libvirt_error = "Disk not found libvirt error"
    disk_create_error = "Disk create error"
    disk_successfully_cloned = "Disk successfully cloned"
    disk_clone_error = "Disk clone error"
    disk_successfully_extended = "Disk successfully extended"
    disk_extend_error = "Disk extend error"
    disk_detach_error = "Disk detach error"
    disk_successfully_detached = "Disk successfully detached"
    disk_delete_error = "Disk delete error"
    disk_successfully_deleted = "Disk successfully deleted"
    disk_successfully_created = "Disk successfully created"
    disk_successfully_attached = "Disk successfully attached"
    disk_already_attached_error = "Disk already attached error"
    disk_already_created = "Disk already created"
    disk_attach_libvirt_error = "Disk attach libvirt error"
    disk_attach_unexpected_error = "Disk attach unexpected error"
    disk_convert_successfully = "Disk convert successfully"
    disk_not_found_by_target_dev = "Disk not found by target_dev"
    disk_founded_by_target_dev = "Disk founded by target_dev"
    vm_edit_success = "VM successfully edited"
    vm_edit_error_unsupport_update_this_params_on_live_mode = (
        "Unsupport update this params on live mode"
    )
    vm_edit_error_in_shutoff_process = "VM edit error in shutoff process"
    can_not_change_cpu_model_on_running_vm = "Can not change cpu model on running VM"
    vm_edit_error = "VM edit error"
    vm_edit_unexpected_error = "VM edit unexpected error"
    virtual_network_successfully_created = "Virtual network successfully created"
    virtual_network_create_error = "Virtual network create error"
    virtual_network_successfully_deleted = "Virtual network successfully deleted"
    virtual_network_delete_error = "Virtual network delete error"
    virtual_network_have_connected_vms = "Virtual network have connected vms"
    virtual_network_found = "Virtual network found"
    virtual_network_not_found = "Virtual network not found"
    virtual_network_interfaces_found = "Virtual network interfaces found"
    virtual_network_interface_attach_error = "Virtual network interface attach error"
    virtual_network_interface_attached = "Virtual network interface attached"
    virtual_network_interface_detached = (
        "Virtual network interface successfully detached"
    )
    networks_list_found = "Networks list found"
    networks_list_not_found = "Networks list not found"
    virtual_network_backup_successfully_created = "Virtual network backup successfully created"
    virtual_network_backup_create_error = "Virtual network backup create error"
    virtual_network_interface_detach_error = "Virtual network interface detach error"
    virtual_network_interface_not_found = "Virtual network interface not found"
    virtual_network_successfully_updated = "Virtual network successfully updated"
    virtual_network_update_error = "Virtual network updat error"
    virtual_network_already_started = "Virtual network already started"
    virtual_network_start_error = "Virtual network start error"
    virtual_network_successfully_started = "Virtual network successfully started"
    virtual_network_successfully_stopped = "Virtual network successfully stopped"
    virtual_network_already_stopped = "Virtual network already stopped"
    virtual_network_stopping_error = "Virtual network stopping error"
    virtual_network_restart_error = "Virtual network restart error"

    # Ресурс пулы

    virtual_rp_create_success = "Virtual resource pool successfully created"
    virtual_rp_create_logic_volume_error = (
        "Virtual resource pool create logic volume error"
    )
    rp_ram_or_cpu_more_than_on_node = "Resource pool RAM/CPU more than on the node"
    rp_already_created = "Resource pool already"
    vm_list_is_correct = "VM List is correct"
    vm_list_found = "VM list found"
    vm_list_not_found = "VM list not found"
    rp_cpu_configuration_error = "Resource pool CPU configuration error"
    rp_ram_configuration_error = "Resource pool RAM configuration error"
    vm_can_not_reserve_resource_when_vm_not_in_virtual_rp = (
        "VM can't reserve resource when VM not in virtual resource pool"
    )
    vm_can_not_reserve_more_cpu_than_available_on_the_virtual_rp = (
        "VM can't reserve more CPU than available on the virtual resource pool"
    )

    vm_can_not_reserve_more_ram_than_available_on_the_virtual_rp = (
        "VM can't reserve more RAM than available on the virtual resource pool"
    )
    vm_can_not_reserve_less_ram_than_use = "VM can't reserve less RAM than use"
    vm_can_not_reserve_less_cpu_than_use = "VM can't reserve less CPU than use"
    rp_create_error = "Resource pool create error"
    vm_present_on_any_virtual_resource_pool = "VM present on any virtual resource pool"

    rp_virtual_delete_success = "Virtual resource pool successfully deleted"
    rp_virtual_config_edit_success = "Virtual resource pool config successfully edited"
    rp_virtual_config_successfully_founded = "Virtual resource pool config successfully founded"
    rp_virtual_edit_error = "Virtual resource pool edit error"
    file_in_use_by_another_process = "File in use by another process"
    rp_virtual_config_edit_error = "Virtual resource pool config edit error"
    rp_virtual_config_sync_error = "Virtual resource pool config sync error"
    rp_virtual_config_sync_success = "Virtual resource pool config sync successfully"
    rp_virtual_edit_success = "Virtual resource pool successfully edited"
    rp_virtual_successfully_found = "Virtual resource pool successfully found"
    rp_virtual_have_vm_need_use_force_for_delete = (
        "Virtual resource pool have VM, need use force for delete"
    )
    rp_virtual_delete_error = "Virtual resource pool delete error"
    rp_virtual_not_found = "Virtual resource pool not found"
    rp_virtual_found_error = "Virtual resource pool found error"

    # Снапшоты
    snapshot_successfully_created = "Snapshot successfully created"
    snapshot_create_error = "Snapshot create error"
    snapshots_successfully_deleted = "Snapshots successfully deleted"
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

    # Logic Volume
    edit_logic_volume_error = "Edit logic volume error"
    delete_logic_volume_error = "Delete logic volume error"
    for_live_migration_vm_need_to_running = "For live migration VM need to running"
    migration_completed_but_did_not_return_domain = (
        "Migration completed but did not return domain"
    )
    migration_successfully_completed = "Migration successfully completed"
    migration_successfully_completed_with_virsh = (
        "Migration successfully completed with virsh"
    )
    migration_with_disks_successfully_completed_with_virsh = (
        "Migration with disks successfully completed with virsh"
    )
    migration_without_disks_successfully_completed_with_virsh = (
        "Migration without disks successfully completed with virsh"
    )
    migration_error = "Migration error"
    migration_virsh_error = "Migration virsh error"
    migration_timeout_error_with_virsh = "Migration timeout error with virsh"

class DefaultMessage(BaseModel):
    code: str


class VmError(DefaultMessage):
    pass


class VmMessage(DefaultMessage):
    success: bool
    command: str | None = None
    vm_info: None | VirtualMachine | VirtualMachinesList = None
    stdout: str | None = None
    stderr: str | None = None
    note: str | None = None


class StorageMessage(DefaultMessage):
    success: bool
    target_path: str | None = None
    note: str | None = None
    disk_info: Disk | LogicVolume | list[Disk] | VMStorageUsedInfo | None = None
    stdout: str | None = None
    stderr: str | None = None


class NetworkMessage(DefaultMessage):
    success: bool
    net_info: NetworkInfo | NetworkInterfacesInfo | NetworkList | NetworkBackup | None = None
    note: str | None = None


class RpMessage(DefaultMessage):
    """Сообщение для работы с пулами ресурсов"""

    success: bool
    rp_info: ResourcePoolVirtual | ResourcePoolVMS | ResourcePoolConnectedVMS | None = None
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
