import random

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.resource_pool import (
    ResourcePoolCreateRequest,
    StoragePoolType,
)
from agent.client.hypervisor.libvirt.models.volume.resource_pool_virtual import (
    ResourcePoolVirtualEdit,
)


@pytest.mark.tags(
    "RP‑04",
    "Назначение ВМ пулу",
)
# @pytest.mark.parametrize("storage_type", (StoragePoolType.DIR, StoragePoolType.LOGICAL))
def test_rp_01_rp_08_create_and_delete_resource_pool(
    resource_pool_session, create_running_vm_session
):
    """
    RP‑04: Назначение ВМ пулу

    Переместить существующую ВМ в пул. Убедиться, что ВМ учитывается в использовании ресурсов пула.
    """
    vm_info, request_id = create_running_vm_session
    vm_name = vm_info.name
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
            pool_type=StoragePoolType.LOGICAL,
        )
        create_rp_info = resource_pool_session.create_resource_pool(
            rp_template, request_id
        )
        assert create_rp_info.message == CommandMessagesEnum.rp_create_success.value
        assert create_rp_info.code == CommandMessagesEnum.rp_create_success.name
        assert create_rp_info.rp_info is not None
        get_rp_info = resource_pool_session.get_pool_info(random_name, request_id)
        assert get_rp_info.rp_info.name == random_name
        assert get_rp_info.rp_info.cpu_limit == rp_template.cpu_limit
        assert get_rp_info.rp_info.memory_limit_gb == rp_template.memory_limit / 1024
        assert get_rp_info.rp_info.type.value == StoragePoolType.LOGICAL.value
        if rp_template.pool_type == StoragePoolType.LOGICAL:
            assert int(get_rp_info.rp_info.capacity_gb) == rp_template.storage_limit
        # ____________________________________Добавление ВМ в ресурс пул______________
        add_vm_to_resource_pool = (
            resource_pool_session.virtual_resource_pool.edit_virtual_resource_pool(
                ResourcePoolVirtualEdit(name=random_name, vm_uuid_list=vm_info.uuid)
            )
        )
        assert (
            add_vm_to_resource_pool.message
            == CommandMessagesEnum.rp_virtual_edit_success.value
        ), add_vm_to_resource_pool.note
        assert (
            add_vm_to_resource_pool.code == CommandMessagesEnum.rp_virtual_edit_success.name
        )
        # ____________________________________Проверка текущего состояния ресурсов______________
        pool_usage_info = resource_pool_session.get_pool_info(random_name, request_id)
        assert (
            pool_usage_info.message == CommandMessagesEnum.rp_info_success.value
        )
        assert pool_usage_info.code == CommandMessagesEnum.rp_info_success.name

        usage_info = pool_usage_info.rp_info.usage
        assert usage_info.memory < rp_template.memory_limit
        assert usage_info.cpu == vm_info.vcpus
        # ____________________________________Удаление ВМ из ресурс пула______________
        add_vm_to_resource_pool = (
            resource_pool_session.virtual_resource_pool.delete_vm_from_virtual_resource_pool(name=random_name, vm_uuid=vm_info.uuid)
        )
        assert (
            add_vm_to_resource_pool.message
            == CommandMessagesEnum.vm_successfully_deleted_from_virtual_resource_pool.value
        ), add_vm_to_resource_pool.note
        assert add_vm_to_resource_pool.code == CommandMessagesEnum.vm_successfully_deleted_from_virtual_resource_pool.name
        # ____________________________________Проверка текущего состояния ресурсов после удаления ВМ______________
        pool_usage_info = resource_pool_session.get_pool_info(random_name, request_id)
        assert (
                pool_usage_info.message == CommandMessagesEnum.rp_info_success.value
        )
        assert pool_usage_info.code == CommandMessagesEnum.rp_info_success.name

        usage_info = pool_usage_info.rp_info.usage
        assert usage_info.memory == 0
        assert usage_info.cpu == 0

    finally:
        # ______________________________Удаление пула ресурсов(постусловие)_______
        if not rp_deleted:
            delete_rp_info = resource_pool_session.delete_resource_pool(
                random_name, request_id
            )
            assert delete_rp_info.message in (
                CommandMessagesEnum.rp_delete_success.value,
                CommandMessagesEnum.rp_not_found.value,
            )
            assert delete_rp_info.code in (
                CommandMessagesEnum.rp_delete_success.name,
                CommandMessagesEnum.rp_not_found.name,
            )
