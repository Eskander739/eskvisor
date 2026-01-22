import random
import time
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.vm import VirtualMachine, VMCreateRequest
from agent.client.tools import wait_while_not


MAC_ADDRESSES = [
    "52:54:00:12:34:56",
    "52:54:00:AB:CD:EF",
    "00:16:3E:78:90:AB",
    "00:16:3E:CD:EF:12",
    "02:00:00:34:56:78",
    "02:00:00:9A:BC:DE",
    "52:54:00:65:43:21",
    "00:16:3E:21:43:65",
    "52:54:00:FE:DC:BA",
    "02:00:00:BA:98:76",
]


@pytest.mark.tags("VM‑07", "Подключение/отключение сети")
def test_vm_07_attach_and_detach_network_adapter(
    vm_session, network_session, create_nat_network_session
):
    """
    VM‑07: Подключение/отключение сети

    Добавить второй сетевой интерфейс, затем отключить его. Проверить, что сетевые настройки в гостевой ОС обновляются.
    """
    vm_created = None
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"

    def kb_to_mb(kb):
        return kb / 1024

    get_state = vm_session.get_vm_state_by_name
    network_name = create_nat_network_session
    try:
        # ____________________________________Создание ВМ_________________________
        new_disk_name = f"disk-{str(random.randint(100000, 999999))}"
        vm_template = VMCreateRequest(
            name=random_name,
            description=f"VM-TEST-{random.randint(10000, 99999)}-DESCRIPTION",
            disks=[DiskCreate(name=new_disk_name)],
            memory_mb=512,
            autostart_vm=True,
        )
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert create_vm_info.vm_info is not None
        vm_info: VirtualMachine = create_vm_info.vm_info
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        assert vm_info.vcpus == vm_template.vcpus
        assert vm_info.name == vm_template.name
        assert vm_info.description == vm_template.description
        assert kb_to_mb(vm_info.memory) == vm_template.memory_mb
        # ____________________________________Подключение сетевого интерфейса_________________________
        random_mac_address = random.choice(MAC_ADDRESSES).lower()
        network_attach_info = network_session.attach_vm_network_interface(
            random_name, network_name, mac_address=random_mac_address
        )
        assert (
            network_attach_info.code
            == CommandMessagesEnum.virtual_network_interface_attached.name
        )
        # ____________________________________Проверка наличия нового сетевого интерфейса_________________________
        get_vm_info = network_session.get_vm_network_info(random_name)
        assert len(get_vm_info.net_info.network_interfaces.interfaces) == 2
        for (
            current_network_interface
        ) in get_vm_info.net_info.network_interfaces.interfaces:
            vm_session.logger.warning(
                f"Интерфейс: {current_network_interface.model_dump_json()}"
            )
            if (
                current_network_interface.mac_address == random_mac_address
                and current_network_interface.source.name == network_name
            ):
                break
        else:
            raise AssertionError(f"Не найден подключенный сетевой интерфейс")
        # ____________________________________Отключение сетевого интерфейса_________________________
        detach_network_info = network_session.detach_vm_network_interface(
            random_name, random_mac_address
        )
        vm_session.shutoff_vm(random_name, True)
        vm_session.start_vm(
            random_name
        )  # TODO: Отключение происходит только после destroy -> start
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        assert (
            detach_network_info.code
            == CommandMessagesEnum.virtual_network_interface_detached.name
        )
        # ____________________________________Проверка отсутствия нового сетевого интерфейса_________________________
        get_net_info = network_session.get_vm_network_info(random_name)
        assert len(get_net_info.net_info.network_interfaces.interfaces) == 1
        for (
            current_network_interface
        ) in get_net_info.net_info.network_interfaces.interfaces:
            vm_session.logger.warning(
                f"Интерфейс: {current_network_interface.model_dump_json()}"
            )
            if (
                current_network_interface.mac_address == random_mac_address
                and current_network_interface.source.name == network_name
            ):
                raise AssertionError(f"Найден подключенный сетевой интерфейс")

    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created is not None:
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name)
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
