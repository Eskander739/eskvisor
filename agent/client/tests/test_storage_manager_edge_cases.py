"""
Тесты для проверки граничных случаев и ошибок StorageManager
"""

import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock

from agent.client.hypervisor.libvirt.managers.storage_manager import StorageManager

# Добавляем путь для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.client.hypervisor.models.disk import (
    DiskCreate, DiskUpdate, DiskAttach, DiskQuery,
    DiskFormat, DiskType, DiskStatus, BusType, CacheMode
)


def test_edge_cases_with_mocks():
    """Тестирование граничных случаев с использованием моков"""

    print("\n🧪 Тестирование граничных случаев StorageManager")
    print("=" * 60)

    # Создаем временную директорию
    test_dir = tempfile.mkdtemp(prefix="vm_storage_edge_test_")
    print(f"📁 Тестовая директория: {test_dir}")

    try:
        # Тест 1: Попытка получения информации о несуществующем диске
        print("\n1. Получение информации о несуществующем диске:")
        with StorageManager() as manager:
            non_existent_path = os.path.join(test_dir, "non-existent-disk.img")
            disk_info = manager.get_disk_info(path=non_existent_path)

            if disk_info is None:
                print("   ✅ Корректная обработка несуществующего диска")
            else:
                print(f"   ⚠️  Информация получена для несуществующего диска")

        # Тест 2: Попытка удаления несуществующего диска
        print("\n2. Удаление несуществующего диска:")
        with StorageManager() as manager:
            result = manager.delete_disk(path=non_existent_path)

            if not result:
                print("   ✅ Корректная обработка удаления несуществующего диска")
            else:
                print(f"   ⚠️  Удаление несуществующего диска вернуло True")

        # Тест 3: Создание диска с недопустимыми параметрами
        print("\n3. Создание диска с нулевым размером:")
        with StorageManager() as manager:
            zero_disk_path = os.path.join(test_dir, "zero-size-disk.img")

            # Пытаемся создать диск размером 0 GB
            zero_disk_create = DiskCreate(
                name="zero-size-disk.img",
                path=zero_disk_path,
                size_gb=0,  # Нулевой размер
                format=DiskFormat.RAW,
                sparse=False
            )

            # Этот тест зависит от валидации в DiskCreate
            # Pydantic должен выбросить исключение при size_gb <= 0
            print("   ⚠️  Pydantic должен валидировать size_gb > 0")

        # Тест 4: Фильтрация с неверными параметрами
        print("\n4. Фильтрация дисков с неверными параметрами:")
        with StorageManager() as manager:
            # min_size > max_size
            invalid_query = DiskQuery(min_size_gb=10, max_size_gb=5)

            # Pydantic должен выбросить ValidationError
            print("   ⚠️  Pydantic должен валидировать min_size_gb <= max_size_gb")

        # Тест 5: Попытка изменения несуществующего диска
        print("\n5. Изменение несуществующего диска:")
        with StorageManager() as manager:
            disk_update = DiskUpdate(name="renamed-disk.img")
            result = manager.edit_disk(path=non_existent_path, disk_update=disk_update)

            if result is None:
                print("   ✅ Корректная обработка изменения несуществующего диска")
            else:
                print(f"   ⚠️  Изменение несуществующего диска вернуло результат")

        # Тест 6: Конвертация несуществующего диска
        print("\n6. Конвертация несуществующего диска:")
        with StorageManager() as manager:
            target_path = os.path.join(test_dir, "converted-disk.img")
            result = manager.convert_disk_format(
                source_path=non_existent_path,
                target_path=target_path,
                target_format=DiskFormat.RAW
            )

            if not result:
                print("   ✅ Корректная обработка конвертации несуществующего диска")
            else:
                print(f"   ⚠️  Конвертация несуществующего диска вернула True")

        print("\n" + "=" * 60)
        print("✅ Тесты граничных случаев выполнены!")

    except Exception as e:
        print(f"\n❌ Ошибка при тестировании граничных случаев: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Очистка
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            print(f"\n🗑️  Удалена тестовая директория: {test_dir}")


def test_integration_scenarios():
    """Тестирование интеграционных сценариев"""

    print("\n🔄 Тестирование интеграционных сценариев")
    print("=" * 60)

    test_dir = tempfile.mkdtemp(prefix="vm_storage_integration_test_")
    print(f"📁 Тестовая директория: {test_dir}")

    try:
        with StorageManager() as manager:
            # Сценарий 1: Полный жизненный цикл диска
            print("\n1. Полный жизненный цикл диска:")
            lifecycle_disk_path = os.path.join(test_dir, "lifecycle-disk.qcow2")

            # 1.1 Создание
            print("   📝 Создание диска...")
            create_cmd = DiskCreate(
                name="lifecycle-disk.qcow2",
                path=lifecycle_disk_path,
                size_gb=1.0,
                format=DiskFormat.QCOW2,
                sparse=True
            )
            disk = manager.create_disk(create_cmd)
            assert disk is not None, "Ошибка создания диска"
            print(f"   ✅ Диск создан: {disk.name}")

            # 1.2 Получение информации
            print("   ℹ️  Получение информации...")
            info = manager.get_disk_info(path=lifecycle_disk_path)
            assert info is not None, "Ошибка получения информации"
            print(f"   ✅ Информация получена: {info.get_effective_size_gb():.1f} GB")

            # 1.3 Обновление (переименование)
            print("   ✏️  Переименование...")
            update_cmd = DiskUpdate(name="lifecycle-disk-renamed.qcow2")
            updated_disk = manager.edit_disk(path=lifecycle_disk_path, disk_update=update_cmd)

            if updated_disk:
                print(f"   ✅ Диск переименован: {updated_disk.name}")
                lifecycle_disk_path = updated_disk.path
            else:
                print("   ⚠️  Переименование не поддерживается для файловых дисков")

            # 1.4 Проверка в списке
            print("   📋 Проверка в списке дисков...")
            all_disks = manager.list_disks()
            disk_in_list = any(d.path == lifecycle_disk_path for d in all_disks)
            assert disk_in_list, "Диск не найден в списке"
            print(f"   ✅ Диск найден в списке ({len(all_disks)} всего)")

            # 1.5 Удаление
            print("   🗑️  Удаление...")
            delete_result = manager.delete_disk(path=lifecycle_disk_path)
            assert delete_result, "Ошибка удаления диска"
            print("   ✅ Диск удален")

            # 1.6 Проверка, что удален
            deleted_info = manager.get_disk_info(path=lifecycle_disk_path)
            assert deleted_info is None, "Диск все еще доступен после удаления"
            print("   ✅ Диск полностью удален из системы")

        # Сценарий 2: Работа с несколькими дисками
        print("\n2. Работа с несколькими дисками:")
        with StorageManager() as manager:
            # Создаем несколько дисков
            disks = []
            for i in range(3):
                disk_path = os.path.join(test_dir, f"multi-disk-{i}.qcow2")
                create_cmd = DiskCreate(
                    name=f"multi-disk-{i}.qcow2",
                    path=disk_path,
                    size_gb=0.5,
                    format=DiskFormat.QCOW2,
                    sparse=True
                )
                disk = manager.create_disk(create_cmd)
                if disk:
                    disks.append(disk)
                    print(f"   ✅ Создан диск {i + 1}/3: {disk.name}")

            print(f"   📊 Создано дисков: {len(disks)}")

            # Фильтрация
            print("\n   Фильтрация дисков:")
            qcow2_query = DiskQuery(format=DiskFormat.QCOW2)
            qcow2_disks = manager.list_disks(qcow2_query)
            print(f"   📁 QCOW2 дисков: {len(qcow2_disks)}")

            size_query = DiskQuery(min_size_gb=0.4, max_size_gb=0.6)
            sized_disks = manager.list_disks(size_query)
            print(f"   📏 Дисков 0.4-0.6 GB: {len(sized_disks)}")

            # Обнаружение
            print("\n   Обнаружение дисков:")
            discovered = manager.discover_disks(search_path=test_dir)
            print(f"   🔍 Обнаружено дисков: {len(discovered)}")

            # Очистка
            print("\n   Очистка тестовых дисков...")
            for disk in disks:
                if os.path.exists(disk.path):
                    manager.delete_disk(path=disk.path)
            print("   ✅ Все тестовые диски удалены")

        print("\n" + "=" * 60)
        print("✅ Интеграционные тесты выполнены успешно!")

    except Exception as e:
        print(f"\n❌ Ошибка при интеграционном тестировании: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Очистка
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            print(f"\n🗑️  Удалена тестовая директория: {test_dir}")


if __name__ == "__main__":
    # Запуск тестов граничных случаев
    test_edge_cases_with_mocks()

    # Запуск интеграционных тестов
    test_integration_scenarios()