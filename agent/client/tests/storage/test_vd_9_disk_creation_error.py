import random

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate, DiskFormat
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum

ERROR_MSG = " The image size is too large for file format '{}'"


@pytest.mark.tags("VD‑09", "Ошибка при создании диска (недостаточно места)")
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_vd_09_disk_creation_error(storage_session, disk_format):
    """
    VD‑09: Ошибка при создании диска (недостаточно места)

    Попытаться создать диск больше, чем доступно в хранилище.
    Получить корректное сообщение об ошибке.
    """

    # ______________________Создание диска с размером превыщающим размер храни
    random_name = random.randint(10000, 99999)
    attach_disk_create = DiskCreate(
        name=f"disk-test-{random_name}", size_gb=65536, format=disk_format, sparse=False
    )
    attach_disk = storage_session.create_disk(attach_disk_create)
    assert attach_disk.message == CommandMessagesEnum.disk_create_error.value
    assert attach_disk.code == CommandMessagesEnum.disk_create_error.name
    if disk_format == DiskFormat.QCOW2:
        assert "timed out after 10 seconds" in attach_disk.note
    else:
        assert attach_disk.disk_info.path in attach_disk.stderr
        assert ERROR_MSG.format(disk_format.value) in attach_disk.stderr
    vm_disk = storage_session.get_disk_info(disk_name=attach_disk_create.name, disk_format=attach_disk_create.format)
    assert vm_disk.message == CommandMessagesEnum.disk_not_found.value
    assert vm_disk.code == CommandMessagesEnum.disk_not_found.name
