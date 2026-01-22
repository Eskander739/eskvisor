import os
import random
import time

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate, DiskType
from agent.client.hypervisor.libvirt.models.enum import NetworkType
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import VmNetAdapter
from agent.client.hypervisor.libvirt.models.vm import (
    VMCreateRequest,
    NetQemuCommandline,
)
from agent.client.tools import wait_while_not

IMG_PATH = os.environ.get("IMAGE_PATH")


@pytest.mark.tags(
    "VM‑02", "VM‑10", "Установка ОС на ВМ (загрузка с ISO)", "Просмотр консоли ВМ"
)
def test_vm_2_connect_iso_image(vm_session, storage_session, virsh_console_session):
    """
    VM‑02: Установка ОС на ВМ (загрузка с ISO)

    Присоединить ISO-образ, запустить ВМ, пройти процесс установки. Убедиться, что ОС загружается.

    VM‑10: Просмотр консоли ВМ

    Открыть графическую или текстовую консоль ВМ, убедиться, что можно взаимодействовать с гостевой ОС.
    """

    vm_created = None
    get_state = vm_session.get_vm_state_by_name
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"
    virsh_console = virsh_console_session(random_name)
    vm_template = VMCreateRequest(
        name=random_name,
        autostart_vm=True,
        disks=[
            DiskCreate(path=IMG_PATH, disk_type=DiskType.CDROM),
            DiskCreate(name=f"disk-{str(random.randint(100000, 999999))}"),
        ],
        networks=[VmNetAdapter(network_type=NetworkType.USER)],
        qemu_commandline=NetQemuCommandline(),
    )
    try:
        # ____________________________________Создание ВМ_________________________
        create_vm_info = vm_session.create_vm(vm_template)
        assert (
            create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        ), create_vm_info.note
        vm_created = True
        assert create_vm_info.vm_info is not None
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        time.sleep(60)
        # ____________________________________Подключение к ВМ____________________
        virsh_console.connect()
        results = virsh_console.execute_commands(
            ["root", "cd /", "mkdir hello_eskvisor", "ls"]
        )
        for result in results:
            if result and "hello_eskvisor" in result:
                break
        else:
            raise AssertionError("Некорректное подключение к ВМ")

    finally:
        # ___________Удаление ВМ(постусловие, если не сработает обычное удаление)_
        if vm_created is not None:
            delete_vm_info = vm_session.delete_vm_with_force(
                name=random_name, delete_disks=False
            )
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            path = (
                vm_template.disks[1].path
                if vm_template.disks[1].path != IMG_PATH
                else vm_template.disks[0].path
            )
            disk_path = (
                path
                + "/"
                + vm_template.disks[1].name
                + "."
                + vm_template.disks[1].format.value
            )
            assert delete_vm_info.success is True
            delete_disk = storage_session.delete_disk(disk_path=disk_path)
            assert delete_disk is True
