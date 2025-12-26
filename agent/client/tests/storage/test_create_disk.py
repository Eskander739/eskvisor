import os

import pytest

from agent.client.hypervisor.models.disk import DiskFormat, DiskCreate, DiskQuery


@pytest.mark.tags("VD‑01", "Создание нового виртуального диска")
def test_vd_01_create_disk(storage_session, setup_test_environment):
    """
    VD‑01: Создание нового виртуального диска

    Указать тип (RAW, QCOW2, VHD), размер, формат.
    Проверить, что диск появляется в списке и занимает указанное место.
    """
    print("\n" + "=" * 60)
    print("VD‑01: Создание нового виртуального диска")
    print("=" * 60)

    # Тест 1: Создание RAW диска
    print("\n1. Тестирование создания RAW диска:")
    raw_disk_create = DiskCreate(
        name="test-raw-disk.img",
        path=os.path.join(setup_test_environment.get("raw_dir"), "test-raw-disk.img"),
        size_gb=1.0,
        format=DiskFormat.RAW,
        sparse=False,
        description="Тестовый RAW диск"
    )

    storage_session.create_disk(raw_disk_create)
    raw_disk_info = storage_session.get_disk_info(path=raw_disk_create.path)
    assert raw_disk_info is not None, "Ошибка: RAW диск не создан"
    assert os.path.exists(raw_disk_info.path), "Ошибка: файл RAW диска не существует"
    assert raw_disk_info.format == DiskFormat.RAW, "Ошибка: неверный формат RAW диска"
    assert raw_disk_info.get_effective_size_gb() == 1.0, f"Ошибка: неверный размер RAW диска: {raw_disk_info.get_effective_size_gb()} GB"

    print(f"   ✅ RAW диск создан: {raw_disk_info.name}")
    print(f"   📏 Размер: {raw_disk_info.get_effective_size_gb()} GB")
    print(f"   📍 Путь: {raw_disk_info.path}")

    # Тест 2: Создание QCOW2 диска
    print("\n2. Тестирование создания QCOW2 диска:")
    qcow2_disk_create = DiskCreate(
        name="test-qcow2-disk.qcow2",
        path=os.path.join(setup_test_environment.get("qcow2_dir"), "test-qcow2-disk.qcow2"),
        size_gb=2.0,
        format=DiskFormat.QCOW2,
        sparse=True,
        description="Тестовый QCOW2 диск"
    )

    storage_session.create_disk(qcow2_disk_create)

    qcow2_disk_info = storage_session.get_disk_info(path=qcow2_disk_create.path)
    assert qcow2_disk_info is not None, "Ошибка: QCOW2 диск не создан"
    assert os.path.exists(qcow2_disk_info.path), "Ошибка: файл QCOW2 диска не существует"
    assert qcow2_disk_info.format == DiskFormat.QCOW2, "Ошибка: неверный формат QCOW2 диска"
    assert qcow2_disk_info.get_effective_size_gb() == 2.0, f"Ошибка: неверный размер QCOW2 диска: {qcow2_disk_info.get_effective_size_gb()} GB"

    print(f"   ✅ QCOW2 диск создан: {qcow2_disk_info.name}")
    print(f"   📏 Размер: {qcow2_disk_info.get_effective_size_gb()} GB")

    # Тест 3: Проверка, что диски появляются в списке
    print("\n3. Проверка списка дисков:")
    all_disks = storage_session.list_disks(DiskQuery(search_path=[setup_test_environment.get("qcow2_dir"),
                                                                  setup_test_environment.get("raw_dir")]))
    print("ВСЕ ДИСКИ: ", all_disks)

    # Фильтруем тестовые диски
    test_disks = [d for d in all_disks if d.name in ['test-raw-disk.img', 'test-qcow2-disk.qcow2']]
    assert len(test_disks) == 2, f"Ошибка: найдено {len(test_disks)} тестовых дисков вместо 2"

    print(f"   ✅ В списке найдено {len(test_disks)} тестовых диска")
