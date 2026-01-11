import os
import random
from pathlib import Path

import pytest
from dotenv import load_dotenv

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.resource_pool import (
    ResourcePoolCreateRequest,
    StoragePoolType,
)
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualEdit,
)

load_dotenv()
SYSTEM_VOLUME_GROUP_NAME = os.environ.get("VOLUME_GROUP")


@pytest.mark.tags(
    "RP‑09",
    "Попытка удаления пула с ВМ",
)
@pytest.mark.parametrize("storage_type", (StoragePoolType.DIR, StoragePoolType.LOGICAL))
def test_rp_09_delete_resource_pool_with_vm(
    resource_pool_session, create_running_vm_func, storage_type
):
    """
    RP‑09: Попытка удаления пула с ВМ

    Попытаться удалить пул, содержащий ВМ. Система должна запросить подтверждение или запретить удаление.
    """
    vm_info, request_id = create_running_vm_func
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
        assert create_rp_info.message == CommandMessagesEnum.rp_create_success.value
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
                ResourcePoolVirtualEdit(name=random_name, vm_uuid_list=vm_info.uuid)
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
        pool_info = resource_pool_session.get_pool_info(random_name, request_id)
        assert pool_info.message == CommandMessagesEnum.rp_info_success.value
        assert pool_info.code == CommandMessagesEnum.rp_info_success.name

        # ____________________________________Удаление ресурс пула с ВМ без force______________
        delete_rp_info = resource_pool_session.delete_resource_pool(
            random_name, request_id
        )
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
        delete_rp_info = resource_pool_session.delete_resource_pool(
            random_name, request_id, True
        )
        assert delete_rp_info.message == CommandMessagesEnum.rp_delete_success.value
        assert delete_rp_info.code == CommandMessagesEnum.rp_delete_success.name
        assert delete_rp_info.success is True
        # ____________________________________Проверка отсутствия DIR/LOGICAL______________
        if storage_type == StoragePoolType.LOGICAL:
            logical_volume_info = (
                resource_pool_session.logic_volume_manager.get_volume_by_name(
                    random_name, SYSTEM_VOLUME_GROUP_NAME
                )
            )
            assert logical_volume_info is None
        else:
            path_storage = Path(pool_info.rp_info.storage_path)
            assert not path_storage.is_dir()
            assert not path_storage.exists()

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
