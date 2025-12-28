import random
import uuid

import pytest
from agent.client.hypervisor.models.disk import DiskCreate, DiskFormat, DiskStatus, DiskAttach, DiskDetach
from agent.client.hypervisor.models.msg import CommandMessagesEnum

RANDOM_NAME = random.randint(10000, 99999)

@pytest.mark.tags("VD‑10", "Одновременное подключение одного диска к нескольким ВМ")
def test_vd_10_concurrent_attachment(storage_session, multi_create_stopped_vm):
    """
    VD‑10: Одновременное подключение одного диска к нескольким ВМ

    Попытаться подключить один и тот же диск к двум ВМ.
    Система должна запретить операцию.
    """

    target_dev_list = ["vdb", "vdd"]
    request_id = str(uuid.uuid4())
    disk_path = None
    vm_name_to_detach = None
    target_dev_to_detach = None
    try:
        # ____________________________________Создание диска____________________________________
        attach_disk_create = DiskCreate(name=f"disk-test-{RANDOM_NAME}.qcow2", size_gb=0.2, format=DiskFormat.QCOW2,
                                        sparse=True)
        attach_disk = storage_session.create_disk(attach_disk_create)
        assert attach_disk is not None, "Ошибка: диск для подключения не создан"

        vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)
        vm_disk = vm_disk.disk_info
        disk_path = vm_disk.path

        assert vm_disk.status.value == DiskStatus.DETACHED.value
        current_disk_name = vm_disk.name.split(".").pop(0)
        assert current_disk_name == attach_disk_create.name
        assert attach_disk_create.format == DiskFormat.QCOW2

        disk_attach_list = []
        for vm_config_name, target_dev in zip(multi_create_stopped_vm, target_dev_list):
            disk_attach_list.append(DiskAttach(vm_name=vm_config_name, path=vm_disk.path, target_dev=target_dev))

        for index, disk_attach in enumerate(disk_attach_list):
            print("ИТЕРАЦИЯ УЕБИЩ СУКА: ", disk_attach.vm_name)
            attach_disk_result = storage_session.attach_disk(disk_attach, request_id=request_id)
            if index == 0:

                # ____________________________________Подключение диска____________________________________
                assert attach_disk_result.message == CommandMessagesEnum.disk_successfully_attached.value
                assert attach_disk_result.code == CommandMessagesEnum.disk_successfully_attached.name
                current_vm_disk = storage_session.get_disk_info_by_target_dev(vm_name=disk_attach.vm_name,
                                                                      target_dev=disk_attach.target_dev,
                                                                      request_id=request_id)

                assert current_vm_disk.message == CommandMessagesEnum.disk_founded_by_target_dev.value
                assert current_vm_disk.code == CommandMessagesEnum.disk_founded_by_target_dev.name
                vm_name_to_detach = disk_attach.vm_name
                target_dev_to_detach = disk_attach.target_dev
            elif index == 1:

                # ____________________________________Подключение диска____________________________________
                assert attach_disk_result.message == CommandMessagesEnum.disk_already_attached_error.value
                assert attach_disk_result.code == CommandMessagesEnum.disk_already_attached_error.name
                current_vm_disk = storage_session.get_disk_info_by_target_dev(vm_name=disk_attach.vm_name,
                                                                      target_dev=disk_attach.target_dev,
                                                                      request_id=request_id)

                assert current_vm_disk.message == CommandMessagesEnum.disk_not_found_by_target_dev.value
                assert current_vm_disk.code == CommandMessagesEnum.disk_not_found_by_target_dev.name

        # ____________________________________Отключение диска____________________________________

        storage_session.detach_disk(DiskDetach(vm_name=vm_name_to_detach, target_dev=target_dev_to_detach))

        vm_disk = storage_session.get_disk_info(path=attach_disk_create.path)
        vm_disk = vm_disk.disk_info

        assert vm_disk.status.value == DiskStatus.DETACHED.value

    finally:
        # ____________________________________Удаление диска(постусловие)____________________________________
        if disk_path is not None:
            storage_session.delete_disk(path=disk_path)
            vm_disk = storage_session.get_disk_info(path=disk_path)
            assert vm_disk.message == CommandMessagesEnum.disk_not_found.value
            assert vm_disk.code == CommandMessagesEnum.disk_not_found.name
