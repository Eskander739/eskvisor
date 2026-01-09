import os
import random

import pytest
from dotenv import load_dotenv

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.resource_pool import (
    ResourcePoolCreateRequest,
    StoragePoolType,
    ResourcePoolEditRequest,
)
from agent.client.hypervisor.libvirt.models.volume.resource_pool_virtual import (
    ResourcePoolVirtualEdit,
)

load_dotenv()
SYSTEM_VOLUME_GROUP_NAME = os.environ.get("VOLUME_GROUP")


@pytest.mark.tags(
    "RP‑11",
    "Уменьшение лимитов ниже используемого",
)
@pytest.mark.parametrize("storage_type", (StoragePoolType.DIR, StoragePoolType.LOGICAL))
def test_rp_11_downgrade_limit_cpu_and_ram_when_more_used(
    resource_pool_session, create_running_vm_func, storage_type
):
    """
    RP‑03: Уменьшение лимитов ниже используемого

    Добавить в пул работающую ВМ, уменьшить лимит ниже используемого,
    ожидается ошибка о том что нельзя уменьшить лимит ниже используемого
    """
    vm_info, request_id = create_running_vm_func
    vm_uuid = vm_info.uuid
    random_name = None
    rp_deleted = False
    try:
        # ____________________________________Создание пула ресурсов______________
        random_name = f"RP-TEST-{random.randint(10000, 99999)}"
        rp_template = ResourcePoolCreateRequest(
            name=random_name,
            cpu_limit=3,
            memory_limit=512,
            storage_limit=2,
            pool_type=storage_type,
        )
        create_rp_info = resource_pool_session.create_resource_pool(
            rp_template, request_id
        )
        assert (
            create_rp_info.message == CommandMessagesEnum.rp_create_success.value
        ), create_rp_info.note
        assert create_rp_info.code == CommandMessagesEnum.rp_create_success.name
        assert create_rp_info.rp_info is not None
        get_rp_info = resource_pool_session.get_pool_info(random_name, request_id)
        assert get_rp_info.rp_info.name == random_name
        assert get_rp_info.rp_info.cpu_limit == rp_template.cpu_limit
        assert get_rp_info.rp_info.memory_limit_gb == rp_template.memory_limit / 1024
        assert get_rp_info.rp_info.type.value == storage_type.value
        if rp_template.pool_type == StoragePoolType.LOGICAL:
            assert int(get_rp_info.rp_info.capacity_gb) == rp_template.storage_limit
        else:
            assert int(get_rp_info.rp_info.capacity_gb) > rp_template.storage_limit
        # ____________________________________Добавление ВМ в ресурс пул______________
        add_vm_to_resource_pool = (
            resource_pool_session.virtual_resource_pool.edit_virtual_resource_pool(
                ResourcePoolVirtualEdit(name=random_name, vm_uuid_list=vm_uuid)
            )
        )
        assert (
            add_vm_to_resource_pool.message
            == CommandMessagesEnum.rp_virtual_edit_success.value
        ), add_vm_to_resource_pool.note
        assert (
            add_vm_to_resource_pool.code
            == CommandMessagesEnum.rp_virtual_edit_success.name
        )
        # ____________________________________Проверка текущего состояния ресурсов______________
        pool_usage_info = resource_pool_session.get_pool_info(random_name, request_id)
        assert pool_usage_info.message == CommandMessagesEnum.rp_info_success.value
        assert pool_usage_info.code == CommandMessagesEnum.rp_info_success.name

        usage_info = pool_usage_info.rp_info.usage
        assert usage_info.memory < rp_template.memory_limit
        assert usage_info.cpu == vm_info.vcpus
        # ________________Уменьшение RAM ресурс пула(в это время используется больше)______________
        delete_rp_info = resource_pool_session.edit_resource_pool(
            ResourcePoolEditRequest(name=random_name, memory_limit=10), request_id
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
        delete_rp_info = resource_pool_session.edit_resource_pool(
            ResourcePoolEditRequest(name=random_name, cpu_limit=1), request_id
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
            delete_rp_info = resource_pool_session.delete_resource_pool(
                random_name, request_id, force=True
            )
            assert delete_rp_info.message in (
                CommandMessagesEnum.rp_delete_success.value,
                CommandMessagesEnum.rp_not_found.value,
            )
            assert delete_rp_info.code in (
                CommandMessagesEnum.rp_delete_success.name,
                CommandMessagesEnum.rp_not_found.name,
            )
