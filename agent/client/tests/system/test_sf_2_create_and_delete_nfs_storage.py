import random

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskCreate,
    DiskStatus, DiskFormat,
)
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags(
    "SF‑02",
    "Создание и удаление NFS хранилища с проверкой создания дисков QCOW2 и RAW",
)
@pytest.mark.parametrize("sparse", (True, False))
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_sf_02_create_and_delete_nfs_storage(storage_session, create_nfs_storage_session, disk_format, sparse):
    """
    SF-01: Создание и удаление NFS хранилища с проверкой создания дисков QCOW2 и RAW

    Создать NFS хранилище, создать диски QCOW2 И RAW на хранилище, убедиться что диски созданы корректно,
    удалить диски, убедиться чтобы диски удалены, удалить хранилище, убедиться что хранилище удалено
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
            path=create_nfs_storage_session
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