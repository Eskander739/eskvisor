import random
from ipaddress import IPv4Network

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import (
    NetworkBridge,
    NetworkDHCPRange,
    NetworkForward,
    NetworkParameters,
)


@pytest.mark.tags("VN‑02", "Создание NAT-сети")
def test_vn_02_create_nat_network(network_session):
    """
    VN‑02: Создание NAT-сети

    Создать сеть с NAT и DHCP. Убедиться, что ВМ получают IP-адреса и имеют выход в интернет.
    """
    network_name = None
    try:
        # ____________________________________Создание виртуальной NAT сети_______
        random_int = random.randint(1000, 9999)
        nat_params = NetworkParameters(
            name=f"nat-test-{random_int}",
            forward=NetworkForward(mode="nat"),
            bridge=NetworkBridge(name=f"virbr-test-{random_int}", stp="on", delay=0),
            ipv4_address=IPv4Network("192.168.100.0/24"),
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
        nat_network = created_network_info.net_info
        assert nat_network.network_type.role == "nat"
        assert nat_network.name == nat_params.name
        assert nat_network.active is True
        assert nat_network.autostart is True

    finally:
        # ____________________________________Удаление сети(постусловие)__________
        if network_name is not None:
            network_session.delete_network(network_name, True)
            v_network = network_session.get_network_info(network_name)
            assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name
