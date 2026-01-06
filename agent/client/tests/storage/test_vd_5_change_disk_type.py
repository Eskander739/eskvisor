import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import (
    DiskFormat,
    DiskCreate,
    DiskStatus,
)
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags("VD‑05", "Изменение типа диска")
@pytest.mark.parametrize("sparse", (True, False))
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_vd_05_convert_disk(storage_session, disk_format, sparse):
    """
    VD‑05: Изменение типа диска (например, с QCOW2 на RAW)

    Конвертировать диск в другой формат.
    Убедиться, что данные сохраняются и диск работает.
    """

    disk_path = None
    disk_format_convert = {
        DiskFormat.QCOW2: DiskFormat.RAW,
        DiskFormat.RAW: DiskFormat.QCOW2,
    }

    def bytes_to_gb(data: int):
        return round(data / (1024**3), 2)

    try:
        # ____________________________________Создание диска____________________________________
        random_name = random.randint(10000, 99999)
        attach_disk_create = DiskCreate(
            name=f"disk-test-{random_name}",
            size_gb=0.2,
            format=disk_format,
            sparse=sparse,
        )
        attach_disk = storage_session.create_disk(attach_disk_create)
        assert attach_disk is not None, "Ошибка: диск для подключения не создан"
        vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)
        vm_disk = vm_disk.disk_info
        before_change_disk_virtual_size = storage_session.get_disk_virtual_size(
            path=attach_disk_create.path
        )
        disk_path = vm_disk.path
        assert (
            bytes_to_gb(before_change_disk_virtual_size) == attach_disk_create.size_gb
        )

        assert vm_disk.status.value == DiskStatus.DETACHED.value
        current_disk_name = vm_disk.name.split(".").pop(0)
        assert current_disk_name == attach_disk_create.name
        assert vm_disk.format == disk_format
        assert vm_disk.file_path_exists is True
        assert vm_disk.path == attach_disk_create.path

        # ____________________________________Изменение типа диска____________________________________
        convert_disk_info = storage_session.convert_disk_format(
            source_path=disk_path,
            target_format=disk_format_convert.get(disk_format),
            request_id=str(uuid.uuid4()),
            sparse=sparse,
        )
        assert (
            convert_disk_info.code == CommandMessagesEnum.disk_convert_successfully.name
        )
        assert (
            convert_disk_info.message
            == CommandMessagesEnum.disk_convert_successfully.value
        )
        assert (
            f".{disk_format_convert.get(disk_format).value}"
            in convert_disk_info.target_path
        )
        vm_disk = storage_session.get_disk_info(path=convert_disk_info.target_path)
        vm_disk = vm_disk.disk_info
        disk_path = vm_disk.path
        assert vm_disk.format.value == disk_format_convert.get(disk_format).value

        if not sparse:
            assert (
                round(vm_disk.capacity_bytes / (1024**3), 2)
                == attach_disk_create.size_gb
            )
        else:
            assert round(vm_disk.capacity_bytes / (1024**3), 2) < 0.1

    finally:
        # ____________________________________Удаление диска(постусловие)____________________________________
        if disk_path is not None:
            storage_session.delete_disk(path=disk_path)
            vm_disk = storage_session.get_disk_info(path=disk_path)
            assert vm_disk.message == CommandMessagesEnum.disk_not_found.value
            assert vm_disk.code == CommandMessagesEnum.disk_not_found.name
