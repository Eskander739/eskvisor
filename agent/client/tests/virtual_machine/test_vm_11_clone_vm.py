import random
import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.vm import VirtualMachine, VMCreateRequest
from agent.client.tools import wait_while_not


@pytest.mark.tags("VM‑11", "Клонировать ВМ с дисками")
@pytest.mark.parametrize("vm_state", (VMState.SHUTOFF, VMState.RUNNING))
def test_vm_11_clone_vm(vm_session, storage_session, vm_state):
    """
    VM‑11: Клонировать ВМ с дисками

    Клонировать ВМ с дисками, проверить что ВМ и диски успешно клонированы
    """

    def kb_to_mb(kb):
        return kb / 1024

    vm_created = None
    clone_vm_created = None
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"
    cloned_vm_name = f"CLONED-VM-TEST-{random.randint(10000, 99999)}"

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
            disks=[DiskCreate(name=new_disk_name, size_gb=0.1)],
            memory_mb=512,
            **autostart,
        )
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert wait_while_not(lambda: get_state(random_name) == vm_state.value, 5)
        # ____________________________________Клонирование ВМ_________________________
        clone_vm_info = vm_session.clone_vm(random_name, cloned_vm_name)
        assert clone_vm_info.code == CommandMessagesEnum.vm_successfully_cloned.name
        # ____________________________________Проверка клонирования ВМ_________________________
        vm_get_info = vm_session.get_vm_by_name(cloned_vm_name)
        vm_info: VirtualMachine = vm_get_info.vm_info
        assert vm_get_info.code == CommandMessagesEnum.vm_successfully_found.name
        clone_vm_created = True
        assert vm_info.name == cloned_vm_name
        assert vm_info.vcpus == vm_template.vcpus
        assert vm_info.description == vm_template.description
        assert vm_info.uuid != create_vm_info.vm_info.uuid
        assert kb_to_mb(vm_info.memory) == vm_template.memory_mb
        assert wait_while_not(
            lambda: get_state(cloned_vm_name) == VMState.SHUTOFF.value, timeout=5
        )
        disk_info = storage_session.get_disks_by_vm(cloned_vm_name)
        assert len(disk_info) == 1
        disk_info = disk_info.pop()
        assert cloned_vm_name in disk_info.name
        assert 0 < disk_info.capacity_gb < 0.1
    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created is not None:
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name)
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
        if clone_vm_created is not None:
            delete_vm_info = vm_session.delete_vm_with_force(name=cloned_vm_name)
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
