import os
import random

import pytest

from agent.client.hypervisor.models.disk import DiskQuery, DiskCreate, DiskFormat, DiskStatus
from agent.client.hypervisor.models.msg import CommandMessagesEnum


@pytest.mark.tags("VD‑07", "Удаление диска")
@pytest.mark.parametrize("sparse", (True, False))
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_vd_07_delete_disk(storage_session, sparse, disk_format):
    """
    VD‑07: Удаление диска

    Удалить диск с подтверждением. Проверить, что место освобождается.
    """
    # ____________________________________Создание диска____________________________________
    random_name = random.randint(10000, 99999)
    attach_disk_create = DiskCreate(name=f"disk-test-{random_name}", size_gb=0.2, format=disk_format, sparse=sparse)
    attach_disk = storage_session.create_disk(attach_disk_create)
    assert attach_disk is not None, "Ошибка: диск для подключения не создан"
    vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)
    vm_disk = vm_disk.disk_info

    assert vm_disk.status.value == DiskStatus.DETACHED.value
    current_disk_name = vm_disk.name.split(".").pop(0)
    assert current_disk_name == attach_disk_create.name
    assert vm_disk.format == disk_format
    if not sparse:
        assert round(vm_disk.capacity_bytes / (1024 ** 3), 2) == attach_disk_create.size_gb
    else:
        assert round(vm_disk.capacity_bytes / (1024 ** 3), 2) < 0.1
    assert vm_disk.file_path_exists is True
    assert vm_disk.path == attach_disk_create.path

    # ____________________________________Удаление диска____________________________________
    storage_session.delete_disk(path=vm_disk.path)
    vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)
    assert vm_disk.message == CommandMessagesEnum.disk_not_found.value
    assert vm_disk.code == CommandMessagesEnum.disk_not_found.name

