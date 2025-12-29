import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.hypervisor.models.general import VMState
from agent.client.hypervisor.models.msg import CommandMessagesEnum
from agent.client.hypervisor.models.vm import VirtualMachine
from agent.client.tools import wait_while_not


@pytest.mark.tags("VM‑10", "Просмотр консоли ВМ")
def test_vm_10_connect_vm_console(vm_session, storage_session):
    """
    VM‑10: Просмотр консоли ВМ

    Открыть графическую или текстовую консоль ВМ, убедиться, что можно взаимодействовать с гостевой ОС.
    """
    random_name = None
    vm_deleted = False
    request_id = str(uuid.uuid4())
    get_state = vm_session.get_vm_state_by_name
    try:
        # ____________________________________Создание ВМ____________________________________

        random_name = f"VM-TEST-{random.randint(10000, 99999)}"
        vm_template = VMCreateRequest(name=random_name, disks=[VMDisk()])
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.message == CommandMessagesEnum.vm_successfully_created.value
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        assert create_vm_info.vm_info is not None
        assert wait_while_not(lambda: get_state(random_name) == VMState.SHUTOFF.value)
        # ____________________________________Подключение к ВМ____________________________________
        raise NotImplementedError
    finally:
        # ___________Удаление ВМ(постусловие, если не сработает обычное удаление)____________
        if random_name is not None:
            if not vm_deleted:
                delete_vm_info = vm_session.delete_vm_with_force(name=random_name, request_id=request_id)
                assert delete_vm_info.message == CommandMessagesEnum.vm_successfully_deleted.value
                assert delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
                assert delete_vm_info.success is True