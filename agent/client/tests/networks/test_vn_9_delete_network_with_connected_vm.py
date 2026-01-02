import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import NetworkParameters, NetworkForward, NetworkBridge, \
    NetworkDHCPRange


@pytest.mark.tags("VN‑09", "Попытка удаления сети с подключенной ВМ")
def test_vn_09_delete_network_with_connected_vm(network_session):
    """
    VN‑09: Попытка удаления сети с подключенной ВМ

    Удалить сеть, к которой подключены ВМ. Проверить, что сеть не исчезает из списка.
    """
    request_id = str(uuid.uuid4())
    network_name = None
    try:
        # ____________________________________Создание виртуальной NAT сети____________________________________
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
        created_network_info = network_session.create_network(nat_params, request_id)
        assert created_network_info.message == CommandMessagesEnum.virtual_network_successfully_created.value
        # _____________________________Создание ВМ и подключение созданной сети NAT_____________________________
        raise NotImplementedError

    finally:
        # ____________________________________Удаление сети(постусловие)____________________________________
        if network_name is not None:
            network_session.delete_network(network_name, request_id, True)
            v_network = network_session.get_network_info(network_name, request_id)
            assert v_network.message == CommandMessagesEnum.virtual_network_not_found.value
            assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name