import os
import random

import pytest

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualCreate,
)
from agent.client.hypervisor.libvirt.models.general import StoragePoolType

SYSTEM_VOLUME_GROUP_NAME = os.environ.get("VOLUME_GROUP")


@pytest.mark.tags(
    "RP‑06",
    "Установка резерва (reservation) для пула",
)
def test_rp_06_set_pool_resource_reserve(resource_pool_session):
    """
    RP‑06: Установка резерва (reservation) для пула

    Задать гарантированный минимум CPU/памяти для пула. Убедиться, что этот резерв не может быть использован другими пулами.
    """
    random_name = None
    rp_deleted = False
    try:
        # ____________________________________Создание пула ресурсов______________
        random_name = f"resource_pool_{random.randint(10000, 99999)}"
        rp_template = ResourcePoolVirtualCreate(
            name=random_name,
            cpu_core_limit=2,
            ram_limit_gb=0.5,
            storage_limit=1,
            storage_type=StoragePoolType.LOGICAL,
            ram_reservation_gb=0.5,
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
        assert (
            get_rp_info.rp_info.ram_reservation_bytes
            == rp_template.ram_reservation_bytes
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
