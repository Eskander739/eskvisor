import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.tools import wait_while_not


@pytest.mark.tags("VM‑03", "Запуск/остановка/перезагрузка ВМ")
def test_vm_03_start_stop_restart_vm(vm_session):
    """
    VM‑03: Запуск/остановка/перезагрузка ВМ

    Выполнить операции power on, power off, restart. Проверить, что состояние ВМ меняется соответственно.
    """
    random_name = None
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

        # ____________________________________Запуск ВМ____________________________________
        start_vm_info = vm_session.start_vm(random_name, request_id)
        assert start_vm_info.message == CommandMessagesEnum.vm_successfully_started.value
        assert start_vm_info.code == CommandMessagesEnum.vm_successfully_started.name

        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        # # ____________________________________Перезапуск ВМ____________________________________
        # TODO: ВМ перезапускается слишком быстро, доработать
        # reboot_vm_info = vm_session.reboot_vm(random_name, request_id)
        # assert reboot_vm_info.message == CommandMessagesEnum.vm_successfully_restarted.value
        # assert reboot_vm_info.code == CommandMessagesEnum.vm_successfully_restarted.name
        #
        # print("get_state(random_name): ", get_state(random_name))
        # assert wait_while_not(lambda: get_state(random_name) == VMState.SHUTDOWN.value, timeout=3)
        # assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value, timeout=3)
        # ____________________________________Выключение ВМ____________________________________
        stop_vm_info = vm_session.shutdown_vm(random_name, request_id, force=True)
        assert stop_vm_info.message == CommandMessagesEnum.vm_successfully_shutdowned.value
        assert stop_vm_info.code == CommandMessagesEnum.vm_successfully_shutdowned.name

        assert wait_while_not(lambda: get_state(random_name) == VMState.SHUTOFF.value)

    finally:
        # ____________________________________Удаление ВМ(постусловие)____________________________________
        if random_name is not None:
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name, request_id=request_id)
            assert delete_vm_info.message == CommandMessagesEnum.vm_successfully_deleted.value
            assert delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            assert delete_vm_info.success is True