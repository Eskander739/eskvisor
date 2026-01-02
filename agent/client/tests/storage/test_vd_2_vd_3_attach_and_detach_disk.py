import random

import pytest
from agent.client.hypervisor.libvirt.models.disk import DiskCreate, DiskFormat, DiskStatus, DiskAttach, DiskDetach
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum

RANDOM_NAME = random.randint(10000, 99999)

@pytest.mark.tags("VD‑02", "VD‑03", "Подключение диска к ВМ", "Отключение диска от ВМ")
# @pytest.mark.parametrize("vm_status", (
#         # "running", TODO: Баг, не отключается диск от работающей ВМ
#         "stopped"
# )
#                          )
def test_vd_02_attach_and_detach_disk(storage_session, create_stopped_vm):
    """
    VD‑02: Подключение диска к ВМ
    VD‑03: Отключение диска к ВМ

    Выбрать существующий диск и подключить к работающей/остановленной ВМ.
    Убедиться, что ВМ видит диск.
    """

    vm_name, request_id = create_stopped_vm
    target_dev = "vdb"
    disk_path = None
    try:
        # ____________________________________Создание диска____________________________________
        attach_disk_create = DiskCreate(name=f"disk-test-{RANDOM_NAME}.qcow2", size_gb=0.2, format=DiskFormat.QCOW2,
                                        sparse=True)
        attach_disk = storage_session.create_disk(attach_disk_create)
        assert attach_disk.message == CommandMessagesEnum.disk_successfully_created.value
        assert attach_disk.code == CommandMessagesEnum.disk_successfully_created.name

        vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)
        vm_disk = vm_disk.disk_info
        disk_path = vm_disk.path

        assert vm_disk.status.value == DiskStatus.DETACHED.value
        current_disk_name = vm_disk.name.split(".").pop(0)
        assert current_disk_name == attach_disk_create.name
        assert attach_disk_create.format == DiskFormat.QCOW2

        disk_attach = DiskAttach(vm_name=vm_name, path=vm_disk.path, target_dev=target_dev)

        # ____________________________________Подключение диска____________________________________

        storage_session.attach_disk(disk_attach, request_id=request_id)

        vm_disk = storage_session.get_disk_info_by_target_dev(vm_name=vm_name,
                                                              target_dev=target_dev,
                                                              request_id=request_id)
        vm_disk = vm_disk.disk_info

        assert vm_disk.status.value == DiskStatus.ATTACHED.value
        assert vm_disk.vm_name == vm_name

        # ____________________________________Отключение диска____________________________________

        storage_session.detach_disk(DiskDetach(vm_name=vm_name, target_dev=disk_attach.target_dev))

        vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)
        vm_disk = vm_disk.disk_info

        assert vm_disk.status.value == DiskStatus.DETACHED.value
    finally:
        # ____________________________________Удаление диска(постусловие)____________________________________
        if disk_path is not None:
            storage_session.delete_disk(path=disk_path)
            vm_disk = storage_session.get_disk_info(path=disk_path)
            assert vm_disk.message == CommandMessagesEnum.disk_not_found.value
            assert vm_disk.code == CommandMessagesEnum.disk_not_found.name
