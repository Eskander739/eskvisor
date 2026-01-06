import time
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import DiskType
from agent.client.hypervisor.libvirt.models.snapshots import SnapshotCreateRequest, SnapshotDeleteRequest
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.vm import VmUpdateRequest
from agent.client.tools import wait_while_not


@pytest.mark.tags("SN‑03", "Восстановление ВМ из снапшота")
def test_sn_03_restore_vm_from_snapshot(snapshot_session, create_stopped_vm, vm_session, storage_session):
    """
    SN‑03: Восстановление ВМ из снапшота

    Выбрать снапшот и выполнить restore. Проверить, что ВМ возвращается в состояние на момент снапшота.
    """
    vm_name, request_id = create_stopped_vm
    description = f"snapshot-description-{uuid.uuid4()}"
    snapshot_name = "snapshot-" + vm_name
    snapshot_deleted = False
    get_state = vm_session.get_vm_state_by_name
    try:
        # _____________________________Получение информации о ВМ_______________________________
        vm_info = vm_session.get_vm_by_name(vm_name, request_id)
        assert vm_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert vm_info.code == CommandMessagesEnum.vm_successfully_found.name
        # _____________________________Проверка отсутствия снапшота_______________________________
        get_snapshot_info = snapshot_session.get_current_snapshot(vm_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_not_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_not_found.name
        # ____________________________Создание снапшота работающей ВМ_____________________________
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
        assert snapshot_info.state.value == VMState.SHUTOFF.value
        assert snapshot_info.size_bytes > 0
        # _________________________________Проверка конфигурации ВМ___________________________________
        vm_config = snapshot_info.vm_config
        assert vm_config.name == vm_name
        assert vm_config.uuid == vm_info.vm_info.uuid
        assert vm_config.memory == vm_info.vm_info.memory
        assert vm_config.max_memory == vm_info.vm_info.max_memory
        assert vm_config.vcpus == vm_info.vm_info.vcpus
        # ____________________________________Изменение ресурсов ВМ____________________________________
        vm_session.shutoff_vm(vm_name, request_id, True)
        edit_vm_info = vm_session.edit_vm(vm_name, VmUpdateRequest(vcpus=3), request_id)
        assert edit_vm_info.message == CommandMessagesEnum.vm_edit_success.value
        assert edit_vm_info.code == CommandMessagesEnum.vm_edit_success.name
        assert wait_while_not(lambda: get_state(vm_name) == VMState.SHUTOFF.value)
        vm_get_info = vm_session.get_vm_by_name(vm_name, request_id)
        assert vm_get_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert vm_get_info.code == CommandMessagesEnum.vm_successfully_found.name
        assert vm_get_info.vm_info.vcpus == 3
        # ________________________________Восстановление ВМ из снапшота________________________________
        revert_vm_info = snapshot_session.revert_to_snapshot(vm_name, snapshot_name, request_id)
        assert revert_vm_info.message == CommandMessagesEnum.snapshot_revert_success.value
        assert revert_vm_info.code == CommandMessagesEnum.snapshot_revert_success.name
        # __________________Проверка конфигурации ВМ после восстановления из снапшота__________________
        assert wait_while_not(lambda: get_state(vm_name) == VMState.RUNNING.value)
        vm_get_info = vm_session.get_vm_by_name(vm_name, request_id)
        assert vm_get_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert vm_get_info.code == CommandMessagesEnum.vm_successfully_found.name
        assert vm_get_info.vm_info.vcpus == vm_info.vm_info.vcpus
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