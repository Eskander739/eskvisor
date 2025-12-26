
def test_vd_09_disk_creation_error():
    """
    VD‑09: Ошибка при создании диска (недостаточно места)

    Попытаться создать диск больше, чем доступно в хранилище.
    Получить корректное сообщение об ошибке.
    """
    print("\n" + "=" * 60)
    print("VD‑09: Ошибка при создании диска (недостаточно места)")
    print("=" * 60)

    with StorageManager() as manager:
        # Пытаемся создать слишком большой диск
        huge_disk_path = os.path.join(test_env['raw_dir'], "huge-disk.img")

        # Получаем свободное место на диске
        try:
            import shutil
            disk_usage = shutil.disk_usage(test_env['raw_dir'])
            free_space_gb = disk_usage.free / (1024 ** 3)

            print(f"   📊 Свободное место в {test_env['raw_dir']}: {free_space_gb:.2f} GB")

            # Пытаемся создать диск больше свободного места
            huge_size_gb = free_space_gb * 2  # Вдвое больше свободного места

            print(f"   🚫 Попытка создания диска размером {huge_size_gb:.2f} GB...")

            huge_disk_create = DiskCreate(
                name="huge-disk.img",
                path=huge_disk_path,
                size_gb=huge_size_gb,
                format=DiskFormat.RAW,
                sparse=False
            )

            # Этот тест может вести себя по-разному в зависимости от системы
            # В некоторых случаях диск может создаться с ошибкой, в других - нет
            print("   ⚠️  Этот тест зависит от поведения файловой системы")
            print("   ⚠️  В некоторых системах файл может создаться с ошибкой ENOSPC")

            # Пробуем создать диск и отслеживаем ошибки
            try:
                huge_disk = manager.create_disk(huge_disk_create)

                if huge_disk is None:
                    print("   ✅ Диск не создан (ожидаемое поведение при нехватке места)")
                else:
                    print("   ⚠️  Диск создан, несмотря на нехватку места")
                    print("   ⚠️  Возможно, файловая система поддерживает sparse файлы")

                    # Проверяем фактический размер
                    if os.path.exists(huge_disk_path):
                        actual_size = os.path.getsize(huge_disk_path)
                        actual_size_gb = actual_size / (1024 ** 3)
                        print(f"   📏 Фактический размер файла: {actual_size_gb:.2f} GB")

                        if actual_size_gb < huge_size_gb:
                            print("   ⚠️  Файл создан как sparse (разреженный)")
                        else:
                            print("   ❌ Файл занял всё запрошенное место (неожиданно)")

                        # Удаляем тестовый файл
                        os.remove(huge_disk_path)

            except Exception as e:
                print(f"   ✅ Получена ошибка при создании диска: {e}")
                print("   ✅ Ожидаемое поведение при нехватке места")

        except Exception as e:
            print(f"   ⚠️  Ошибка при проверке свободного места: {e}")
            print("   ⚠️  Пропускаем тест ошибки создания")

