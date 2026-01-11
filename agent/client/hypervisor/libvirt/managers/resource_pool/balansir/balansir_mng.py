import datetime
import random
import shutil
import xml.etree.ElementTree as ET

import orjson
import os
import uuid
from pathlib import Path, PurePosixPath

from dotenv import load_dotenv

from agent.client.cli import CLIControl
from agent.client.constants import INVALID_LINUX_CHAR
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.managers.resource_pool.volume_managers.logical_volume_manager import (
    LogicalVolumeManager,
)
from agent.client.hypervisor.libvirt.managers.resource_pool.volume_managers.physical_volume_manager import (
    PhysicalVolumeManager,
)
from agent.client.hypervisor.libvirt.managers.resource_pool.volume_managers.volume_group_manager import (
    VolumeGroupManager,
)
from agent.client.hypervisor.libvirt.managers.storage_manager import StorageManager
from agent.client.hypervisor.libvirt.managers.vm_manager import VmManager
from agent.client.hypervisor.libvirt.models.msg import RpMessage, CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualCreate,
    ResourcePoolVirtual,
    ResourcePoolVirtualEdit,
    ResourceReservationVM,
)
from agent.client.hypervisor.libvirt.models.volume.logic_volume import (
    LogicalVolumeSizeType,
)
from agent.client.hypervisor.libvirt.models.general import StoragePoolType
from agent.client.logger_config import DefaultLogger

load_dotenv()


