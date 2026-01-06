import uuid

import pytest

from agent.client.hypervisor.libvirt.models.snapshots import SnapshotCreateRequest, SnapshotDeleteRequest
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags("SN‑02", "Создание снапшота остановленной ВМ")
def test_rp_01_rp_08_create_and_delete_resource_pool(snapshot_session, create_stopped_vm):
    """
    SN‑02: Создание снапшота остановленной ВМ

    Создать снапшот при выключенной ВМ. Убедиться, что снапшот сохраняет состояние дисков и конфигурации.
    """
    vm_name, request_id = create_stopped_vm
    description = f"snapshot-description-{uuid.uuid4()}"
    snapshot_name = "snapshot-" + vm_name
    snapshot_deleted = False
    try:
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
        # _______________________________Проверка наличия снапшота________________________________
        assert snapshot_info.name == snapshot_name
        assert snapshot_info.description == description
        assert snapshot_info.vm_name == vm_name
        assert snapshot_info.state.value == VMState.SHUTOFF.value
        assert snapshot_info.size_bytes > 0
    finally:
        # ______________________________Удаление снапшота(постусловие)_____________________________
        if not snapshot_deleted:
            delete_snapshot_info = snapshot_session.delete_snapshot(SnapshotDeleteRequest(vm_name=vm_name,
                                                                                          snapshot_name=snapshot_name,
                                                                                          remove_children=True),
                                                              request_id)
            assert delete_snapshot_info.message == CommandMessagesEnum.snapshot_successfully_deleted.value
            assert delete_snapshot_info.code == CommandMessagesEnum.snapshot_successfully_deleted.name
            assert delete_snapshot_info.success is True