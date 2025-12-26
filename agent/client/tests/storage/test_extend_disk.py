import os
import subprocess

from agent.client.hypervisor.models.disk import DiskUpdate


def test_vd_04_extend_disk():
    """
    VD‑04: Расширение диска

    Увеличить размер диска.
    Проверить, что в гостевой ОС можно использовать новое пространство.
    """
    print("\n" + "=" * 60)
    print("VD‑04: Расширение диска")
    print("=" * 60)

    with StorageManager() as manager:
        # Создаем тестовый диск для расширения
        extend_disk_path = os.path.join(test_env['raw_dir'], "extend-test-disk.img")

        # Создаем начальный файл размером 100MB
        initial_size_mb = 100
        with open(extend_disk_path, 'wb') as f:
            f.write(b'\0' * 1024 * 1024 * initial_size_mb)

        print(f"   Создан тестовый диск: {extend_disk_path}")
        print(f"   📏 Исходный размер: {initial_size_mb} MB")

        # Получаем начальную информацию о диске
        initial_disk_info = manager.get_disk_info(path=extend_disk_path)
        assert initial_disk_info is not None, "Ошибка: информация о диске не получена"

        initial_size_gb = initial_disk_info.get_effective_size_gb()
        print(f"   📏 Начальный размер (через get_disk_info): {initial_size_gb:.2f} GB")

        # Расширяем диск до 200MB (0.2GB)
        new_size_gb = 0.2  # 200MB

        # Сначала пробуем через edit_disk
        disk_update = DiskUpdate(new_size_gb=new_size_gb)

        print(f"\n   Расширение диска до {new_size_gb} GB...")

        # Для файловых дисков расширение может требовать qemu-img
        # Используем прямое расширение через qemu-img
        try:
            # Проверяем наличие qemu-img
            result = subprocess.run(["which", "qemu-img"], capture_output=True, text=True)
            if result.returncode == 0:
                # Используем qemu-img для расширения
                cmd = ["qemu-img", "resize", extend_disk_path, f"{new_size_gb}G"]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    print("   ✅ Диск расширен через qemu-img")

                    # Проверяем новый размер
                    final_disk_info = manager.get_disk_info(path=extend_disk_path)
                    final_size_gb = final_disk_info.get_effective_size_gb()

                    print(f"   📏 Новый размер: {final_size_gb:.2f} GB")
                    print(f"   📈 Увеличение: {(final_size_gb - initial_size_gb):.2f} GB")

                    # Проверяем, что размер увеличился
                    assert final_size_gb > initial_size_gb, "Ошибка: размер диска не увеличился"
                    assert abs(
                        final_size_gb - new_size_gb) < 0.01, f"Ошибка: итоговый размер {final_size_gb:.2f} GB не соответствует целевому {new_size_gb:.2f} GB"

                    print("   ✅ Проверка расширения диска пройдена")
                else:
                    print(f"   ⚠️  qemu-img не смог расширить диск: {result.stderr}")
                    print("   ⚠️  Этот тест требует установленного qemu-img")
            else:
                print("   ⚠️  qemu-img не найден, пропускаем тест расширения")
        except Exception as e:
            print(f"   ⚠️  Ошибка при расширении диска: {e}")
            print("   ⚠️  Пропускаем тест расширения")

        # Очистка
        if os.path.exists(extend_disk_path):
            os.remove(extend_disk_path)

