import os
import random
import time

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualCreate,
    ResourcePoolVirtualEdit,
)
from agent.client.hypervisor.libvirt.models.volume.logic_volume import (
    LogicalVolumeSizeType,
)
from agent.client.hypervisor.libvirt.models.general import StoragePoolType

SYSTEM_VOLUME_GROUP_NAME = os.environ.get("VOLUME_GROUP")


@pytest.mark.tags(
    "RP‑03",
    "Удаление ресурсов из пула",
)
def test_rp_3_remove_resource_from_resource_pool(resource_pool_session):
    """
    RP‑03: Удаление ресурсов из пула

    Уменьшить лимит. Проверить, что пул не позволяет выделить больше ресурсов.
    """
    random_name = None
    rp_deleted = False
    try:
        # ____________________________________Создание пула ресурсов______________
        random_name = f"resource_pool_{random.randint(10000, 99999)}"
        rp_template = ResourcePoolVirtualCreate(
            name=random_name,
            cpu_core_limit=2,
            ram_limit_gb=1,
            storage_limit=1,
            storage_type=StoragePoolType.LOGICAL,
        )
        edit_rp_template = ResourcePoolVirtualEdit(
            name=random_name,
            ram_limit_gb=0.2,
            cpu_core_limit=1,
            storage_limit=1,
            storage_type=StoragePoolType.LOGICAL,
            volume_size_type=LogicalVolumeSizeType.GB,
        )
        create_rp_info = resource_pool_session.create_virtual_resource_pool(rp_template)
        assert (
            create_rp_info.message
            == CommandMessagesEnum.virtual_rp_create_success.value
        )
        assert create_rp_info.code == CommandMessagesEnum.virtual_rp_create_success.name
        # ____________________________________Проверка текущего состояния ресурсов______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.message
            == CommandMessagesEnum.rp_virtual_successfully_found.value
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
        # ____________________________________Удаленеи ресурсов из пула______________
        add_resource_info = resource_pool_session.edit_virtual_resource_pool(
            edit_rp_template
        )
        assert (
            add_resource_info.message
            == CommandMessagesEnum.rp_virtual_edit_success.value
        )
        assert (
            add_resource_info.code == CommandMessagesEnum.rp_virtual_edit_success.name
        )
        # ____________________________________Проверка уменьшения ресурсов______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.message
            == CommandMessagesEnum.rp_virtual_successfully_found.value
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )
        assert get_rp_info.rp_info.name == random_name
        assert get_rp_info.rp_info.cpu_core_limit == edit_rp_template.cpu_core_limit
        assert get_rp_info.rp_info.ram_limit_bytes == edit_rp_template.ram_limit_bytes
        assert get_rp_info.rp_info.storage_type.value == StoragePoolType.LOGICAL.value

        lv_capacity = resource_pool_session.logic_volume_manager.get_volume_by_name(
            random_name, SYSTEM_VOLUME_GROUP_NAME
        )
        assert (
            int(lv_capacity.volume_size_gb)
            == rp_template.storage_limit + edit_rp_template.storage_limit
        )
    finally:
        # ______________________________Удаление пула ресурсов(постусловие)_______
        if not rp_deleted:
            delete_rp_info = resource_pool_session.delete_virtual_resource_pool(
                random_name, True
            )
            assert delete_rp_info.message in (
                CommandMessagesEnum.rp_virtual_delete_success.value,
                CommandMessagesEnum.rp_virtual_not_found.value,
            ), delete_rp_info.note
            assert delete_rp_info.code in (
                CommandMessagesEnum.rp_virtual_delete_success.name,
                CommandMessagesEnum.rp_virtual_not_found.name,
            )
