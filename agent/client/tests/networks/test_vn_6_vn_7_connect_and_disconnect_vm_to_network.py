import os
import random
import time

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskCreate,
    DiskType,
)
from agent.client.hypervisor.libvirt.models.enum import NetworkType
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import (
    NetworkBridge,
    NetworkDHCPRange,
    NetworkForward,
    NetworkParameters,
    VmNetAdapter,
)
from agent.client.hypervisor.libvirt.models.vm import (
    VMCreateRequest,
    NetQemuCommandline,
)
from agent.client.tools import wait_while_not

IMG_PATH = os.environ.get("IMAGE_PATH")


@pytest.mark.tags("VN‑06", "VN‑07", "Подключение ВМ к сети", "Отключение ВМ от сети")
def test_vn_06_vn_07_connect_and_disconnect_vm_to_network(
    network_session, vm_session, virsh_console_session, storage_session
):
    """
    VN‑06: Подключение ВМ к сети
    VN‑07: Отключение ВМ от сети

    Выбрать сеть и подключить к ней ВМ. Убедиться, что ВМ получает сетевые настройки.
    Отсоединить ВМ от сети. Проверить, что сетевой интерфейс в ВМ теряет соединение.
    """

    get_state = vm_session.get_vm_state_by_name
    vm_created = None
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"
    virsh_console = virsh_console_session(random_name)
    vm_template = VMCreateRequest(
        name=random_name,
        autostart_vm=True,
        disks=[
            DiskCreate(path=IMG_PATH, disk_type=DiskType.CDROM),
            DiskCreate(),
        ],
        networks=[VmNetAdapter(network_type=NetworkType.NETWORK)],
        qemu_commandline=NetQemuCommandline(),
    )
    network_name = None
    try:
        # ____________________________________Создание NAT сети________________
        nat_params = NetworkParameters(
            name=f"nat-{random.randint(1000, 9999)}",
            forward=NetworkForward(mode="nat"),
            bridge=NetworkBridge(name="virbr-test-ntt", stp="on", delay=0),
            ipv4_address="192.168.100.0/24",
            dhcp_ranges=[
                NetworkDHCPRange(start="192.168.100.100", end="192.168.100.200")
            ],
            autostart=True,
        )

        network_name = nat_params.name
        created_network_info = network_session.create_network(nat_params)
        assert (
            created_network_info.code
            == CommandMessagesEnum.virtual_network_successfully_created.name
        )
        vm_template.networks[0].source = nat_params.name
        # ____________________________________Создание ВМ_________________________
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert create_vm_info.vm_info is not None
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        time.sleep(30)
        # _________________________Проверка наличия виртуальной сети у ВМ_________
        get_net_vm_info = network_session.get_vm_network_info(vm_template.name)
        assert (
            get_net_vm_info.code
            == CommandMessagesEnum.virtual_network_interfaces_found.name
        )
        assert get_net_vm_info.net_info.network_interfaces.count == 1
        network_interface = get_net_vm_info.net_info.network_interfaces.interfaces.pop()
        network_mac_address = network_interface.mac_address
        assert network_interface.interface_type == NetworkType.NETWORK.value
        assert network_interface.source.name == nat_params.name
        assert network_interface.source.network_info.bridge == nat_params.bridge.name
        # ____________________________________Подключение к ВМ____________________
        virsh_console.connect()
        results = virsh_console.execute_commands(
            ["root", "ip link set eth0 up", "udhcpc -i eth0", "sleep 15", "ip a"]
        )
        result = results.pop()
        assert network_mac_address in result
        # ____________________________Отключить сетевой интерфейс у ВМ____________
        detach_net_itnerface_info = network_session.detach_vm_network_interface(
            random_name, network_mac_address
        )
        assert (
            detach_net_itnerface_info.code
            == CommandMessagesEnum.virtual_network_interface_detached.name
        )
        results = virsh_console.execute_commands(["ip a"])
        result = results.pop()
        assert network_mac_address not in result
        # _________________________Проверка отсутствия виртуальной сети у ВМ______
        get_net_vm_info = network_session.get_vm_network_info(vm_template.name)
        assert (
            get_net_vm_info.code
            == CommandMessagesEnum.virtual_network_interfaces_found.name
        )
        assert get_net_vm_info.net_info.network_interfaces.count == 0
        assert not get_net_vm_info.net_info.network_interfaces.interfaces
    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created:
            delete_vm_info = vm_session.delete_vm_with_force(
                name=random_name, delete_disks=False
            )
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
            disk_path = (
                vm_template.disks[1].path
                + "/"
                + vm_template.disks[1].name
                + "."
                + vm_template.disks[1].format.value
            )
            delete_disk = storage_session.delete_disk(disk_path=disk_path)
            assert delete_disk is True
        # ____________________________________Удаление сети(постусловие)__________
        if network_name is not None:
            network_session.delete_network(network_name, True)
            v_network = network_session.get_network_info(network_name)
            assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name
