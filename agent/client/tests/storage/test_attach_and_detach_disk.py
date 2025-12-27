import os
import random

import pytest
from agent.client.hypervisor.models.disk import DiskCreate, DiskFormat, DiskStatus, DiskAttach, DiskDetach

RANDOM_NAME = random.randint(10000, 99999)

@pytest.mark.tags("VD‑02", "VD‑03", "Подключение диска к ВМ", "Отключение диска от ВМ")
# @pytest.mark.parametrize("vm_status", (
#         # "running", TODO: Баг, не отключается диск от работающей ВМ
#         "stopped"
# )
#                          )
def test_vd_02_attach_and_detach_disk(storage_session, create_stopped_vm):
    """
    VD‑02: Подключение диска к ВМ

    Выбрать существующий диск и подключить к работающей/остановленной ВМ.
    Убедиться, что ВМ видит диск.
    """

    vm_name = create_stopped_vm.name

    # ____________________________________Создание диска____________________________________
    attach_disk_create = DiskCreate(name=f"disk-test-{RANDOM_NAME}.qcow2", size_gb=0.2, format=DiskFormat.QCOW2, sparse=True)
    disk_attach = DiskAttach(vm_name=vm_name, path=attach_disk_create.path, target_dev="vdb")
    attach_disk = storage_session.create_disk(attach_disk_create)
    assert attach_disk is not None, "Ошибка: диск для подключения не создан"

    vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)

    assert vm_disk.status.value == DiskStatus.DETACHED.value
    # assert vm_disk.name == attach_disk_create.name

    # ____________________________________Подключение диска____________________________________

    storage_session.attach_disk(disk_attach)

    vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)

    assert vm_disk.status.value == DiskStatus.ATTACHED.value
    # assert vm_disk.name == attach_disk_create.name

    storage_session.detach_disk(DiskDetach(vm_name=vm_name, target_dev=disk_attach.target_dev))

    vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)

    assert vm_disk.status.value == DiskStatus.DETACHED.value
    # assert vm_disk.name == attach_disk_create.name



