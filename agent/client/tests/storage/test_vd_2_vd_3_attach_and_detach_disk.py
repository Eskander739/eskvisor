import random

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskAttach,
    DiskCreate,
    DiskDetach,
    DiskFormat,
    DiskStatus,
)
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

    vm_name = create_stopped_vm
    target_dev = "vdb"
    disk_path = None
    try:
        # ____________________________________Создание диска______________________
        attach_disk_create = DiskCreate(
            name=f"disk-test-{RANDOM_NAME}",
            size_gb=0.2,
            format=DiskFormat.QCOW2,
            sparse=True,
        )
        attach_disk = storage_session.create_disk(attach_disk_create)
        assert attach_disk.code == CommandMessagesEnum.disk_successfully_created.name

        vm_disk = storage_session.get_disk_info(
            disk_name=attach_disk_create.name, disk_format=attach_disk_create.format
        )
        vm_disk = vm_disk.disk_info
        disk_path = (
            vm_disk.path
            + "/"
            + attach_disk_create.name
            + "."
            + attach_disk_create.format.value
        )
        assert vm_disk.status.value == DiskStatus.DETACHED.value
        assert vm_disk.name == attach_disk_create.name
        assert attach_disk_create.format == DiskFormat.QCOW2

        disk_attach = DiskAttach(
            vm_name=vm_name,
            path=vm_disk.path,
            name=attach_disk_create.name,
            format=attach_disk_create.format,
            target_dev=target_dev,
        )

        # ____________________________________Подключение диска___________________
        storage_session.attach_disk(disk_attach)

        vm_disk = storage_session.get_disk_info_by_target_dev(
            vm_name=vm_name, target_dev=target_dev
        )
        vm_disk = vm_disk.disk_info

        assert vm_disk.status.value == DiskStatus.ATTACHED.value
        assert vm_disk.vm_name == vm_name

        # ____________________________________Отключение диска____________________

        storage_session.detach_disk(
            DiskDetach(vm_name=vm_name, target_dev=disk_attach.target_dev)
        )

        vm_disk = storage_session.get_disk_info(
            disk_name=attach_disk_create.name, disk_format=attach_disk_create.format
        )
        vm_disk = vm_disk.disk_info

        assert vm_disk.status.value == DiskStatus.DETACHED.value
    finally:
        # ____________________________________Удаление диска(постусловие)_________
        if disk_path is not None:
            delete_disk_info = storage_session.delete_disk(disk_path=disk_path)
            assert delete_disk_info is True
