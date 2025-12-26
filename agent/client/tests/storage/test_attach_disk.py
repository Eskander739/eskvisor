import os

import pytest

from agent.client.hypervisor.models.disk import DiskCreate, DiskFormat, DiskStatus


@pytest.mark.tags("VD‑02", "Подключение диска к ВМ")
def test_vd_02_attach_disk(storage_session, setup_test_environment):
    """
    VD‑02: Подключение диска к ВМ

    Выбрать существующий диск и подключить к работающей/остановленной ВМ.
    Убедиться, что ВМ видит диск.
    """
    # Создаем тестовый диск для подключения
    attach_disk_path = os.path.join(setup_test_environment.get("attached_dir"), "attach-test-disk.qcow2")

    attach_disk_create = DiskCreate(
        name="attach-test-disk.qcow2",
        path=attach_disk_path,
        size_gb=0.5,
        format=DiskFormat.QCOW2,
        sparse=True
    )

    attach_disk = storage_session.create_disk(attach_disk_create)
    assert attach_disk is not None, "Ошибка: диск для подключения не создан"

    vm_disk = storage_session.get_disk_info(attach_disk_path)

    assert vm_disk.status.value == DiskStatus.DETACHED.value

    storage_session.attach_disk_to_vm("test-vm-01", attach_disk_path)

    vm_disk = storage_session.get_disk_info(attach_disk_path)

    assert vm_disk.status.value == DiskStatus.ATTACHED.value


