import os
import random
import pytest

from agent.client.hypervisor.libvirt.models.general import StoragePoolType
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualEdit,
    ResourcePoolVirtualCreate,
)

SYSTEM_VOLUME_GROUP_NAME = os.environ.get("VOLUME_GROUP")


@pytest.mark.tags(
    "RP‑09",
    "Попытка удаления пула с ВМ",
)
def test_rp_09_delete_resource_pool_with_vm(
    resource_pool_session, create_running_vm_func
):
    """
    RP‑09: Попытка удаления пула с ВМ

    Попытаться удалить пул, содержащий ВМ. Система должна запросить подтверждение или запретить удаление.
    """
    vm_info = create_running_vm_func
    random_name = None
    rp_deleted = False
    try:
        # ____________________________________Создание пула ресурсов______________
        random_name = f"resource_pool_{random.randint(10000, 99999)}"
        rp_template = ResourcePoolVirtualCreate(
            name=random_name,
            cpu_core_limit=2,
            ram_limit_gb=2,
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
            ResourcePoolVirtualEdit(name=random_name, vms=vm_info.name)
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
        rp_info = get_rp_info.rp_info
        assert vm_info.name in rp_info.vms
        assert rp_info.ram_allocated < vm_info.max_memory * 1024
        assert rp_info.cpu_core_allocated < vm_info.vcpus
        # ____________________________________Удаление ресурс пула с ВМ без force______________
        delete_rp_info = resource_pool_session.delete_virtual_resource_pool(random_name)
        assert (
            delete_rp_info.message
            == CommandMessagesEnum.rp_virtual_have_vm_need_use_force_for_delete.value
        )
        assert (
            delete_rp_info.code
            == CommandMessagesEnum.rp_virtual_have_vm_need_use_force_for_delete.name
        )
        assert delete_rp_info.success is False
        # ____________________________________Удаление ресурс пула с ВМ с force______________
        delete_rp_info = resource_pool_session.delete_virtual_resource_pool(
            random_name, True
        )
        assert (
            delete_rp_info.message
            == CommandMessagesEnum.rp_virtual_delete_success.value
        )
        assert delete_rp_info.code == CommandMessagesEnum.rp_virtual_delete_success.name
        assert delete_rp_info.success is True
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
            assert delete_rp_info.message in (
                CommandMessagesEnum.rp_virtual_delete_success.value,
                CommandMessagesEnum.rp_virtual_not_found.value,
            ), delete_rp_info.note
            assert delete_rp_info.code in (
                CommandMessagesEnum.rp_virtual_delete_success.name,
                CommandMessagesEnum.rp_virtual_not_found.name,
            )
