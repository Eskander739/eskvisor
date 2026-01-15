import datetime
import os
import uuid

from dotenv import load_dotenv

from agent.client.cli import CLIControl
from agent.client.constants import INVALID_LINUX_CHAR
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.pycgroup.pycgroup import PYCGroup
from agent.client.hypervisor.volumes.logical import (
    LogicalVolumeManager,
)
from agent.client.hypervisor.volumes.physical import (
    PhysicalVolumeManager,
)
from agent.client.hypervisor.volumes.group import (
    VolumeGroupManager,
)
from agent.client.hypervisor.libvirt.managers.storage import StorageManager
from agent.client.hypervisor.libvirt.managers.vm import VmManager
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
        self.pycgroup = PYCGroup()
        self.vm_manager = VmManager()
        self.vm_manager.connect()
        self.node_info = self.vm_manager.get_node_info()

        self.logger.info(f"Виртуальный менеджер ресурс пулов инициализирован")

    @staticmethod
    def validate_name(vm_name: str):
        for invalid_linux_char in INVALID_LINUX_CHAR:
            if invalid_linux_char in vm_name:
                raise ValueError(
                    f"Запрещенный символ: '{invalid_linux_char}' в NAME: '{vm_name}'"
                )

    def validate_vm_list(
            self,
            current_rp: ResourcePoolVirtualCreate | ResourcePoolVirtualEdit,
            create_config: bool = False,
    ) -> RpMessage:
        self.logger.info(f"Старт валидации списка ВМ")
        internal_request_id = f"internal_{str(uuid.uuid4())}"

        if create_config:
            resource_pool_config = current_rp
        else:
            pool_data = self.get_virtual_resource_pool_by_name(current_rp.name)
            if not pool_data.success:
                return pool_data
            resource_pool_config = pool_data.rp_info

        if isinstance(current_rp.vms, list):
            for vm_name in current_rp.vms:

                try:
                    for current_name in current_rp.vms:
                        self.validate_name(current_name)
                    self.logger.info(f"Поиск ВМ {vm_name}")
                    virtual_machine = self.vm_manager.conn.lookupByName(vm_name)
                    current_vm_info = self.vm_manager.get_vm_info(virtual_machine)
                    if (
                            current_vm_info.memory_bytes
                            > resource_pool_config.ram_limit_bytes
                    ):
                        err_text = (
                            f"Объем оперативной памяти ВМ: '{current_vm_info.memory_bytes}' "
                            f"больше чем у создаваемого пула: '{resource_pool_config.ram_limit_bytes}'"
                        )
                        self.logger.info(err_text)
                        return RpMessage(
                            request_id=internal_request_id,
                            message=CommandMessagesEnum.rp_create_error.value,
                            code=CommandMessagesEnum.rp_create_error.name,
                            success=False,
                            note=err_text,
                        )
                    if current_vm_info.vcpus > resource_pool_config.cpu_core_limit:
                        err_text = (
                            f"Количество ядер ВМ: '{current_vm_info.vcpus}' "
                            f"больше чем у создаваемого пула: '{resource_pool_config.cpu_core_limit}'"
                        )
                        self.logger.info(err_text)
                        return RpMessage(
                            request_id=internal_request_id,
                            message=CommandMessagesEnum.rp_create_error.value,
                            code=CommandMessagesEnum.rp_create_error.name,
                            success=False,
                            note=err_text,
                        )
                except Exception as e:
                    self.logger.info(f"ВМ {vm_name} не найдена")
                    return RpMessage(
                        request_id=internal_request_id,
                        message=CommandMessagesEnum.vm_found_error.value,
                        code=CommandMessagesEnum.vm_found_error.name,
                        success=False,
                        note=str(e),
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
                f"Некорректный тип данных: '{type(current_rp.vms)}'"
            )

    def validate_resource_reservation(
            self,
            name: str,
            vm_reservation_list: list[ResourceReservationVM],
            vms: list[str],
    ):
        internal_request_id = str(uuid.uuid4())
        current_virtual_resource_pool = self.get_virtual_resource_pool_by_name(name)
        if not current_virtual_resource_pool.success:
            return current_virtual_resource_pool

        virtual_machines = {}
        for current_name in vms:
            domain = self.vm_manager.conn.lookupByUUIDString(current_name)
            try:
                current_vm = self.vm_manager.get_vm_info(domain)
                virtual_machines[current_name] = current_vm
            except Exception:
                pass
        virtual_rp_info = current_virtual_resource_pool.rp_info
        for current_resource_reservation_vm in vm_reservation_list:
            current_vm = virtual_machines[current_resource_reservation_vm.name]
            if not isinstance(current_resource_reservation_vm, ResourceReservationVM):
                raise ValueError(
                    f"Неизвестный тип данных: '{type(current_resource_reservation_vm)}'"
                )
            if current_resource_reservation_vm.name not in vms:
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
                    note=f"VM: {current_resource_reservation_vm.name}, "
                         f"CPU COUNT RESERVE: {current_resource_reservation_vm.cpu_core_count},"
                         f"AVAILABLE CPU COUNT: {virtual_rp_info.cpu_core_limit}",
                )
            if current_resource_reservation_vm.ram > virtual_rp_info.ram_limit_bytes:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.vm_can_not_reserve_more_ram_than_available_on_the_virtual_rp.value,
                    code=CommandMessagesEnum.vm_can_not_reserve_more_ram_than_available_on_the_virtual_rp.name,
                    success=False,
                    note=f"VM: {current_resource_reservation_vm.name}, "
                         f"RAM RESERVE: {current_resource_reservation_vm.ram},"
                         f"AVAILABLE RAM: {virtual_rp_info.ram_limit_bytes}",
                )

            if current_vm.memory_bytes > current_resource_reservation_vm.ram:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.vm_can_not_reserve_less_ram_than_use.value,
                    code=CommandMessagesEnum.vm_can_not_reserve_less_ram_than_use.name,
                    success=False,
                    note=f"VM: {current_resource_reservation_vm.name}, "
                         f"RAM RESERVE: {current_resource_reservation_vm.ram},"
                         f"CURRENT USE RAM: {current_vm.memory_bytes}",
                )
            if current_vm.vcpus > current_resource_reservation_vm.cpu_core_count:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.vm_can_not_reserve_less_cpu_than_use.value,
                    code=CommandMessagesEnum.vm_can_not_reserve_less_cpu_than_use.name,
                    success=False,
                    note=f"VM: {current_resource_reservation_vm.name}, "
                         f"CPU RESERVE: {current_resource_reservation_vm.cpu_core_count},"
                         f"CURRENT USE CPU: {current_vm.vcpus}",
                )
        else:
            return True

    def configuration_cpu(
            self,
            rp_name: str,
            cpu_core_limit: int,
            cpu_weight: int | None,
    ) -> RpMessage | bool:
        self.logger.info(f"Старт конфигурации CPU")
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        try:
            self.pycgroup.edit_cgroup_pool(
                name=rp_name,
                cpu_core_limit=cpu_core_limit, cpu_weight=cpu_weight
            )

            self.logger.info(f"Конфигурация CPU для пула '{rp_name}' успешно применена")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка конфигурации CPU: {e}")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_cpu_configuration_error.value,
                code=CommandMessagesEnum.rp_cpu_configuration_error.name,
                success=False,
                note=str(e)
            )

    def configuration_storage(
            self,
            rp_name: str,
            volume_size_type: LogicalVolumeSizeType,
            storage_limit: int | float = 0,
            create_config: bool = False,
            storage_type: StoragePoolType = StoragePoolType.LOGICAL,
    ) -> RpMessage | bool:
        self.logger.info(f"Старт конфигурации STORAGE")
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        if create_config:
            if storage_type == StoragePoolType.LOGICAL:
                result_create_lv = self.logic_volume_manager.create_volume(
                    logic_volume_name=rp_name,
                    logic_volume_size=storage_limit,
                    volume_group_name=self.system_volume_group_name,
                    logic_volume_size_type=volume_size_type,
                )
                if (
                        f'Logical volume "{rp_name}" created'
                        not in result_create_lv
                ):
                    self.logger.error(
                        f"Не удалось создать LVM пул {rp_name} в VG {self.system_volume_group_name}: {result_create_lv}"
                    )
                    return RpMessage(
                        request_id=internal_request_id,
                        message=CommandMessagesEnum.virtual_rp_create_logic_volume_error.value,
                        code=CommandMessagesEnum.virtual_rp_create_logic_volume_error.name,
                        success=False,
                    )
            else:
                raise ValueError("Отсутствует поддержка других типов")

        self.logger.info(f"Конфигурация STORAGE для пула '{rp_name}' успешно применена")
        return True

    def configuration_ram(
            self,
            rp_name: str,
            ram_limit: int | float,
            ram_reservation: int | float,
    ) -> RpMessage | bool:
        self.logger.info(f"Старт конфигурации RAM")
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        try:
            # Преобразование байт в килобайты для cgroup
            ram_limit_kb = ram_limit // 1024
            ram_reservation_kb = ram_reservation // 1024
            self.pycgroup.edit_cgroup_pool(
                name=rp_name,
                max_memory=ram_limit_kb,
                memory_reservation=ram_reservation_kb
            )
            self.logger.info(f"Конфигурация RAM для пула '{rp_name}': {ram_limit} успешно применена")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка конфигурации RAM: {e}")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_ram_configuration_error.value,
                code=CommandMessagesEnum.rp_ram_configuration_error.name,
                success=False,
                note=str(e)
            )

    def read_vm_on_any_virtual_resource_pools(self, vm_name: str):
        """
        Проверка наличия ВМ в других ресурс пулах
        """
        all_virtual_rp_list = self.get_virtual_resource_pool_list()
        for virtual_rp in all_virtual_rp_list:
            if virtual_rp.vms is not None:
                if vm_name in virtual_rp.vms:
                    return True
        return False

    def configuration_vm(
            self,
            rp_name: str,
            vms: str | list[str],
            vm_reservation_list: list[ResourceReservationVM] | None = None,
    ) -> RpMessage | bool:
        internal_request_id = f"internal_{str(uuid.uuid4())}"
        try:
            if isinstance(vms, str):
                vms = [vms]
            self.logger.info(f"Старт конфигурации ВМ")

            # Проверка существования пула через cgroup
            try:
                self.pycgroup.get_cgroup_pool(rp_name)
            except Exception:
                return RpMessage(
                    request_id=internal_request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                )

            self.logger.info(
                f"Проверка отсутствия ВМ в других ресурс пулах"
            )
            if vms:
                for current_name in vms:
                    vm_on_any_rp = self.read_vm_on_any_virtual_resource_pools(current_name)
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
                    rp_name, vm_reservation_list, vms
                )
                if validate_vm_reservation_list is not True:
                    return validate_vm_reservation_list

            self.pycgroup.add_vms_to_pool(rp_name, vms)
            self.logger.info(f"Конфигурация ВМ для пула '{rp_name}' успешно применена")
            return True

        except Exception as e:
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_create_error.value,
                code=CommandMessagesEnum.rp_create_error.name,
                success=False,
                note=str(e),
            )

    def delete_vm_from_virtual_resource_pool(self, name: str, vn_name: str):
        self.logger.info(f"Старт удаления ВМ из ресурс пула")
        internal_request_id = f"internal_{str(uuid.uuid4())}"

        # Проверка существования пула через cgroup
        try:
            self.pycgroup.get_cgroup_pool(name)
        except Exception:
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )
        self.pycgroup.delete_vm_from_pool(name, vn_name)
        self.logger.info(f"ВМ '{name}' из ресурс пула успешно удалена")
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

        all_pools = self.get_virtual_resource_pool_list()
        for pool in all_pools:
            if pool.ram_limit_bytes == "max" or pool.cpu_core_limit == "max":
                raise ValueError("Запрещен контекст ресурс пула с безграничными ресурсами")
            ram_allocated += pool.ram_limit_bytes
            cpu_allocated += pool.cpu_core_limit

        self.logger.info(
            f"Определен общий объем используемых ресурсов ресурс пулами - "
            f"CPU ядер: '{cpu_allocated}', "
            f"RAM памяти: '{ram_allocated}' байт"
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
        internal_request_id = f"internal_{str(uuid.uuid4())}"

        if isinstance(create_rp.ram_limit_bytes, float):
            raise ValueError("Байты не могут быть числом с плавающей точкой")

        if not self.validate_max_ram_and_max_cpu(
                create_rp.ram_limit_bytes, create_rp.cpu_core_limit
        ):
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_ram_or_cpu_more_than_on_node.value,
                code=CommandMessagesEnum.rp_ram_or_cpu_more_than_on_node.name,
                success=False,
            )

        # Проверка существования cgroup
        try:
            self.pycgroup.get_cgroup_pool(create_rp.name)
            self.logger.warning(
                f"Виртуальный ресурс пул '{create_rp.name}' уже существует"
            )
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_already_created.value,
                code=CommandMessagesEnum.rp_already_created.name,
                success=False,
            )
        except Exception:
            # Пул не существует, продолжаем создание
            pass

        try:
            if create_rp.vms is not None:
                for current_uuid in create_rp.vms:
                    vm_on_any_rp = self.read_vm_on_any_virtual_resource_pools(current_uuid)
                    if vm_on_any_rp:
                        return RpMessage(
                            request_id=internal_request_id,
                            message=CommandMessagesEnum.vm_present_on_any_virtual_resource_pool.value,
                            code=CommandMessagesEnum.vm_present_on_any_virtual_resource_pool.name,
                            success=False,
                        )
                validate_vm_list_info = self.validate_vm_list(create_rp, True)
                if (
                        validate_vm_list_info.message
                        != CommandMessagesEnum.vm_list_is_correct.value
                ):
                    return validate_vm_list_info

            self.pycgroup.create_cgroup_pool(create_rp.name)

            create_storage_config = self.configuration_storage(
                create_rp.name,
                create_rp.volume_size_type,
                create_rp.storage_limit,
                storage_type=create_rp.storage_type,
                create_config=True,
            )
            if create_storage_config is not True:
                return create_storage_config
            self.logger.info(f"STORAGE конфигурация ресурс пула успешно установлена")

            create_cpu_config = self.configuration_cpu(
                create_rp.name, create_rp.cpu_core_limit, create_rp.cpu_weight
            )
            if create_cpu_config is not True:
                return create_cpu_config
            self.logger.info(f"CPU конфигурация ресурс пула успешно установлена")

            create_ram_config = self.configuration_ram(
                create_rp.name, create_rp.ram_limit_bytes, create_rp.ram_reservation_bytes
            )
            if create_ram_config is not True:
                return create_ram_config
            self.logger.info(f"RAM конфигурация ресурс пула успешно установлена")

            self.logger.warning(f"Виртуальный ресурс пул '{create_rp.name}' успешно создан")

            self.configuration_vm(create_rp.name, create_rp.vms)
            self.logger.info(
                f"ВМ конфигурация ресурс пула '{create_rp.cpu_core_limit}' успешно установлена"
            )


            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.virtual_rp_create_success.value,
                code=CommandMessagesEnum.virtual_rp_create_success.name,
                success=True,
            )
        except Exception as e:
            self.pycgroup.delete_cgroup_pool(create_rp.name, force=True)
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_create_error.value,
                code=CommandMessagesEnum.rp_create_error.name,
                success=False,
                note=str(e)
            )

    def edit_virtual_resource_pool(self, edit_rp: ResourcePoolVirtualEdit) -> RpMessage:
        self.logger.info(f"Редактирование виртуального ресурс пула: '{edit_rp.name}'")
        internal_request_id = f"internal_{str(uuid.uuid4())}"

        if edit_rp.ram_limit_gb is not None:
            if isinstance(edit_rp.ram_limit_bytes, float):
                raise ValueError("Байты не могут быть числом с плавающей точкой")

        # Проверка существования пула через cgroup
        try:
            self.pycgroup.get_cgroup_pool(edit_rp.name)
        except Exception:
            self.logger.warning(f"Виртуальный ресурс пул '{edit_rp.name}' не найден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )

        current_virtual_rp = self.get_virtual_resource_pool_by_name(edit_rp.name)
        if not current_virtual_rp.success:
            return current_virtual_rp

        current_virtual_rp = current_virtual_rp.rp_info
        if not self.validate_max_ram_and_max_cpu(
                current_virtual_rp.ram_limit_bytes, current_virtual_rp.cpu_core_limit
        ):
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_ram_or_cpu_more_than_on_node.value,
                code=CommandMessagesEnum.rp_ram_or_cpu_more_than_on_node.name,
                success=False,
            )

        if edit_rp.vms is not None:
            if isinstance(edit_rp.vms, str):
                edit_rp.vms = [edit_rp.vms]
            for current_name in edit_rp.vms:
                self.validate_name(current_name)
            validate_vm_list_info = self.validate_vm_list(edit_rp)
            if (
                    validate_vm_list_info.message
                    != CommandMessagesEnum.vm_list_is_correct.value
            ):
                return validate_vm_list_info
            self.configuration_vm(
                edit_rp.name,
                edit_rp.vms,
            )
            self.logger.info(
                f"ВМ конфигурация ресурс пула '{edit_rp.cpu_core_limit}' успешно изменена"
            )

        if edit_rp.storage_limit is not None:
            self.logger.info(
                f"Изменение STORAGE конфигурации ресурс пула: '{edit_rp.storage_limit}'"
            )
            edit_logic_volume = self.logic_volume_manager.edit_volume(
                edit_rp.name,
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
                edit_rp.name,
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
                edit_rp.name, edit_rp.cpu_core_limit, edit_rp.cpu_weight
            )
            if create_cpu_config is not True:
                return create_cpu_config
            self.logger.info(
                f"CPU конфигурация ресурс пула '{edit_rp.cpu_core_limit}' успешно изменена"
            )

        if edit_rp.ram_limit_bytes is not None:
            self.logger.info(
                f"Изменение RAM конфигурации ресурс пула: '{edit_rp.cpu_core_limit}'"
            )
            create_ram_config = self.configuration_ram(
                edit_rp.name, edit_rp.ram_limit_bytes
            )
            if create_ram_config is not True:
                return create_ram_config
            self.logger.info(
                f"RAM конфигурация ресурс пула '{edit_rp.ram_limit_bytes}' успешно изменена"
            )

        self.logger.warning(f"Виртуальный ресурс пул '{edit_rp.name}' успешно изменен")

        return RpMessage(
            request_id=internal_request_id,
            message=CommandMessagesEnum.rp_virtual_edit_success.value,
            code=CommandMessagesEnum.rp_virtual_edit_success.name,
            success=True,
        )

    def delete_virtual_resource_pool(self, name: str, force: bool = False):
        self.logger.info(f"Удаление ресурс пула: '{name}'")
        internal_request_id = f"internal_{str(uuid.uuid4())}"

        # Проверка существования пула через cgroup
        try:
            self.pycgroup.get_cgroup_pool(name)
        except Exception:
            self.logger.warning(f"Виртуальный ресурс пул '{name}' не найден")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_virtual_not_found.value,
                code=CommandMessagesEnum.rp_virtual_not_found.name,
                success=False,
            )

        current_virtual_rp = self.get_virtual_resource_pool_by_name(name)
        if not current_virtual_rp.success:
            return current_virtual_rp

        current_virtual_rp = current_virtual_rp.rp_info
        if current_virtual_rp.vms is not None and not force:
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

        # Удаление cgroup
        try:
            self.pycgroup.delete_cgroup_pool(name, force)
        except Exception as e:
            self.logger.warning(f"Ошибка удаления cgroup: {e}")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_virtual_delete_error.value,
                code=CommandMessagesEnum.rp_virtual_delete_error.name,
                success=False,
                note=str(e)
            )
        self.logger.info(f"Виртуальный ресурс пул '{name}' удален")
        return RpMessage(
            request_id=internal_request_id,
            message=CommandMessagesEnum.rp_virtual_delete_success.value,
            code=CommandMessagesEnum.rp_virtual_delete_success.name,
            success=True,
        )

    def get_virtual_resource_pool_by_name(self, name: str) -> RpMessage:
        internal_request_id = f"internal_{str(uuid.uuid4())}"

        # Получение информации из cgroup
        try:
            cgroup_info = self.pycgroup.get_cgroup_pool(name)
        except Exception as e:
            self.logger.warning(f"Виртуальный ресурс пул '{name}' не найден в cgroup: {e}")
            return RpMessage(
                request_id=internal_request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )

        vms = self.pycgroup.pid_ctl.get_vm_names_resource_pool(cgroup_info.get("path"))
        vm_reservation_list = None

        storage_info = self.logic_volume_manager.get_volume_by_name(name, self.system_volume_group_name)
        cpu = cgroup_info.get("cpu")
        ram = cgroup_info.get("ram")
        cpu_limit = cpu[0]
        cpu_allocated = cpu[2]
        cpu_available = cpu[3]
        cpu_weight = cpu[4]

        ram_limit = ram[0] if ram[0] != "max" else 0
        ram_allocated = ram[2]
        ram_available =  ram[1]
        ram_reservation = ram[3]

        storage_allocated = storage_info.volume_size - storage_info.available_volume_size
        current_rp_virtual = ResourcePoolVirtual(
            name=name,
            cpu_core_limit=cpu_limit,
            cpu_core_allocated=cpu_allocated,
            cpu_core_available=cpu_available,
            cpu_weight=cpu_weight,
            ram_limit_bytes=ram_limit,
            ram_allocated=ram_allocated,
            ram_available=ram_available,
            ram_reservation_bytes=ram_reservation,
            vms=list(vms) if vms else None,
            vm_reservation_list=vm_reservation_list,
            storage_type=StoragePoolType.LOGICAL,
            storage_limit=storage_info.volume_size,
            storage_allocated=storage_allocated,
            storage_available=storage_info.available_volume_size,
            group_volume=self.system_volume_group_name,
            logical_volume=name,
        )
        return RpMessage(
            request_id=internal_request_id,
            message=CommandMessagesEnum.rp_virtual_successfully_found.value,
            code=CommandMessagesEnum.rp_virtual_successfully_found.name,
            success=True,
            rp_info=current_rp_virtual,
        )

    def get_virtual_resource_pool_list(self, name: str | None = None,
                                       cpu_core_limit: int | float | None = None,
                                       ram_limit_bytes: int | None = None,
                                       storage_type: StoragePoolType | None = None,
                                       ) -> list[ResourcePoolVirtual]:
        self.logger.info("Получение списка ресурс пулов")
        all_rp_virtal = []

        try:
            pool_names = self.pycgroup.get_cgroup_pool_names
            if name:
                pool_names = [current_name for current_name in pool_names if name in current_name]
            if pool_names:
                for pool_name in pool_names:
                    rp_data = self.get_virtual_resource_pool_by_name(pool_name)

                    if cpu_core_limit is not None or ram_limit_bytes is not None or storage_type is not None:
                        if cpu_core_limit is not None and cpu_core_limit != rp_data.cpu_core_limit:
                            continue
                        if ram_limit_bytes is not None and ram_limit_bytes != rp_data.ram_limit_bytes:
                            continue
                        if storage_type is not None and storage_type.value != rp_data.storage_type.value:
                            continue
                        all_rp_virtal.append(rp_data.rp_info)
                    else:
                        all_rp_virtal.append(rp_data.rp_info)
        except Exception as e:
            self.logger.error(f"Ошибка получения списка пулов: {e}")

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
    #         name="resource_pool_678",
    #         cpu_core_limit=3,
    #         ram_limit_gb=2,
    #         storage_limit=1,
    #         vms=["VM-TEST-83852"],
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
    #     print("vm_uuid_list: ", rp_virtual.vms)
    #     print("СТАТИСТИКА ИСПОЛЬЗОВАНИЯ CPU: ", rp_virtual.usage_info.cpu_percent)

    # for _ in range(10):
    #     rp_virtual = mng.get_virtual_resource_pool_by_name("MAIN_RP3")
    #     rp_virtual = rp_virtual.rp_info
    #     print("СТАТИСТИКА ИСПОЛЬЗОВАНИЯ CPU: ", rp_virtual.usage_info.cpu_percent)
    # b = datetime.datetime.now()
    # print(b)
    # print(b - a)
    mng.delete_vm_from_virtual_resource_pool("resource_pool_678", "VM-TEST-83852")