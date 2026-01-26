import random
import time

import pytest
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest, VirtualMachine
from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskCreate,
    DiskStatus,
    DiskFormat,
)
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.tools import wait_while_not


@pytest.mark.tags(
    "SF‑04",
    "Создание конфигурации ВМ в NFS хранилище",
)
@pytest.mark.parametrize("disk_format", (DiskFormat.QCOW2, DiskFormat.RAW))
@pytest.mark.parametrize("vm_state", (VMState.SHUTOFF, VMState.RUNNING))
def test_sf_4_create_vm_config_in_nfs(
    storage_session, vm_session, disk_format, vm_state
):
    """
    SF-04: Создание конфигурации ВМ в NFS хранилище

    Создать ВМ на хосте с подключенным NFS хранилищем, проверить,
    что конфигурация ВМ и диски создаются в указанном NFS хранилище, не на внутреннем хранилище хоста
    """

    def kb_to_mb(kb):
        return kb / 1024

    get_state = vm_session.get_vm_state_by_name
    random_name = None
    vm_created = False
    time.sleep(5)
    try:
        # _________________Проверка наличия подключенных HA NFS хранилищ(предусловие)_________________
        ha_nfs_storages = vm_session.ha_controller.loaded_nfs_storages.nfs_storages
        assert ha_nfs_storages, "Отсутствуют HA NFS хранилища"
        ha_nfs_storage = ha_nfs_storages.pop()
        # ____________________________________Создание диска______________________
        random_name = random.randint(10000, 99999)
        attach_disk_create = DiskCreate(
            name=f"disk-test-{random_name}",
            size_gb=0.2,
            format=disk_format,
            description="Create disk description",
        )
        attach_disk = storage_session.create_disk(attach_disk_create)
        assert attach_disk.code == CommandMessagesEnum.disk_successfully_created.name
        vm_disk = storage_session.get_disk_info(
            disk_name=attach_disk_create.name,
            path=attach_disk_create.path,
            disk_format=attach_disk_create.format,
        )
        vm_disk = vm_disk.disk_info
        assert vm_disk.status.value == DiskStatus.DETACHED.value
        assert vm_disk.name == attach_disk_create.name
        assert vm_disk.format == disk_format
        assert vm_disk.file_path_exists is True
        assert (
            ha_nfs_storage.mount == vm_disk.path or vm_disk.path in ha_nfs_storage.mount
        )
        # ____________________________________Создание ВМ_________________________
        random_name = f"VM-TEST-{random.randint(10000, 99999)}"
        autostart = {}
        if vm_state.value == vm_state.RUNNING.value:
            autostart["autostart"] = True
            autostart["autostart_vm"] = True
        else:
            autostart["autostart"] = False
        vm_template = VMCreateRequest(
            name=random_name, disks=[attach_disk_create], **autostart
        )
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert create_vm_info.vm_info is not None
        vm_info: VirtualMachine = create_vm_info.vm_info
        assert wait_while_not(lambda: get_state(random_name) == vm_state.value)
        assert vm_info.vcpus == vm_template.vcpus
        assert vm_info.name == vm_template.name
        assert kb_to_mb(vm_info.memory) == vm_template.memory_mb
        # ____________________________________Проверка наличия конфигурации ВМ в NFS хранилище_________________________
        vm_cnfigs_from_ha_storages = (
            vm_session.ha_controller.vm_configs_from_nfs_storages
        )
        if vm_state.value == vm_state.RUNNING.value:
            assert f"{random_name}.xml" in vm_cnfigs_from_ha_storages[0]
            assert f"{random_name}.xml" in vm_cnfigs_from_ha_storages[1]
        else:
            assert f"{random_name}.xml" in vm_cnfigs_from_ha_storages[0]
            assert f"{random_name}.xml" not in vm_cnfigs_from_ha_storages[1]
    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created:
            delete_vm_info = vm_session.delete_vm_with_force(name=random_name)
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
