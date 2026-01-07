import os
import random
import re
import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

import libvirt
from dotenv import load_dotenv

from agent.client.cli import CLIControl
from agent.client.constants import LVM_SAFE_FORBIDDEN, DIR_SAFE_FORBIDDEN
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.managers.resource_pool.cgroups_manager import (
    CGroupsManager,
)
from agent.client.hypervisor.libvirt.managers.resource_pool.volume_managers.logical_volume_manager import (
    LogicalVolumeManager,
)
from agent.client.hypervisor.libvirt.managers.resource_pool.volume_managers.physical_volume_manager import (
    PhysicalVolumeManager,
)
from agent.client.hypervisor.libvirt.managers.resource_pool.volume_managers.volume_group_manager import (
    VolumeGroupManager,
)

from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum, RpMessage
from agent.client.hypervisor.libvirt.models.volume.resource_pool import (
    POOL_STATE,
    AddVMInResourcePool,
    AdjustResourcePool,
    DeleteResourcePool,
    RemoveVMInResourcePool,
    ResourcePool,
    ResourcePoolAdjustRequest,
    ResourcePoolControlRequest,
    ResourcePoolCreateRequest,
    ResourcePoolEditRequest,
    ResourcePoolInfoRequest,
    ResourcePoolLimitRequest,
    ResourcePoolList,
    ResourcePoolReservation,
    ResourcePoolReservationRequest,
    ResourcePoolState,
    ResourcePoolType,
    ResourcePoolUpdates,
    ResourcePoolUsageInfo,
    StoragePoolType,
    UsageInfo,
    VMPoolAssignmentRequest,
    UsageResourcePool,
)
from agent.client.logger_config import DefaultLogger

load_dotenv()


