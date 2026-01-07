import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import (
    NetworkBridge,
    NetworkDHCPRange,
    NetworkForward,
    NetworkParameters,
)


@pytest.mark.tags("VN‑08", "Удаление сети")
@pytest.mark.parametrize(
    "network_model",
    (
        NetworkParameters(
            name=f"nat-{random.randint(1000, 9999)}",
            forward=NetworkForward(mode="nat"),
            bridge=NetworkBridge(name="virbr-test-ntt", stp="on", delay=0),
            ipv4_address="192.168.100.0/24",
            dhcp_ranges=[
                NetworkDHCPRange(start="192.168.100.100", end="192.168.100.200")
            ],
            autostart=True,
        ),
        NetworkParameters(
            name=f"isolated-{random.randint(1000, 9999)}",
            ipv4=True,
            ipv4_address="192.168.101.0/24",
            isolated=True,
            autostart=True,
        ),
        NetworkParameters(
            name=f"bridge-{random.randint(1000, 9999)}",
            forward=NetworkForward(mode="bridge"),
            bridge=NetworkBridge(name="virbr-test-bridge"),
            autostart=True,
        ),
    ),
)
def test_vn_08_delete_network(network_session, network_model):
    """
    VN‑08: Удаление сети

    Удалить сеть, к которой не подключены ВМ. Проверить, что сеть исчезает из списка.
    """
    request_id = str(uuid.uuid4())
    network_name = None
    network_deleted = False
    try:
        # ____________________________________Создание виртуальной сети___________
        network_name = network_model.name
        created_network_info = network_session.create_network(network_model, request_id)
        assert (
            created_network_info.message
            == CommandMessagesEnum.virtual_network_successfully_created.value
        )
        # ____________________________________Удаление виртуальной сети___________
        delete_network_info = network_session.delete_network(
            network_name, request_id, True
        )
        assert (
            delete_network_info.message
            == CommandMessagesEnum.virtual_network_successfully_deleted.value
        )
        assert (
            delete_network_info.code
            == CommandMessagesEnum.virtual_network_successfully_deleted.name
        )
        v_network = network_session.get_network_info(network_name, request_id)
        assert v_network.message == CommandMessagesEnum.virtual_network_not_found.value
        assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name
        network_list = network_session.list_all_networks()
        for current_network in network_list:
            assert current_network.name != network_name
        network_deleted = True

    finally:
        # ____________________________________Удаление сети(постусловие)__________
        if network_name is not None and not network_deleted:
            network_session.delete_network(network_name, request_id, True)
            v_network = network_session.get_network_info(network_name, request_id)
            assert (
                v_network.message == CommandMessagesEnum.virtual_network_not_found.value
            )
            assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name
