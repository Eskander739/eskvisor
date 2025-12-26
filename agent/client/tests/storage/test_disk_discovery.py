import os

from agent.client.hypervisor.models.disk import DiskFormat


def test_disk_discovery():
    """
    Дополнительный тест: обнаружение дисков в файловой системе
    """
    print("\n" + "=" * 60)
    print("Дополнительный тест: Обнаружение дисков")
    print("=" * 60)

    with StorageManager() as manager:
        # Создаем несколько тестовых дисков в разных форматах
        test_disks = [
            ("discovered-raw.img", DiskFormat.RAW, 0.1),
            ("discovered-qcow2.qcow2", DiskFormat.QCOW2, 0.2),
            ("discovered-vmdk.vmdk", DiskFormat.VMDK, 0.3),
        ]

        print("\n1. Создание тестовых дисков для обнаружения:")
        for filename, disk_format, size_gb in test_disks:
            disk_path = os.path.join(test_env['test_dir'], filename)

            # Создаем простые файлы
            with open(disk_path, 'wb') as f:
                f.write(b'\0' * 1024 * 1024 * int(size_gb * 1024))  # Приблизительный размер

            print(f"   📁 Создан {disk_format.value}: {filename} ({size_gb:.1f} GB)")

        # Обнаружение дисков
        print("\n2. Обнаружение дисков в тестовой директории:")
        discovered_disks = manager.discover_disks(search_path=test_env['test_dir'])

        print(f"   Найдено дисков: {len(discovered_disks)}")

        # Должны найти как минимум наши тестовые файлы
        found_disks = [d.name for d in discovered_disks]
        expected_disks = [filename for filename, _, _ in test_disks]

        print(f"   Ожидаемые диски: {expected_disks}")
        print(f"   Найденные диски: {found_disks}")

        # Проверяем найденные форматы
        print("\n3. Проверка форматов найденных дисков:")
        for disk in discovered_disks:
            print(f"   📝 {disk.name}: {disk.format.value}, {disk.get_effective_size_gb():.2f} GB")

        # Поиск дисков по шаблону
        print("\n4. Поиск дисков по шаблону пути:")

        # Ищем QCOW2 диски
        qcow2_pattern = r".*\.qcow2$"
        qcow2_disks = manager.find_disk_by_path_pattern(qcow2_pattern)
        print(f"   QCOW2 дисков по шаблону: {len(qcow2_disks)}")

        # Ищем raw/img диски
        raw_pattern = r".*\.(img|raw)$"
        raw_disks = manager.find_disk_by_path_pattern(raw_pattern)
        print(f"   RAW/IMG дисков по шаблону: {len(raw_disks)}")
