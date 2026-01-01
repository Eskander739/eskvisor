import logging
import random
import sys
import uuid

import pytest

from agent.client.hypervisor.libvirt.managers.storage_manager import StorageManager
from agent.client.hypervisor.libvirt.managers.vm_manager import VmManager
from agent.client.hypervisor.libvirt.models.disk_storage_manager import DiskCreate
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.tools import wait_while_not


def pytest_configure(config):
    """Настройка логирования при запуске pytest"""

    # Создаем handler для вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
    with VmManager().with_default_user() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        request_id = str(uuid.uuid4())
        vm_config = VMCreateRequest(name=random_name, disks=[DiskCreate()])
        vm_config.name = random_name
        vm_manager.create_vm(vm_config)
        assert wait_while_not(lambda: vm_manager.get_vm_state_by_name(vm_config.name) == VMState.SHUTOFF.value, timeout=120)

        yield random_name, request_id
        vm_manager.delete_vm_with_force(vm_config.name, request_id)


@pytest.fixture(scope="session")
def multi_create_stopped_vm():
    with VmManager().with_default_user() as vm_manager:
        vm_config_names = []
        request_id = str(uuid.uuid4())
        for _ in range(2):
            current_vm_name = f"TEST-VM_{random.randint(10000, 99999)}"
            vm_config = VMCreateRequest(name=current_vm_name, disks=[DiskCreate()])
            vm_config.name = current_vm_name
            vm_manager.create_vm(vm_config)
            assert wait_while_not(lambda: vm_manager.get_vm_state_by_name(vm_config.name) == VMState.SHUTOFF.value,
                                  timeout=120)
            vm_config_names.append(current_vm_name)
        yield vm_config_names, request_id

        for vm_config_name in vm_config_names:
            vm_manager.delete_vm_with_force(vm_config_name, request_id)



@pytest.fixture(scope="session", autouse=True)
def storage_session():
    with StorageManager().with_default_user() as storage_manager:
        yield storage_manager


@pytest.fixture(scope="session", autouse=True)
def vm_session():
    with VmManager().with_default_user() as vm_manager:
        yield vm_manager
