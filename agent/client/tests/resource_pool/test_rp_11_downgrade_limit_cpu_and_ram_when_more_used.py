import os
import random

import pytest
from dotenv import load_dotenv

from agent.client.hypervisor.libvirt.models.general import StoragePoolType
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualCreate,
    ResourcePoolVirtualEdit,
)

load_dotenv()
SYSTEM_VOLUME_GROUP_NAME = os.environ.get("VOLUME_GROUP")


@pytest.mark.tags(
    "RP‑11",
    "Уменьшение лимитов ниже используемого",
)
def test_rp_11_downgrade_limit_cpu_and_ram_when_more_used(
    resource_pool_session, create_running_vm_func
):
    """
    RP‑03: Уменьшение лимитов ниже используемого

    Добавить в пул работающую ВМ, уменьшить лимит ниже используемого,
    ожидается ошибка о том что нельзя уменьшить лимит ниже используемого
    """
    vm_info, request_id = create_running_vm_func
    random_name = None
    rp_deleted = False
    try:
        # ____________________________________Создание пула ресурсов______________
        random_name = f"RP-TEST-{random.randint(10000, 99999)}"
        rp_template = ResourcePoolVirtualCreate(
            name=random_name,
            cpu_core_limit=2,
            ram_limit_gb=0.5,
            storage_limit=1,
            storage_type=StoragePoolType.LOGICAL,
        )
        create_rp_info = resource_pool_session.create_virtual_resource_pool(rp_template)
        assert (
            create_rp_info.message
            == CommandMessagesEnum.virtual_rp_create_success.value
        )
        assert create_rp_info.code == CommandMessagesEnum.virtual_rp_create_success.name
        # ____________________________________Получение информации о пуле ресурсов______________
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
        # ____________________________________Добавление ВМ в ресурс пул______________
        add_vm_to_resource_pool = resource_pool_session.edit_virtual_resource_pool(
            ResourcePoolVirtualEdit(name=random_name, vm_uuid_list=vm_info.uuid)
        )
        assert (
            add_vm_to_resource_pool.message
            == CommandMessagesEnum.rp_virtual_edit_success.value
        ), add_vm_to_resource_pool.note
        assert (
            add_vm_to_resource_pool.code
            == CommandMessagesEnum.rp_virtual_edit_success.name
        )
        # ________________Уменьшение RAM ресурс пула(в это время используется больше)______________
        delete_rp_info = resource_pool_session.edit_virtual_resource_pool(
            ResourcePoolVirtualEdit(name=random_name, ram_limit_gb=0.1)
        )
        assert (
            delete_rp_info.message
            == CommandMessagesEnum.rp_ram_configuration_error_allocated_more_than_on_new_limit.value
        )
        assert (
            delete_rp_info.code
            == CommandMessagesEnum.rp_ram_configuration_error_allocated_more_than_on_new_limit.name
        )
        assert delete_rp_info.success is False
        # ________________Уменьшение CPU ресурс пула(в это время используется больше)______________
        delete_rp_info = resource_pool_session.edit_virtual_resource_pool(
            ResourcePoolVirtualEdit(name=random_name, cpu_core_limit=1)
        )
        assert (
            delete_rp_info.message
            == CommandMessagesEnum.rp_cpu_configuration_error_allocated_more_than_on_new_limit.value
        )
        assert (
            delete_rp_info.code
            == CommandMessagesEnum.rp_cpu_configuration_error_allocated_more_than_on_new_limit.name
        )
        assert delete_rp_info.success is False

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
