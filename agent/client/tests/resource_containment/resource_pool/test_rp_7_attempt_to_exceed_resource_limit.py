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


@pytest.mark.tags("RP‑07", "Установка лимита (limit) для пула")
@pytest.mark.skip("Требуется доработка")
def test_rp_04_rp_05_add_vm_to_resource_pool_and_delete_vm_from_resource_pool(
    resource_pool_session, create_running_vm_session_with_os, virsh_console_session
):
    """
    RP‑07: Установка лимита (limit) для пула

    Задать максимальное использование CPU/памяти.
    Попытаться превысить лимит через нагрузку на ВМ – система должна ограничить.
    """

    vm_info = create_running_vm_session_with_os
    virsh_console = virsh_console_session(vm_info.name)
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
            add_vm_to_resource_pool.code
            == CommandMessagesEnum.rp_virtual_edit_success.name
        ), add_vm_to_resource_pool.note
        # ____________________________________Проверка текущего состояния ресурсов______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )
        rp_info = get_rp_info.rp_info
        assert vm_info.name in rp_info.vms
        assert rp_info.ram_allocated < vm_info.max_memory * 1024
        assert rp_info.cpu_core_allocated < vm_info.vcpus
        current_pid_rp = resource_pool_session.pycgroup.pid_ctl.get_pids_from_pool(
            random_name
        ).pop()
        assert current_pid_rp == resource_pool_session.pycgroup.pid_ctl.vm_pid(
            vm_info.name
        )
        # ____________________________________Подключение к ВМ____________________
        virsh_console.connect()
        results = virsh_console.execute_commands(
            ["root", "cd /", "apk update", "apk add stress-ng"]
        )
        # TODO: Требуется доработка
        for result in results:
            if result and "hello_eskvisor" in result:
                break
        else:
            raise AssertionError("Некорректное подключение к ВМ")
        # ____________________________________Удаление ВМ из ресурс пула______________
        add_vm_to_resource_pool = (
            resource_pool_session.delete_vm_from_virtual_resource_pool(
                name=random_name, vn_name=vm_info.name
            )
        )
        assert (
            add_vm_to_resource_pool.code
            == CommandMessagesEnum.vm_successfully_deleted_from_virtual_resource_pool.name
        ), add_vm_to_resource_pool.note
        # ____________________________________Проверка текущего состояния ресурсов после удаления ВМ______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )
        rp_info = get_rp_info.rp_info
        assert get_rp_info.rp_info.vms is None
        assert rp_info.ram_allocated == 4096
        assert rp_info.cpu_core_allocated < 0.7
        assert (
            resource_pool_session.pycgroup.pid_ctl.get_pids_from_pool(random_name)
            is None
        )

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
