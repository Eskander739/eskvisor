import uuid

import pytest

from agent.client.hypervisor.libvirt.models.snapshots import SnapshotCreateRequest, SnapshotDeleteRequest, \
    SnapshotCloneRequest
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.tools import wait_while_not


@pytest.mark.tags("SN‑05", "Клонирование ВМ из снапшота")
@pytest.mark.parametrize("vm_state", (VMState.SHUTOFF, VMState.RUNNING, VMState.PAUSED))
def test_sn_05_clone_vm_from_snapshot(snapshot_session, create_running_vm_func, vm_session, storage_session, vm_state):
    """
    SN‑05: Клонирование ВМ из снапшота

    Создать новую ВМ на основе снапшота. Проверить, что клон идентичен исходной ВМ на момент снапшота.
    """
    vm_name, request_id = create_running_vm_func
    description = f"snapshot-description-{uuid.uuid4()}"
    snapshot_name = "snapshot-" + vm_name
    new_vm_name = "CLONED_VM_" + vm_name
    snapshot_deleted = False
    cloned_vm_created = False
    get_state = vm_session.get_vm_state_by_name
    try:
        # _____________________________Получение информации о ВМ_______________________________
        if vm_state.value == VMState.SHUTOFF.value:
            vm_session.shutoff_vm(vm_name, request_id, True)
            assert wait_while_not(lambda: get_state(vm_name) == VMState.SHUTOFF.value)
        elif vm_state.value == VMState.PAUSED.value:
            vm_session.suspend_vm(vm_name, request_id)
            assert wait_while_not(lambda: get_state(vm_name) == VMState.PAUSED.value)
        else:
            assert wait_while_not(lambda: get_state(vm_name) == VMState.RUNNING.value)
        vm_info = vm_session.get_vm_by_name(vm_name, request_id)
        assert vm_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert vm_info.code == CommandMessagesEnum.vm_successfully_found.name
        # _____________________________Проверка отсутствия снапшота_______________________________
        get_snapshot_info = snapshot_session.get_current_snapshot(vm_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_not_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_not_found.name
        # __________________________________Создание снапшота ВМ__________________________________
        vm_template = SnapshotCreateRequest(vm_name=vm_name,
                                            snapshot_name=snapshot_name,
                                            description=description)
        create_vm_info = snapshot_session.create_snapshot(vm_template, request_id)
        assert create_vm_info.message == CommandMessagesEnum.snapshot_successfully_created.value
        assert create_vm_info.code == CommandMessagesEnum.snapshot_successfully_created.name
        assert create_vm_info.snapshot_info is not None
        snapshot_info = create_vm_info.snapshot_info
        # ________________________________Проверка наличия снапшота___________________________________
        assert snapshot_info.name == snapshot_name
        assert snapshot_info.description == description
        assert snapshot_info.vm_name == vm_name
        assert snapshot_info.state.value == vm_state.value
        assert snapshot_info.size_bytes > 0
        # _________________________________Проверка конфигурации ВМ___________________________________
        vm_config = snapshot_info.vm_config
        assert vm_config.name == vm_name
        assert vm_config.uuid == vm_info.vm_info.uuid
        assert vm_config.memory == vm_info.vm_info.memory
        assert vm_config.max_memory == vm_info.vm_info.max_memory
        assert vm_config.vcpus == vm_info.vm_info.vcpus
        # ________________________________Клонирование ВМ из снапшота________________________________
        revert_vm_info = snapshot_session.clone_vm_from_snapshot(SnapshotCloneRequest(source_vm_name=vm_name,
                                                                                      source_snapshot_name=snapshot_name,
                                                                                      new_vm_name=new_vm_name),
                                                                 request_id)
        assert revert_vm_info.message == CommandMessagesEnum.snapshot_clone_success.value
        assert revert_vm_info.code == CommandMessagesEnum.snapshot_clone_success.name
        # ___________________Проверка конфигурации ВМ после клонирования из снапшота___________________
        get_vm_info = vm_session.get_vm_by_name(new_vm_name, request_id)
        assert get_vm_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert get_vm_info.code == CommandMessagesEnum.vm_successfully_found.name
        cloned_vm_created = True
        vm_config = get_vm_info.vm_info
        assert vm_config.name == new_vm_name
        assert vm_config.uuid != vm_info.vm_info.uuid
        assert vm_config.memory == vm_info.vm_info.memory
        assert vm_config.max_memory == vm_info.vm_info.max_memory
        assert vm_config.vcpus == vm_info.vm_info.vcpus
        assert wait_while_not(lambda: get_state(vm_name) == vm_state.value)
        # ______________________Проверка дисков ВМ после клонирования из снапшота______________________
        disks_cloned_vm = sorted(storage_session.get_disks_by_vm(new_vm_name, request_id))
        disks_vm = sorted(storage_session.get_disks_by_vm(vm_name, request_id))
        for disk_cloned, just_disk in zip(disks_cloned_vm, disks_vm):
            assert disk_cloned.name != just_disk.name
            assert disk_cloned.path != just_disk.path
            assert disk_cloned.type.value == just_disk.type.value
            assert disk_cloned.bus_type.value == just_disk.bus_type.value
            assert disk_cloned.format.value == just_disk.format.value
            assert disk_cloned.target_dev == just_disk.target_dev
            assert disk_cloned.capacity_bytes == just_disk.capacity_bytes
            assert disk_cloned.file_path_exists is True
            assert just_disk.file_path_exists is True
            assert just_disk.vm_name == vm_name
            assert disk_cloned.vm_name == new_vm_name
    finally:
        # ______________________________Удаление снапшота(постусловие)_________________________________
        if not snapshot_deleted:
            delete_snapshot_info = snapshot_session.delete_snapshot(SnapshotDeleteRequest(vm_name=vm_name,
                                                                                          snapshot_name=snapshot_name,
                                                                                          remove_children=True),
                                                              request_id)
            assert delete_snapshot_info.message == CommandMessagesEnum.snapshot_successfully_deleted.value
            assert delete_snapshot_info.code == CommandMessagesEnum.snapshot_successfully_deleted.name
            assert delete_snapshot_info.success is True
        # ____________________________________Удаление ВМ(постусловие)____________________________________
        if cloned_vm_created:
            delete_vm_info = vm_session.delete_vm_with_force(name=new_vm_name, request_id=request_id)
            assert delete_vm_info.message == CommandMessagesEnum.vm_successfully_deleted.value
            assert delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            assert delete_vm_info.success is True