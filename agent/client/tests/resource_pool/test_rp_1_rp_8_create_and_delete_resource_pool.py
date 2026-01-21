import os
import random

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualCreate,
)
from agent.client.hypervisor.libvirt.models.general import StoragePoolType

SYSTEM_VOLUME_GROUP_NAME = os.environ.get("VOLUME_GROUP")


@pytest.mark.tags(
    "RP‑01",
    "RP‑08",
    "Создание пула ресурсов (CPU, memory, storage)",
    "Удаление пула (пустой)",
)
def test_rp_01_rp_08_create_and_delete_resource_pool(resource_pool_session):
    """
    RP‑01: Создание пула ресурсов (CPU, memory, storage)
    RP‑08: Удаление пула (пустой)

    Указать имя, лимиты по CPU, памяти, хранилищу. Проверить, что пул появляется в списке.
    Удалить пул, в котором нет ВМ. Проверить, что пул исчезает.
    """
    random_name = None
    rp_deleted = False
    try:
        # ____________________________________Создание пула ресурсов______________
        random_name = f"resource_pool_{random.randint(10000, 99999)}"
        rp_template = ResourcePoolVirtualCreate(
            name=random_name,
            cpu_core_limit=2,
            ram_limit_gb=0.5,
            storage_limit=1,
            storage_type=StoragePoolType.LOGICAL,
        )
        create_rp_info = resource_pool_session.create_virtual_resource_pool(rp_template)
        assert create_rp_info.code == CommandMessagesEnum.virtual_rp_create_success.name, create_rp_info.note
        # ____________________________________Получение информации о пуле ресурсов______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )
        assert get_rp_info.rp_info.name == random_name
        assert get_rp_info.rp_info.cpu_core_limit == rp_template.cpu_core_limit
        assert get_rp_info.rp_info.ram_limit_bytes == rp_template.ram_limit_bytes
        assert get_rp_info.rp_info.storage_type.value == StoragePoolType.LOGICAL.value

        lv_capacity = resource_pool_session.logic_volume_manager.get_volume_by_name(
            random_name, SYSTEM_VOLUME_GROUP_NAME
        )
        assert int(lv_capacity.volume_size_gb) == rp_template.storage_limit
        # ____________________________________Удаление пула ресурсов______________
        delete_rp_info = resource_pool_session.delete_virtual_resource_pool(
            random_name, True
        )
        assert delete_rp_info.code == CommandMessagesEnum.rp_virtual_delete_success.name
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert get_rp_info.code == CommandMessagesEnum.rp_virtual_not_found.name
        rp_deleted = True
        # ____________________________________Проверка отсутствия LOGICAL______________
        logical_volume_info = (
            resource_pool_session.logic_volume_manager.get_volume_by_name(
                random_name, SYSTEM_VOLUME_GROUP_NAME
            )
        )
        assert logical_volume_info is None
    finally:
        # ______________________________Удаление пула ресурсов(постусловие)_______
        if not rp_deleted:
            delete_rp_info = resource_pool_session.delete_virtual_resource_pool(
                random_name, True
            )
            assert delete_rp_info.code in (
                CommandMessagesEnum.rp_virtual_delete_success.name,
                CommandMessagesEnum.rp_virtual_not_found.name,
            )
