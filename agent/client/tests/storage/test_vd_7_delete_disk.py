import random

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskCreate,
    DiskFormat,
    DiskStatus,
)
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags("VD‑07", "Удаление диска")
@pytest.mark.parametrize("sparse", (True, False))
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_vd_07_delete_disk(storage_session, sparse, disk_format):
    """
    VD‑07: Удаление диска

    Удалить диск с подтверждением. Проверить, что место освобождается.
    """
    disk_path = None
    disk_deleted = False
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

        # ____________________________________Удаление диска______________________
        delete_disk_info = storage_session.delete_disk(disk_path=disk_path)
        assert delete_disk_info is True
        vm_disk = storage_session.get_disk_info(
            disk_name=attach_disk_create.name, disk_format=attach_disk_create.format
        )
        assert vm_disk.code == CommandMessagesEnum.disk_not_found.name
        disk_deleted = True

    finally:
        # ____________________________________Удаление диска(постусловие)_________
        if disk_path is not None and not disk_deleted:
            delete_disk_info = storage_session.delete_disk(disk_path=disk_path)
            assert delete_disk_info is True
