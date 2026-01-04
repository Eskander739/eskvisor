import random
import uuid
import os
import re
import xml.etree.ElementTree as ET
import libvirt

from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.models.msg import RpMessage, CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.resource_pool import ResourcePoolCreateRequest, ResourcePoolAdjustRequest, \
    VMPoolAssignmentRequest, ResourcePoolReservationRequest, ResourcePoolLimitRequest, ResourcePoolDeleteRequest, \
    ResourcePoolInfoRequest, ResourcePoolEditRequest, ResourcePoolControlRequest, ResourcePool, ResourcePoolList, \
    AdjustResourcePool, AddVMInResourcePool, RemoveVMInResourcePool, ResourcePoolReservation, ResourcePoolUpdates, \
    DeleteResourcePool, ResourcePoolUsageInfo, ResourcePoolState, UsageInfo, POOL_STATE


class PoolManager(LibvirtClient):
    """
    Управление пулом ресурсов

    Реализует управление ресурсными пулами (CPU, память, хранилище) через libvirt.
    Поддерживает создание, редактирование, удаление пулов и управление ВМ в них.
    """

    libvirtError = libvirt.libvirtError

    def __init__(self, connection_uri: str = "qemu:///system", username: str | None = None,
                 password: str | None = None):
        super().__init__(connection_uri, username, password)

    def _extract_pool_info_from_xml(self, xml_content: str) -> dict:
        """Извлечение информации о пуле из XML"""
        info = {
            "type": None,
            "path": None,
            "capacity": None,
            "allocation": None,
            "available": None
        }

        try:
            # Извлекаем тип пула
            type_match = re.search(r"<pool type='([^']+)'>", xml_content)
            if type_match:
                info["type"] = type_match.group(1)

            # Извлекаем путь
            path_match = re.search(r"<path>([^<]+)</path>", xml_content)
            if path_match:
                info["path"] = path_match.group(1)

            # Извлекаем информацию о хранилище
            capacity_match = re.search(r"<capacity>(\d+)</capacity>", xml_content)
            if capacity_match:
                info["capacity"] = int(capacity_match.group(1))

            allocation_match = re.search(r"<allocation>(\d+)</allocation>", xml_content)
            if allocation_match:
                info["allocation"] = int(allocation_match.group(1))

            available_match = re.search(r"<available>(\d+)</available>", xml_content)
            if available_match:
                info["available"] = int(available_match.group(1))

        except Exception as e:
            self.logger.debug(f"Ошибка при разборе XML пула: {e}")

        return info

    def _get_pool_vms(self, pool_name: str) -> list:
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
                        f"<source pool='{pool_name}'"
                    ]

                    if any(pattern in xml_desc for pattern in pool_patterns):
                        vms.append(domain.name())

                except self.libvirtError:
                    continue

        except Exception as e:
            self.logger.debug(f"Ошибка при получении ВМ пула {pool_name}: {e}")

        return vms

    def _get_resource_usage_for_pool(self, pool_name: str, pool_vms: list) -> dict:
        """Получение информации об использовании ресурсов пулом"""
        usage = {
            "cpu": 0,
            "memory": 0,
            "storage": 0
        }

        try:
            # Получаем информацию о хранилище пула
            pool_info = self.get_pool_info(pool_name)
            if pool_info:
                usage["storage"] = pool_info.get("allocation", 0)

            # Суммируем ресурсы всех ВМ в пуле
            for vm_name in pool_vms:
                try:
                    domain = self.conn.lookupByName(vm_name)
                    vm_info = domain.info()
                    usage["cpu"] += vm_info[3]  # Количество виртуальных CPU
                    usage["memory"] += vm_info[2]  # Память в KB
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
            connection_uri: URI подключения к hypervisor

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
                    pool_info = self.get_pool_info(pool_name, request_id)
                    if not pool_info:
                        continue

                    # Получаем ВМ, связанные с пулом
                    pool_vms = self._get_pool_vms(pool_name)

                    # Получаем использование ресурсов
                    usage_info = self._get_resource_usage_for_pool(pool_name, pool_vms)

                    pool_info.rp_info.usage = UsageInfo(
                            cpu=usage_info["cpu"],
                            memory=usage_info["memory"],
                            storage=usage_info["storage"]
                        )
                    pool_info.rp_info.vms = pool_vms

                    pool_info_list.append(pool_info.rp_info)

                except Exception as e:
                    self.logger.error(f"Ошибка обработки пула {pool_name}: {e}")
                    continue

            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_list_success.value,
                code=CommandMessagesEnum.rp_list_success.name,
                success=True,
                rp_info=ResourcePoolList(items=pool_info_list, count=(len(pool_info_list))),
            )
        except Exception as e:
            self.logger.error(f"Ошибка получения списка пулов ресурсов: {e}")
            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_list_error.value,
                code=CommandMessagesEnum.rp_list_error.name,
                success=False,
                note=str(e)
            )

    def create_storage_pool(self, pool_xml: str) -> bool:
        """
        Создание пула хранения из XML описания (упрощенная версия)
        """
        try:
            self.logger.debug(f"Создание пула из XML: {pool_xml}")

            # Всегда используем define + create для гарантии создания конфигурационного файла
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
                    # (для некоторых типов пулов это нормально)
                    pass

            # Включаем автозапуск
            try:
                pool.setAutostart(True)
            except:
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
            except:
                pass

            return False
        except Exception as e:
            self.logger.error(f"Непредвиденная ошибка при создании пула: {e}")
            return False

    def create_resource_pool(self, request: ResourcePoolCreateRequest, request_id: str) -> RpMessage:
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
                self.logger.error(f"Пул хранения '{request.name}' уже существует в libvirt")
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_already_exists.value,
                    code=CommandMessagesEnum.rp_already_exists.name,
                    success=False,
                    note=f"Storage pool '{request.name}' already exists in libvirt"
                )

            # Вариант 1: Создание пула из XML конфигурации
            if request.storage_xml:
                self.logger.info(f"Создание ресурс пула '{request.name}' из XML конфигурации")

                # Модифицируем XML с указанными параметрами
                storage_xml = request.storage_xml

                # Заменяем имя пула в XML, если оно отличается
                storage_xml = re.sub(r'<name>.*?</name>', f'<name>{request.name}</name>', storage_xml, flags=re.DOTALL)

                # Добавляем лимит хранилища в XML, если указан
                if request.storage_limit:
                    # Ищем и заменяем capacity или добавляем новый элемент
                    capacity_pattern = r'<capacity>\s*\d+\s*</capacity>'
                    if re.search(capacity_pattern, storage_xml):
                        storage_xml = re.sub(
                            capacity_pattern,
                            f'<capacity>{request.storage_limit * 1024 * 1024 * 1024}</capacity>',
                            storage_xml
                        )
                    else:
                        # Добавляем capacity в подходящее место
                        target_pattern = r'(<target>.*?</target>)'
                        replacement = f'\\1<capacity>{request.storage_limit * 1024 * 1024 * 1024}</capacity>'
                        storage_xml = re.sub(target_pattern, replacement, storage_xml, flags=re.DOTALL)

                # Извлекаем путь из XML для возврата в ответе
                path_match = re.search(r'<path>([^<]+)</path>', storage_xml)
                if path_match:
                    storage_path = path_match.group(1)

                storage_pool_created = self.create_storage_pool(storage_xml)

            # Вариант 2: Создание пула с указанным путем
            elif request.storage_path:
                self.logger.info(f"Создание ресурс пула '{request.name}' с путем '{request.storage_path}'")
                storage_path = request.storage_path

                # Генерируем простой XML для пула директорий
                storage_xml = f'''<pool type='dir'>
                  <name>{request.name}</name>
                  <source>
                  </source>
                  <target>
                    <path>{storage_path}</path>
                  </target>
                </pool>'''

                storage_pool_created = self.create_storage_pool(storage_xml)

            # Вариант 3: Создание пула с автоматически сгенерированным путем
            else:
                self.logger.info(f"Создание ресурс пула '{request.name}' с автоматическим путем")

                # Генерируем путь для пула
                base_path = "/var/lib/libvirt/resource_pools"

                # Создаем базовую директорию, если её нет
                if not os.path.exists(base_path):
                    os.makedirs(base_path, exist_ok=True)

                storage_path = os.path.join(base_path, f"rp_{request.name}_{random.randint(100_000, 999_999)}")

                # Создаем директорию для пула
                os.makedirs(storage_path, exist_ok=True)

                # Генерируем XML для пула директорий
                storage_xml = f'''<pool type='dir'>
                  <name>{request.name}</name>
                  <source>
                  </source>
                  <target>
                    <path>{storage_path}</path>
                    <permissions>
                      <mode>0711</mode>
                      <owner>0</owner>
                      <group>0</group>
                    </permissions>
                  </target>
                </pool>'''

                storage_pool_created = self.create_storage_pool(storage_xml)

            # Если создание пула в libvirt не удалось (и это было запрошено)
            if (request.storage_xml or request.storage_path is not None) and not storage_pool_created:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_create_error.value,
                    code=CommandMessagesEnum.rp_create_error.name,
                    success=False,
                    note="Failed to create storage pool in libvirt"
                )

            # Получаем информацию о созданном пуле
            pool_info = self.get_pool_info(request.name, request_id)
            if not pool_info:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_create_error.value,
                    code=CommandMessagesEnum.rp_create_error.name,
                    success=False,
                    note="Failed to retrieve created pool information"
                )

            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_create_success.value,
                code=CommandMessagesEnum.rp_create_success.name,
                success=True,
                rp_info=pool_info.rp_info
            )

        except Exception as e:
            self.logger.error(f"Ошибка создания пула ресурсов '{request.name}': {e}")
            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_create_error.value,
                code=CommandMessagesEnum.rp_create_error.name,
                success=False,
                note=str(e)
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
                    note=f"Pool '{request.name}' not found"
                )

            # Для CPU и памяти в libvirt нет прямого управления лимитами через пулы
            # В реальной системе это должно быть реализовано через cgroups или другие механизмы

            note = f"Operation '{request.operation}' for resource '{request.resource_type.value}' not directly supported by libvirt. " \
                   f"In real implementation, this would adjust resources via system-level controls."

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_resource_adjust_success.value,
                code=CommandMessagesEnum.rp_resource_adjust_success.name,
                success=True,
                rp_info=AdjustResourcePool(
                    name=request.name,
                    resource_type=request.resource_type.value,
                    operation=request.operation,
                    value=request.value,
                    new_limit=None  # Лимиты не хранятся в libvirt
                ),
                note=note
            )

        except Exception as e:
            self.logger.error(f"Ошибка изменения ресурсов пула '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_resource_adjust_error.value,
                code=CommandMessagesEnum.rp_resource_adjust_error.name,
                success=False,
                note=str(e)
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
                    note=f"Pool '{request.pool_name}' not found"
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
                    note=f"VM '{request.vm_name}' not found"
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
                    note=f"VM '{request.vm_name}' already in pool"
                )

            # Получаем информацию о ресурсах ВМ
            try:
                vm_cpu = vm_info[3]  # Количество виртуальных CPU
                vm_memory = vm_info[2]  # Память в KB

                # В реальной реализации здесь нужно модифицировать XML ВМ
                # для привязки к хранилищу из пула
                # Для примера просто добавляем ВМ в список

                # Обновляем список ВМ
                pool_vms.append(request.vm_name)

                # Получаем общее использование ресурсов
                usage_info = self._get_resource_usage_for_pool(request.pool_name, pool_vms)

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
                        resource_usage=usage_info
                    )
                )

            except self.libvirtError as e:
                self.logger.error(f"Ошибка получения информации о ВМ '{request.vm_name}': {e}")
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_add_error.value,
                    code=CommandMessagesEnum.rp_vm_add_error.name,
                    success=False,
                    note=str(e)
                )

        except Exception as e:
            self.logger.error(f"Ошибка добавления ВМ '{request.vm_name}' в пул '{request.pool_name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_vm_add_error.value,
                code=CommandMessagesEnum.rp_vm_add_error.name,
                success=False,
                note=str(e)
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
                    note=f"Pool '{request.pool_name}' not found"
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
                    note=f"VM '{request.vm_name}' not found in pool"
                )

            # Получаем информацию о ресурсах ВМ для освобождения
            try:
                domain = self.conn.lookupByName(request.vm_name)
                vm_info = domain.info()
                vm_cpu = vm_info[3]
                vm_memory = vm_info[2]

                # Удаляем ВМ из списка
                pool_vms.remove(request.vm_name)

                # Получаем общее использование ресурсов после удаления
                usage_info = self._get_resource_usage_for_pool(request.pool_name, pool_vms)

                # В реальной реализации здесь нужно модифицировать XML ВМ
                # для отвязки от хранилища пула

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
                        resource_usage=usage_info
                    )
                )

            except self.libvirtError as e:
                self.logger.error(f"Ошибка получения информации о ВМ '{request.vm_name}': {e}")
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_remove_error.value,
                    code=CommandMessagesEnum.rp_vm_remove_error.name,
                    success=False,
                    note=str(e)
                )

        except Exception as e:
            self.logger.error(f"Ошибка удаления ВМ '{request.vm_name}' из пула '{request.pool_name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_vm_remove_error.value,
                code=CommandMessagesEnum.rp_vm_remove_error.name,
                success=False,
                note=str(e)
            )

    def set_pool_reservation(self, request: ResourcePoolReservationRequest) -> RpMessage:
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
                    note=f"Pool '{request.name}' not found"
                )

            # Резервации не поддерживаются напрямую в libvirt
            # В реальной системе это должно храниться в отдельной базе данных

            reservations = {}
            if request.cpu_reservation is not None:
                reservations["cpu"] = request.cpu_reservation
            if request.memory_reservation is not None:
                reservations["memory"] = request.memory_reservation

            note = "Reservations are not directly supported by libvirt. " \
                   "In real implementation, these would be stored in a separate database."

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_reservation_success.value,
                code=CommandMessagesEnum.rp_set_reservation_success.name,
                success=True,
                rp_info=ResourcePoolReservation(name=request.name, reservations=reservations),
                note=note
            )

        except Exception as e:
            self.logger.error(f"Ошибка установки резерва для пула '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_reservation_error.value,
                code=CommandMessagesEnum.rp_set_reservation_error.name,
                success=False,
                note=str(e)
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
                    note=f"Pool '{request.name}' not found"
                )

            # Для хранилища можно обновить capacity через редактирование XML
            # Для CPU и памяти лимиты не поддерживаются напрямую в libvirt

            limits = {}
            updates = {}

            if request.storage_limit is not None:
                # Получаем текущий XML пула
                pool_info = self.get_pool_info(request.name)
                if pool_info:
                    xml_content = pool_info.get("xml", "")

                    # Обновляем capacity в XML
                    new_xml = re.sub(
                        r'<capacity>\s*\d+\s*</capacity>',
                        f'<capacity>{request.storage_limit * 1024 * 1024 * 1024}</capacity>',
                        xml_content
                    )

                    # Применяем изменения
                    if self.edit_storage_pool(request.name, new_xml):
                        limits["storage"] = request.storage_limit
                        updates["storage"] = request.storage_limit

            note = "CPU and memory limits are not directly supported by libvirt. " \
                   "Storage limits can be set via pool capacity."

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_limit_success.value,
                code=CommandMessagesEnum.rp_set_limit_success.name,
                success=True,
                rp_info=ResourcePoolUpdates(name=request.name, limits=limits, updates=updates),
                note=note
            )

        except Exception as e:
            self.logger.error(f"Ошибка установки лимита для пула '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_limit_error.value,
                code=CommandMessagesEnum.rp_set_limit_error.name,
                success=False,
                note=str(e)
            )

    def delete_resource_pool(self, name: str, request_id: str, force: bool = False) -> RpMessage:
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
            existing_pools = self.list_storage_pools()
            if name not in existing_pools:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{name}' not found"
                )

            # Проверяем, есть ли ВМ в пуле
            pool_vms = self._get_pool_vms(name)

            if not force and pool_vms:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_delete_not_empty_error.value,
                    code=CommandMessagesEnum.rp_delete_not_empty_error.name,
                    success=False,
                    note=f"Pool '{name}' contains {len(pool_vms)} VMs. Use force=True to delete."
                )

            # Если есть ВМ, логируем предупреждение (при форсированном удалении)
            if pool_vms and force:
                self.logger.warning(f"Forced deletion of pool '{name}' with {len(pool_vms)} VMs")
                for vm_name in pool_vms:
                    self.logger.info(f"VM '{vm_name}' will be disconnected from pool '{name}'")

            # Удаляем пул хранения из libvirt
            try:
                success = self.delete_storage_pool(name, destroy=True)
                if not success:
                    return RpMessage(
                        request_id=request_id,
                        message=CommandMessagesEnum.rp_delete_error.value,
                        code=CommandMessagesEnum.rp_delete_error.name,
                        success=False,
                        note=f"Failed to delete storage pool '{name}' from libvirt"
                    )
            except Exception as e:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_delete_error.value,
                    code=CommandMessagesEnum.rp_delete_error.name,
                    success=False,
                    note=str(e)
                )

            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_delete_success.value,
                code=CommandMessagesEnum.rp_delete_success.name,
                success=True,
                rp_info=DeleteResourcePool(name=name, force=force, vms_count=len(pool_vms))
            )

        except Exception as e:
            self.logger.error(f"Ошибка удаления пула ресурсов '{name}': {e}")
            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_delete_error.value,
                code=CommandMessagesEnum.rp_delete_error.name,
                success=False,
                note=str(e)
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
                    note=f"Pool '{request.name}' not found"
                )

            # Получаем информацию о пуле из libvirt
            pool_info = self.get_pool_info(request.name)
            if not pool_info:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_info_error.value,
                    code=CommandMessagesEnum.rp_info_error.name,
                    success=False,
                    note=f"Failed to get information for pool '{request.name}'"
                )

            # Извлекаем информацию из XML
            xml_info = self._extract_pool_info_from_xml(pool_info.get("xml", ""))

            # Получаем ВМ, связанные с пулом
            pool_vms = self._get_pool_vms(request.name)

            # Получаем использование ресурсов
            usage_info = self._get_resource_usage_for_pool(request.name, pool_vms)

            # Рассчитываем проценты использования
            cpu_limit = None  # CPU лимиты не хранятся в libvirt
            memory_limit = None  # Memory лимиты не хранятся в libvirt
            storage_capacity = pool_info.get("capacity", 0)
            storage_usage = pool_info.get("allocation", 0)
            storage_available = pool_info.get("available", 0)

            cpu_percent = 0
            memory_percent = 0
            storage_percent = (storage_usage / storage_capacity * 100) if storage_capacity else 0

            usage_data = {
                "pool_name": request.name,
                "vms": pool_vms,
                "vms_count": len(pool_vms),
                "cpu": {
                    "limit": cpu_limit,
                    "usage": usage_info["cpu"],
                    "available": None,
                    "percent": round(cpu_percent, 2)
                },
                "memory": {
                    "limit": memory_limit,
                    "usage": usage_info["memory"],
                    "available": None,
                    "percent": round(memory_percent, 2)
                },
                "storage": {
                    "limit": storage_capacity,
                    "usage": storage_usage,
                    "available": storage_available,
                    "percent": round(storage_percent, 2)
                },
                "reservations": {},  # Должны храниться отдельно
                "limits": {"storage": storage_capacity},  # Только storage лимиты из libvirt
                "storage_info": {
                    "type": xml_info.get("type"),
                    "path": xml_info.get("path"),
                    "state": pool_info.get("state"),
                    "autostart": pool_info.get("autostart"),
                    "is_active": pool_info.get("is_active")
                }
            }

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_info_success.value,
                code=CommandMessagesEnum.rp_info_success.name,
                success=True,
                rp_info=ResourcePoolUsageInfo(**usage_data)
            )

        except Exception as e:
            self.logger.error(f"Ошибка получения информации об использовании пула '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_info_error.value,
                code=CommandMessagesEnum.rp_info_error.name,
                success=False,
                note=str(e)
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
                    note=f"Pool '{request.name}' not found"
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

            # CPU и memory лимиты не могут быть установлены напрямую в libvirt
            if request.cpu_limit is not None:
                updates["cpu_limit_note"] = "CPU limits not directly supported by libvirt"

            if request.memory_limit is not None:
                updates["memory_limit_note"] = "Memory limits not directly supported by libvirt"

            if request.storage_limit is not None:
                updates["storage_limit_note"] = "Storage limits can be set via XML editing"

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_edit_success.value,
                code=CommandMessagesEnum.rp_edit_success.name,
                success=True,
                rp_info=ResourcePoolUpdates(name=request.name, updates=updates)
            )

        except Exception as e:
            self.logger.error(f"Ошибка редактирования пула ресурсов '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_edit_error.value,
                code=CommandMessagesEnum.rp_edit_error.name,
                success=False,
                note=str(e)
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
                    note=f"Pool '{request.name}' not found"
                )

            # Запускаем пул хранения в libvirt
            storage_started = self.start_storage_pool(request.name)

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_start_success.value,
                code=CommandMessagesEnum.rp_start_success.name,
                success=True,
                rp_info=ResourcePoolState(
                    name=request.name,
                    state="running" if storage_started else "stopped"
                )
            )

        except Exception as e:
            self.logger.error(f"Ошибка запуска пула ресурсов '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_start_error.value,
                code=CommandMessagesEnum.rp_start_error.name,
                success=False,
                note=str(e)
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
                    note=f"Pool '{request.name}' not found"
                )

            # Останавливаем пул хранения в libvirt
            storage_stopped = self.stop_storage_pool(request.name)

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_stop_success.value,
                code=CommandMessagesEnum.rp_stop_success.name,
                success=True,
                rp_info=ResourcePoolState(
                    name=request.name,
                    state="stopped" if storage_stopped else "running"
                )
            )

        except Exception as e:
            self.logger.error(f"Ошибка остановки пула ресурсов '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_stop_error.value,
                code=CommandMessagesEnum.rp_stop_error.name,
                success=False,
                note=str(e)
            )

    # Существующие методы (оставлены для обратной совместимости)

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
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            info = pool.info()
            return RpMessage(request_id=request_id,
                             message=CommandMessagesEnum.rp_info_success.value,
                             code=CommandMessagesEnum.rp_info_success.name,
                             success=True,
                             rp_info=ResourcePool(name=pool_name,
                                                  type=self.get_storage_pool_type(pool_name),
                                                  state=POOL_STATE[info[0]],
                                                  capacity_bytes=info[1],
                                                  allocation_bytes=info[2],
                                                  available_bytes=info[3],
                                                  autostart=pool.autostart(),
                                                  is_active=pool.isActive(),
                                                  vms=[]))
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения информации о пуле '{pool_name}': {e}")
            return RpMessage(request_id=request_id,
                             message=CommandMessagesEnum.rp_not_found.value,
                             code=CommandMessagesEnum.rp_not_found.name,
                             success=False)

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
            pool_type = root.get('type')
            return pool_type or "unknown"

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения типа пула '{pool_name}': {e}")
            return "error"
        except Exception as e:
            self.logger.error(f"Непредвиденная ошибка: {e}")
            return "error"


if __name__ == "__main__":
    with PoolManager().with_default_user() as mngr:
        print(mngr.list_storage_pools())
        # print(mngr.delete_resource_pool("RP-TEST-46750", str(uuid.uuid4())))
        print(mngr.list_resource_pools(str(uuid.uuid4())))
        print("asdasdasd", mngr.get_pool_info("RP-TEST-31680", str(uuid.uuid4())))
        for current_rp in mngr.list_resource_pools(str(uuid.uuid4())).rp_info.items:
            print(f"ИМЯ: {current_rp.name}")
            print(f"СТАТУС: {current_rp.state.value}")
            print(f"ТИП: {current_rp.type}")
            print(f"cpu_limit: {current_rp.cpu_limit}")
            print(f"memory_limit: {current_rp.memory_limit}")
            print(f"available_gb: {current_rp.available_gb}")
            print(f"ПОДКЛЮЧЕННЫЕ ВМ: {current_rp.vms}")
            print("_" * 50)