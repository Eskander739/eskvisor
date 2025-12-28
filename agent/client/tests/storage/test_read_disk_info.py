import random

import pytest

from agent.client.hypervisor.models.disk import DiskFormat, DiskCreate, DiskStatus

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
        return round(data / (1024 ** 3), 2)
    try:
        # ____________________________________Создание диска____________________________________
        random_name = random.randint(10000, 99999)
        attach_disk_create = DiskCreate(name=f"disk-test-{random_name}",
                                        size_gb=0.2,
                                        format=disk_format,
                                        sparse=sparse)
        attach_disk = storage_session.create_disk(attach_disk_create)
        assert attach_disk is not None, "Ошибка: диск для подключения не создан"
        vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)
        disk_virtual_size = storage_session.get_disk_virtual_size(path=attach_disk_create.path)
        disk_path = vm_disk.path
        assert vm_disk.status.value == DiskStatus.DETACHED.value
        current_disk_name = vm_disk.name.split(".").pop(0)
        assert current_disk_name == attach_disk_create.name
        assert vm_disk.format == disk_format
        if not sparse:
            assert round(vm_disk.capacity_bytes / (1024 ** 3), 2) == attach_disk_create.size_gb
        else:
            assert round(vm_disk.capacity_bytes / (1024 ** 3), 2) < 0.1

        assert bytes_to_gb(disk_virtual_size) == attach_disk_create.size_gb
        assert vm_disk.file_path_exists is True
        assert vm_disk.path == attach_disk_create.path
    finally:
        # ____________________________________Удаление диска(постусловие)____________________________________
        if disk_path is not None:
            storage_session.delete_disk(path=disk_path)
            vm_disk = storage_session.get_disk_info(path=disk_path)
            assert vm_disk.file_path_exists is False

