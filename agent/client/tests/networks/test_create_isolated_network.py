import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import NetworkParameters


@pytest.mark.tags("VN‑01", "Создание изолированной сети (isolated)")
def test_vn_01_create_isolated_network(network_session):
    """
    VN‑01: Создание изолированной сети (isolated)

    Указать имя, тип isolated. Проверить, что сеть появляется в списке.
    """
    request_id = str(uuid.uuid4())
    network_name = None
    try:
        # ____________________________________Создание виртуальной изолированной сети____________________________________
        isolated_params = NetworkParameters(
            name=f"isolated-{random.randint(1000, 9999)}",
            ipv4=True,
            ipv4_address="192.168.101.0/24",
            isolated=True,
            autostart=True,
        )
        network_name = isolated_params.name
        created_network_info = network_session.create_network(isolated_params, request_id)
        assert created_network_info.message == CommandMessagesEnum.virtual_network_successfully_created.value
        assert created_network_info.code == CommandMessagesEnum.virtual_network_successfully_created.name
        isolated_network = created_network_info.net_info
        assert isolated_network.network_type.type == "no-forward"
        assert isolated_network.name == isolated_params.name
        assert isolated_network.active is True
        assert isolated_network.autostart is True

    finally:
        # ____________________________________Удаление сети(постусловие)____________________________________
        if network_name is not None:
            network_session.delete_network(network_name, request_id, True)
            v_network = network_session.get_network_info(network_name, request_id)
            assert v_network.message == CommandMessagesEnum.virtual_network_not_found.value
            assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name