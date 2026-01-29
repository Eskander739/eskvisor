import logging
import os
import random
import sys
import time
from ipaddress import IPv4Network

import pytest

from agent.client.cli import CLIControl
from agent.client.hypervisor.libvirt.managers.network import NetworkManager
from agent.client.hypervisor.libvirt.managers.balansir import (
    Balansir,
)
from agent.client.hypervisor.libvirt.managers.snapshot import SnapshotManager
from agent.client.hypervisor.libvirt.managers.storage import StorageManager
from agent.client.tests.virsh import (
    VirshConsoleController,
)
from agent.client.hypervisor.libvirt.managers.vm import VmManager
from agent.client.hypervisor.libvirt.models.enum import NetworkType
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import (
    VmNetAdapter,
    NetworkParameters,
    NetworkBridge,
    NetworkForward,
    NetworkDHCPRange,
)
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualCreate,
)
from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState, StoragePoolType
from agent.client.hypervisor.libvirt.models.vm import (
    VMCreateRequest,
    NetQemuCommandline,
)
from agent.client.lvm.group import VolumeGroupManager
from agent.client.lvm.logical import LogicalVolumeManager
from agent.client.lvm.physical import PhysicalVolumeManager
from agent.client.stg.nfs import NFSStorageManager
from agent.client.tools import wait_while_not

IMG_PATH = os.environ.get("IMAGE_PATH")


def pytest_configure(config):
    """Настройка логирования при запуске pytest"""

    # Создаем handler для вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)

    # Настраиваем root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # Включаем логи для твоих модулей
    logging.getLogger("agent.client").setLevel(logging.DEBUG)
    logging.getLogger("agent.client.hypervisor").setLevel(logging.DEBUG)

    # Отключаем слишком шумные логи
    logging.getLogger("urllib3").setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def volume_session():
    return VolumeGroupManager(), LogicalVolumeManager(), PhysicalVolumeManager()


@pytest.fixture(scope="session")
def cli_session():
    cli = CLIControl()
    return cli


@pytest.fixture(scope="session")
def create_nfs_storage_session():
    cli = CLIControl()
    nfs_stg = NFSStorageManager()
    nfs_path = f"/share_{random.randint(100000, 999999)}"
    nfs_mount_path = f"/mnt/nfs_{random.randint(100000, 999999)}"

    # Создать директории
    nfs_share_mkdir = ["mkdir", "-p", nfs_path]
    cli.execute(nfs_share_mkdir)

    # Настроить экспорт
    setting_export = [nfs_path, "127.0.0.1(rw,sync,no_subtree_check)"]
    cli.execute(setting_export)

    # Применить
    apply_setting = ["exportfs", "-a"]
    cli.execute(apply_setting)

    # Монтировать локально
    mkdir_local = ["mkdir", "-p", nfs_mount_path]
    cli.execute(mkdir_local)
    nfs_stg.mount(f"127.0.0.1:{nfs_path}", nfs_mount_path)

    yield nfs_mount_path, cli

    # Отмонтировать принудительно
    nfs_stg.umount(nfs_mount_path)

    # Удаление локальных директории хранилища
    nfs_local_rmdir = ["rmdir", nfs_path]
    cli.execute(nfs_local_rmdir)

    nfs_local_rmdir = ["rmdir", nfs_mount_path]
    cli.execute(nfs_local_rmdir)


# @pytest.fixture(scope="session", autouse=True)
# def delete_all_network_info():
#     cli = CLIControl()
#     yield
#     with NetworkManager() as nm:
#         for network in nm.list_all_networks().net_info.items:
#             if network.name != "default":
#                 nm.delete_network(network.name, force=True)
#
#     cmd_arg = "ip link show | grep virbr | awk -F': ' '{print $2}'"
#     result = cli.execute(cmd_arg, shell=True, is_text=True)
#     if result:
#         bridge_list_for_delete = [bridge for bridge in result.split("\n") if bridge]
#         for current_bridge in bridge_list_for_delete:
#             if "test" in current_bridge and current_bridge != "virbr-test-ntt2":
#                 cmd_args_delete_bridge = ["ip", "link", "delete", current_bridge]
#                 cli.execute(cmd_args_delete_bridge)
#
#
# @pytest.fixture(scope="session", autouse=True)
# def delete_all_virtual_machines():
#     yield
#     with VmManager() as vm_manager:
#         vms = vm_manager.list_vms().vm_info
#         for vm in vms.items:
#             if "test" in vm.name.lower():
#                 vm_manager.delete_vm_with_force(vm.name)
#                 vm_manager.logger.info(
#                     f"Удаление ВМ - {vm.name}: {vm.state}, {vm.memory} KB RAM, {vm.vcpus} vCPUs, UUID: {vm.uuid}, NET_ID: {vm.net_id}"
#                 )


@pytest.fixture(scope="session")
def create_stopped_vm():
    with VmManager() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        vm_config = VMCreateRequest(name=random_name, disks=[DiskCreate()])
        vm_config.name = random_name
        vm_manager.create_vm(vm_config)
        assert wait_while_not(
            lambda: vm_manager.get_vm_state_by_name(vm_config.name)
            == VMState.SHUTOFF.value,
            timeout=120,
        )

        yield random_name
        vm_manager.delete_vm_with_force(vm_config.name)


@pytest.fixture(scope="function")
def create_stopped_vm_func():
    with VmManager() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        vm_config = VMCreateRequest(name=random_name, disks=[DiskCreate()])
        vm_config.name = random_name
        vm_manager.create_vm(vm_config)
        assert wait_while_not(
            lambda: vm_manager.get_vm_state_by_name(vm_config.name)
            == VMState.SHUTOFF.value,
            timeout=120,
        )

        yield random_name
        vm_manager.delete_vm_with_force(vm_config.name)


