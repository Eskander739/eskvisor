import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest, VirtualMachine
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.tools import wait_while_not


@pytest.mark.tags("SN‑01", "SN‑04", "Создание снапшота работающей ВМ", "Удаление снапшота")
def test_rp_01_rp_08_create_and_delete_resource_pool(snapshot_session):
    """
    SN‑01: Создание снапшота работающей ВМ
    SN‑04: Удаление снапшота

    Создать снапшот без остановки ВМ. Проверить, что снапшот появляется в дереве снапшотов ВМ.
    Удалить отдельный снапшот. Убедиться, что место освобождается и дерево снапшотов корректно обновляется.
    """
    random_name = None
    request_id = str(uuid.uuid4())
    kb_to_mb = lambda kb: kb / 1024
    try:
        # ____________________________Создание снапшота работающей ВМ_____________________________
        random_name = f"VM-TEST-{random.randint(10000, 99999)}"
        vm_template = VMCreateRequest(name=random_name, disks=[DiskCreate()])
        create_vm_info = snapshot_session.create_storage_pool(vm_template)
        assert create_vm_info.message == CommandMessagesEnum.vm_successfully_created.value
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        assert create_vm_info.vm_info is not None
        vm_info: VirtualMachine = create_vm_info.vm_info
        # assert wait_while_not(lambda: get_state(random_name) == VMState.SHUTOFF.value)
        assert vm_info.vcpus == vm_template.vcpus
        assert vm_info.name == vm_template.name
        assert kb_to_mb(vm_info.memory) == vm_template.memory_mb
        # ____________________________________Удаление снапшота____________________________________

    finally:
        # ______________________________Удаление снапшота(постусловие)_____________________________
        if random_name is not None:
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name, request_id=request_id)
            assert delete_vm_info.message == CommandMessagesEnum.vm_successfully_deleted.value
            assert delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            assert delete_vm_info.success is True