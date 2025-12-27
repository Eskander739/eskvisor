import os
import random
import shutil
import tempfile
import uuid

import pytest

from agent.client.hypervisor.libvirt.managers.storage_manager import StorageManager
from agent.client.hypervisor.libvirt.managers.vm_manager import VmManager
from agent.client.hypervisor.models.general import VMState
from agent.client.hypervisor.templates.vm import simple_hotplug_vm_config
from agent.client.tools import wait_while_not


@pytest.fixture(scope="session")
def create_stopped_vm():
    with VmManager().with_default_user() as vm_manager:
        random_name = f"TEST-VM_{random.randint(10000, 99999)}"
        vm_config = simple_hotplug_vm_config
        vm_config.name = random_name
        vm_manager.create_vm(vm_config)
        vm_manager.shutdown_vm(simple_hotplug_vm_config.name, force=True)
        assert wait_while_not(lambda: vm_manager.get_vm_by_name(vm_config.name).state == VMState.SHUTOFF, timeout=120)

        yield vm_config
        vm_manager.delete_vm_with_force(simple_hotplug_vm_config.name)



@pytest.fixture(scope="session", autouse=True)
def storage_session():
    with StorageManager().with_default_user() as storage_manager:
        yield storage_manager

@pytest.fixture(scope="session")
def setup_test_environment():
    """Настройка тестового окружения"""
    test_dir = tempfile.mkdtemp(prefix="vm_storage_test_")
    print(f"📁 Создана тестовая директория: {test_dir}")

    # Создаем поддиректории для тестов
    raw_dir = os.path.join(test_dir, "raw_disks")
    qcow2_dir = os.path.join(test_dir, "qcow2_disks")
    attached_dir = os.path.join(test_dir, "attached_disks")

    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(qcow2_dir, exist_ok=True)
    os.makedirs(attached_dir, exist_ok=True)
    dirs = {
        'test_dir': test_dir,
        'raw_dir': raw_dir,
        'qcow2_dir': qcow2_dir,
        'attached_dir': attached_dir
    }

    yield dirs

    """Очистка тестового окружения"""
    for _, current_dir in dirs.items():
        if os.path.exists(current_dir):
            shutil.rmtree(current_dir)
            print(f"🗑️  Удалена тестовая директория: {current_dir}")