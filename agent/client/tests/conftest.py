import os
import shutil
import tempfile

import pytest

from agent.client.hypervisor.libvirt.managers.storage_manager import StorageManager


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