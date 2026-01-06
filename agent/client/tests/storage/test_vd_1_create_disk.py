import random

import pytest

from agent.client.hypervisor.libvirt.models.disk import (
    DiskFormat,
    DiskCreate,
    DiskStatus,
)
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags("VD‑01", "Создание нового виртуального диска")
@pytest.mark.parametrize("sparse", (True, False))
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_vd_01_create_disk(storage_session, sparse, disk_format):
    """
    VD‑01: Создание нового виртуального диска

    Указать тип (RAW, QCOW2, VHD), размер, формат.
    Проверить, что диск появляется в списке и занимает указанное место.
    """
    disk_path = None
    try:
        # ____________________________________Создание диска______________________
        random_name = random.randint(10000, 99999)
        attach_disk_create = DiskCreate(
            name=f"disk-test-{random_name}",
            size_gb=0.2,
            format=disk_format,
            sparse=sparse,
            description="Create disk description",
        )
        attach_disk = storage_session.create_disk(attach_disk_create)
        assert attach_disk is not None, "Ошибка: диск для подключения не создан"
        vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)
        vm_disk = vm_disk.disk_info
        disk_path = vm_disk.path
        assert vm_disk.status.value == DiskStatus.DETACHED.value
        current_disk_name = vm_disk.name.split(".").pop(0)
        assert current_disk_name == attach_disk_create.name
        assert vm_disk.format == disk_format
        if not sparse:
            assert (
                round(vm_disk.capacity_bytes / (1024**3), 2)
                == attach_disk_create.size_gb
            )
        else:
            assert round(vm_disk.capacity_bytes / (1024**3), 2) < 0.1
        assert vm_disk.file_path_exists is True
        assert vm_disk.path == attach_disk_create.path
    finally:
        # ____________________________________Удаление диска(постусловие)_________
        if disk_path is not None:
            storage_session.delete_disk(path=disk_path)
            vm_disk = storage_session.get_disk_info(path=disk_path)
            assert vm_disk.message == CommandMessagesEnum.disk_not_found.value
            assert vm_disk.code == CommandMessagesEnum.disk_not_found.name
