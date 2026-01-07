import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import (
    NetworkBridge,
    NetworkForward,
    NetworkParameters,
)


@pytest.mark.tags("VN‑03", "Создание bridge-сети")
def test_vn_03_create_bridge_network(network_session):
    """
    VN‑03: Создание bridge-сети

    Привязать виртуальную сеть к физическому интерфейсу. Проверить, что ВМ видны в физической сети.
    """
    request_id = str(uuid.uuid4())
    network_name = None
    try:
        # ____________________________________Создание виртуальной Bridge сети____
        bridge_params = NetworkParameters(
            name=f"bridge-{random.randint(1000, 9999)}",
            forward=NetworkForward(mode="bridge"),
            bridge=NetworkBridge(name="virbr-test-bridge"),
            autostart=True,
        )
        network_name = bridge_params.name
        created_network_info = network_session.create_network(bridge_params, request_id)
        assert (
            created_network_info.message
            == CommandMessagesEnum.virtual_network_successfully_created.value
        )
        assert (
            created_network_info.code
            == CommandMessagesEnum.virtual_network_successfully_created.name
        )
        bridge_network = created_network_info.net_info
        assert bridge_network.network_type.type == "bridge"
        assert bridge_network.name == bridge_params.name
        assert bridge_network.active is True
        assert bridge_network.autostart is True

    finally:
        # ____________________________________Удаление сети(постусловие)__________
        if network_name is not None:
            network_session.delete_network(network_name, request_id, True)
            v_network = network_session.get_network_info(network_name, request_id)
            assert (
                v_network.message == CommandMessagesEnum.virtual_network_not_found.value
            )
            assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name