class Balansir(LibvirtClient):
    """
    Балансиръ - виртуальный менеджер ресурс пулов для контроля CPU и RAM лимитов

    Мониторинг ресурсов - не даем текущим ВМ превышать лимит по ресурсам + резервы

    При попытке ВМ взять ресурсов больше чем доступно в ресурс пуле ->
    проверяем есть ли ресурсы в резерве, если есть - берем не превышая лимиты УЖЕ резерва
    """

    def __init__(self):
        super().__init__()
        self.logger = DefaultLogger("Балансиръ")
        self.logger.info(f"Инициализация виртуального менеджера ресурс пулов")
        self.system_volume_group_name = os.environ.get("VOLUME_GROUP")
        self.storage_type_dir_base_path = os.environ.get("STORAGE_TYPE_DIR_BASE_PATH")
        self.storage_manager = StorageManager()
        self.storage_manager.connect()
        self.physical_volume_manager = PhysicalVolumeManager()
        self.volume_group_manager = VolumeGroupManager()
        system_volume_group = self.volume_group_manager.get_volume_by_name(
            self.system_volume_group_name
        )
        if system_volume_group is None:
            valid_physical_volumes = (
                self.physical_volume_manager.valid_physical_volumes()
            )
            self.volume_group_manager.create_volume_group(
                pv_names=valid_physical_volumes,
                volume_group_name=self.system_volume_group_name,
            )
        self.logic_volume_manager = LogicalVolumeManager()
        self.virtual_rp_manager_path = os.environ.get("RP_VIRTUAL_MANAGER_PATH")
        self.cli = CLIControl()
        self.vm_manager = VmManager()
        self.vm_manager.connect()
        self.node_info = self.vm_manager.get_node_info()
        # self.memory_virtual_resoruce_pool = {}
        if not os.path.exists(self.virtual_rp_manager_path):
            root_dir = f"/{self.virtual_rp_manager_path.split('/')[1]}"
            if not os.path.exists(root_dir):
                cmd_args = ["mkdir", root_dir]
                self.logger.info(f"Создание корневой директории: '{root_dir}'")
                result = self.cli.execute(cmd_args)
                if not os.path.exists(root_dir):
                    err_text = f"Ошибка создания корневой директории: '{root_dir}', команда: '{cmd_args}', результат: '{result}'"
                    self.logger.warning(err_text)
                    raise RuntimeError(err_text)
                self.logger.info(f"Корневая директория '{root_dir}' успешно создана")

            self.logger.info(
                f"Создание основной директории: '{self.virtual_rp_manager_path}'"
            )
            cmd_args = ["mkdir", self.virtual_rp_manager_path]
            result = self.cli.execute(cmd_args)
            if not os.path.exists(self.virtual_rp_manager_path):
                err_text = f"Ошибка создания директории: '{self.virtual_rp_manager_path}', команда: '{cmd_args}', результат: '{result}'"
                self.logger.warning(err_text)
                raise RuntimeError(err_text)
            self.logger.info(
                f"Основная директория '{self.virtual_rp_manager_path}' успешно создана"
            )
            self.cli.execute(["chmod", "-R", "777", self.virtual_rp_manager_path])
        self.logger.info(f"Виртуальный менеджер ресурс пулов инициализирован")

    def validate_uuid(self, vm_uuid: str):
        for invalid_linux_char in INVALID_LINUX_CHAR:
            if invalid_linux_char in vm_uuid:
                raise ValueError(
                    f"Запрещенный символ: '{invalid_linux_char}' в UUID: '{vm_uuid}'"
                )

    def validate_vm_list(self, create_rp: ResourcePoolVirtualCreate) -> RpMessage:
        self.logger.info(f"Старт валидации списка ВМ")
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        if isinstance(create_rp.vm_uuid_list, list):
            for vm_uuid in create_rp.vm_uuid_list:
                self.validate_uuid(vm_uuid)

                try:
                    self.logger.info(f"Поиск ВМ {vm_uuid}")
                    virtual_machine = self.vm_manager.conn.lookupByUUIDString(vm_uuid)
                    current_vm_info = self.vm_manager.get_vm_info(virtual_machine)
                    if current_vm_info.memory_bytes > create_rp.ram_limit:
                        err_text = (
                            f"Объем оперативной памяти ВМ: '{current_vm_info.memory_bytes}' "
                            f"больше чем у создаваемого пула: '{create_rp.ram_limit}'"
                        )
                        self.logger.info(err_text)
                        return RpMessage(
                            request_id=internal_request_id,
                            message=CommandMessagesEnum.rp_create_error.value,
                            code=CommandMessagesEnum.rp_create_error.name,
                            success=False,
                            note=err_text,
                        )
                    if current_vm_info.vcpus > create_rp.cpu_core_limit:
                        err_text = (
                            f"Количество ядер ВМ: '{current_vm_info.vcpus}' "
                            f"больше чем у создаваемого пула: '{create_rp.cpu_core_limit}'"
                        )
                        self.logger.info(err_text)
                        return RpMessage(
                            request_id=internal_request_id,
                            message=CommandMessagesEnum.rp_create_error.value,
                            code=CommandMessagesEnum.rp_create_error.name,
                            success=False,
                            note=err_text,
                        )
                except Exception:
                    self.logger.info(f"ВМ {vm_uuid} не найдена")
                    return RpMessage(
                        request_id=internal_request_id,
                        message=CommandMessagesEnum.vm_found_error.value,
                        code=CommandMessagesEnum.vm_found_error.name,
                        success=False,
                    )
            self.logger.info(f"Список ВМ валиден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.vm_list_is_correct.value,
                code=CommandMessagesEnum.vm_list_is_correct.name,
                success=True,
            )
        else:
            raise ValueError(
                f"Некорректный тип данных: '{type(create_rp.vm_uuid_list)}'"
            )

    def validate_resource_reservation(
        self,
        name: str | Path,
        vm_reservation_list: list[ResourceReservationVM],
        vm_uuid_list: list[str],
    ):
        internal_request_id = str(uuid.uuid4())
        current_virtual_resource_pool = self.get_virtual_resource_pool_by_name(name)
        virtual_machines = {}
        for current_uuid in vm_uuid_list:
            domain = self.vm_manager.conn.lookupByUUIDString(current_uuid)
            try:
                current_vm = self.vm_manager.get_vm_info(domain)
                virtual_machines[current_uuid] = current_vm
            except Exception:
                pass
        virtual_rp_info = current_virtual_resource_pool.rp_info
        for current_resource_reservation_vm in vm_reservation_list:
            current_vm = virtual_machines[current_resource_reservation_vm.vm_uuid]
            if not isinstance(current_resource_reservation_vm, ResourceReservationVM):
                raise ValueError(
                    f"Неизвестный тип данных: '{type(current_resource_reservation_vm)}'"
                )
            if not current_resource_reservation_vm.vm_uuid_list in vm_uuid_list:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.vm_can_not_reserve_resource_when_vm_not_in_virtual_rp.value,
                    code=CommandMessagesEnum.vm_can_not_reserve_resource_when_vm_not_in_virtual_rp.name,
                    success=False,
                )
            if (
                current_resource_reservation_vm.cpu_core_count
                > virtual_rp_info.cpu_core_limit
            ):
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.vm_can_not_reserve_more_cpu_than_available_on_the_virtual_rp.value,
                    code=CommandMessagesEnum.vm_can_not_reserve_more_cpu_than_available_on_the_virtual_rp.name,
                    success=False,
                    note=f"VM: {current_resource_reservation_vm.vm_uuid}, "
                    f"CPU COUNT RESERVE: {current_resource_reservation_vm.cpu_core_count},"
                    f"AVAILABLE CPU COUNT: {virtual_rp_info.cpu_core_limit}",
                )
            if current_resource_reservation_vm.ram > virtual_rp_info.ram_limit:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.vm_can_not_reserve_more_ram_than_available_on_the_virtual_rp.value,
                    code=CommandMessagesEnum.vm_can_not_reserve_more_ram_than_available_on_the_virtual_rp.name,
                    success=False,
                    note=f"VM: {current_resource_reservation_vm.vm_uuid}, "
                    f"RAM RESERVE: {current_resource_reservation_vm.ram},"
                    f"AVAILABLE RAM: {virtual_rp_info.ram_limit}",
                )

            if current_vm.memory_bytes > current_resource_reservation_vm.ram:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.vm_can_not_reserve_less_ram_than_use.value,
                    code=CommandMessagesEnum.vm_can_not_reserve_less_ram_than_use.name,
                    success=False,
                    note=f"VM: {current_resource_reservation_vm.vm_uuid}, "
                    f"RAM RESERVE: {current_resource_reservation_vm.ram},"
                    f"CURRENT USE RAM: {current_vm.memory_bytes}",
                )
            if current_vm.vcpus > current_resource_reservation_vm.cpu_core_count:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.vm_can_not_reserve_less_cpu_than_use.value,
                    code=CommandMessagesEnum.vm_can_not_reserve_less_cpu_than_use.name,
                    success=False,
                    note=f"VM: {current_resource_reservation_vm.vm_uuid}, "
                    f"CPU RESERVE: {current_resource_reservation_vm.ram},"
                    f"CURRENT USE CPU: {current_vm.vcpus}",
                )
        else:
            return True

    def configuration_cpu(
        self,
        rp_main_path: Path,
        cpu_core_limit: int,
        cpu_core_allocated: int = 0,
        cpu_core_available: int = 0,
        create_config: bool = False,
    ) -> RpMessage | bool:
        self.logger.info(f"Старт конфигурации CPU")
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        if create_config:
            if cpu_core_allocated or cpu_core_available:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.forbidden_set_available_and_allocated_data.value,
                    code=CommandMessagesEnum.forbidden_set_available_and_allocated_data.name,
                    success=False,
                )
        if not rp_main_path.exists():
            self.logger.warning(f"Виртуальный ресурс пул '{rp_main_path}' не найден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )

        cpu_info = rp_main_path / "cpu_info.json"
        self.logger.info(f"Изменение конфигурации CPU: '{str(cpu_info)}'")
        if not create_config:  # Для редактирования
            if not cpu_info.is_file():
                self.logger.warning(
                    f"Ошибка конфигурации CPU: '{str(cpu_info)}' файл отсутствует"
                )
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.rp_cpu_configuration_file_not_found.value,
                    code=CommandMessagesEnum.rp_cpu_configuration_file_not_found.name,
                    success=False,
                )
            with open(cpu_info, "rb") as cpu_info_file_read:
                cpu_data = orjson.loads(cpu_info_file_read.read())

            if cpu_data.get("cpu_core_allocated"):
                if cpu_data.get("cpu_core_allocated") > cpu_core_limit:
                    return RpMessage(
                        request_id=internal_request_id,
                        message=CommandMessagesEnum.rp_cpu_configuration_error_allocated_more_than_on_new_limit.value,
                        code=CommandMessagesEnum.rp_cpu_configuration_error_allocated_more_than_on_new_limit.name,
                        success=False,
                    )
        cpu_info_data = {
            "cpu_core_limit": cpu_core_limit,
            "cpu_core_allocated": cpu_core_allocated,
            "cpu_core_available": cpu_core_available,
        }
        with open(cpu_info, "wb") as cpu_info_file:
            cpu_info_file.write(orjson.dumps(cpu_info_data))

        self.logger.info(f"Конфигурация RAM '{str(cpu_info)}' успешно применена")

        return True

    def configuration_storage(
        self,
        rp_main_path: Path,
        volume_size_type: LogicalVolumeSizeType,
        storage_limit: int | float = 0,
        storage_allocated: int = 0,
        storage_available: int = 0,
        create_config: bool = False,
        storage_type: StoragePoolType = StoragePoolType.LOGICAL,
    ) -> RpMessage | bool:
        self.logger.info(f"Старт конфигурации STORAGE")
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        storage_info_data = {}
        if create_config:
            if storage_allocated or storage_available:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.forbidden_set_available_and_allocated_data.value,
                    code=CommandMessagesEnum.forbidden_set_available_and_allocated_data.name,
                    success=False,
                )
        if not rp_main_path.exists():
            self.logger.warning(f"Виртуальный ресурс пул '{rp_main_path}' не найден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )

        storage_info = rp_main_path / "storage_info.json"
        self.logger.info(f"Изменение конфигурации CPU: '{str(storage_info)}'")
        if not create_config:  # Для редактирования
            if not storage_info.is_file():
                self.logger.warning(
                    f"Ошибка конфигурации STORAGE: '{str(storage_info)}' файл отсутствует"
                )
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.rp_storage_configuration_file_not_found.value,
                    code=CommandMessagesEnum.rp_storage_configuration_file_not_found.name,
                    success=False,
                )
            with open(storage_info, "rb") as storage_info_file_read:
                storage_data = orjson.loads(storage_info_file_read.read())

            if storage_data.get("storage_allocated"):
                if storage_data.get("storage_allocated") > storage_limit:
                    return RpMessage(
                        request_id=internal_request_id,
                        message=CommandMessagesEnum.rp_storage_configuration_error_allocated_more_than_on_new_limit.value,
                        code=CommandMessagesEnum.rp_storage_configuration_error_allocated_more_than_on_new_limit.name,
                        success=False,
                    )
            if storage_type == StoragePoolType.LOGICAL:
                storage_info_data["storage_type"] = storage_data.get("storage_type")
                storage_info_data["group_volume"] = storage_data.get("group_volume")
                storage_info_data["logical_volume"] = storage_data.get("logical_volume")
            else:
                raise ValueError("Отсутствует поддержка других типов")
        if create_config:
            if storage_type == StoragePoolType.LOGICAL:
                result_create_lv = self.logic_volume_manager.create_volume(
                    logic_volume_name=rp_main_path.name,
                    logic_volume_size=storage_limit,
                    volume_group_name=self.system_volume_group_name,
                    logic_volume_size_type=volume_size_type,
                )
                if (
                    f'Logical volume "{rp_main_path.name}" created'
                    not in result_create_lv
                ):
                    self.logger.error(
                        f"Не удалось создать LVM пул {rp_main_path.name} в VG {self.system_volume_group_name}: {result_create_lv}"
                    )
                    return RpMessage(
                        request_id=internal_request_id,
                        message=CommandMessagesEnum.virtual_rp_create_logic_volume_error.value,
                        code=CommandMessagesEnum.virtual_rp_create_logic_volume_error.name,
                        success=False,
                    )
                storage_info_data["storage_type"] = storage_type.value
                storage_info_data["group_volume"] = self.system_volume_group_name
                storage_info_data["logical_volume"] = rp_main_path.name
            else:
                raise ValueError("Отсутствует поддержка других типов")
        storage_info_data["storage_limit"] = storage_limit
        storage_info_data["storage_allocated"] = storage_allocated
        storage_info_data["storage_available"] = storage_available
        with open(storage_info, "wb") as storage_info_file:
            storage_info_file.write(orjson.dumps(storage_info_data))

        self.logger.info(
            f"Конфигурация STORAGE '{str(storage_info)}' успешно применена"
        )

        return True

    def configuration_ram(
        self,
        rp_main_path: Path,
        ram_limit: int,
        ram_allocated: int = 0,
        ram_available: int = 0,
        create_config: bool = False,
    ) -> RpMessage | bool:
        self.logger.info(f"Старт конфигурации RAM")
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        if create_config:
            if ram_allocated or ram_available:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.forbidden_set_available_and_allocated_data.value,
                    code=CommandMessagesEnum.forbidden_set_available_and_allocated_data.name,
                    success=False,
                )
        if not rp_main_path.exists():
            self.logger.warning(f"Виртуальный ресурс пул '{rp_main_path}' не найден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )

        ram_info = rp_main_path / "ram_info.json"
        self.logger.info(f"Изменение конфигурации RAM: '{str(ram_info)}'")

        if not create_config:
            if not ram_info.is_file():
                self.logger.warning(
                    f"Ошибка конфигурации RAM: '{str(ram_info)}' файл отсутствует"
                )
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.rp_ram_configuration_error.value,
                    code=CommandMessagesEnum.rp_ram_configuration_error.name,
                    success=False,
                )
            with open(ram_info, "rb") as ram_info_file_read:
                ram_data = orjson.loads(ram_info_file_read.read())

            print("ram_data: ", ram_data)
            print("ram_limit3333: ", ram_limit)
            if ram_data.get("ram_allocated"):
                if ram_data.get("ram_allocated") > ram_limit:
                    return RpMessage(
                        request_id=internal_request_id,
                        message=CommandMessagesEnum.rp_ram_configuration_error_allocated_more_than_on_new_limit.value,
                        code=CommandMessagesEnum.rp_ram_configuration_error_allocated_more_than_on_new_limit.name,
                        success=False,
                    )

        ram_info_data = {
            "ram_limit": ram_limit,
            "ram_allocated": ram_allocated,
            "ram_available": ram_available,
        }
        with open(ram_info, "wb") as ram_info_file:
            ram_info_file.write(orjson.dumps(ram_info_data))

        self.logger.info(f"Конфигурация RAM '{str(ram_info)}' успешно применена")

        return True

    def read_vm_on_any_virtual_resource_pools(self, vm_uuid: str):
        """
        Проверка наличия ВМ в других ресурс пулах
        """

        self.sync_resource_pools()
        all_virtual_rp_list = self.get_virtual_resource_pool_list()
        for virtual_rp in all_virtual_rp_list:
            if virtual_rp.vm_uuid_list is not None:
                if vm_uuid in virtual_rp.vm_uuid_list:
                    return True
        return False

    def configuration_vm(
        self,
        rp_main_path: Path,
        vm_uuid_list: str | list[str],
        save_current_vms: bool = True,
        vm_reservation_list: list[ResourceReservationVM] | None = None,
    ) -> RpMessage | bool:
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        try:
            if isinstance(vm_uuid_list, str):
                vm_uuid_list = [vm_uuid_list]
            self.logger.info(f"Старт конфигурации ВМ")
            if not rp_main_path.exists():
                self.logger.warning(
                    f"Виртуальный ресурс пул '{rp_main_path}' не найден"
                )
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                )
            vm_info = rp_main_path / "vm_info.json"
            self.logger.info(f"Конфигурация ВМ: '{str(vm_info)}'")
            if save_current_vms:
                if vm_info.is_file():
                    with open(vm_info, "r") as vm_info_file_read:
                        current_vms_uuid_list = orjson.loads(vm_info_file_read.read())[
                            "vm_uuid_list"
                        ]
                    vm_uuid_list.extend(current_vms_uuid_list)
            self.logger.info(
                f"Проверка отсутствия ВМ: '{str(vm_info)}' в других ресурс пулах"
            )
            for current_uuid in vm_uuid_list:
                vm_on_any_rp = self.read_vm_on_any_virtual_resource_pools(current_uuid)
                if vm_on_any_rp:
                    return RpMessage(
                        request_id=internal_request_id,
                        message=CommandMessagesEnum.vm_present_on_any_virtual_resource_pool.value,
                        code=CommandMessagesEnum.vm_present_on_any_virtual_resource_pool.name,
                        success=False,
                    )

            if vm_reservation_list is not None:
                if not isinstance(vm_reservation_list, list):
                    raise ValueError(
                        f"Неизвестный тип данных: '{type(vm_reservation_list)}'"
                    )

                validate_vm_reservation_list = self.validate_resource_reservation(
                    rp_main_path, vm_reservation_list, vm_uuid_list
                )
                if validate_vm_reservation_list is not True:
                    return validate_vm_reservation_list
            vm_info_data = {"vm_uuid_list": vm_uuid_list}
            if vm_reservation_list is not None:
                vm_info_data["vm_reservation_list"] = [
                    rr_vm.model_dump() for rr_vm in vm_reservation_list
                ]
            with open(vm_info, "wb") as vm_info_file:
                vm_info_file.write(orjson.dumps(vm_info_data))

            if not vm_info.is_file():
                self.logger.warning(f"Ошибка конфигурации ВМ: '{str(vm_info)}'")
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.rp_create_error.value,
                    code=CommandMessagesEnum.rp_create_error.name,
                    success=False,
                )

            self.logger.info(f"Конфигурация ВМ '{str(vm_info)}' успешно применена")

            return True
        except Exception as e:
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_create_error.value,
                code=CommandMessagesEnum.rp_create_error.name,
                success=False,
                note=str(e),
            )

    def delete_vm_from_virtual_resource_pool(self, name: str, vm_uuid: str | list[str]):
        self.logger.info(f"Старт конфигурации ВМ")
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        rp_main_path = Path(self.virtual_rp_manager_path) / name
        if not rp_main_path.exists():
            self.logger.warning(f"Виртуальный ресурс пул '{rp_main_path}' не найден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )
        vm_info = rp_main_path / "vm_info.json"
        self.logger.info(f"Конфигурация ВМ: '{str(vm_info)}'")
        # TODO: Добавить проверку наличия ВМ в других ресурс пулах
        if vm_info.is_file():
            with open(vm_info, "r") as vm_info_file_read:
                current_vms_uuid_list: list = orjson.loads(vm_info_file_read.read())[
                    "vm_uuid_list"
                ]
        else:
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.vm_config_not_found.value,
                code=CommandMessagesEnum.vm_config_not_found.name,
                success=False,
            )

        current_vms_uuid_list.remove(vm_uuid)
        vm_info_data = {"vm_uuid_list": current_vms_uuid_list}
        with open(vm_info, "wb") as vm_info_file:
            vm_info_file.write(orjson.dumps(vm_info_data))

        if not vm_info.is_file():
            self.logger.warning(f"Ошибка конфигурации ВМ: '{str(vm_info)}'")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_create_error.value,
                code=CommandMessagesEnum.rp_create_error.name,
                success=False,
            )

        self.logger.info(f"Конфигурация ВМ '{str(vm_info)}' успешно применена")

        return RpMessage(
            request_id=internal_request_id,
            message=CommandMessagesEnum.vm_successfully_deleted_from_virtual_resource_pool.value,
            code=CommandMessagesEnum.vm_successfully_deleted_from_virtual_resource_pool.name,
            success=True,
        )

    @property
    def used_ram_and_cpu_by_resource_pools(self) -> tuple[int, int]:
        self.logger.info(
            "Определение общего объема используемых ресурсов ресурс пулами"
        )
        ram_allocated = 0
        cpu_allocated = 0
        for current_rp_virtual in self.get_virtual_resource_pool_list():
            ram_allocated += current_rp_virtual.ram_limit
            cpu_allocated += current_rp_virtual.cpu_core_limit
        self.logger.info(
            f"Определен общий объем используемых ресурсов ресурс пулами - "
            f"CPU ядер: '{cpu_allocated}', "
            f"RAM памяти: '{ram_allocated}'"
        )
        return ram_allocated, cpu_allocated

    def validate_max_ram_and_max_cpu(self, ram_limit: int, cpu_core_limit: int) -> bool:
        used_ram_by_resource_pools, used_cpu_by_resource_pools = (
            self.used_ram_and_cpu_by_resource_pools
        )
        available_ram_on_node = self.node_info.memory_bytes - used_ram_by_resource_pools
        available_cpu_on_node = self.node_info.cpus - used_cpu_by_resource_pools
        if ram_limit > available_ram_on_node:
            self.logger.warning(
                f"Объем RAM на хосте '{self.node_info.memory_bytes}' больше чем доступно в системе: '{available_ram_on_node}'"
            )
            return False
        if cpu_core_limit > available_cpu_on_node:
            self.logger.warning(
                f"Количество CPU ядер на хосте '{self.node_info.cpus}'  больше чем доступно в системе: '{available_cpu_on_node}'"
            )
            return False

        return True

    def create_virtual_resource_pool(self, create_rp: ResourcePoolVirtualCreate):
        self.logger.info(f"Создание виртуального ресурс пула: '{create_rp.name}'")

        rp_main_path = Path(self.virtual_rp_manager_path) / create_rp.name
        internal_request_id = f"internal_{str(uuid.uuid4())}"

        if not self.validate_max_ram_and_max_cpu(
            create_rp.ram_limit, create_rp.cpu_core_limit
        ):
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_ram_or_cpu_more_than_on_node.value,
                code=CommandMessagesEnum.rp_ram_or_cpu_more_than_on_node.name,
                success=False,
            )

        if rp_main_path.exists():
            self.logger.warning(
                f"Виртуальный ресурс пул '{create_rp.name}' уже существует"
            )
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_already_created.value,
                code=CommandMessagesEnum.rp_already_created.name,
                success=False,
            )
        rp_main_path.mkdir(parents=True, exist_ok=True)
        if not rp_main_path.exists():
            self.logger.warning(f"Виртуальный ресурс пул '{create_rp.name}' не создан")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_create_error.value,
                code=CommandMessagesEnum.rp_create_error.name,
                success=False,
            )

        if create_rp.vm_uuid_list is not None:
            for current_uuid in create_rp.vm_uuid_list:
                vm_on_any_rp = self.read_vm_on_any_virtual_resource_pools(current_uuid)
                if vm_on_any_rp:
                    rp_main_path.rmdir()
                    return RpMessage(
                        request_id=internal_request_id,
                        message=CommandMessagesEnum.vm_present_on_any_virtual_resource_pool.value,
                        code=CommandMessagesEnum.vm_present_on_any_virtual_resource_pool.name,
                        success=False,
                    )
            validate_vm_list_info = self.validate_vm_list(create_rp)
            if (
                validate_vm_list_info.message
                != CommandMessagesEnum.vm_list_is_correct.value
            ):
                rp_main_path.rmdir()
                return validate_vm_list_info
            self.configuration_vm(rp_main_path, create_rp.vm_uuid_list)
            self.logger.info(
                f"ВМ конфигурация ресурс пула '{create_rp.cpu_core_limit}' успешно установлена"
            )

        create_storage_config = self.configuration_storage(
            rp_main_path,
            create_rp.volume_size_type,
            create_rp.storage_limit,
            storage_type=create_rp.storage_type,
            create_config=True,
        )
        if create_storage_config is not True:
            rp_main_path.rmdir()
            return create_storage_config
        self.logger.info(f"STORAGE конфигурация ресурс пула успешно установлена")

        create_cpu_config = self.configuration_cpu(
            rp_main_path, create_rp.cpu_core_limit, create_config=True
        )
        if create_cpu_config is not True:
            rp_main_path.rmdir()
            return create_cpu_config
        self.logger.info(f"CPU конфигурация ресурс пула успешно установлена")

        create_ram_config = self.configuration_ram(
            rp_main_path, create_rp.ram_limit, create_config=True
        )
        if create_ram_config is not True:
            rp_main_path.rmdir()
            return create_ram_config
        self.logger.info(f"RAM конфигурация ресурс пула успешно установлена")

        self.logger.warning(f"Виртуальный ресурс пул '{create_rp.name}' успешно создан")

        return RpMessage(
            request_id=internal_request_id,
            message=CommandMessagesEnum.virtual_rp_create_success.value,
            code=CommandMessagesEnum.virtual_rp_create_success.name,
            success=True,
        )

    def edit_virtual_resource_pool(self, edit_rp: ResourcePoolVirtualEdit) -> RpMessage:
        self.logger.info(f"Редактирование виртуального ресурс пула: '{edit_rp.name}'")

        rp_main_path = Path(self.virtual_rp_manager_path) / edit_rp.name
        internal_request_id = f"internal_{str(uuid.uuid4())}"

        if not rp_main_path.exists():
            self.logger.warning(f"Виртуальный ресурс пул '{edit_rp.name}' не найден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )

        current_virtual_rp = self.get_virtual_resource_pool_by_name(edit_rp.name)
        current_virtual_rp = current_virtual_rp.rp_info
        if not self.validate_max_ram_and_max_cpu(
            current_virtual_rp.ram_limit, current_virtual_rp.cpu_core_limit
        ):
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_ram_or_cpu_more_than_on_node.value,
                code=CommandMessagesEnum.rp_ram_or_cpu_more_than_on_node.name,
                success=False,
            )

        if edit_rp.vm_uuid_list is not None:
            if isinstance(edit_rp.vm_uuid_list, str):
                edit_rp.vm_uuid_list = [edit_rp.vm_uuid_list]
            for current_uuid in edit_rp.vm_uuid_list:
                self.validate_uuid(current_uuid)
            self.configuration_vm(
                rp_main_path,
                edit_rp.vm_uuid_list,
                edit_rp.save_current_vms,
                edit_rp.vm_reservation_list,
            )
            self.logger.info(
                f"ВМ конфигурация ресурс пула '{edit_rp.cpu_core_limit}' успешно изменена"
            )

        if edit_rp.storage_limit is not None:
            self.logger.info(
                f"Изменение STORAGE конфигурации ресурс пула: '{edit_rp.storage_limit}'"
            )
            edit_logic_volume = self.logic_volume_manager.edit_volume(
                rp_main_path.name,
                self.system_volume_group_name,
                edit_rp.storage_limit,
                edit_rp.volume_size_type,
            )
            if (
                f"Logical volume {self.system_volume_group_name}/{edit_rp.name} successfully resized"
                not in edit_logic_volume
            ):
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.edit_logic_volume_error.value,
                    code=CommandMessagesEnum.edit_logic_volume_error.name,
                    success=True,
                )
            create_cpu_config = self.configuration_storage(
                rp_main_path,
                edit_rp.volume_size_type,
                edit_rp.storage_limit,
                storage_type=edit_rp.storage_type,
            )
            if create_cpu_config is not True:
                return create_cpu_config
            self.logger.info(
                f"STORAGE конфигурация ресурс пула '{edit_rp.storage_limit}' успешно изменена"
            )

        if edit_rp.cpu_core_limit is not None:
            self.logger.info(
                f"Изменение CPU конфигурации ресурс пула: '{edit_rp.cpu_core_limit}'"
            )
            create_cpu_config = self.configuration_cpu(
                rp_main_path, edit_rp.cpu_core_limit
            )
            if create_cpu_config is not True:
                return create_cpu_config
            self.logger.info(
                f"CPU конфигурация ресурс пула '{edit_rp.cpu_core_limit}' успешно изменена"
            )

        if edit_rp.ram_limit is not None:
            self.logger.info(
                f"Изменение RAM конфигурации ресурс пула: '{edit_rp.cpu_core_limit}'"
            )
            create_ram_config = self.configuration_ram(rp_main_path, edit_rp.ram_limit)
            if create_ram_config is not True:
                return create_ram_config
            self.logger.info(
                f"RAM конфигурация ресурс пула '{edit_rp.ram_limit}' успешно изменена"
            )

        self.logger.warning(f"Виртуальный ресурс пул '{edit_rp.name}' успешно изменен")

        self.sync_resource_pool(edit_rp.name)

        return RpMessage(
            request_id=internal_request_id,
            message=CommandMessagesEnum.rp_virtual_edit_success.value,
            code=CommandMessagesEnum.rp_virtual_edit_success.name,
            success=True,
        )

    def delete_virtual_resource_pool(self, name: str, force: bool = False):
        self.logger.info(f"Удаление ресурс пула: '{name}'")
        rp_main_path = Path(self.virtual_rp_manager_path) / name
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        if not rp_main_path.exists():
            self.logger.warning(f"Виртуальный ресурс пул '{name}' не найден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_virtual_not_found.value,
                code=CommandMessagesEnum.rp_virtual_not_found.name,
                success=False,
            )

        current_virtual_rp = self.get_virtual_resource_pool_by_name(name).rp_info
        if current_virtual_rp.vm_uuid_list is not None and not force:
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_virtual_have_vm_need_use_force_for_delete.value,
                code=CommandMessagesEnum.rp_virtual_have_vm_need_use_force_for_delete.name,
                success=False,
            )

        self.logic_volume_manager.delete_logical_volume(
            name, self.system_volume_group_name
        )
        current_logic_volume = self.logic_volume_manager.get_volume_by_name(
            name, self.system_volume_group_name
        )
        if current_logic_volume is not None:
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.delete_logic_volume_error.value,
                code=CommandMessagesEnum.delete_logic_volume_error.name,
                success=False,
            )
        shutil.rmtree(rp_main_path)
        if rp_main_path.exists():
            self.logger.warning(f"Виртуальный ресурс пул '{name}' не удален")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_virtual_delete_error.value,
                code=CommandMessagesEnum.rp_virtual_delete_error.name,
                success=False,
            )
        self.logger.info(f"Виртуальный ресурс пул '{name}' удален")
        return RpMessage(
            request_id=internal_request_id,
            message=CommandMessagesEnum.rp_virtual_delete_success.value,
            code=CommandMessagesEnum.rp_virtual_delete_success.name,
            success=True,
        )

    def sync_resource_pools(self):
        self.logger.info("Синхронизация ресурс пулов")
        rp_main_path = Path(self.virtual_rp_manager_path)
        all_rp_virtual_dirs = [
            str(current_dir.name)
            for current_dir in rp_main_path.iterdir()
            if current_dir.is_dir()
        ]
        for current_virtual_rp_name in all_rp_virtual_dirs:
            ram_config = rp_main_path / current_virtual_rp_name / "ram_info.json"
            cpu_config = rp_main_path / current_virtual_rp_name / "cpu_info.json"
            if not cpu_config.is_file() or not ram_config.is_file():
                continue
            self.sync_resource_pool(current_virtual_rp_name)
        self.logger.info("Синхронизация ресурс пулов выполнена")

    def sync_resource_pool(self, name: str):
        self.logger.info(f"Синхронизация ресурс пула '{name}'")
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        rp_virtual_info = self.get_virtual_resource_pool_by_name(name)
        rp_virtual_info = rp_virtual_info.rp_info
        cpu_core_used = 0
        ram_used = 0
        storage_used = 0
        if rp_virtual_info.vm_uuid_list:
            for current_uuid in rp_virtual_info.vm_uuid_list:
                try:
                    domain = self.vm_manager.conn.lookupByUUIDString(current_uuid)
                    current_vm = self.vm_manager.get_vm_info(domain)

                    cpu_core_used += current_vm.vcpus
                    ram_used += current_vm.max_memory_bytes
                    storage_used += self.storage_manager.get_storage_used(
                        current_vm.name, internal_request_id
                    )
                except Exception:
                    pass
        rp_main_path = Path(self.virtual_rp_manager_path) / name
        storage_config = rp_main_path / "storage_info.json"
        ram_config = rp_main_path / "ram_info.json"
        cpu_config = rp_main_path / "cpu_info.json"

        with open(storage_config, "r") as storage_info_file_read:
            storage_info = orjson.loads(storage_info_file_read.read())

        with open(storage_config, "wb") as storage_info_file:
            storage_info["storage_allocated"] = storage_used
            current_storage_available = storage_info["storage_limit"] - storage_used
            if rp_virtual_info.vm_reservation_list is not None:
                for current_rr_vm in rp_virtual_info.vm_reservation_list:
                    current_storage_available = (
                        current_storage_available - current_rr_vm.storage
                    )
            storage_info["storage_available"] = current_storage_available
            storage_info_file.write(orjson.dumps(storage_info))

        with open(ram_config, "r") as ram_info_file_read:
            ram_info = orjson.loads(ram_info_file_read.read())

        with open(ram_config, "wb") as ram_info_file:
            ram_info["ram_allocated"] = ram_used
            current_ram_available = ram_info["ram_limit"] - ram_used
            if rp_virtual_info.vm_reservation_list is not None:
                for current_rr_vm in rp_virtual_info.vm_reservation_list:
                    current_ram_available = current_ram_available - current_rr_vm.ram
            ram_info["ram_available"] = current_ram_available
            ram_info_file.write(orjson.dumps(ram_info))

        with open(cpu_config, "r") as cpu_info_file_read:
            cpu_info = orjson.loads(cpu_info_file_read.read())

        with open(cpu_config, "wb") as cpu_info_file:
            cpu_info["cpu_core_allocated"] = cpu_core_used
            current_cpu_core_available = cpu_info["cpu_core_limit"] - cpu_core_used
            if rp_virtual_info.vm_reservation_list is not None:
                for current_rr_vm in rp_virtual_info.vm_reservation_list:
                    current_cpu_core_available = (
                        current_cpu_core_available - current_rr_vm.cpu_core_count
                    )
            cpu_info["cpu_core_available"] = current_cpu_core_available
            cpu_info_file.write(orjson.dumps(cpu_info))
        self.logger.info(f"Синхронизация ресурс пула '{name}' завершена")

    def get_virtual_resource_pool_by_name(self, name: str | Path) -> RpMessage:
        if isinstance(name, str):
            rp_main_path = Path(self.virtual_rp_manager_path) / name
        elif isinstance(name, Path):
            rp_main_path = name
        else:
            raise ValueError(f"Неизвестный тип данных: '{type(name)}'")
        vm_uuid_list = None
        vm_reservation_list = []
        vm_reservation_list_data = None
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        if not rp_main_path.exists():
            self.logger.warning(f"Виртуальный ресурс пул '{rp_main_path}' не найден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )

        storage_config = rp_main_path / "storage_info.json"
        if not storage_config.exists():
            self.logger.warning(
                f"STORAGE конфигурация ресурс пула '{rp_main_path}' не найдена"
            )
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_storage_configuration_file_not_found.value,
                code=CommandMessagesEnum.rp_storage_configuration_file_not_found.name,
                success=False,
            )
        with open(storage_config, "r") as storage_info_file:
            storage_info = orjson.loads(storage_info_file.read())

        cpu_config = rp_main_path / "cpu_info.json"
        if not cpu_config.exists():
            self.logger.warning(
                f"CPU конфигурация ресурс пула '{rp_main_path}' не найдена"
            )
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_cpu_configuration_not_found.value,
                code=CommandMessagesEnum.rp_cpu_configuration_not_found.name,
                success=False,
            )
        with open(cpu_config, "r") as cpu_info_file:
            cpu_info = orjson.loads(cpu_info_file.read())

        ram_config = rp_main_path / "ram_info.json"
        if not ram_config.exists():
            self.logger.warning(
                f"RAM конфигурация ресурс пула '{rp_main_path}' не найдена"
            )
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_ram_configuration_not_found.value,
                code=CommandMessagesEnum.rp_ram_configuration_not_found.name,
                success=False,
            )
        with open(ram_config, "r") as ram_info_file:
            ram_info = orjson.loads(ram_info_file.read())

        vm_config = rp_main_path / "vm_info.json"
        if vm_config.exists():
            with open(vm_config, "r") as vm_info_file:
                file_data = orjson.loads(vm_info_file.read())
                vm_uuid_list = file_data.get("vm_uuid_list")
                vm_reservation_list_data = file_data.get("vm_reservation_list")

        if vm_reservation_list_data:
            for current_rr_vm in vm_reservation_list_data:
                vm_reservation_list.append(
                    ResourceReservationVM(
                        cpu_core_count=current_rr_vm.get("cpu_core_count"),
                        ram=current_rr_vm.get("ram"),
                        vm_uuid=current_rr_vm.get("vm_uuid"),
                    )
                )

        rp_virtual = ResourcePoolVirtual(
            name=name,
            cpu_core_limit=cpu_info.get("cpu_core_limit"),
            cpu_core_allocated=cpu_info.get("cpu_core_allocated"),
            cpu_core_available=cpu_info.get("cpu_core_available"),
            ram_limit=ram_info.get("ram_limit"),
            ram_allocated=ram_info.get("ram_allocated"),
            ram_available=ram_info.get("ram_available"),
            vm_uuid_list=vm_uuid_list,
            vm_reservation_list=vm_reservation_list if vm_reservation_list else None,
            storage_type=storage_info.get("storage_type"),
            storage_limit=storage_info.get("storage_limit"),
            storage_allocated=storage_info.get("storage_allocated"),
            storage_available=storage_info.get("storage_available"),
            group_volume=storage_info.get("group_volume"),
            logical_volume=storage_info.get("logical_volume"),
        )
        return RpMessage(
            request_id=internal_request_id,
            message=CommandMessagesEnum.rp_virtual_successfully_found.value,
            code=CommandMessagesEnum.rp_virtual_successfully_found.name,
            success=True,
            rp_info=rp_virtual,
        )

    def get_virtual_resource_pool_list(self) -> list[ResourcePoolVirtual]:
        rp_main_path = Path(self.virtual_rp_manager_path)
        self.logger.info("Получение списка ресурс пулов")
        all_rp_virtual_dirs = [
            str(current_dir.name)
            for current_dir in rp_main_path.iterdir()
            if current_dir.is_dir()
        ]
        all_rp_virtal = []
        for virtual_rp_name in all_rp_virtual_dirs:
            storage_config = rp_main_path / virtual_rp_name / "storage_info.json"
            ram_config = rp_main_path / virtual_rp_name / "ram_info.json"
            cpu_config = rp_main_path / virtual_rp_name / "cpu_info.json"
            print("storage_config.is_file(): ", storage_config.is_file())
            if (
                not cpu_config.is_file()
                or not ram_config.is_file()
                or not storage_config.is_file()
            ):
                continue
            all_rp_virtal.append(
                self.get_virtual_resource_pool_by_name(virtual_rp_name).rp_info
            )
        self.logger.info("Список ресурс пулов успешно получен")
        return all_rp_virtal


