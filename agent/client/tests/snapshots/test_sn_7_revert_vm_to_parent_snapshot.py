import uuid

import pytest

from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.snapshots import SnapshotCreateRequest


@pytest.mark.tags(
    "SN‑07",
    "Восстановление из родительского снапшота (откат к более раннему состоянию)",
)
def test_sn_06_create_snapshot_chain(
    snapshot_session, create_stopped_vm_func, vm_session, storage_session
):
    """
    SN‑07: Восстановление из родительского снапшота (откат к более раннему состоянию)

    СВыбрать родительский снапшот в цепочке и восстановить его. Убедиться,
    что родитель начинает отображаться как текущий снапшот и цепочка снапшотов остается неизменной
    """
    vm_name, request_id = create_stopped_vm_func
    description = f"snapshot-description-{uuid.uuid4()}"
    snapshot_name_first = "snapshot-" + vm_name + str(uuid.uuid4())
    snapshot_name_second = "snapshot-" + vm_name + str(uuid.uuid4())
    snapshot_name_third = "snapshot-" + vm_name + str(uuid.uuid4())
    try:
        # _____________________________Получение информации о ВМ__________________
        vm_info = vm_session.get_vm_by_name(vm_name, request_id)
        assert vm_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert vm_info.code == CommandMessagesEnum.vm_successfully_found.name
        # _____________________________Проверка отсутствия снапшота_______________
        get_snapshot_info = snapshot_session.get_current_snapshot(vm_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_not_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_not_found.name
        # ____________________________Создание снапшота остановленной ВМ_____________

        for snapshot_name in (
            snapshot_name_first,
            snapshot_name_second,
            snapshot_name_third,
        ):
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
            assert snapshot_info.state.value == VMState.SHUTOFF.value
            assert snapshot_info.size_bytes > 0

        # _______________________________Проверка цепочки снапшотов ВМ_________________
        snaphot_chain = snapshot_session.get_snapshot_chain(vm_name, request_id)
        assert snaphot_chain.snapshot_info.chain_depth == 3
        first_snap, second_snap, third_snap = snaphot_chain.snapshot_info.chains.pop()
        assert first_snap.parent is None
        assert second_snap.parent.name == first_snap.name
        assert third_snap.parent.name == second_snap.name

        # ________________________________Проверка текущего снапшота___________
        get_snapshot_info = snapshot_session.get_current_snapshot(vm_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_found.name
        assert get_snapshot_info.snapshot_info.name == third_snap.name

        # ________________________________Восстановление ВМ из снапшота___________
        revert_vm_info = snapshot_session.revert_to_snapshot(
            vm_name, first_snap.name, request_id
        )
        assert (
            revert_vm_info.message == CommandMessagesEnum.snapshot_revert_success.value
        )
        assert revert_vm_info.code == CommandMessagesEnum.snapshot_revert_success.name

        # _____Проверка того, что теперь текущим снапшотом является восстановленный родитель_____
        get_snapshot_info = snapshot_session.get_current_snapshot(vm_name, request_id)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_found.name
        assert get_snapshot_info.snapshot_info.name == first_snap.name

        # _______________________________Проверка сохранности цепочки снапшотов ВМ_________________
        snaphot_chain = snapshot_session.get_snapshot_chain(vm_name, request_id)
        assert snaphot_chain.snapshot_info.chain_depth == 3
        first_snap, second_snap, third_snap = snaphot_chain.snapshot_info.chains.pop()
        assert first_snap.parent is None
        assert second_snap.parent.name == first_snap.name
        assert third_snap.parent.name == second_snap.name

    finally:
        # ______________________________Удаление снапшота(постусловие)____________
        for snapshot_name in (snapshot_name_first, snapshot_name_second):
            delete_snapshot_info = snapshot_session.delete_snapshot(
                vm_name=vm_name,
                snapshot_name=snapshot_name,
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
