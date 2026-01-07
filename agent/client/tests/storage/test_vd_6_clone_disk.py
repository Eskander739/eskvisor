import random

import pytest

from agent.client.hypervisor.libvirt.models.disk import (DiskCreate,
                                                         DiskFormat,
                                                         DiskStatus, DiskType)
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags("VD‑07", "Клонирование диска")
@pytest.mark.parametrize("sparse", (True, False))
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_vd_06_clone_disk(storage_session, sparse, disk_format):
    """
    VD‑06: Клонирование диска

    Создать копию диска. Проверить, что клон идентичен исходному.
    """

    first_disk_path = None
    cloned_disk_path = None

    try:
        # ____________________________________Создание диска______________________
        random_name = random.randint(10000, 99999)
        cloned_disk_name = f"disk-test-cloned-{random_name}"
        cloned_disk_file_name = f"disk-test-cloned-{random_name}.{disk_format.value}"
        attach_disk_create = DiskCreate(
            name=f"disk-test-{random_name}",
            size_gb=0.2,
            format=disk_format,
            sparse=sparse,
        )
        attach_disk = storage_session.create_disk(attach_disk_create)
        assert attach_disk is not None, "Ошибка: диск для подключения не создан"
        vm_disk_start = storage_session.get_disk_info(path=attach_disk_create.path)
        vm_disk_start = vm_disk_start.disk_info
        first_disk_path = vm_disk_start.path

        assert vm_disk_start.status.value == DiskStatus.DETACHED.value
        current_disk_name = vm_disk_start.name.split(".").pop(0)
        assert current_disk_name == attach_disk_create.name
        assert vm_disk_start.format == disk_format
        if not sparse:
            assert (
                round(vm_disk_start.capacity_bytes / (1024**3), 2)
                == attach_disk_create.size_gb
            )
        else:
            assert round(vm_disk_start.capacity_bytes / (1024**3), 2) < 0.1
        assert vm_disk_start.file_path_exists is True
        assert vm_disk_start.path == attach_disk_create.path

        # ____________________________________Клонирование диска диска____________
        target_path = vm_disk_start.path.replace(
            f"{attach_disk_create.name}.{attach_disk_create.format.value}",
            cloned_disk_file_name,
        )
        storage_session.clone_disk(
            source_path=vm_disk_start.path,
            target_path=target_path,
            target_name=cloned_disk_name,
        )
        vm_disk = storage_session.get_disk_info(path=target_path)
        vm_disk = vm_disk.disk_info
        cloned_disk_path = vm_disk.path

        assert vm_disk.status.value == DiskStatus.DETACHED.value
        assert vm_disk.format.value == disk_format.value
        assert vm_disk.type.value == DiskType.EXTERNAL_DISK.value
        assert vm_disk.file_path_exists is True
        if not sparse:
            assert (
                round(vm_disk_start.capacity_bytes / (1024**3), 2)
                == attach_disk_create.size_gb
            )
        else:
            assert round(vm_disk_start.capacity_bytes / (1024**3), 2) < 0.1
        assert vm_disk.path == target_path

        current_disk_name = vm_disk.name.split(".").pop(0)
        assert current_disk_name == cloned_disk_name
    finally:

        # ____________________________________Удаление дисков(постусловие)________

        if first_disk_path is not None:
            storage_session.delete_disk(path=first_disk_path)
            vm_disk = storage_session.get_disk_info(path=first_disk_path)
            assert vm_disk.message == CommandMessagesEnum.disk_not_found.value
            assert vm_disk.code == CommandMessagesEnum.disk_not_found.name
        if cloned_disk_path is not None:
            storage_session.delete_disk(path=cloned_disk_path)
            vm_disk = storage_session.get_disk_info(path=cloned_disk_path)
            assert vm_disk.message == CommandMessagesEnum.disk_not_found.value
            assert vm_disk.code == CommandMessagesEnum.disk_not_found.name