if __name__ == "__main__":
    mng = Balansir()
    # TODO: Изучить системные вызовы чтобы добавить системные ограничения для нашего виртуального менеджера
    # TODO: Изучить вопрос чтения данных из памяти, а при внесении изменений - обновлять данные в файлах и памяти
    a = datetime.datetime.now()
    # print(a)
    # data = mng.create_virtual_resource_pool(
    #     create_rp=ResourcePoolVirtualCreate(
    #         name="MAIN_RP3",
    #         cpu_core_limit=2,
    #         ram_limit=536_870_912,
    #         vm_uuid_list=["94df5b49-2da4-44d6-8fe1-9f910b775402"],
    #     )
    # )
    # print(data)
    # mng.sync_resource_pools()
    # # print(mng.delete_virtual_resource_pool("RP-TEST-12033"))
    # rp_virtual = mng.get_virtual_resource_pool_by_name("MAIN_RP")
    # rp_virtual = rp_virtual.rp_info
    # print(mng.get_virtual_resource_pool_list())
    #
    # for rp_virtual in mng.get_virtual_resource_pool_list():
    #     print("ИМЯ РЕСУРС ПУЛА: ", rp_virtual.name)
    #     print("cpu_core_limit: ", rp_virtual.cpu_core_limit)
    #     print("cpu_core_allocated: ", rp_virtual.cpu_core_allocated)
    #     print("cpu_core_available: ", rp_virtual.cpu_core_available)
    #     print("ram_limit: ", rp_virtual.ram_limit)
    #     print("ram_allocated: ", rp_virtual.ram_allocated)
    #     print("ram_available: ", rp_virtual.ram_available)
    #     print("vm_uuid_list: ", rp_virtual.vm_uuid_list)
    #     print("СТАТИСТИКА ИСПОЛЬЗОВАНИЯ CPU: ", rp_virtual.usage_info.cpu_percent)

    for _ in range(10):
        rp_virtual = mng.get_virtual_resource_pool_by_name("MAIN_RP3")
        rp_virtual = rp_virtual.rp_info
        print("СТАТИСТИКА ИСПОЛЬЗОВАНИЯ CPU: ", rp_virtual.usage_info.cpu_percent)
    b = datetime.datetime.now()
    print(b)
    print(b - a)
