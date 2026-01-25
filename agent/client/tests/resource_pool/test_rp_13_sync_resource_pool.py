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


@pytest.mark.tags("RP‑13", "Синхронизация ресурс пула")
def test_rp_13_sync_resource_pool(
    resource_pool_session, create_running_vm_session
):
    """
    RP‑13: Синхронизация ресурс пула

    Создать ресурс пул, добавить туда ВМ, удалить ВМ из cgroup v2 ресурс пула, проверить отсутствие PID в пуле cgroup v2,
    выполнить синхронизацию и проверить что ВМ появляется в пуле cgroup v2
    """
    vm_info = create_running_vm_session
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

        # ____________________________________Добавление ВМ в ресурс пул______________
        add_vm_to_resource_pool = resource_pool_session.edit_virtual_resource_pool(
            ResourcePoolVirtualEdit(name=random_name, vms=vm_info.name)
        )
        assert (
            add_vm_to_resource_pool.code
            == CommandMessagesEnum.rp_virtual_edit_success.name
        )
        # ____________________________________Проверка текущего состояния ресурсов______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )
        rp_info = get_rp_info.rp_info
        assert vm_info.name in rp_info.vms
        current_pid_rp = resource_pool_session.pycgroup.pid_ctl.get_pids_from_pool(
            random_name
        ).pop()
        assert current_pid_rp == resource_pool_session.pycgroup.pid_ctl.vm_pid(
            vm_info.name
        )

        # ____________________________________Удаление PID ВМ из ресурс пула______________
        resource_pool_session.pycgroup.delete_vm_from_pool(random_name, vm_info.name)

        # ____________________________________Проверка отсутствия ВМ в пуле______________
        time.sleep(5)  # ожидаем тк нагрузка CPU не сразу падает
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )
        assert get_rp_info.rp_info.vms is None
        assert (
            resource_pool_session.pycgroup.pid_ctl.get_pids_from_pool(random_name)
            is None
        )
        # ____________________________________Синхронизация ресурс пулов______________
        sync_rps_info = resource_pool_session.sync_rps_config_vms()
        assert sync_rps_info.code == CommandMessagesEnum.rp_virtual_config_sync_success.name
        # ____________________________________Проверка присутствия ВМ в пуле______________
        time.sleep(1)
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )
        assert vm_info.name in get_rp_info.rp_info.vms
        current_pid_rp = resource_pool_session.pycgroup.pid_ctl.get_pids_from_pool(
            random_name
        ).pop()
        assert current_pid_rp == resource_pool_session.pycgroup.pid_ctl.vm_pid(
            vm_info.name
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
