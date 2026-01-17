import os
import random

import pytest
from dotenv import load_dotenv

from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskCreate,
    DiskFormat,
    DiskStatus,
)
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


load_dotenv()
SYSTEM_VOLUME_GROUP_NAME = os.environ.get("VOLUME_GROUP")


@pytest.mark.tags("VD‑12", "Создание виртуального диска в ресурс пуле")
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
def test_vd_12_create_disk_to_resource_pool(
    storage_session,
    resource_pool_session,
    create_resource_pool_session,
    disk_format,
):
    """
    VD‑12: Создание виртуального диска в ресурс пуле

    Создать диск QCOW2/RAW в ресурс пуле, проверить что диск создан корректно, работает чтение/запись
    """

    rp_name = create_resource_pool_session
    random_name = random.randint(10000, 99999)
    attach_disk_create = DiskCreate(
        name=f"disk-test-{random_name}",
        size_gb=0.2,
        format=disk_format,
        description="Create disk description",
        resource_pool=rp_name,
    )
    try:
        # ____________________________________Создание диска______________________
        attach_disk = storage_session.create_disk(attach_disk_create)
        assert attach_disk.message == CommandMessagesEnum.disk_successfully_created.value
        assert attach_disk.code == CommandMessagesEnum.disk_successfully_created.name
        print("attach_disk_create.path: ", attach_disk_create.path)
        vm_disk = storage_session.get_disk_info(disk_name=attach_disk_create.name, path=attach_disk_create.path, disk_format=attach_disk_create.format, is_pool=True)
        logic_volume_disk_current = storage_session.logic_volume_manager.get_volume_by_name(attach_disk_create.name, SYSTEM_VOLUME_GROUP_NAME)
        vm_disk = vm_disk.disk_info
        assert vm_disk.status.value == DiskStatus.DETACHED.value
        assert vm_disk.name == attach_disk_create.name
        assert vm_disk.format == disk_format
        assert vm_disk.file_path_exists is True
        if disk_format == DiskFormat.RAW:
            assert vm_disk.path == logic_volume_disk_current.logic_volume_path

    finally:
        # ____________________________________Удаление диска(постусловие)_________
        if disk_format == DiskFormat.QCOW2:
            delete_disk_info = storage_session.delete_pool_disk_qcow2(disk_name=attach_disk_create.name)
            assert delete_disk_info is True
        else:
            delete_disk_info = storage_session.delete_pool_disk_raw(disk_name=attach_disk_create.name)
            assert delete_disk_info is True
