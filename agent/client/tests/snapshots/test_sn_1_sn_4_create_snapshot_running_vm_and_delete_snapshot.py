import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.snapshots import SnapshotCreateRequest, SnapshotDeleteRequest
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest, VirtualMachine
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.tools import wait_while_not


@pytest.mark.tags("SN‑01", "SN‑04", "Создание снапшота работающей ВМ", "Удаление снапшота")
def test_rp_01_rp_08_create_and_delete_resource_pool(snapshot_session, create_running_vm):
    """
    SN‑01: Создание снапшота работающей ВМ
    SN‑04: Удаление снапшота

    Создать снапшот без остановки ВМ. Проверить, что снапшот появляется в дереве снапшотов ВМ.
    Удалить отдельный снапшот. Убедиться, что место освобождается и дерево снапшотов корректно обновляется.
    """
    random_name, request_id = create_running_vm
    snapshot_name = "snapshot-" + random_name
    snapshot_deleted = False
    try:
        # _____________________________Проверка отсутствия снапшота_______________________________
        get_snapshot_info = snapshot_session.get_current_snapshot(random_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_not_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_not_found.name
        # ____________________________Создание снапшота работающей ВМ_____________________________
        vm_template = SnapshotCreateRequest(vm_name=random_name, snapshot_name=snapshot_name)
        create_vm_info = snapshot_session.create_snapshot(vm_template, request_id)
        assert create_vm_info.message == CommandMessagesEnum.snapshot_successfully_created.value
        assert create_vm_info.code == CommandMessagesEnum.snapshot_successfully_created.name
        assert create_vm_info.snapshot_info is not None
        # _______________________________Проверка наличия снапшота________________________________
        get_snapshot_info = snapshot_session.get_current_snapshot(random_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_found.name
        # ____________________________________Удаление снапшота____________________________________
        delete_snapshot_info = snapshot_session.delete_snapshot(SnapshotDeleteRequest(vm_name=random_name,
                                                                                      snapshot_name=snapshot_name,
                                                                                      remove_children=True),
                                                          request_id)

        assert delete_snapshot_info.message == CommandMessagesEnum.snapshot_successfully_deleted.value
        assert delete_snapshot_info.code == CommandMessagesEnum.snapshot_successfully_deleted.name
        assert delete_snapshot_info.success is True
        snapshot_deleted = True
        # _____________________________Проверка отсутствия снапшота_______________________________
        get_snapshot_info = snapshot_session.get_current_snapshot(random_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_not_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_not_found.name
    finally:
        # ______________________________Удаление снапшота(постусловие)_____________________________
        if not snapshot_deleted:
            delete_snapshot_info = snapshot_session.delete_snapshot(SnapshotDeleteRequest(vm_name=random_name,
                                                                                          snapshot_name=snapshot_name,
                                                                                          remove_children=True),
                                                              request_id)
            assert delete_snapshot_info.message == CommandMessagesEnum.snapshot_successfully_deleted.value
            assert delete_snapshot_info.code == CommandMessagesEnum.snapshot_successfully_deleted.name
            assert delete_snapshot_info.success is True