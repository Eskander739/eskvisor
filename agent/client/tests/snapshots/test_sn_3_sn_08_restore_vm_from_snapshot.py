import datetime
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.snapshots import SnapshotCreateRequest
from agent.client.hypervisor.libvirt.models.vm import VmUpdateRequest
from agent.client.tools import wait_while_not


@pytest.mark.tags(
    "SN‑03",
    "SN‑08",
    "Восстановление ВМ из снапшота",
    "Просмотр информации о снапшоте (дата, размер, описание)",
)
def test_sn_03_sn_08_restore_vm_from_snapshot(
    snapshot_session, create_stopped_vm_func, vm_session, storage_session
):
    """
    SN‑03: Восстановление ВМ из снапшота
    SN‑08: Просмотр информации о снапшоте (дата, размер, описание)

    Выбрать снапшот и выполнить restore. Проверить, что ВМ возвращается в состояние на момент снапшота.
    Открыть свойства снапшота: время создания, занимаемое место, пользовательское описание.
    """
    vm_name = create_stopped_vm_func
    description = f"snapshot-description-{uuid.uuid4()}"
    snapshot_name = "snapshot-" + vm_name
    snapshot_deleted = False
    get_state = vm_session.get_vm_state_by_name
    try:
        # _____________________________Получение информации о ВМ__________________
        vm_info = vm_session.get_vm_by_name(vm_name)
        assert vm_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert vm_info.code == CommandMessagesEnum.vm_successfully_found.name
        # _____________________________Проверка отсутствия снапшота_______________
        get_snapshot_info = snapshot_session.get_current_snapshot(vm_name)
        assert get_snapshot_info.message == CommandMessagesEnum.snapshot_not_found.value
        assert get_snapshot_info.code == CommandMessagesEnum.snapshot_not_found.name
        # ____________________________Создание снапшота работающей ВМ_____________
        vm_template = SnapshotCreateRequest(
            vm_name=vm_name, snapshot_name=snapshot_name, description=description
        )
        create_vm_info = snapshot_session.create_snapshot(vm_template)
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
        # ________________________________Проверка наличия снапшота_______________
        assert snapshot_info.name == snapshot_name
        assert snapshot_info.description == description
        assert snapshot_info.vm_name == vm_name
        assert snapshot_info.state.value == VMState.SHUTOFF.value
        assert snapshot_info.size_bytes > 0
        assert (
            datetime.datetime.now(datetime.timezone.utc) - snapshot_info.created
        ).total_seconds() < 5
        # _________________________________Проверка конфигурации ВМ_______________
        vm_config = snapshot_info.vm_config
        assert vm_config.name == vm_name
        assert vm_config.uuid == vm_info.vm_info.uuid
        assert vm_config.memory == vm_info.vm_info.memory
        assert vm_config.max_memory == vm_info.vm_info.max_memory
        assert vm_config.vcpus == vm_info.vm_info.vcpus
        # ____________________________________Изменение ресурсов ВМ_______________
        vm_session.start_vm(vm_name)
        edit_vm_info = vm_session.edit_vm(vm_name, VmUpdateRequest(vcpus=3))
        assert (
            edit_vm_info.message == CommandMessagesEnum.vm_edit_success.value
        ), edit_vm_info.note
        assert edit_vm_info.code == CommandMessagesEnum.vm_edit_success.name
        assert wait_while_not(lambda: get_state(vm_name) == VMState.RUNNING.value)
        vm_get_info = vm_session.get_vm_by_name(vm_name)
        assert vm_get_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert vm_get_info.code == CommandMessagesEnum.vm_successfully_found.name
        assert wait_while_not(
            lambda: vm_session.get_vm_by_name(vm_name).vm_info.vcpus == 3,
            timeout=30,
        )
        # ________________________________Восстановление ВМ из снапшота___________
        revert_vm_info = snapshot_session.revert_to_snapshot(
            vm_name, snapshot_name
        )
        assert (
            revert_vm_info.message == CommandMessagesEnum.snapshot_revert_success.value
        )
        assert revert_vm_info.code == CommandMessagesEnum.snapshot_revert_success.name
        # __________________Проверка конфигурации ВМ после восстановления из снапш
        assert wait_while_not(lambda: get_state(vm_name) == VMState.SHUTOFF.value)
        vm_get_info = vm_session.get_vm_by_name(vm_name)
        assert vm_get_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert vm_get_info.code == CommandMessagesEnum.vm_successfully_found.name
        assert vm_get_info.vm_info.vcpus == vm_info.vm_info.vcpus
    finally:
        # ______________________________Удаление снапшота(постусловие)____________
        if not snapshot_deleted:
            delete_snapshot_info = snapshot_session.delete_snapshot(
                vm_name=vm_name,
                snapshot_name=snapshot_name,
                remove_children=True
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
