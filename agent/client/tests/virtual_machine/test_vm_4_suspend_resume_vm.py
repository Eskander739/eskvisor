import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.tools import wait_while_not


@pytest.mark.tags("VM‑04", "Приостановка (suspend) и возобновление (resume) ВМ")
def test_vm_04_suspend_resume_vm(vm_session):
    """
    VM‑04: Приостановка (suspend) и возобновление (resume) ВМ

    Приостановить работающую ВМ, затем возобновить. Убедиться, что ВМ продолжает работу с того же места.
    """
    vm_created = None
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"
    get_state = vm_session.get_vm_state_by_name
    try:
        # ____________________________________Создание ВМ_________________________
        vm_template = VMCreateRequest(name=random_name, disks=[DiskCreate()])
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert create_vm_info.vm_info is not None
        assert wait_while_not(lambda: get_state(random_name) == VMState.SHUTOFF.value)

        # ____________________________________Запуск ВМ___________________________
        start_vm_info = vm_session.start_vm(random_name)
        assert start_vm_info.code == CommandMessagesEnum.vm_successfully_started.name

        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        # ____________________________________Остановка ВМ________________________
        stop_vm_info = vm_session.suspend_vm(random_name)

        assert stop_vm_info.code == CommandMessagesEnum.vm_successfully_stopped.name

        assert wait_while_not(lambda: get_state(random_name) == VMState.PAUSED.value)
        # ____________________________________Возобновление ВМ____________________
        resume_vm_info = vm_session.resume_vm(random_name)
        assert resume_vm_info.code == CommandMessagesEnum.vm_successfully_resumed.name

        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)

    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created is not None:
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name)
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
