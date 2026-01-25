import os
import random
import time

import pytest

from agent.client.hypervisor.libvirt.models.general import StoragePoolType
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualEdit,
    ResourcePoolVirtualCreate,
)


@pytest.mark.tags("RP‑14", "Добавление и удаление ВМ в конфиге ресурс пула")
def test_rp_14_add_and_delete_vm_to_rp_config(
    resource_pool_session
):
    """
    RP‑14: Добавление и удаление ВМ в конфиге ресурс пула

    Создать ресурс пул, проверить добавление и удаление ВМ в конфиг ресурс пула
    """
    vm_name = f"VM-CONFIG-TEST-{random.randint(10000, 99999)}"
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
        assert create_rp_info.code == CommandMessagesEnum.virtual_rp_create_success.name
        # ____________________________________Получение информации о пуле ресурсов______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )
        assert get_rp_info.rp_info.name == random_name

        # ____________________________________Проверка текущего состояния ресурсов______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )

        # ____________________________________Добавление ВМ в конфиг ресурс пула______________
        add_vm_to_rp_config_info = resource_pool_session.add_vm_to_rp_config(random_name, vm_name)
        assert add_vm_to_rp_config_info.code == CommandMessagesEnum.rp_virtual_config_edit_success.name

        # ____________________________________Проверка наличия ВМ в конфиге ресурс пула______________
        add_vm_to_rp_config_info = resource_pool_session.get_rp_from_config(random_name)
        assert add_vm_to_rp_config_info.code == CommandMessagesEnum.rp_virtual_config_successfully_founded.name
        assert vm_name in add_vm_to_rp_config_info.rp_info.connected_vms

        # ____________________________________Удаление ВМ из конфига ресурс пула______________
        add_vm_to_rp_config_info = resource_pool_session.delete_vms_from_rp_config(random_name, vm_name)
        assert add_vm_to_rp_config_info.code == CommandMessagesEnum.rp_virtual_config_edit_success.name

        # ____________________________________Проверка отсутствия ВМ в конфиге ресурс пула______________
        add_vm_to_rp_config_info = resource_pool_session.get_rp_from_config(random_name)
        assert add_vm_to_rp_config_info.code == CommandMessagesEnum.rp_virtual_config_successfully_founded.name
        assert vm_name not in add_vm_to_rp_config_info.rp_info.connected_vms

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
