import os

import pytest

from agent.client.hypervisor.models.disk import DiskQuery, DiskCreate, DiskFormat


@pytest.mark.tags("VD‑07", "Удаление диска")
def test_vd_07_delete_disk(storage_session, setup_test_environment):
    """
    VD‑07: Удаление диска

    Удалить диск с подтверждением. Проверить, что место освобождается.
    """

    disk_directory = setup_test_environment.get("raw_dir")
    delete_disk_path = os.path.join(disk_directory, "delete-test-disk.img")

    raw_disk_create = DiskCreate(
        name="test-raw-disk.img",
        path=delete_disk_path,
        size_gb=0.1,
        format=DiskFormat.RAW,
        sparse=False,
        description="Тестовый RAW диск"
    )

    storage_session.create_disk(raw_disk_create)
    raw_disk_info = storage_session.get_disk_info(path=raw_disk_create.path)
    assert raw_disk_info is not None, "Ошибка: RAW диск не создан"

    assert os.path.exists(delete_disk_path), "Ошибка: тестовый файл для удаления не создан"

    delete_result = storage_session.delete_disk(path=delete_disk_path)

    assert delete_result is True, "Ошибка: удаление диска не удалось"
    assert not os.path.exists(delete_disk_path), "Ошибка: файл диска не удален"

    all_disks = storage_session.list_disks(DiskQuery(search_path=disk_directory))
    deleted_disk_in_list = any(d.path == delete_disk_path for d in all_disks)
    assert not deleted_disk_in_list, "Ошибка: удаленный диск все еще в списке"

