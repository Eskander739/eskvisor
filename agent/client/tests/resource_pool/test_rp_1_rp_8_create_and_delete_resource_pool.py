import random
import uuid

import pytest

from agent.client.hypervisor.libvirt.models.resource_pool import ResourcePoolCreateRequest
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum


@pytest.mark.tags("RP‑01", "RP‑08", "Создание пула ресурсов (CPU, memory, storage)", "Удаление пула (пустой)")
def test_rp_01_rp_08_create_and_delete_resource_pool(resource_pool_session):
    """
    RP‑01: Создание пула ресурсов (CPU, memory, storage)
    RP‑08: Удаление пула (пустой)

    Указать имя, лимиты по CPU, памяти, хранилищу. Проверить, что пул появляется в списке.
    Удалить пул, в котором нет ВМ. Проверить, что пул исчезает.
    """
    random_name = None
    rp_deleted = False
    request_id = str(uuid.uuid4())
    try:
        # ____________________________________Создание пула ресурсов____________________________________
        random_name = f"RP-TEST-{random.randint(10000, 99999)}"
        rp_template = ResourcePoolCreateRequest(name=random_name, cpu_limit=2, memory_limit=512, storage_limit=1)
        create_rp_info = resource_pool_session.create_resource_pool(rp_template, request_id)
        assert create_rp_info.message == CommandMessagesEnum.rp_create_success.value
        assert create_rp_info.code == CommandMessagesEnum.rp_create_success.name
        assert create_rp_info.rp_info is not None
        get_rp_info = resource_pool_session.get_pool_info(random_name, request_id)
        assert get_rp_info.rp_info.name == random_name
        # ____________________________________Удаление пула ресурсов_____________________________________
        delete_rp_info = resource_pool_session.delete_resource_pool(random_name, request_id)
        assert delete_rp_info.message == CommandMessagesEnum.rp_delete_success.value
        assert delete_rp_info.code == CommandMessagesEnum.rp_delete_success.name
        get_rp_info = resource_pool_session.get_pool_info(random_name, request_id)
        assert get_rp_info.message == CommandMessagesEnum.rp_not_found.value
        assert get_rp_info.code == CommandMessagesEnum.rp_not_found.name
        rp_deleted = True
    finally:
        # ______________________________Удаление пула ресурсов(постусловие)______________________________
        if not rp_deleted:
            delete_rp_info = resource_pool_session.delete_resource_pool(random_name, request_id)
            assert delete_rp_info.message in (CommandMessagesEnum.rp_delete_success.value, CommandMessagesEnum.rp_not_found.value)
            assert delete_rp_info.code == (CommandMessagesEnum.rp_delete_success.name, CommandMessagesEnum.rp_not_found.name)
            assert delete_rp_info.success is True