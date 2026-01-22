import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.vm import VirtualMachine, VMCreateRequest
from agent.client.tools import wait_while_not


@pytest.mark.tags("VM‑01", "Создание ВМ (без установки ОС)")
@pytest.mark.parametrize("vm_state", (VMState.SHUTOFF, VMState.RUNNING))
def test_vm_01_create_vm(vm_session, vm_state):
    """
    VM‑01: Создание ВМ (без установки ОС)

    Указать имя, ресурсы (CPU, RAM, диск), сеть. Проверить, что ВМ появляется в списке в состоянии «Выключена».
    """
    vm_created = None
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"
    def kb_to_mb(kb):
        return kb / 1024

    get_state = vm_session.get_vm_state_by_name
    try:
        # ____________________________________Создание ВМ_________________________
        autostart = {}
        if vm_state.value == vm_state.RUNNING.value:
            autostart["autostart_vm"] = True
        new_disk_name = f"disk-{str(random.randint(100000, 999999))}"
        vm_template = VMCreateRequest(
            name=random_name,
            description=f"VM-TEST-{random.randint(10000, 99999)}-DESCRIPTION",
            disks=[DiskCreate(name=new_disk_name)],
            memory_mb=512,
            **autostart,
        )
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert create_vm_info.vm_info is not None
        vm_info: VirtualMachine = create_vm_info.vm_info
        assert wait_while_not(lambda: get_state(random_name) == vm_state.value)
        assert vm_info.vcpus == vm_template.vcpus
        assert vm_info.name == vm_template.name
        assert vm_info.description == vm_template.description
        assert kb_to_mb(vm_info.memory) == vm_template.memory_mb
    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created is not None:
            if vm_state.value == vm_state.SHUTOFF.value:
                delete_vm_info = vm_session.delete_vm_with_force(name=random_name)
                assert (
                        delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
                )
                assert delete_vm_info.success is True