@pytest.fixture(scope="session")
def create_running_vm_session():
    with VmManager() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        vm_config = VMCreateRequest(
            name=random_name, disks=[DiskCreate()], autostart_vm=True
        )
        vm_config.name = random_name
        vm_info = vm_manager.create_vm(vm_config)
        assert wait_while_not(
            lambda: vm_manager.get_vm_state_by_name(vm_config.name)
            == VMState.RUNNING.value,
            timeout=120,
        )

        yield vm_info.vm_info
        vm_manager.delete_vm_with_force(vm_config.name)


@pytest.fixture(scope="session")
def create_running_vm_session_with_os():
    with VmManager() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        vm_template = VMCreateRequest(
            name=random_name,
            autostart_vm=True,
            disks=[DiskCreate(path=IMG_PATH), DiskCreate()],
            networks=[VmNetAdapter(network_type=NetworkType.USER)],
            net_qemu_commandline=NetQemuCommandline(),
        )
        # ____________________________________Создание ВМ_________________________
        vm_info = vm_manager.create_vm(vm_template)
        time.sleep(60)
        assert wait_while_not(
            lambda: vm_manager.get_vm_state_by_name(vm_info.name)
            == VMState.RUNNING.value,
            timeout=120,
        )

        yield vm_info.vm_info
        vm_manager.delete_vm_with_force(vm_info.name)


@pytest.fixture(scope="function")
def create_running_vm_func():
    with VmManager() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        vm_config = VMCreateRequest(
            name=random_name, disks=[DiskCreate()], autostart_vm=True
        )
        vm_config.name = random_name
        vm_info = vm_manager.create_vm(vm_config)
        assert wait_while_not(
            lambda: vm_manager.get_vm_state_by_name(vm_config.name)
            == VMState.RUNNING.value,
            timeout=120,
        )

        yield vm_info.vm_info
        vm_manager.delete_vm_with_force(vm_config.name)


@pytest.fixture(scope="session")
def multi_create_stopped_vm():
    with VmManager() as vm_manager:
        vm_config_names = []
        for _ in range(2):
            current_vm_name = f"TEST-VM_{random.randint(10000, 99999)}"
            new_disk_name = f"disk-{str(random.randint(100000, 999999))}"
            vm_config = VMCreateRequest(
                name=current_vm_name, disks=[DiskCreate(name=new_disk_name)]
            )
            vm_config.name = current_vm_name
            vm_manager.create_vm(vm_config)
            assert wait_while_not(
                lambda: vm_manager.get_vm_state_by_name(vm_config.name)
                == VMState.SHUTOFF.value,
                timeout=120,
            )
            vm_config_names.append(current_vm_name)
        yield vm_config_names

        for vm_config_name in vm_config_names:
            vm_manager.delete_vm_with_force(vm_config_name)


@pytest.fixture(scope="session")
def create_resource_pool_session():
    random_name = f"resource_pool_{random.randint(10000, 99999)}"
    with Balansir() as rp_manager:
        rp_template = ResourcePoolVirtualCreate(
            name=random_name,
            cpu_core_limit=2,
            ram_limit_gb=0.2,
            storage_limit=2,
            storage_type=StoragePoolType.LOGICAL,
        )
        create_rp_info = rp_manager.create_virtual_resource_pool(rp_template)
        assert (
            create_rp_info.code == CommandMessagesEnum.virtual_rp_create_success.name
        ), create_rp_info.note

        yield random_name

        delete_rp_info = rp_manager.delete_virtual_resource_pool(random_name, True)
        assert delete_rp_info.code in (
            CommandMessagesEnum.rp_virtual_delete_success.name,
            CommandMessagesEnum.rp_virtual_not_found.name,
        ), delete_rp_info.note


@pytest.fixture(scope="session")
def create_nat_network_session():
    with NetworkManager() as vn_manager:
        network_name = f"network-name-{random.randint(10000, 99999)}"
        nat_params = NetworkParameters(
            name=network_name,
            forward=NetworkForward(mode="nat"),
            bridge=NetworkBridge(name="virbr-test-ntt", stp="on", delay=0),
            ipv4_address=IPv4Network("192.168.100.0/24"),
            dhcp_ranges=[
                NetworkDHCPRange(start="192.168.100.100", end="192.168.100.200")
            ],
            autostart=True,
        )
        network_name = nat_params.name
        created_network_info = vn_manager.create_network(nat_params)
        assert (
            created_network_info.code
            == CommandMessagesEnum.virtual_network_successfully_created.name
        )
        nat_network = created_network_info.net_info
        assert nat_network.network_type.type == "nat"
        assert nat_network.name == nat_params.name
        assert nat_network.active is True
        assert nat_network.autostart is True
        yield network_name

        if network_name is not None:
            vn_manager.delete_network(network_name, True)
            v_network = vn_manager.get_network_info(network_name)
            assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name


@pytest.fixture(scope="session")
def storage_session():
    with StorageManager() as storage_manager:
        yield storage_manager


@pytest.fixture(scope="session")
def vm_session():
    with VmManager() as vm_manager:
        yield vm_manager


@pytest.fixture(scope="session")
def network_session():
    with NetworkManager() as vn_manager:
        yield vn_manager


@pytest.fixture(scope="session")
def virsh_console_session():
    yield VirshConsoleController


@pytest.fixture(scope="session")
def resource_pool_session():
    with Balansir() as rp_manager:
        yield rp_manager


@pytest.fixture(scope="session")
def snapshot_session():
    with SnapshotManager() as sn_manager:
        yield sn_manager
