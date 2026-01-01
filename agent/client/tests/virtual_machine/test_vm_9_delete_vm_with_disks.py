import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest, VirtualMachine
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.tools import wait_while_not


@pytest.mark.tags("VM‑09", "Удаление ВМ (с удалением дисков)")
def test_vm_09_delete_vm_with_disks(vm_session, storage_session):
    """
    VM‑09: Удаление ВМ (с удалением дисков)

    Удалить ВМ вместе с её дисками. Проверить, что все ресурсы освобождаются.
    """
    random_name = None
    vm_deleted = False
    request_id = str(uuid.uuid4())
    kb_to_mb = lambda kb: kb / 1024
    get_state = vm_session.get_vm_state_by_name
    try:
        # ____________________________________Создание ВМ____________________________________

        random_name = f"VM-TEST-{random.randint(10000, 99999)}"
        vm_template = VMCreateRequest(name=random_name, disks=[VMDisk(), VMDisk()])
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.message == CommandMessagesEnum.vm_successfully_created.value
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        assert create_vm_info.vm_info is not None
        vm_info: VirtualMachine = create_vm_info.vm_info
        assert wait_while_not(lambda: get_state(random_name) == VMState.SHUTOFF.value)
        assert vm_info.vcpus == vm_template.vcpus
        assert vm_info.name == vm_template.name
        assert kb_to_mb(vm_info.memory) == vm_template.memory_mb
        disks_by_vm_name = storage_session.get_disks_by_vm(random_name, request_id)
        disk_paths = []
        for current_disk in disks_by_vm_name:
            disk_paths.append(current_disk.path)
        assert len(disks_by_vm_name) == 2
        # ____________________________________Удаление ВМ с дисками____________________________________
        delete_vm_info = vm_session.delete_vm_with_force(name=random_name, request_id=request_id)
        assert delete_vm_info.message == CommandMessagesEnum.vm_successfully_deleted.value
        assert delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
        assert delete_vm_info.success is True
        for current_disk_path in disk_paths:
            disks_by_path = storage_session.get_disk_info(path=current_disk_path, request_id=request_id)
            assert disks_by_path.message == CommandMessagesEnum.disk_not_found.value
            assert disks_by_path.code == CommandMessagesEnum.disk_not_found.name
        vm_deleted = True
    finally:
        # ___________Удаление ВМ(постусловие, если не сработает обычное удаление)____________
        if random_name is not None:
            if not vm_deleted:
                delete_vm_info = vm_session.delete_vm_with_force(name=random_name, request_id=request_id)
                assert delete_vm_info.message == CommandMessagesEnum.vm_successfully_deleted.value
                assert delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
                assert delete_vm_info.success is True