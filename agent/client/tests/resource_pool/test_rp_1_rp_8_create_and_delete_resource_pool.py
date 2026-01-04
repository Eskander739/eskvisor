import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.resource_pool import ResourcePoolCreateRequest
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest, VirtualMachine
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.tools import wait_while_not


@pytest.mark.tags("RP‑01", "RP‑08", "Создание пула ресурсов (CPU, memory, storage)", "Удаление пула (пустой)")
def test_rp_01_rp_08_create_and_delete_resource_pool(resource_pool_session):
    """
    RP‑01: Создание пула ресурсов (CPU, memory, storage)
    RP‑08: Удаление пула (пустой)

    Указать имя, лимиты по CPU, памяти, хранилищу. Проверить, что пул появляется в списке.
    Удалить пул, в котором нет ВМ. Проверить, что пул исчезает.
    """
    random_name = None
    request_id = str(uuid.uuid4())
    kb_to_mb = lambda kb: kb / 1024
    try:
        # ____________________________________Создание пула ресурсов____________________________________
        random_name = f"RP-TEST-{random.randint(10000, 99999)}"
        rp_template = ResourcePoolCreateRequest(name=random_name)
        create_vm_info = resource_pool_session.create_resource_pool(rp_template, request_id)
        assert create_vm_info.message == CommandMessagesEnum.vm_successfully_created.value
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        assert create_vm_info.vm_info is not None
        vm_info: VirtualMachine = create_vm_info.vm_info
        # assert wait_while_not(lambda: get_state(random_name) == VMState.SHUTOFF.value)
        assert vm_info.vcpus == vm_template.vcpus
        assert vm_info.name == vm_template.name
        assert kb_to_mb(vm_info.memory) == vm_template.memory_mb
        # ____________________________________Удаление пула ресурсов_____________________________________
    finally:
        # ______________________________Удаление пула ресурсов(постусловие)______________________________
        if random_name is not None:
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name, request_id=request_id)
            assert delete_vm_info.message == CommandMessagesEnum.vm_successfully_deleted.value
            assert delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            assert delete_vm_info.success is True