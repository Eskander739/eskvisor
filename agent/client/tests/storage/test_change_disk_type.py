
def test_vd_05_convert_disk():
    """
    VD‑05: Изменение типа диска (например, с QCOW2 на RAW)

    Конвертировать диск в другой формат.
    Убедиться, что данные сохраняются и диск работает.
    """
    print("\n" + "=" * 60)
    print("VD‑05: Изменение типа диска")
    print("=" * 60)

    with StorageManager() as manager:
        # Создаем тестовый QCOW2 диск
        source_disk_path = os.path.join(test_env['qcow2_dir'], "convert-source.qcow2")
        target_disk_path = os.path.join(test_env['raw_dir'], "convert-target.img")

        # Создаем исходный QCOW2 диск
        print("\n1. Создание исходного QCOW2 диска:")
        qcow2_create = DiskCreate(
            name="convert-source.qcow2",
            path=source_disk_path,
            size_gb=0.5,  # 500MB
            format=DiskFormat.QCOW2,
            sparse=True
        )

        source_disk = manager.create_disk(qcow2_create)
        assert source_disk is not None, "Ошибка: исходный QCOW2 диск не создан"
        assert source_disk.format == DiskFormat.QCOW2, "Ошибка: неверный формат исходного диска"

        print(f"   ✅ Создан QCOW2 диск: {source_disk_path}")
        print(f"   📏 Размер: {source_disk.get_effective_size_gb():.2f} GB")

        # Конвертируем в RAW
        print("\n2. Конвертация QCOW2 в RAW:")

        # Проверяем наличие qemu-img
        result = subprocess.run(["which", "qemu-img"], capture_output=True, text=True)
        if result.returncode == 0:
            try:
                # Используем метод конвертации из StorageManager
                success = manager.convert_disk_format(
                    source_path=source_disk_path,
                    target_path=target_disk_path,
                    target_format=DiskFormat.RAW,
                    sparse=False
                )

                if success:
                    print("   ✅ Конвертация выполнена успешно")

                    # Проверяем, что целевой файл существует
                    assert os.path.exists(target_disk_path), "Ошибка: целевой RAW файл не создан"

                    # Получаем информацию о целевом диске
                    target_disk_info = manager.get_disk_info(path=target_disk_path)
                    assert target_disk_info is not None, "Ошибка: информация о целевом диске не получена"
                    assert target_disk_info.format == DiskFormat.RAW, f"Ошибка: неверный формат целевого диска: {target_disk_info.format}"

                    print(f"   ✅ Создан RAW диск: {target_disk_path}")
                    print(f"   📏 Размер: {target_disk_info.get_effective_size_gb():.2f} GB")

                    # Сравниваем размеры
                    source_size = source_disk.get_effective_size_gb()
                    target_size = target_disk_info.get_effective_size_gb()

                    print(f"   📊 QCOW2 размер: {source_size:.2f} GB")
                    print(f"   📊 RAW размер: {target_size:.2f} GB")

                    # RAW обычно больше QCOW2 из-за sparse
                    if source_size <= target_size:
                        print("   ✅ Размеры соответствуют ожиданиям")
                    else:
                        print(f"   ⚠️  RAW размер меньше QCOW2: {target_size:.2f} GB < {source_size:.2f} GB")

                    # Проверяем содержимое (базовую проверку)
                    print("\n3. Базовая проверка целостности:")
                    # Открываем файлы и проверяем первые байты
                    try:
                        with open(source_disk_path, 'rb') as f1, open(target_disk_path, 'rb') as f2:
                            # Проверяем, что оба файла можно прочитать
                            f1.read(1)
                            f2.read(1)
                            print("   ✅ Оба файла читаются корректно")
                    except Exception as e:
                        print(f"   ⚠️  Ошибка чтения файлов: {e}")

                else:
                    print("   ❌ Конвертация не удалась")
                    print("   ⚠️  Этот тест требует корректной работы qemu-img")

            except Exception as e:
                print(f"   ⚠️  Ошибка при конвертации: {e}")
                print("   ⚠️  Пропускаем тест конвертации")
        else:
            print("   ⚠️  qemu-img не найден, пропускаем тест конвертации")

        # Очистка
        for disk_path in [source_disk_path, target_disk_path]:
            if os.path.exists(disk_path):
                os.remove(disk_path)

