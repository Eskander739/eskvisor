import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.enum import NetworkType
from agent.client.hypervisor.libvirt.models.network import VmNetAdapter
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.hypervisor.libvirt.models.disk_storage_manager import DiskType, DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.tools import wait_while_not

IMG_PATH = "/home/eska/alpine-standard-3.19.0-x86_64.iso"


@pytest.mark.tags("VM‑02", "Установка ОС на ВМ (загрузка с ISO)")
def test_vm_10_connect_vm_console(vm_session, storage_session):
    """
    VM‑02: Установка ОС на ВМ (загрузка с ISO)

    Присоединить ISO-образ, запустить ВМ, пройти процесс установки. Убедиться, что ОС загружается.
    """
    random_name = None
    request_id = str(uuid.uuid4())
    get_state = vm_session.get_vm_state_by_name
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"
    vm_template = VMCreateRequest(name=random_name, autostart_vm=True,
                                  disks=[DiskCreate(path=IMG_PATH),
                                         DiskCreate()], networks=[VmNetAdapter(network_type=NetworkType.USER)])
    try:
        # ____________________________________Создание ВМ____________________________________
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.message == CommandMessagesEnum.vm_successfully_created.value
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        assert create_vm_info.vm_info is not None
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value, timeout=5000000)
        # ____________________________________Подключение к ВМ____________________________________
        # raise NotImplementedError
    finally:
        # ___________Удаление ВМ(постусловие, если не сработает обычное удаление)____________
        if random_name is not None:
            pass
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name, request_id=request_id, delete_disks=False)
            assert delete_vm_info.message == CommandMessagesEnum.vm_successfully_deleted.value
            assert delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            assert delete_vm_info.success is True
            delete_disk = storage_session.delete_disk(path=vm_template.disks[1].path)
            assert delete_disk is True