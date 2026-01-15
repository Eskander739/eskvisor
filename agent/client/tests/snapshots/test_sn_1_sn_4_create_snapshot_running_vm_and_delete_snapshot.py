import uuid

import pytest

from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.snapshots import SnapshotCreateRequest


@pytest.mark.tags(
    "SN‑01", "SN‑04", "Создание снапшота работающей ВМ", "Удаление снапшота"
)
def test_sn_01_sn_04_create_snapshot_running_vm_and_delete_snapshot(
    snapshot_session, create_running_vm_func
):
    """
    SN‑01: Создание снапшота работающей ВМ
    SN‑04: Удаление снапшота

    Создать снапшот без остановки ВМ. Проверить, что снапшот появляется в дереве снапшотов ВМ.
    Удалить отдельный снапшот. Убедиться, что место освобождается и дерево снапшотов корректно обновляется.
    """
    vm_info, request_id = create_running_vm_func
    vm_name = vm_info.name
    description = f"snapshot-description-{uuid.uuid4()}"
    snapshot_name = "snapshot-" + vm_name
    snapshot_deleted = False
    try:
        # _____________________________Проверка отсутствия снапшота_______________
        get_snapshot_info = snapshot_session.get_current_snapshot(vm_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_not_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_not_found.name
        # ____________________________Создание снапшота работающей ВМ_____________
        vm_template = SnapshotCreateRequest(
            vm_name=vm_name, snapshot_name=snapshot_name, description=description
        )
        create_vm_info = snapshot_session.create_snapshot(vm_template, request_id)
        assert (
            create_vm_info.message
            == CommandMessagesEnum.snapshot_successfully_created.value
        )
        assert (
            create_vm_info.code
            == CommandMessagesEnum.snapshot_successfully_created.name
        )
        assert create_vm_info.snapshot_info is not None
        snapshot_info = create_vm_info.snapshot_info
        # _______________________________Проверка наличия снапшота________________
        assert snapshot_info.name == snapshot_name
        assert snapshot_info.description == description
        assert snapshot_info.vm_name == vm_name
        assert snapshot_info.state.value == VMState.RUNNING.value
        # ____________________Проверка корректного обновления дерева снапшотов____
        get_snapshots_tree_info = snapshot_session.get_snapshot_chain(
            vm_name, request_id
        )
        assert (
            get_snapshots_tree_info.message == CommandMessagesEnum.snapshot_found.value
        )
        assert get_snapshots_tree_info.code == CommandMessagesEnum.snapshot_found.name
        assert get_snapshots_tree_info.success is True
        assert get_snapshots_tree_info.snapshot_info is not None
        snapshots_tree = get_snapshots_tree_info.snapshot_info
        assert len(snapshots_tree.snapshots) == 1
        assert (
            snapshots_tree.snapshot_tree.get("nodes")[snapshot_name]["info"].name
            == snapshot_name
        )
        assert (
            snapshots_tree.snapshot_tree.get("nodes")[snapshot_name]["info"].vm_name
            == vm_name
        )
        assert not snapshots_tree.snapshot_tree.get("nodes")[snapshot_name]["children"]
        snapshot_from_snapshots = snapshots_tree.snapshots.pop()
        assert snapshot_from_snapshots.vm_name == vm_name
        assert snapshot_from_snapshots.name == snapshot_name
        # ____________________________________Удаление снапшота___________________
        delete_snapshot_info = snapshot_session.delete_snapshot(
            vm_name=vm_name,
            snapshot_name=snapshot_name,
            remove_children=True,
            request_id=request_id,
        )

        assert (
            delete_snapshot_info.message
            == CommandMessagesEnum.snapshot_successfully_deleted.value
        )
        assert (
            delete_snapshot_info.code
            == CommandMessagesEnum.snapshot_successfully_deleted.name
        )
        assert delete_snapshot_info.success is True
        snapshot_deleted = True
        # _____________________________Проверка отсутствия снапшота_______________
        get_snapshot_info = snapshot_session.get_current_snapshot(vm_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_not_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_not_found.name
        # ____________Проверка корректного обновления дерева снапшотов после удале
        get_snapshots_tree_info = snapshot_session.get_snapshot_chain(
            vm_name, request_id
        )
        assert (
            get_snapshots_tree_info.message
            == CommandMessagesEnum.snapshot_list_error.value
        )
        assert (
            get_snapshots_tree_info.code == CommandMessagesEnum.snapshot_list_error.name
        )
        assert get_snapshots_tree_info.success is False
    finally:
        # ______________________________Удаление снапшота(постусловие)____________
        if not snapshot_deleted:
            delete_snapshot_info = snapshot_session.delete_snapshot(
                vm_name=vm_name,
                snapshot_name=snapshot_name,
                remove_children=True,
                request_id=request_id,
            )
            assert (
                delete_snapshot_info.message
                == CommandMessagesEnum.snapshot_successfully_deleted.value
            )
            assert (
                delete_snapshot_info.code
                == CommandMessagesEnum.snapshot_successfully_deleted.name
            )
            assert delete_snapshot_info.success is True
