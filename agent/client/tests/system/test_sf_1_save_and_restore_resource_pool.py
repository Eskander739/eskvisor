import os
import random
from pathlib import Path

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualCreate,
)
from agent.client.hypervisor.libvirt.models.general import StoragePoolType

SYSTEM_VOLUME_GROUP_NAME = os.environ.get("VOLUME_GROUP")
CURRENT_PATH = Path(__file__).parent.parent.parent / "pycgroup" / "state"
SAVE_SCRIPT = str(CURRENT_PATH / "save.sh")
RESTORE_SCRIPT = str(CURRENT_PATH / "restore.sh")


@pytest.mark.tags(
    "SF‑01",
    "Сохранение и восстановление ресурс пула через скрипт агента",
)
def test_sf_01_save_and_restore_resource_pool(resource_pool_session):
    """
    SF-01: Сохранение и восстановление ресурс пула через скрипт агента

    Необходимо проверить скрипт сохранения и восстановления ресурс пула в cgroup v2
    """
    random_name = None
    cli = resource_pool_session.cli
    try:
        # ____________________________________Создание пула ресурсов______________
        random_name = f"resource_pool_{random.randint(10000, 99999)}"
        rp_template = ResourcePoolVirtualCreate(
            name=random_name,
            cpu_core_limit=2,
            ram_limit_gb=0.5,
            storage_limit=1,
            storage_type=StoragePoolType.LOGICAL,
            cpu_weight=479,
            ram_reservation_gb=0.5,
        )
        create_rp_info = resource_pool_session.create_virtual_resource_pool(rp_template)
        assert (
            create_rp_info.code == CommandMessagesEnum.virtual_rp_create_success.name
        ), create_rp_info.note
        # ____________________________________Получение информации о пуле ресурсов______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert (
            get_rp_info.code == CommandMessagesEnum.rp_virtual_successfully_found.name
        )
        assert get_rp_info.rp_info.name == random_name
        assert get_rp_info.rp_info.cpu_core_limit == rp_template.cpu_core_limit
        assert get_rp_info.rp_info.cpu_weight == rp_template.cpu_weight
        assert (
            get_rp_info.rp_info.ram_reservation_bytes
            == rp_template.ram_reservation_bytes
        )
        assert get_rp_info.rp_info.ram_limit_bytes == rp_template.ram_limit_bytes
        assert get_rp_info.rp_info.storage_type.value == StoragePoolType.LOGICAL.value

        lv_capacity = resource_pool_session.logic_volume_manager.get_volume_by_name(
            random_name, SYSTEM_VOLUME_GROUP_NAME
        )
        assert int(lv_capacity.volume_size_gb) == rp_template.storage_limit

        # ____________________________________Сохранение пула ресурсов через скрипт______________
        cmd_args = ["bash", SAVE_SCRIPT]
        cli.execute(cmd_args)

        # ______________________________Удаление пула ресурсов_______
        delete_rp_info = resource_pool_session.delete_virtual_resource_pool(
            random_name, True
        )
        assert delete_rp_info.code in (
            CommandMessagesEnum.rp_virtual_delete_success.name,
        ), delete_rp_info.note

        # ____________________________________Проверка отсутствия ресурс пула______________
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert get_rp_info.code == CommandMessagesEnum.rp_virtual_not_found.name

        # ____________________________________Восстановление пула ресурсов через скрипт______________
        cmd_args = ["bash", RESTORE_SCRIPT]
        result = cli.execute(cmd_args)
        print("Результат выполнения команды восстановления ресурс пула: ", result)

        # ____________________________________Проверка восстановления ресурс пула______________
        pool_info = resource_pool_session.pycgroup.get_cgroup_pool(random_name)
        assert pool_info.get("name") == random_name
        assert pool_info.get("cpu")[0] == rp_template.cpu_core_limit
        assert pool_info.get("ram")[0] == rp_template.ram_limit_bytes
        assert pool_info.get("ram")[3] == rp_template.ram_reservation_bytes
        assert pool_info.get("cpu")[4] == rp_template.cpu_weight

    finally:
        # ______________________________Удаление пула ресурсов(постусловие)_______
        resource_pool_session.pycgroup.delete_cgroup_pool(random_name, True)
        get_rp_info = resource_pool_session.get_virtual_resource_pool_by_name(
            random_name
        )
        assert get_rp_info.code == CommandMessagesEnum.rp_virtual_not_found.name
