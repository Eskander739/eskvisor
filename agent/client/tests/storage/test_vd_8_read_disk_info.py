import random

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskCreate,
    DiskFormat,
    DiskStatus,
)
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags("VD‑08", "Просмотр информации о диске")
@pytest.mark.parametrize("sparse", (True, False))
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_vd_08_disk_info(storage_session, disk_format, sparse):
    """
    VD‑08: Просмотр информации о диске

    Открыть свойства диска: размер, формат, путь, использование.
    """

    disk_path = None

    def bytes_to_gb(data: int):
        return round(data / (1024**3), 2)

    try:
        # ____________________________________Создание диска______________________
        random_name = random.randint(10000, 99999)
        disk_create = DiskCreate(
            name=f"disk-test-{random_name}",
            size_gb=0.2,
            format=disk_format,
            sparse=sparse,
        )
        attach_disk = storage_session.create_disk(disk_create)
        assert attach_disk.code == CommandMessagesEnum.disk_successfully_created.name
        vm_disk = storage_session.get_disk_info(
            disk_name=disk_create.name, disk_format=disk_create.format
        )
        vm_disk = vm_disk.disk_info
        disk_path = f"{vm_disk.path}/{disk_create.name}.{disk_format.value}"
        disk_virtual_size = storage_session.get_disk_virtual_size(disk_path=disk_path)
        assert vm_disk.status.value == DiskStatus.DETACHED.value
        assert vm_disk.name == disk_create.name
        assert vm_disk.format == disk_format
        if not sparse:
            assert round(vm_disk.capacity_bytes / (1024**3), 2) == disk_create.size_gb
        else:
            assert round(vm_disk.capacity_bytes / (1024**3), 2) < 0.1

        assert bytes_to_gb(disk_virtual_size) == disk_create.size_gb
        assert vm_disk.file_path_exists is True
        assert vm_disk.path == disk_create.path
    finally:
        # ____________________________________Удаление диска(постусловие)_________
        if disk_path is not None:
            delete_disk_info = storage_session.delete_disk(disk_path=disk_path)
            assert delete_disk_info is True
