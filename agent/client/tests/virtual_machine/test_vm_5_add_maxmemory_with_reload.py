import random
import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.vm import (
    VirtualMachine,
    VMCreateRequest,
    VmUpdateRequest,
)
from agent.client.tools import wait_while_not


@pytest.mark.tags("VM‑05", "Увеличение maxmemory с остановкой ВМ")
@pytest.mark.parametrize(
    "vm_resource",
    (
        # VmUpdateRequest(memory_mb=1024),
        VmUpdateRequest(max_memory_mb=512),  # TODO: Hot-unplug добавить в будущем
    ),
)
def test_vm_05_add_maxmemory_with_reload(vm_session, vm_resource):
    """
    VM‑05: Увеличение maxmemory с остановкой ВМ
    """
    vm_created = None
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"

    def kb_to_mb(kb):
        return kb / 1024

    get_state = vm_session.get_vm_state_by_name
    try:
        # ____________________________________Создание ВМ_________________________
        vm_template = VMCreateRequest(
            name=random_name, disks=[DiskCreate()], autostart_vm=True, max_memory_mb=256
        )
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert create_vm_info.vm_info is not None
        vm_info: VirtualMachine = create_vm_info.vm_info
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        assert vm_info.vcpus == vm_template.vcpus
        assert vm_info.name == vm_template.name
        assert kb_to_mb(vm_info.memory) == vm_template.max_memory_mb
        # ____________________________________Изменение ресурсов ВМ_______________
        edit_vm_info = vm_session.edit_vm(random_name, vm_resource)
        assert edit_vm_info.code == CommandMessagesEnum.vm_edit_success.name
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        vm_get_info = vm_session.get_vm_by_name(random_name)
        assert vm_get_info.code == CommandMessagesEnum.vm_successfully_found.name
        assert wait_while_not(
            lambda: kb_to_mb(vm_session.get_vm_by_name(random_name).vm_info.max_memory)
            == vm_resource.max_memory_mb,
            timeout=5,
        )

    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created is not None:
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name)
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
