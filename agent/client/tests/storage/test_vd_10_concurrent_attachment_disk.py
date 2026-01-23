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


@pytest.mark.tags("VD‑10", "Одновременное подключение одного диска к нескольким ВМ")
def test_vd_10_concurrent_attachment(storage_session, multi_create_stopped_vm):
    """
    VD‑10: Одновременное подключение одного диска к нескольким ВМ

    Попытаться подключить один и тот же диск к двум ВМ.
    Система должна запретить операцию.
    """

    target_dev_list = ["vdb", "vdd"]
    vm_config_names = multi_create_stopped_vm
    disk_path = None
    vm_name_to_detach = None
    target_dev_to_detach = None
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
        disk_attach_list = []
        for vm_config_name, target_dev in zip(vm_config_names, target_dev_list):
            disk_attach_list.append(
                DiskAttach(
                    vm_name=vm_config_name,
                    name=attach_disk_create.name,
                    path=vm_disk.path,
                    format=attach_disk_create.format,
                    target_dev=target_dev,
                )
            )

        for index, disk_attach in enumerate(disk_attach_list):
            attach_disk_result = storage_session.attach_disk(disk_attach)
            if index == 0:

                # ____________________________________Подключение диска___________________
                assert (
                    attach_disk_result.code
                    == CommandMessagesEnum.disk_successfully_attached.name
                )
                current_vm_disk = storage_session.get_disk_info_by_target_dev(
                    vm_name=disk_attach.vm_name, target_dev=disk_attach.target_dev
                )
                assert (
                    current_vm_disk.code
                    == CommandMessagesEnum.disk_founded_by_target_dev.name
                )
                vm_name_to_detach = disk_attach.vm_name
                target_dev_to_detach = disk_attach.target_dev
            elif index == 1:

                # ____________________________________Подключение диска___________________
                assert (
                    attach_disk_result.code
                    == CommandMessagesEnum.disk_already_attached_error.name
                )
                current_vm_disk = storage_session.get_disk_info_by_target_dev(
                    vm_name=disk_attach.vm_name, target_dev=disk_attach.target_dev
                )
                assert (
                    current_vm_disk.code
                    == CommandMessagesEnum.disk_not_found_by_target_dev.name
                )

        # ____________________________________Отключение диска____________________

        storage_session.detach_disk(
            DiskDetach(vm_name=vm_name_to_detach, target_dev=target_dev_to_detach)
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
