import os

from agent.client.hypervisor.models.disk import DiskQuery, DiskFormat


def test_vd_08_disk_info():
    """
    VD‑08: Просмотр информации о диске

    Открыть свойства диска: размер, формат, путь, использование.
    """
    print("\n" + "=" * 60)
    print("VD‑08: Просмотр информации о диске")
    print("=" * 60)

    with StorageManager() as manager:
        # Создаем тестовый диск для проверки информации
        test_disk_path = os.path.join(test_env['raw_dir'], "info-test-disk.img")

        # Создаем простой файл для теста
        with open(test_disk_path, 'wb') as f:
            f.write(b'\0' * 1024 * 1024)  # 1MB файл

        # Получаем информацию о диске
        disk_info = manager.get_disk_info(path=test_disk_path)

        assert disk_info is not None, "Ошибка: информация о диске не получена"
        assert disk_info.name == "info-test-disk.img", f"Ошибка: неверное имя диска: {disk_info.name}"
        assert disk_info.path == test_disk_path, f"Ошибка: неверный путь к диску: {disk_info.path}"
        assert disk_info.format in [DiskFormat.RAW, DiskFormat.UNKNOWN], f"Ошибка: неверный формат: {disk_info.format}"
        assert disk_info.capacity_bytes >= 1024 * 1024, f"Ошибка: неверный размер в байтах: {disk_info.capacity_bytes}"

        print("   ✅ Информация о диске получена:")
        print(f"     📝 Имя: {disk_info.name}")
        print(f"     📍 Путь: {disk_info.path}")
        print(f"     🏷️  Формат: {disk_info.format.value}")
        print(f"     📏 Размер: {disk_info.get_effective_size_gb()} GB")
        print(f"     📊 Использование: {disk_info.get_allocation_percentage()}%")
        print(f"     🏷️  Тип: {disk_info.type.value}")
        print(f"     📊 Статус: {disk_info.status.value if disk_info.status else 'N/A'}")

        # Проверяем информацию через list_disks с фильтром
        print("\n   Проверка фильтрации дисков:")

        # Фильтр по формату
        raw_query = DiskQuery(format=DiskFormat.RAW)
        raw_disks = manager.list_disks(raw_query)
        print(f"     RAW дисков найдено: {len(raw_disks)}")

        # Фильтр по размеру
        size_query = DiskQuery(min_size_gb=0.5)
        large_disks = manager.list_disks(size_query)
        print(f"     Дисков > 0.5GB: {len(large_disks)}")

        # Фильтр по имени
        name_query = DiskQuery(vm_name=None)  # Диски без ВМ
        detached_disks = manager.list_disks(name_query)
        print(f"     Отключенных дисков: {len(detached_disks)}")

