import random
import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest


@pytest.mark.tags("VM‑01", "Создание ВМ с проверкой включения/отключения Secure Boot")
@pytest.mark.parametrize("vm_state", (VMState.SHUTOFF, VMState.RUNNING))
@pytest.mark.parametrize("secure_boot", [True, False])
def test_vm_01_create_vm_with_secure_boot(vm_session, vm_state, secure_boot):
    """
    VM‑01: Создание ВМ с проверкой включения/отключения Secure Boot
    """
    vm_created = None
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"

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
            boot_uefi=True,
            secure_boot=secure_boot,
            **autostart,
        )
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        # ___________________Проверка наличия/отсутствия Secure Boot______________
        secure_boot_info = vm_session.get_vm_secure_boot_status(random_name)
        assert secure_boot_info.has_uefi is True
        assert secure_boot_info.has_secure_boot is secure_boot
    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created is not None:
            if vm_state == VMState.RUNNING:
                delete_vm_info = vm_session.delete_vm_with_force(name=random_name)
                assert (
                        delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
                )
                assert delete_vm_info.success is True
