import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import DiskType
from agent.client.hypervisor.libvirt.models.snapshots import SnapshotCreateRequest
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags("SN‑02", "Создание снапшота остановленной ВМ")
def test_sn_02_create_snapshot_stopped_vm(
    snapshot_session, create_stopped_vm, vm_session, storage_session
):
    """
    SN‑02: Создание снапшота остановленной ВМ

    Создать снапшот при выключенной ВМ. Убедиться, что снапшот сохраняет состояние дисков и конфигурации.
    """
    vm_name, request_id = create_stopped_vm
    description = f"snapshot-description-{uuid.uuid4()}"
    snapshot_name = "snapshot-" + vm_name
    snapshot_deleted = False
    try:
        # _____________________________Получение информации о ВМ__________________
        vm_info = vm_session.get_vm_by_name(vm_name, request_id)
        assert vm_info.message == CommandMessagesEnum.vm_successfully_found.value
        assert vm_info.code == CommandMessagesEnum.vm_successfully_found.name
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
        assert snapshot_info.state.value == VMState.SHUTOFF.value
        assert snapshot_info.size_bytes > 0
        # _______________________________Проверка конфигурации ВМ_________________
        vm_config = snapshot_info.vm_config
        assert vm_config.name == vm_name
        assert vm_config.uuid == vm_info.vm_info.uuid
        assert vm_config.memory == vm_info.vm_info.memory
        assert vm_config.max_memory == vm_info.vm_info.max_memory
        assert vm_config.vcpus == vm_info.vm_info.vcpus

        # _____________________________Проверка конфигурации дисков_______________
        vm_disk_info = storage_session.get_disks_by_vm(vm_name, request_id)
        for current_disk, snapshot_disk in zip(
            sorted(vm_disk_info), sorted(snapshot_info.disks)
        ):
            assert current_disk.name == snapshot_disk.name
            assert current_disk.path == snapshot_disk.path
            assert snapshot_disk.type.value == DiskType.SNAPSHOT.value
            assert current_disk.format.value == snapshot_disk.format.value
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
