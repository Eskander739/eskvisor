import logging
import random
import sys
import time
import uuid

import pytest

from agent.client.hypervisor.libvirt.managers.network import NetworkManager
from agent.client.hypervisor.libvirt.managers.balansir import (
    Balansir,
)
from agent.client.hypervisor.libvirt.managers.snapshot import SnapshotManager
from agent.client.hypervisor.libvirt.managers.storage import StorageManager
from agent.client.hypervisor.libvirt.managers.virsh import (
    VirshConsoleController,
)
from agent.client.hypervisor.libvirt.managers.vm import VmManager
from agent.client.hypervisor.libvirt.models.enum import NetworkType
from agent.client.hypervisor.libvirt.models.network import VmNetAdapter
from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.tools import wait_while_not

IMG_PATH = "/home/eska/alpine-virt-3.19.0-x86_64.iso"


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
def create_stopped_vm():
    with VmManager() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        request_id = str(uuid.uuid4())
        vm_config = VMCreateRequest(name=random_name, disks=[DiskCreate()])
        vm_config.name = random_name
        vm_manager.create_vm(vm_config)
        assert wait_while_not(
            lambda: vm_manager.get_vm_state_by_name(vm_config.name)
            == VMState.SHUTOFF.value,
            timeout=120,
        )

        yield random_name, request_id
        vm_manager.delete_vm_with_force(vm_config.name, request_id)


@pytest.fixture(scope="session")
def create_running_vm_session():
    with VmManager() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        request_id = str(uuid.uuid4())
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

        yield vm_info.vm_info, request_id
        vm_manager.delete_vm_with_force(vm_config.name, request_id)




@pytest.fixture(scope="session")
def create_running_vm_session_with_os():
    with VmManager() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        request_id = str(uuid.uuid4())
        vm_template = VMCreateRequest(
            name=random_name,
            autostart_vm=True,
            disks=[DiskCreate(path=IMG_PATH), DiskCreate()],
            networks=[VmNetAdapter(network_type=NetworkType.USER)],
        )
        # ____________________________________Создание ВМ_________________________
        vm_info = vm_manager.create_vm(vm_template)
        time.sleep(60)
        assert wait_while_not(
            lambda: vm_manager.get_vm_state_by_name(vm_info.name)
            == VMState.RUNNING.value,
            timeout=120,
        )

        yield vm_info.vm_info, request_id
        vm_manager.delete_vm_with_force(vm_info.name, request_id)


@pytest.fixture(scope="function")
def create_running_vm_func():
    with VmManager() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        request_id = str(uuid.uuid4())
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

        yield vm_info.vm_info, request_id
        vm_manager.delete_vm_with_force(vm_config.name, request_id)


@pytest.fixture(scope="session")
def multi_create_stopped_vm():
    with VmManager() as vm_manager:
        vm_config_names = []
        request_id = str(uuid.uuid4())
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
        yield vm_config_names, request_id

        for vm_config_name in vm_config_names:
            vm_manager.delete_vm_with_force(vm_config_name, request_id)


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