class PoolManager(LibvirtClient, CGroupsManager):
    """
    Управление пулом ресурсов

    Реализует управление ресурсными пулами (CPU, память, хранилище) через libvirt.
    Поддерживает создание, редактирование, удаление пулов и управление ВМ в них.
    """

    libvirtError = libvirt.libvirtError

    def __init__(self):
        super().__init__()
        # Инициализируем CGroupsManager
        CGroupsManager.__init__(self)
        self.logger = DefaultLogger("ResourcePoolManager")
        self.system_volume_group_name = os.environ.get("VOLUME_GROUP")
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
        self.cli = CLIControl()

    def check_lvm_support(self) -> bool:
        """
        Надежная проверка поддержки LVM в системе Linux.
        Работает в разных дистрибутивах.

        Returns:
            bool: True если LVM поддерживается, False в противном случае
        """
        try:
            result = self.cli.execute(["command", "-v", "lvs"])
            if result.strip():
                return True
            return False
        except Exception:
            return False

    def _extract_pool_info_from_xml(self, xml_content: str) -> dict[str, object]:
        """Извлечение информации о пуле из XML"""
        info = {
            "type": None,
            "path": None,
            "capacity": 0,
            "allocation": 0,
            "available": 0,
            "vg_name": None,
            "device_path": None,
        }

        try:
            root = ET.fromstring(xml_content)
            info["type"] = root.get("type")

            # Извлекаем путь для dir пулов
            path_elem = root.find(".//target/path")
            if path_elem is not None:
                info["path"] = path_elem.text

            # Извлекаем информацию о хранилище
            capacity_elem = root.find(".//capacity")
            if capacity_elem is not None and capacity_elem.text:
                info["capacity"] = int(capacity_elem.text)

            allocation_elem = root.find(".//allocation")
            if allocation_elem is not None and allocation_elem.text:
                info["allocation"] = int(allocation_elem.text)

            available_elem = root.find(".//available")
            if available_elem is not None and available_elem.text:
                info["available"] = int(available_elem.text)

            # Для LVM пулов извлекаем дополнительные параметры
            if info["type"] == "logical":
                name_elem = root.find(".//source/name")
                if name_elem is not None:
                    info["vg_name"] = name_elem.text

                device_elem = root.find(".//source/device")
                if device_elem is not None:
                    info["device_path"] = device_elem.get("path")

        except Exception as e:
            self.logger.debug(f"Ошибка при разборе XML пула: {e}")

        return info

    def _get_pool_vms(self, pool_name: str) -> list[str]:
        """Получение списка ВМ, связанных с пулом"""
        vms = []
        try:
            # Получаем все ВМ
            domains = self.conn.listAllDomains(0)

            for domain in domains:
                try:
                    xml_desc = domain.XMLDesc(0)

                    # Проверяем, связана ли ВМ с пулом хранилища
                    # Ищем ссылки на пул в XML ВМ
                    pool_patterns = [
                        f"pool='{pool_name}'",
                        f"<pool>{pool_name}</pool>",
                        f"<source pool='{pool_name}'",
                    ]

                    if any(pattern in xml_desc for pattern in pool_patterns):
                        vms.append(domain.name())

                except self.libvirtError:
                    continue

        except Exception as e:
            self.logger.debug(f"Ошибка при получении ВМ пула {pool_name}: {e}")

        return vms

    def _get_resource_usage_for_pool(
        self, pool_name: str, pool_vms: list[str]
    ) -> UsageResourcePool:
        """Получение информации об использовании ресурсов пулом"""
        usage = UsageResourcePool()

        try:
            # Получаем информацию о хранилище пула
            pool_info_msg = self.get_pool_info(pool_name, str(uuid.uuid4()))
            if pool_info_msg.success and pool_info_msg.rp_info:
                usage.storage = pool_info_msg.rp_info.allocation_bytes

            # Суммируем ресурсы всех ВМ в пуле
            for vm_name in pool_vms:
                try:
                    domain = self.conn.lookupByName(vm_name)
                    vm_info = domain.info()
                    usage.cpu += vm_info[3]  # Количество виртуальных CPU
                    usage.memory += vm_info[2]  # Память в KB
                except self.libvirtError:
                    continue

        except Exception as e:
            self.logger.debug(f"Ошибка при получении использования ресурсов: {e}")

        return usage

    def get_pool_xml_by_name(self, pool_name: str) -> str:
        """
        Получить XML описание пула хранилища по имени

        Args:
            pool_name: Имя пула

        Returns:
            str: XML описание пула
        """
        try:
            # Поиск пула по имени
            pool = self.conn.storagePoolLookupByName(pool_name)

            # Получение XML с флагами
            xml_desc = pool.XMLDesc(0)  # 0 - без флагов

            return xml_desc

        except libvirt.libvirtError as e:
            raise Exception(f"Ошибка libvirt: {e}")
        except Exception as e:
            raise Exception(f"Ошибка получения XML пула: {e}")

    def list_resource_pools(self, request_id: str) -> RpMessage:
        """Получение списка всех пулов ресурсов"""
        try:
            pools = self.list_storage_pools()

            # Получаем подробную информацию о каждом пуле
            pool_info_list = []
            for pool_name in pools:
                try:
                    # Получаем информацию о пуле из libvirt
                    pool_info_msg = self.get_pool_info(pool_name, request_id)
                    if not pool_info_msg.success or not pool_info_msg.rp_info:
                        continue

                    pool_info = pool_info_msg.rp_info

                    # Получаем ВМ, связанные с пулом
                    pool_vms = self._get_pool_vms(pool_name)

                    # Получаем использование ресурсов
                    usage_info = self._get_resource_usage_for_pool(pool_name, pool_vms)

                    pool_info.usage = UsageInfo(
                        cpu=usage_info.cpu,
                        memory=usage_info.memory,
                        storage=usage_info.storage,
                    )
                    pool_info.vms = pool_vms

                    pool_info_list.append(pool_info)

                except Exception as e:
                    self.logger.error(f"Ошибка обработки пула {pool_name}: {e}")
                    continue

            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_list_success.value,
                code=CommandMessagesEnum.rp_list_success.name,
                success=True,
                rp_info=ResourcePoolList(
                    items=pool_info_list, count=(len(pool_info_list))
                ),
            )
        except Exception as e:
            self.logger.error(f"Ошибка получения списка пулов ресурсов: {e}")
            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_list_error.value,
                code=CommandMessagesEnum.rp_list_error.name,
                success=False,
                note=str(e),
            )

    def create_storage_pool(self, pool_xml: str) -> bool:
        """
        Создание пула хранения из XML описания
        """
        try:
            self.logger.debug(f"Создание пула из XML: {pool_xml}")

            # Всегда используем define + create для гарантии создания
            # конфигурационного файла
            pool = self.conn.storagePoolDefineXML(pool_xml, 0)

            if not pool:
                self.logger.error("Не удалось определить пул хранения")
                return False

            try:
                # Пытаемся создать (активировать) пул
                pool.create(0)
            except self.libvirtError as e:
                self.logger.warning(f"Не удалось активировать пул, пробуем build: {e}")

                # Для некоторых пулов требуется build перед create
                try:
                    pool.build(0)
                    pool.create(0)
                except self.libvirtError as build_error:
                    self.logger.error(f"Не удалось построить пул: {build_error}")
                    # Если пул нельзя построить, просто оставляем его определенным
                    pass

            # Включаем автозапуск
            try:
                pool.setAutostart(True)
            except BaseException:
                pass  # Не критично если не удалось установить автозапуск

            self.logger.info("Пул хранения успешно создан")
            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка создания пула хранения: {e}")

            # Пробуем старый метод для обратной совместимости
            try:
                pool = self.conn.storagePoolCreateXML(pool_xml, 0)
                if pool:
                    pool.setAutostart(True)
                    self.logger.info("Пул создан через CreateXML")
                    return True
            except BaseException:
                pass

            return False
        except Exception as e:
            self.logger.error(f"Непредвиденная ошибка при создании пула: {e}")
            return False

    @staticmethod
    def is_valid_lvm_name(name: str) -> bool:
        if not name or len(name) > 128:  # LVM ограничение
            return False

        # Имена '.' и '..' недопустимы
        if name in [".", ".."]:
            return False

        # Проверка символов
        for char in LVM_SAFE_FORBIDDEN:
            if char in name:
                return False

        if not re.match(r"^[a-zA-Z0-9+_.-]+$", name):
            return False

        return True

    @staticmethod
    def is_valid_linux_path(path_str: str) -> bool:

        # 1. Проверка на пустоту
        if not path_str:
            return False

        if not isinstance(path_str, str):
            return False

        # 2. Проверка на null bytes
        if "\x00" in path_str:
            return False

        # 3. Проверка длины (системные ограничения)
        if len(path_str) > 4096:  # PATH_MAX в Linux обычно 4096
            return False

        # 4. Проверка синтаксиса через pathlib
        try:
            PurePosixPath(path_str)
        except (ValueError, RuntimeError) as e:
            return False

        # 6. Проверка специальных случаев
        # Слишком много точек подряд
        if "..." in path_str:
            return False

        return True

    def _prepare_storage_pool_xml(
        self, request: ResourcePoolCreateRequest
    ) -> tuple[str, str | None]:
        """
        Подготовка XML для создания пула хранения в зависимости от типа

        Args:
            request: Запрос на создание пула

        Returns:
            tuple: (xml_content, storage_path)
        """
        storage_path = None

        if request.storage_xml:
            self.logger.info("Создание пула из предоставленного XML")
            return request.storage_xml, storage_path

        elif request.pool_type == StoragePoolType.DIR:
            # Вариант 1: DIR пул с указанным путем
            if request.storage_path:
                if not request.storage_path.startswith("/"):
                    raise ValueError(
                        f"Некорректный формат пути: {request.storage_path}"
                    )

                if not self.is_valid_linux_path(request.storage_path):
                    raise ValueError(
                        f"Некорректное путь для {StoragePoolType.DIR.value}: '{request.name}'"
                    )
                storage_path = request.storage_path
                self.logger.info(f"Создание DIR пула с путем '{storage_path}'")
            else:
                # Вариант 2: DIR пул с автоматическим путем
                base_path = "/var/lib/libvirt/resource_pools"
                if not os.path.exists(base_path):
                    self.cli.execute(["mkdir", base_path])
                    self.cli.execute(["chmod", "-R", "777", base_path])
                storage_path = os.path.join(
                    base_path, f"rp_{request.name}_{random.randint(100_000, 999_999)}"
                )
                os.makedirs(storage_path, exist_ok=True)
                self.logger.info(
                    f"Создание DIR пула с автоматическим путем '{storage_path}'"
                )

            # Генерируем XML для DIR пула
            xml = f"""<pool type='dir'>
  <name>{request.name}</name>
  <target>
    <path>{storage_path}</path>
    <permissions>
      <mode>0711</mode>
      <owner>0</owner>
      <group>0</group>
    </permissions>
  </target>
</pool>"""

        elif request.pool_type == StoragePoolType.LOGICAL:
            # Для LVM пулов проверяем поддержку LVM
            if not self.check_lvm_support():
                raise ValueError("LVM не поддерживается в системе")

            if not self.is_valid_lvm_name(request.name):
                self.logger.error(
                    f"Некорректное имя для {StoragePoolType.LOGICAL.value}: '{request.name}'"
                )
                raise ValueError(
                    f"Некорректное имя для {StoragePoolType.LOGICAL.value}: '{request.name}'"
                )
            result = self.logic_volume_manager.create_volume(
                request.name, request.storage_limit, self.system_volume_group_name
            )
            if f'Logical volume "{request.name}" created' not in result:
                self.logger.error(
                    f"Не удалось создать LVM пул {request.name} в VG {self.system_volume_group_name}: {result}"
                )
                raise ValueError(
                    f"Не удалось создать LVM пул {request.name} в VG {self.system_volume_group_name}: {result}"
                )

            # Генерируем XML для LVM пула с новым VG
            xml = f"""<pool type='logical'>
              <name>{request.name}</name>
              <source>
                <name>{self.system_volume_group_name}</name>
                <format type='lvm2'/>
              </source>
              <target>
                <path>/dev/{self.system_volume_group_name}</path>
              </target>
            </pool>"""

        else:
            raise ValueError(
                f"Тип пула {request.pool_type} не поддерживается для автоматического создания"
            )

        return xml, storage_path

    def _find_available_devices(self) -> list[str]:
        """
        Поиск доступных устройств для создания LVM пулов

        Returns:
            list[str]: Список путей к доступным устройствам
        """
        try:
            # Получаем список блочных устройств
            result = subprocess.run(
                ["lsblk", "-d", "-n", "-o", "NAME,TYPE,SIZE"],
                capture_output=True,
                text=True,
            )

            available_devices = []
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        device_name, device_type, device_size = (
                            parts[0],
                            parts[1],
                            " ".join(parts[2:]),
                        )

                        # Ищем диски (не разделы) без файловых систем
                        if device_type == "disk":
                            device_path = f"/dev/{device_name}"

                            # Проверяем, не используется ли устройство
                            if not self._is_device_used(device_path):
                                available_devices.append(device_path)
                                self.logger.debug(
                                    f"Найдено доступное устройство: {device_path} ({device_size})"
                                )

            return available_devices

        except Exception as e:
            self.logger.error(f"Ошибка поиска доступных устройств: {e}")
            return []

    def _is_device_used(self, device_path: str) -> bool:
        """Проверяет, используется ли устройство"""
        try:
            # Проверяем, есть ли файловая система
            result = subprocess.run(
                ["blkid", device_path], capture_output=True, text=True
            )

            # Если blkid возвращает информацию, значит устройство используется
            if result.returncode == 0 and result.stdout.strip():
                return True

            # Проверяем, является ли устройство частью LVM
            result = subprocess.run(
                ["pvs", device_path, "--noheadings"], capture_output=True, text=True
            )

            if result.returncode == 0 and result.stdout.strip():
                return True

            return False

        except Exception as e:
            self.logger.debug(f"Ошибка проверки устройства {device_path}: {e}")
            return True

    def create_resource_pool(
        self, request: ResourcePoolCreateRequest, request_id: str
    ) -> RpMessage:
        """
        Создание пула ресурсов (RP-01)

        Args:
            request: Запрос на создание пула ресурсов
            request_id: Id запроса

        Returns:
            RpMessage: Результат операции
        """
        try:
            self.logger.info(f"Запуск создания ресурс пула '{request.name}'")

            # Проверяем, существует ли уже пул с таким именем
            existing_pools = self.list_storage_pools()
            if request.name in existing_pools:
                self.logger.error(
                    f"Пул хранения '{request.name}' уже существует в libvirt"
                )
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_already_exists.value,
                    code=CommandMessagesEnum.rp_already_exists.name,
                    success=False,
                    note=f"Storage pool '{request.name}' already exists in libvirt",
                )

            # Для LVM пулов предварительно проверяем доступность LVM
            if request.pool_type == StoragePoolType.LOGICAL:
                self.logger.info(f"Проверка поддержки LVM для пула '{request.name}'")
                if not self.check_lvm_support():
                    return RpMessage(
                        request_id=request_id,
                        message=CommandMessagesEnum.rp_create_error.value,
                        code=CommandMessagesEnum.rp_create_error.name,
                        success=False,
                        note="LVM не поддерживается в системе. Установите пакеты lvm2.",
                    )

            # Подготавливаем XML в зависимости от типа пула
            try:
                storage_xml, storage_path = self._prepare_storage_pool_xml(request)
            except Exception as e:
                self.logger.error(
                    f"Ошибка подготовки XML для пула '{request.name}': {e}"
                )
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_create_error.value,
                    code=CommandMessagesEnum.rp_create_error.name,
                    success=False,
                    note=str(e),
                )

            # Добавляем capacity в XML если указан лимит хранилища
            if request.storage_limit:
                capacity_bytes = request.storage_limit_bytes
                self.logger.info(
                    f"Установка ограничения хранилища {request.storage_limit} ГБ ({capacity_bytes} байт)"
                )

                # Добавляем или обновляем элемент capacity в XML
                root = ET.fromstring(storage_xml)
                capacity_elem = root.find(".//capacity")
                if capacity_elem is None:
                    # Добавляем новый элемент capacity
                    capacity_elem = ET.SubElement(root, "capacity")
                capacity_elem.text = str(capacity_bytes)

                # Преобразуем обратно в строку
                storage_xml = ET.tostring(root, encoding="unicode")

            # Создаем пул хранения
            storage_pool_created = self.create_storage_pool(storage_xml)

            if not storage_pool_created:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_create_error.value,
                    code=CommandMessagesEnum.rp_create_error.name,
                    success=False,
                    note="Failed to create storage pool in libvirt",
                )

            # СОЗДАЕМ CGroups ДЛЯ CPU И RAM
            if request.cpu_limit or request.memory_limit:
                # Создаем cgroup для пула
                self.logger.warning(
                    f"Запуск создания cgroup для пула {request.name} "
                    f"с ресурсами cpu: {request.cpu_limit} and memory: {request.memory_limit}"
                )
                cgroup_created = self.create_pool_cgroup(request.name)

                if not cgroup_created:
                    self.logger.warning(
                        f"Не удалось создать cgroup для пула {request.name}"
                    )
                else:
                    # Устанавливаем лимиты CPU через CGroups
                    if request.cpu_limit:
                        cpu_set = self.set_cpu_limit(request.name, request.cpu_limit)
                        if cpu_set:
                            self.logger.info(
                                f"Установлен лимит CPU для пула {request.name}: {request.cpu_limit} ядер"
                            )

                    # Устанавливаем лимиты памяти через CGroups
                    if request.memory_limit:
                        memory_set = self.set_memory_limit(
                            request.name, request.memory_limit
                        )
                        if memory_set:
                            self.logger.info(
                                f"Установлен лимит памяти для пула {request.name}: {request.memory_limit} MB"
                            )

            # Получаем информацию о созданном пуле
            pool_info_msg = self.get_pool_info(request.name, request_id)
            if not pool_info_msg.success or not pool_info_msg.rp_info:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_create_error.value,
                    code=CommandMessagesEnum.rp_create_error.name,
                    success=False,
                    note="Failed to retrieve created pool information",
                )

            pool_info = pool_info_msg.rp_info
            # Добавляем лимиты ресурсов в информацию о пуле
            pool_info.cpu_limit = request.cpu_limit
            pool_info.memory_limit = request.memory_limit
            pool_info.capacity_bytes = request.storage_limit_bytes

            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_create_success.value,
                code=CommandMessagesEnum.rp_create_success.name,
                success=True,
                rp_info=pool_info,
            )

        except Exception as e:
            self.logger.error(f"Ошибка создания пула ресурсов '{request.name}': {e}")
            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_create_error.value,
                code=CommandMessagesEnum.rp_create_error.name,
                success=False,
                note=str(e),
            )

    def adjust_pool_resources(self, request: ResourcePoolAdjustRequest) -> RpMessage:
        """
        Добавление или удаление ресурсов из пула (RP-02, RP-03)

        Args:
            request: Запрос на изменение ресурсов

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pools = self.list_storage_pools()
            if request.name not in existing_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found",
                )

            new_limit = None

            if request.resource_type == ResourcePoolType.CPU:
                # Получаем текущий лимит CPU из CGroups
                cpu_limit_info = self.get_cpu_limit_info(request.name)
                current_cpu = cpu_limit_info.cpu_limit_cores

                if request.operation == "add":
                    new_cpu = current_cpu + request.value
                elif request.operation == "remove":
                    new_cpu = max(0, current_cpu - request.value)
                else:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_adjust_error.value,
                        code=CommandMessagesEnum.rp_resource_adjust_error.name,
                        success=False,
                        note=f"Invalid operation: {request.operation}",
                    )

                # Применяем новый лимит через CGroups
                if self.set_cpu_limit(request.name, new_cpu):
                    new_limit = str(new_cpu)
                    self.logger.info(
                        f"Лимит CPU для пула {request.name} изменен на {new_cpu} ядер"
                    )
                else:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_adjust_error.value,
                        code=CommandMessagesEnum.rp_resource_adjust_error.name,
                        success=False,
                        note="Failed to set CPU limit via CGroups",
                    )

            elif request.resource_type == ResourcePoolType.MEMORY:
                # Получаем текущий лимит памяти из CGroups
                cgroup_stats = self.get_cgroup_stats(request.name)
                current_memory_mb = (
                    cgroup_stats.memory_limit / (1024 * 1024)
                    if cgroup_stats.memory_limit > 0
                    else 0
                )

                if request.operation == "add":
                    new_memory = current_memory_mb + request.value
                elif request.operation == "remove":
                    new_memory = max(0, current_memory_mb - request.value)
                else:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_adjust_error.value,
                        code=CommandMessagesEnum.rp_resource_adjust_error.name,
                        success=False,
                        note=f"Invalid operation: {request.operation}",
                    )

                # Применяем новый лимит через CGroups
                if self.set_memory_limit(request.name, new_memory):
                    new_limit = f"{new_memory} MB"
                    self.logger.info(
                        f"Лимит памяти для пула {request.name} изменен на {new_memory} MB"
                    )
                else:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_adjust_error.value,
                        code=CommandMessagesEnum.rp_resource_adjust_error.name,
                        success=False,
                        note="Failed to set memory limit via CGroups",
                    )

            elif request.resource_type == ResourcePoolType.STORAGE:
                # Для хранилища получаем информацию из XML
                pool_info_msg = self.get_pool_info(request.name, request.request_id)
                if not pool_info_msg.success or not pool_info_msg.rp_info:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_adjust_error.value,
                        code=CommandMessagesEnum.rp_resource_adjust_error.name,
                        success=False,
                        note="Failed to get pool information",
                    )

                current_storage_gb = pool_info_msg.rp_info.capacity_gb

                if request.operation == "add":
                    new_storage_gb = current_storage_gb + request.value
                elif request.operation == "remove":
                    new_storage_gb = max(0, int(current_storage_gb - request.value))
                else:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_adjust_error.value,
                        code=CommandMessagesEnum.rp_resource_adjust_error.name,
                        success=False,
                        note=f"Invalid operation: {request.operation}",
                    )

                # Обновляем XML пула с новым capacity
                xml_desc = self.get_pool_xml_by_name(request.name)
                root = ET.fromstring(xml_desc)
                capacity_elem = root.find(".//capacity")

                if capacity_elem is None:
                    capacity_elem = ET.SubElement(root, "capacity")

                capacity_elem.text = str(int(new_storage_gb * 1024 * 1024 * 1024))
                new_xml = ET.tostring(root, encoding="unicode")

                if self.edit_storage_pool(request.name, new_xml):
                    new_limit = f"{new_storage_gb:.2f} GB"
                    self.logger.info(
                        f"Лимит хранилища для пула {request.name} изменен на {new_storage_gb} GB"
                    )
                else:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_adjust_error.value,
                        code=CommandMessagesEnum.rp_resource_adjust_error.name,
                        success=False,
                        note="Failed to update storage pool capacity",
                    )

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_resource_adjust_success.value,
                code=CommandMessagesEnum.rp_resource_adjust_success.name,
                success=True,
                rp_info=AdjustResourcePool(
                    name=request.name,
                    resource_type=request.resource_type,
                    operation=request.operation,
                    value=request.value,
                    new_limit=new_limit,
                ),
            )

        except Exception as e:
            self.logger.error(f"Ошибка изменения ресурсов пула '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_resource_adjust_error.value,
                code=CommandMessagesEnum.rp_resource_adjust_error.name,
                success=False,
                note=str(e),
            )

    def add_vm_to_pool(self, request: VMPoolAssignmentRequest) -> RpMessage:
        """
        Добавление виртуальной машины в пул ресурсов (RP-04)

        Args:
            request: Запрос на добавление ВМ в пул

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pools = self.list_storage_pools()
            if request.pool_name not in existing_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.pool_name}' not found",
                )

            # Проверяем существование ВМ
            try:
                domain = self.conn.lookupByName(request.vm_name)
                vm_info = domain.info()
            except self.libvirtError:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_not_found.value,
                    code=CommandMessagesEnum.rp_vm_not_found.name,
                    success=False,
                    note=f"VM '{request.vm_name}' not found",
                )

            # Получаем текущие ВМ пула
            pool_vms = self._get_pool_vms(request.pool_name)

            # Проверяем, не добавлена ли уже ВМ
            if request.vm_name in pool_vms:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_add_error.value,
                    code=CommandMessagesEnum.rp_vm_add_error.name,
                    success=False,
                    note=f"VM '{request.vm_name}' already in pool",
                )

            # Получаем информацию о ресурсах ВМ
            try:
                vm_cpu = vm_info[3]  # Количество виртуальных CPU
                vm_memory = vm_info[2]  # Память в KB

                # ДОБАВЛЯЕМ ВМ В CGroups
                vm_pid = self.get_vm_pid(request.vm_name)
                if vm_pid:
                    # Добавляем процесс ВМ в cgroup пула
                    added_to_cgroup = self.add_vm_to_cgroup(request.pool_name, vm_pid)
                    if not added_to_cgroup:
                        self.logger.warning(
                            f"Не удалось добавить ВМ {request.vm_name} в cgroup пула {request.pool_name}"
                        )
                else:
                    self.logger.warning(
                        f"Не удалось получить PID для ВМ {request.vm_name}"
                    )

                # Обновляем список ВМ
                pool_vms.append(request.vm_name)

                # Получаем общее использование ресурсов
                usage_info = self._get_resource_usage_for_pool(
                    request.pool_name, pool_vms
                )

                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_add_success.value,
                    code=CommandMessagesEnum.rp_vm_add_success.name,
                    success=True,
                    rp_info=AddVMInResourcePool(
                        name=request.pool_name,
                        vm_name=request.vm_name,
                        vm_cpu=vm_cpu,
                        vm_memory=vm_memory,
                        total_vms=len(pool_vms),
                        resource_usage=usage_info,
                    ),
                )

            except self.libvirtError as e:
                self.logger.error(
                    f"Ошибка получения информации о ВМ '{request.vm_name}': {e}"
                )
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_add_error.value,
                    code=CommandMessagesEnum.rp_vm_add_error.name,
                    success=False,
                    note=str(e),
                )

        except Exception as e:
            self.logger.error(
                f"Ошибка добавления ВМ '{request.vm_name}' в пул '{request.pool_name}': {e}"
            )
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_vm_add_error.value,
                code=CommandMessagesEnum.rp_vm_add_error.name,
                success=False,
                note=str(e),
            )

    def remove_vm_from_pool(self, request: VMPoolAssignmentRequest) -> RpMessage:
        """
        Удаление виртуальной машины из пула ресурсов (RP-05)

        Args:
            request: Запрос на удаление ВМ из пула

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pools = self.list_storage_pools()
            if request.pool_name not in existing_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.pool_name}' not found",
                )

            # Получаем текущие ВМ пула
            pool_vms = self._get_pool_vms(request.pool_name)

            # Проверяем, есть ли ВМ в пуле
            if request.vm_name not in pool_vms:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_remove_error.value,
                    code=CommandMessagesEnum.rp_vm_remove_error.name,
                    success=False,
                    note=f"VM '{request.vm_name}' not found in pool",
                )

            # Получаем информацию о ресурсах ВМ для освобождения
            try:
                domain = self.conn.lookupByName(request.vm_name)
                vm_info = domain.info()
                vm_cpu = vm_info[3]
                vm_memory = vm_info[2]

                # УДАЛЯЕМ ВМ ИЗ CGroups
                vm_pid = self.get_vm_pid(request.vm_name)
                if vm_pid:
                    # Удаляем процесс ВМ из cgroup пула
                    removed_from_cgroup = self.remove_vm_from_cgroup(
                        request.pool_name, vm_pid
                    )
                    if not removed_from_cgroup:
                        self.logger.warning(
                            f"Не удалось удалить ВМ {request.vm_name} из cgroup пула {request.pool_name}"
                        )

                # Удаляем ВМ из списка
                pool_vms.remove(request.vm_name)

                # Получаем общее использование ресурсов после удаления
                usage_info = self._get_resource_usage_for_pool(
                    request.pool_name, pool_vms
                )

                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_remove_success.value,
                    code=CommandMessagesEnum.rp_vm_remove_success.name,
                    success=True,
                    rp_info=RemoveVMInResourcePool(
                        name=request.pool_name,
                        vm_name=request.vm_name,
                        freed_cpu=vm_cpu,
                        freed_memory=vm_memory,
                        total_vms=len(pool_vms),
                        resource_usage=usage_info,
                    ),
                )

            except self.libvirtError as e:
                self.logger.error(
                    f"Ошибка получения информации о ВМ '{request.vm_name}': {e}"
                )
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_remove_error.value,
                    code=CommandMessagesEnum.rp_vm_remove_error.name,
                    success=False,
                    note=str(e),
                )

        except Exception as e:
            self.logger.error(
                f"Ошибка удаления ВМ '{request.vm_name}' из пула '{request.pool_name}': {e}"
            )
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_vm_remove_error.value,
                code=CommandMessagesEnum.rp_vm_remove_error.name,
                success=False,
                note=str(e),
            )

    def set_pool_reservation(
        self, request: ResourcePoolReservationRequest
    ) -> RpMessage:
        """
        Установка резерва (reservation) для пула (RP-06)

        Args:
            request: Запрос на установку резерва

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pools = self.list_storage_pools()
            if request.name not in existing_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found",
                )

            # УСТАНАВЛИВАЕМ РЕЗЕРВАЦИИ ЧЕРЕЗ CGroups
            reservations = {}

            if request.cpu_reservation is not None:
                # Для CPU резервация устанавливается через cpu.shares
                cpu_shares = max(2, request.cpu_reservation * 1024)  # 1024 за ядро
                if self.set_cpu_shares(request.name, cpu_shares):
                    reservations["cpu"] = request.cpu_reservation
                    self.logger.info(
                        f"Установлена резервация CPU для пула {request.name}: {request.cpu_reservation} ядер"
                    )

            if request.memory_reservation is not None:
                # Устанавливаем гарантированную память через CGroups
                if self.set_memory_reservation(
                    request.name, request.memory_reservation
                ):
                    reservations["memory"] = request.memory_reservation
                    self.logger.info(
                        f"Установлена резервация памяти для пула {request.name}: {request.memory_reservation} MB"
                    )

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_reservation_success.value,
                code=CommandMessagesEnum.rp_set_reservation_success.name,
                success=True,
                rp_info=ResourcePoolReservation(
                    name=request.name, reservations=reservations
                ),
            )

        except Exception as e:
            self.logger.error(
                f"Ошибка установки резерва для пула '{request.name}': {e}"
            )
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_reservation_error.value,
                code=CommandMessagesEnum.rp_set_reservation_error.name,
                success=False,
                note=str(e),
            )

    def set_pool_limit(self, request: ResourcePoolLimitRequest) -> RpMessage:
        """
        Установка лимита (limit) для пула (RP-07)

        Args:
            request: Запрос на установку лимита

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pools = self.list_storage_pools()
            if request.name not in existing_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found",
                )

            limits: dict = {}
            updates = {}

            # УСТАНАВЛИВАЕМ ЛИМИТЫ CPU И RAM ЧЕРЕЗ CGroups
            if request.cpu_limit is not None:
                if self.set_cpu_limit(request.name, request.cpu_limit):
                    limits["cpu"] = request.cpu_limit
                    updates["cpu"] = request.cpu_limit
                    self.logger.info(
                        f"Установлен лимит CPU для пула {request.name}: {request.cpu_limit} ядер"
                    )

            if request.memory_limit is not None:
                if self.set_memory_limit(request.name, request.memory_limit):
                    limits["memory"] = request.memory_limit
                    updates["memory"] = request.memory_limit
                    self.logger.info(
                        f"Установлен лимит памяти для пула {request.name}: {request.memory_limit} MB"
                    )

            # Для хранилища работаем через libvirt
            if request.storage_limit is not None:
                # Получаем текущий XML пула
                xml_content = self.get_pool_xml_by_name(request.name)
                root = ET.fromstring(xml_content)
                capacity_elem = root.find(".//capacity")

                if capacity_elem is None:
                    capacity_elem = ET.SubElement(root, "capacity")

                capacity_elem.text = str(
                    int(request.storage_limit * 1024 * 1024 * 1024)
                )
                new_xml = ET.tostring(root, encoding="unicode")

                # Применяем изменения
                if self.edit_storage_pool(request.name, new_xml):
                    limits["storage"] = request.storage_limit
                    updates["storage"] = request.storage_limit

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_limit_success.value,
                code=CommandMessagesEnum.rp_set_limit_success.name,
                success=True,
                rp_info=ResourcePoolUpdates(
                    name=request.name, limits=limits, updates=updates
                ),
            )

        except Exception as e:
            self.logger.error(f"Ошибка установки лимита для пула '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_limit_error.value,
                code=CommandMessagesEnum.rp_set_limit_error.name,
                success=False,
                note=str(e),
            )

    def delete_resource_pool(
        self, name: str, request_id: str, force: bool = False
    ) -> RpMessage:
        """
        Удаление пула ресурсов (RP-08, RP-09)

        Args:
            name: Имя пула
            request_id: id запроса
            force: Принудительное удаление даже если есть ВМ

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pool_info = self.get_pool_info(name, request_id)
            if existing_pool_info.message == CommandMessagesEnum.rp_not_found.value:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{name}' not found",
                )
            current_pool = existing_pool_info.rp_info

            # Проверяем, есть ли ВМ в пуле
            pool_vms = self._get_pool_vms(name)

            if not force and pool_vms:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_delete_not_empty_error.value,
                    code=CommandMessagesEnum.rp_delete_not_empty_error.name,
                    success=False,
                    note=f"Pool '{name}' contains {len(pool_vms)} VMs. Use force=True to delete.",
                )

            # Если есть ВМ, логируем предупреждение (при форсированном удалении)
            if pool_vms and force:
                self.logger.warning(
                    f"Forced deletion of pool '{name}' with {len(pool_vms)} VMs"
                )
                for vm_name in pool_vms:
                    self.logger.info(
                        f"VM '{vm_name}' will be disconnected from pool '{name}'"
                    )

                    # Удаляем ВМ из CGroups
                    vm_pid = self.get_vm_pid(vm_name)
                    if vm_pid:
                        self.remove_vm_from_cgroup(name, vm_pid)

            # Удаляем cgroup для CPU и RAM
            self.delete_pool_cgroup(name)

            if current_pool.type.value == StoragePoolType.LOGICAL.value:
                self.logic_volume_manager.delete_logical_volume(
                    name, self.system_volume_group_name
                )

            # Удаляем пул хранения из libvirt
            try:
                success = self.delete_storage_pool(name, destroy=True)

                # Удаляем саму директорию
                if current_pool.type.value == StoragePoolType.DIR.value:
                    self.logger.info(
                        f"Запуск удаления директории: {current_pool.storage_path}"
                    )
                    if os.path.exists(current_pool.storage_path):
                        os.rmdir(current_pool.storage_path)
                    if not os.path.exists(current_pool.storage_path):
                        self.logger.info(
                            f"Директория {current_pool.storage_path} успешно удалена"
                        )
                    else:
                        self.logger.info(
                            f"Ошибка при удалении директории: {current_pool.storage_path}"
                        )
                if not success:
                    return RpMessage(
                        request_id=request_id,
                        message=CommandMessagesEnum.rp_delete_error.value,
                        code=CommandMessagesEnum.rp_delete_error.name,
                        success=False,
                        note=f"Failed to delete storage pool '{name}' from libvirt",
                    )
            except Exception as e:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_delete_error.value,
                    code=CommandMessagesEnum.rp_delete_error.name,
                    success=False,
                    note=str(e),
                )

            self.logger.info(f"Пул ресурсов '{name}' успешно удален")
            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_delete_success.value,
                code=CommandMessagesEnum.rp_delete_success.name,
                success=True,
                rp_info=DeleteResourcePool(
                    name=name, force=force, vms_count=len(pool_vms)
                ),
            )

        except Exception as e:
            self.logger.error(f"Ошибка удаления пула ресурсов '{name}': {e}")
            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_delete_error.value,
                code=CommandMessagesEnum.rp_delete_error.name,
                success=False,
                note=str(e),
            )

    def get_pool_usage(self, request: ResourcePoolInfoRequest) -> RpMessage:
        """
        Просмотр использования ресурсов пула (RP-10)

        Args:
            request: Запрос на получение информации о пуле

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pools = self.list_storage_pools()
            if request.name not in existing_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found",
                )

            # Получаем информацию о пуле из libvirt
            pool_info_msg = self.get_pool_info(request.name, request.request_id)
            if not pool_info_msg.success or not pool_info_msg.rp_info:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_info_error.value,
                    code=CommandMessagesEnum.rp_info_error.name,
                    success=False,
                    note=f"Failed to get information for pool '{request.name}'",
                )

            pool_info = pool_info_msg.rp_info

            # Извлекаем информацию из XML
            xml_content = self.get_pool_xml_by_name(request.name)
            xml_info = self._extract_pool_info_from_xml(xml_content)

            # Получаем ВМ, связанные с пулом
            pool_vms = self._get_pool_vms(request.name)

            # Получаем использование ресурсов
            usage_info = self._get_resource_usage_for_pool(request.name, pool_vms)

            # ПОЛУЧАЕМ СТАТИСТИКУ ИЗ CGroups
            cgroup_stats = self.get_cgroup_stats(request.name)

            # Получаем точную информацию о лимитах CPU из CGroups
            cpu_limit_info = self.get_cpu_limit_info(request.name)
            cpu_limit_cores = cpu_limit_info.cpu_limit_cores

            # Получаем лимиты памяти из CGroups
            memory_limit_mb = (
                cgroup_stats.memory_limit / (1024 * 1024)
                if cgroup_stats.memory_limit > 0
                else None
            )

            storage_capacity = pool_info.capacity_bytes
            storage_usage = pool_info.allocation_bytes
            storage_available = pool_info.available_bytes

            # Рассчитываем проценты использования
            cpu_percent = 0
            cpu_usage_cores = usage_info.cpu  # Количество виртуальных CPU
            if cpu_limit_cores > 0:
                cpu_percent = min(100, int((cpu_usage_cores / cpu_limit_cores)) * 100)

            memory_percent = 0
            if memory_limit_mb and memory_limit_mb > 0:
                memory_usage_mb = usage_info.memory / 1024  # Конвертируем KB в MB
                memory_percent = min(
                    100, int((memory_usage_mb / memory_limit_mb)) * 100
                )

            storage_percent = (
                (storage_usage / storage_capacity * 100) if storage_capacity else 0
            )

            # Для LVM пулов получаем дополнительную информацию
            lvm_info = {}
            if xml_info.get("type") == "logical" and xml_info.get("vg_name"):
                vg_name = xml_info["vg_name"]
                vg_info = self.lvm_manager.get_vg_info(vg_name)
                lvm_volumes = self.lvm_manager.get_lvm_volumes(vg_name)

                lvm_info = {
                    "vg_name": vg_name,
                    "vg_size_bytes": vg_info.get("size_bytes"),
                    "vg_free_bytes": vg_info.get("free_bytes"),
                    "vg_extent_size": vg_info.get("extent_size"),
                    "lvm_volumes": lvm_volumes,
                    "lvm_volumes_count": len(lvm_volumes),
                }

            usage_data = {
                "pool_name": request.name,
                "vms": [{"name": vm} for vm in pool_vms],
                "vms_count": len(pool_vms),
                "cpu": {
                    "limit": round(cpu_limit_cores, 2),
                    "limit_period_us": cpu_limit_info.cpu_limit_period_us,
                    "limit_quota_us": cpu_limit_info.cpu_limit_quota_us,
                    "usage": cpu_usage_cores,
                    "usage_seconds": round(cgroup_stats.cpu_usage_seconds, 2),
                    "available": (
                        round(cpu_limit_cores - cpu_usage_cores, 2)
                        if cpu_limit_cores > 0
                        else None
                    ),
                    "percent": round(cpu_percent, 2),
                    "shares": cgroup_stats.get("cpu_shares", 1024),
                },
                "memory": {
                    "limit": memory_limit_mb,
                    "limit_bytes": cgroup_stats.memory_limit,
                    "usage": usage_info.memory / 1024,  # Конвертируем KB в MB
                    "usage_bytes": cgroup_stats.memory_usage,
                    "available": (
                        round(memory_limit_mb - (usage_info.memory / 1024), 2)
                        if memory_limit_mb
                        else None
                    ),
                    "percent": round(memory_percent, 2),
                    "reservation_bytes": cgroup_stats.memory_reservation,
                },
                "storage": {
                    "limit": storage_capacity,
                    "usage": storage_usage,
                    "available": storage_available,
                    "percent": round(storage_percent, 2),
                    "configured_limit_gb": pool_info.storage_limit,
                },
                "reservations": {},
                "limits": {
                    "cpu": round(cpu_limit_cores, 2),
                    "cpu_period_us": cpu_limit_info.cpu_limit_period_us,
                    "cpu_quota_us": cpu_limit_info.cpu_limit_quota_us,
                    "memory": memory_limit_mb,
                    "storage": storage_capacity,
                    "storage_gb": pool_info.storage_limit,
                },
                "storage_info": {
                    "type": xml_info.get("type"),
                    "path": xml_info.get("path"),
                    "vg_name": xml_info.get("vg_name"),
                    "device_path": xml_info.get("device_path"),
                    "state": (
                        pool_info.state.value
                        if hasattr(pool_info.state, "value")
                        else str(pool_info.state)
                    ),
                    "autostart": pool_info.autostart,
                    "is_active": pool_info.is_active,
                },
                "cgroup_stats": {
                    "process_count": cgroup_stats.process_count,
                    "cpu_shares": cgroup_stats.cpu_shares,
                    "cpu_limit_cores": round(cpu_limit_cores, 2),
                    "cpu_limit_period_us": cpu_limit_info.cpu_limit_period_us,
                    "cpu_limit_quota_us": cpu_limit_info.cpu_limit_quota_us,
                },
                "lvm_info": lvm_info if lvm_info else None,
            }

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_info_success.value,
                code=CommandMessagesEnum.rp_info_success.name,
                success=True,
                rp_info=ResourcePoolUsageInfo(**usage_data),
            )

        except Exception as e:
            self.logger.error(
                f"Ошибка получения информации об использовании пула '{request.name}': {e}"
            )
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_info_error.value,
                code=CommandMessagesEnum.rp_info_error.name,
                success=False,
                note=str(e),
            )

    def edit_resource_pool(self, request: ResourcePoolEditRequest) -> RpMessage:
        """
        Редактирование пула ресурсов

        Args:
            request: Запрос на редактирование пула

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pools = self.list_storage_pools()
            if request.name not in existing_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found",
                )

            updates = {}

            # Обновляем XML пула хранения, если предоставлен
            if request.storage_xml:
                try:
                    # Редактируем пул хранения в libvirt
                    success = self.edit_storage_pool(request.name, request.storage_xml)
                    updates["storage_xml_updated"] = success
                except Exception as e:
                    self.logger.error(f"Ошибка обновления XML пула хранения: {e}")
                    updates["storage_xml_updated"] = False
                    updates["storage_xml_error"] = str(e)

            # Обновляем лимиты CPU и RAM через CGroups
            if request.cpu_limit is not None:
                cpu_updated = self.set_cpu_limit(request.name, request.cpu_limit)
                updates["cpu_limit_updated"] = cpu_updated

            if request.memory_limit is not None:
                memory_updated = self.set_memory_limit(
                    request.name, request.memory_limit
                )
                updates["memory_limit_updated"] = memory_updated

            if request.storage_limit is not None:
                updates["storage_limit_note"] = (
                    "Storage limits can be set via XML editing"
                )

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_edit_success.value,
                code=CommandMessagesEnum.rp_edit_success.name,
                success=True,
                rp_info=ResourcePoolUpdates(
                    name=request.name, updates=updates, limits=None
                ),
            )

        except Exception as e:
            self.logger.error(
                f"Ошибка редактирования пула ресурсов '{request.name}': {e}"
            )
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_edit_error.value,
                code=CommandMessagesEnum.rp_edit_error.name,
                success=False,
                note=str(e),
            )

    def start_resource_pool(self, request: ResourcePoolControlRequest) -> RpMessage:
        """
        Запуск пула ресурсов

        Args:
            request: Запрос на запуск пула

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pools = self.list_storage_pools()
            if request.name not in existing_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found",
                )

            # Запускаем пул хранения в libvirt
            storage_started = self.start_storage_pool(request.name)

            # Создаем cgroup если его нет
            self.create_pool_cgroup(request.name)

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_start_success.value,
                code=CommandMessagesEnum.rp_start_success.name,
                success=True,
                rp_info=ResourcePoolState(
                    name=request.name, state="running" if storage_started else "stopped"
                ),
            )

        except Exception as e:
            self.logger.error(f"Ошибка запуска пула ресурсов '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_start_error.value,
                code=CommandMessagesEnum.rp_start_error.name,
                success=False,
                note=str(e),
            )

    def stop_resource_pool(self, request: ResourcePoolControlRequest) -> RpMessage:
        """
        Остановка пула ресурсов

        Args:
            request: Запрос на остановку пула

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            existing_pools = self.list_storage_pools()
            if request.name not in existing_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found",
                )

            # Останавливаем пул хранения в libvirt
            storage_stopped = self.stop_storage_pool(request.name)

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_stop_success.value,
                code=CommandMessagesEnum.rp_stop_success.name,
                success=True,
                rp_info=ResourcePoolState(
                    name=request.name, state="stopped" if storage_stopped else "running"
                ),
            )

        except Exception as e:
            self.logger.error(f"Ошибка остановки пула ресурсов '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_stop_error.value,
                code=CommandMessagesEnum.rp_stop_error.name,
                success=False,
                note=str(e),
            )

    def list_storage_pools(self) -> list[str]:
        """Получение списка пулов хранения"""
        try:
            pools = self.conn.listStoragePools()
            return pools
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения списка пулов хранения: {e}")
            return []

    def delete_storage_pool(self, pool_name: str, destroy: bool = True) -> bool:
        """
        Удаление пула хранения
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            if destroy:
                pool.destroy()
            pool.undefine()
            self.logger.info(f"Пул хранения '{pool_name}' успешно удален")
            return True
        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления пула хранения '{pool_name}': {e}")
            return False

    def edit_storage_pool(self, pool_name: str, new_pool_xml: str) -> bool:
        """
        Редактирование пула хранения
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            if pool.isActive():
                pool.destroy()
            self.conn.storagePoolDefineXML(new_pool_xml, 0)
            pool = self.conn.storagePoolLookupByName(pool_name)
            pool.create(0)
            pool.setAutostart(True)
            self.logger.info(f"Пул хранения '{pool_name}' успешно отредактирован")
            return True
        except self.libvirtError as e:
            self.logger.error(f"Ошибка редактирования пула хранения '{pool_name}': {e}")
            return False

    def get_pool_info(self, pool_name: str, request_id: str) -> RpMessage:
        """
        Получение информации о пуле хранения

        Включает информацию о capacity (лимите хранилища) из XML
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            info = pool.info()

            # Получаем XML пула для извлечения capacity
            xml_content = pool.XMLDesc(0)
            storage_path = ET.fromstring(xml_content).find("target").find("path").text
            # Извлекаем capacity из XML
            storage_capacity_from_xml = None
            try:
                root = ET.fromstring(xml_content)
                # Ищем элемент capacity
                capacity_elem = root.find(".//capacity")
                if capacity_elem is not None and capacity_elem.text:
                    storage_capacity_from_xml = int(capacity_elem.text)
                    self.logger.debug(
                        f"Capacity из XML для пула {pool_name}: {storage_capacity_from_xml} байт"
                    )
            except Exception as xml_e:
                self.logger.warning(
                    f"Не удалось извлечь capacity из XML пула {pool_name}: {xml_e}"
                )

            # Получаем тип пула
            pool_type_str = self.get_storage_pool_type(pool_name)
            pool_type = StoragePoolType.UNKNOWN
            try:
                pool_type = StoragePoolType(pool_type_str)
            except ValueError:
                pass

            # Получаем информацию из CGroups для CPU и RAM
            cgroup_pool = self.get_cgroup_stats(pool_name)

            # Используем capacity из XML если он есть, иначе из info[1]
            if pool_type == StoragePoolType.LOGICAL:
                capacity_bytes = self.logic_volume_manager.get_volume_by_name(
                    pool_name, self.system_volume_group_name
                ).volume_size
            else:
                capacity_bytes = (
                    storage_capacity_from_xml
                    if storage_capacity_from_xml is not None
                    else info[1]
                )

            self.logger.debug(
                f"Итоговый capacity для пула {pool_name}: {capacity_bytes} байт "
                f"(из XML: {storage_capacity_from_xml}, из info: {info[1]})"
            )

            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_info_success.value,
                code=CommandMessagesEnum.rp_info_success.name,
                success=True,
                rp_info=ResourcePool(
                    name=pool_name,
                    type=pool_type,
                    storage_path=storage_path,
                    state=POOL_STATE[info[0]],
                    capacity_bytes=capacity_bytes,
                    allocation_bytes=info[2],
                    available_bytes=info[3],
                    autostart=pool.autostart(),
                    is_active=pool.isActive(),
                    vms=[],
                    cpu_limit=cgroup_pool.cpu_limit_cores,
                    memory_limit=cgroup_pool.memory_limit,
                    # storage_limit=None,  # storage_limit теперь только в запросе создания
                ),
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения информации о пуле '{pool_name}': {e}")
            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_not_found.value,
                code=CommandMessagesEnum.rp_not_found.name,
                success=False,
            )

    def start_storage_pool(self, pool_name: str) -> bool:
        """
        Запуск пула хранения
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            if not pool.isActive():
                pool.create(0)
                self.logger.info(f"Пул хранения '{pool_name}' успешно запущен")
                return True
            return True
        except self.libvirtError as e:
            self.logger.error(f"Ошибка запуска пула хранения '{pool_name}': {e}")
            return False

    def stop_storage_pool(self, pool_name: str) -> bool:
        """
        Остановка пула хранения
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            if pool.isActive():
                pool.destroy()
                self.logger.info(f"Пул хранения '{pool_name}' успешно остановлен")
                return True
            return True
        except self.libvirtError as e:
            self.logger.error(f"Ошибка остановки пула хранения '{pool_name}': {e}")
            return False

    def get_storage_pool_type(self, pool_name: str) -> str:
        """
        Получить тип пула хранилища

        Args:
            pool_name: Имя пула

        Returns:
            str: Тип пула (dir, fs, logical и т.д.)
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            xml_desc = pool.XMLDesc(0)

            # Извлечение типа
            root = ET.fromstring(xml_desc)
            pool_type = root.get("type")
            return pool_type or "unknown"

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения типа пула '{pool_name}': {e}")
            return "error"
        except Exception as e:
            self.logger.error(f"Непредвиденная ошибка: {e}")
            return "error"


if __name__ == "__main__":
    with PoolManager() as mngr:
        print(mngr.list_storage_pools())
        print(mngr.list_resource_pools(str(uuid.uuid4())))
        print("asdasdasd", mngr.get_pool_info("RP-TEST-31680", str(uuid.uuid4())))
        for current_rp in mngr.list_resource_pools(str(uuid.uuid4())).rp_info.items:
            print(f"ИМЯ: {current_rp.name}")
            print(f"СТАТУС: {current_rp.state.value}")
            print(f"ТИП: {current_rp.type}")
            print(f"cpu_limit: {current_rp.cpu_limit}")
            print(f"memory_limit: {current_rp.memory_limit}")
            print(f"storage_limit: {current_rp.capacity_gb}")
            print(f"available_gb: {current_rp.available_gb}")
            print(f"ПОДКЛЮЧЕННЫЕ ВМ: {current_rp.vms}")
            print("_" * 50)
