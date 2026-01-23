import random
import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.tools import wait_while_not


@pytest.mark.tags("VM‑03", "Запуск/остановка/перезагрузка ВМ")
def test_vm_03_start_stop_restart_vm(vm_session):
    """
    VM‑03: Запуск/остановка/перезагрузка ВМ

    Выполнить операции power on, power off, restart. Проверить, что состояние ВМ меняется соответственно.
    """
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"
    vm_created = None
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
        # # ____________________________________Перезапуск ВМ_____________________
        # TODO: ВМ перезапускается слишком быстро, доработать
        # reboot_vm_info = vm_session.reboot_vm(random_name)
        # assert reboot_vm_info.code == CommandMessagesEnum.vm_successfully_restarted.name
        #
        # print("get_state(random_name): ", get_state(random_name))
        # assert wait_while_not(lambda: get_state(random_name) == VMState.SHUTDOWN.value, timeout=3)
        # assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value, timeout=3)
        # ____________________________________Выключение ВМ_______________________
        stop_vm_info = vm_session.shutoff_vm(random_name, force=True)
        assert stop_vm_info.code == CommandMessagesEnum.vm_successfully_shutdowned.name

        assert wait_while_not(lambda: get_state(random_name) == VMState.SHUTOFF.value)

    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created is not None:
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name)
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
