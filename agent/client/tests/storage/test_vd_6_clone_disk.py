import random
import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskCreate,
    DiskFormat,
    DiskStatus,
    DiskType,
)
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
        disk_create = DiskCreate(
            name=f"disk-test-{random_name}",
            size_gb=0.2,
            format=disk_format,
            sparse=sparse,
        )
        attach_disk = storage_session.create_disk(disk_create)
        assert attach_disk.code == CommandMessagesEnum.disk_successfully_created.name
        vm_disk_start = storage_session.get_disk_info(
            disk_name=disk_create.name, disk_format=disk_create.format
        )
        assert vm_disk_start.code == CommandMessagesEnum.disk_founded.name
        vm_disk_start = vm_disk_start.disk_info
        first_disk_path = (
            vm_disk_start.path + "/" + disk_create.name + "." + disk_create.format.value
        )

        assert vm_disk_start.status.value == DiskStatus.DETACHED.value
        assert vm_disk_start.name == disk_create.name
        assert vm_disk_start.format == disk_format
        assert vm_disk_start.file_path_exists is True
        assert vm_disk_start.path == disk_create.path
        if not sparse:
            assert (
                round(vm_disk_start.capacity_bytes / (1024**3), 2)
                == disk_create.size_gb
            )
        else:
            assert 0 < round(vm_disk_start.capacity_bytes / (1024**3), 10) < 0.1

        # ____________________________________Клонирование диска диска____________
        clone_disk_info = storage_session.clone_disk(
            disk_name=disk_create.name,
            path=vm_disk_start.path,
            disk_format=vm_disk_start.format,
            target_name=cloned_disk_name,
        )
        assert clone_disk_info.code == CommandMessagesEnum.disk_successfully_cloned.name
        vm_disk = storage_session.get_disk_info(
            disk_name=cloned_disk_name, disk_format=disk_create.format
        )
        vm_disk = vm_disk.disk_info
        cloned_disk_path = (
            vm_disk.path + "/" + vm_disk.name + "." + vm_disk.format.value
        )

        assert vm_disk.status.value == DiskStatus.DETACHED.value
        assert vm_disk.format.value == disk_format.value
        assert vm_disk.type.value == DiskType.EXTERNAL_DISK.value
        assert vm_disk.file_path_exists is True
        assert vm_disk.name == cloned_disk_name

        if not sparse:
            assert (
                round(vm_disk_start.capacity_bytes / (1024**3), 2)
                == disk_create.size_gb
            )
        else:
            assert round(vm_disk_start.capacity_bytes / (1024**3), 2) < 0.1
    finally:
        # ____________________________________Удаление дисков(постусловие)________
        if first_disk_path is not None:
            delete_disk_info = storage_session.delete_disk(disk_path=first_disk_path)
            assert delete_disk_info is True
        if cloned_disk_path is not None:
            delete_disk_info = storage_session.delete_disk(disk_path=cloned_disk_path)
            assert delete_disk_info is True
