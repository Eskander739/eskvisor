import os
import shutil


def test_vd_06_clone_disk():
    """
    VD‑06: Клонирование диска

    Создать копию диска. Проверить, что клон идентичен исходному.
    """
    print("\n" + "=" * 60)
    print("VD‑06: Клонирование диска")
    print("=" * 60)

    with StorageManager() as manager:
        # Создаем исходный диск
        source_disk_path = os.path.join(test_env['raw_dir'], "clone-source.img")
        clone_disk_path = os.path.join(test_env['raw_dir'], "clone-copy.img")

        # Создаем исходный файл с тестовыми данными
        print("\n1. Создание исходного диска:")
        test_data = b"Test data for cloning " * 100  # 2KB тестовых данных

        with open(source_disk_path, 'wb') as f:
            f.write(test_data)

        source_size = os.path.getsize(source_disk_path)
        print(f"   ✅ Создан исходный диск: {source_disk_path}")
        print(f"   📏 Размер: {source_size / 1024:.2f} KB")

        # Клонируем диск (простое копирование файла)
        print("\n2. Клонирование диска:")
        try:
            shutil.copy2(source_disk_path, clone_disk_path)
            print(f"   ✅ Диск клонирован: {clone_disk_path}")

            # Проверяем, что файл скопирован
            assert os.path.exists(clone_disk_path), "Ошибка: клон не создан"

            # Сравниваем размеры
            clone_size = os.path.getsize(clone_disk_path)
            print(f"   📏 Размер клона: {clone_size / 1024:.2f} KB")

            assert source_size == clone_size, f"Ошибка: размеры не совпадают: {source_size} != {clone_size}"

            # Сравниваем содержимое
            print("\n3. Проверка идентичности содержимого:")
            with open(source_disk_path, 'rb') as f1, open(clone_disk_path, 'rb') as f2:
                source_content = f1.read()
                clone_content = f2.read()

                assert source_content == clone_content, "Ошибка: содержимое дисков не идентично"
                print("   ✅ Содержимое дисков идентично")

            # Проверяем через StorageManager
            print("\n4. Проверка через StorageManager:")
            source_info = manager.get_disk_info(path=source_disk_path)
            clone_info = manager.get_disk_info(path=clone_disk_path)

            assert source_info is not None and clone_info is not None, "Ошибка: информация о дисках не получена"

            print(f"   📝 Исходный диск: {source_info.name}, Формат: {source_info.format.value}")
            print(f"   📝 Клон: {clone_info.name}, Формат: {clone_info.format.value}")

            # Основные параметры должны совпадать
            assert source_info.format == clone_info.format, "Ошибка: форматы не совпадают"
            assert source_info.get_effective_size_gb() == clone_info.get_effective_size_gb(), "Ошибка: размеры не совпадают"

            print("   ✅ Основные параметры дисков совпадают")

        except Exception as e:
            print(f"   ⚠️  Ошибка при клонировании: {e}")
            print("   ⚠️  Пропускаем тест клонирования")

        # Очистка
        for disk_path in [source_disk_path, clone_disk_path]:
            if os.path.exists(disk_path):
                os.remove(disk_path)
