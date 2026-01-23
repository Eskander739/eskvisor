import random

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskCreate,
    DiskFormat,
    DiskStatus,
    DiskUpdate,
)
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags("VD‑04", "Расширение диска")
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_vd_04_extend_disk(storage_session, disk_format):
    """
    VD‑04: Расширение диска

    Увеличить размер диска.
    """
    edit_disk = DiskUpdate(new_size_gb=0.5)
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
            sparse=False,
        )
        attach_disk = storage_session.create_disk(disk_create)
        assert attach_disk.code == CommandMessagesEnum.disk_successfully_created.name
        vm_disk = storage_session.get_disk_info(
            disk_name=disk_create.name, disk_format=disk_format
        )
        vm_disk = vm_disk.disk_info
        disk_path = f"{vm_disk.path}/{disk_create.name}.{disk_format.value}"
        before_change_disk_virtual_size = storage_session.get_disk_virtual_size(
            disk_path=disk_path
        )
        assert bytes_to_gb(before_change_disk_virtual_size) == disk_create.size_gb

        assert vm_disk.status.value == DiskStatus.DETACHED.value
        assert vm_disk.name == disk_create.name
        assert vm_disk.format == disk_format
        assert vm_disk.file_path_exists is True
        assert vm_disk.path == disk_create.path

        # ____________________________________Редактирование диска________________
        storage_session.extend_disk(
            new_size_gb=edit_disk.new_size_gb,
            path=vm_disk.path,
            disk_name=disk_create.name,
            disk_format=disk_format,
        )
        vm_disk = storage_session.get_disk_info(
            disk_name=disk_create.name, disk_format=disk_format
        )
        vm_disk = vm_disk.disk_info
        disk_path = f"{vm_disk.path}/{disk_create.name}.{disk_format.value}"
        assert vm_disk.path == disk_create.path

        after_change_disk_virtual_size = storage_session.get_disk_virtual_size(
            disk_path=disk_path
        )
        assert bytes_to_gb(after_change_disk_virtual_size) == edit_disk.new_size_gb
        assert (
            round(after_change_disk_virtual_size / before_change_disk_virtual_size, 2)
            == 2.5
        )

    finally:
        # ____________________________________Удаление диска(постусловие)_________
        if disk_path is not None:
            delete_disk_info = storage_session.delete_disk(disk_path=disk_path)
            assert delete_disk_info is True
