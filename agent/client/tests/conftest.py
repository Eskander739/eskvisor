import logging
import os
import random
import shutil
import sys
import tempfile
import uuid

import pytest

from agent.client.hypervisor.libvirt.managers.storage_manager import StorageManager
from agent.client.hypervisor.libvirt.managers.vm_manager import VmManager
from agent.client.hypervisor.models.general import VMState
from agent.client.hypervisor.templates.vm import simple_hotplug_vm_config
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
        vm_config = simple_hotplug_vm_config
        vm_config.name = random_name
        vm_manager.create_vm(vm_config)
        assert wait_while_not(lambda: vm_manager.get_vm_by_name(vm_config.name, vm_config.request_id).state == VMState.SHUTOFF, timeout=120)

        yield vm_config
        vm_manager.delete_vm_with_force(vm_config.name)


@pytest.fixture(scope="session")
def multi_create_stopped_vm():
    with VmManager().with_default_user() as vm_manager:
        vm_config_names = []

        for _ in range(2):
            current_vm_name = f"TEST-VM_{random.randint(10000, 99999)}"
            vm_config = simple_hotplug_vm_config
            vm_config.name = current_vm_name
            vm_manager.create_vm(vm_config)
            assert wait_while_not(lambda: vm_manager.get_vm_by_name(vm_config.name, vm_config.request_id).state == VMState.SHUTOFF,
                                  timeout=120)
            vm_config_names.append(current_vm_name)
        yield vm_config_names

        for vm_config_name in vm_config_names:
            vm_manager.delete_vm_with_force(vm_config_name)



@pytest.fixture(scope="session", autouse=True)
def storage_session():
    with StorageManager().with_default_user() as storage_manager:
        yield storage_manager


@pytest.fixture(scope="session", autouse=True)
def vm_session():
    with VmManager().with_default_user() as vm_manager:
        yield vm_manager
