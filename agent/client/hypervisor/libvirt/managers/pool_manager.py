import libvirt

from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.models.msg import RpMessage, CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.resource_pool import ResourcePoolCreateRequest, ResourcePoolAdjustRequest, \
    VMPoolAssignmentRequest, ResourcePoolReservationRequest, ResourcePoolLimitRequest, ResourcePoolDeleteRequest, \
    ResourcePoolInfoRequest, ResourcePoolEditRequest, ResourcePoolControlRequest, ResourcePool, ResourcePoolList, \
    AdjustResourcePool, AddVMInResourcePool, RemoveVMInResourcePool, ResourcePoolReservation, ResourcePoolUpdates, \
    DeleteResourcePool, ResourcePoolUsageInfo, ResourcePoolState


class PoolManager(LibvirtClient):
    """
    Управление пулом ресурсов

    Реализует управление ресурсными пулами (CPU, память, хранилище) через libvirt.
    Поддерживает создание, редактирование, удаление пулов и управление ВМ в них.
    """

    libvirtError = libvirt.libvirtError

    def __init__(self, connection_uri: str = "qemu:///system"):
        super().__init__(connection_uri)
        # Кэш для хранения информации о пулах (в реальной системе можно использовать БД)
        self._resource_pools = {}

    def list_resource_pools(self, request_id: str) -> RpMessage:
        """Получение списка всех пулов ресурсов"""
        try:
            pools = self.list_storage_pools()

            # Добавляем информацию о ресурсных пулах из кэша
            pool_info_list = []
            for pool_name in pools:
                pool_data = self._resource_pools.get(pool_name, {})
                pool_info = ResourcePool(name=pool_name,
                                         type=pool_data.get("type"),
                                         cpu_limit=pool_data.get("cpu_limit"),
                                         memory_limit=pool_data.get("memory_limit"),
                                         storage_limit=pool_data.get("storage_limit"),
                                         vms=pool_data.get("vms", []),
                                         reservations=pool_data.get("reservations", {}),
                                         limits=pool_data.get("limits", {}))
                pool_info_list.append(pool_info)

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

    def create_resource_pool(self, request: ResourcePoolCreateRequest, request_id: str) -> RpMessage:
        """
        Создание пула ресурсов (RP-01)

        Args:
            request: Запрос на создание пула ресурсов

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем, существует ли уже пул с таким именем
            if request.name in self._resource_pools:
                return RpMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.rp_already_exists.value,
                    code=CommandMessagesEnum.rp_already_exists.name,
                    success=False,
                    note=f"Pool '{request.name}' already exists"
                )

            # Создаем пул хранения в libvirt, если предоставлен XML
            storage_pool_created = False
            if request.storage_xml:
                # Модифицируем XML с указанными параметрами
                storage_xml = request.storage_xml
                if request.storage_limit:
                    # Добавляем лимит хранилища в XML (упрощенный пример)
                    storage_xml = storage_xml.replace(
                        "<capacity>",
                        f"<capacity>{request.storage_limit * 1024 * 1024 * 1024}</capacity>"
                    )

                storage_pool_created = self.create_storage_pool(storage_xml)
                if not storage_pool_created:
                    return RpMessage(
                        request_id=request_id,
                        message=CommandMessagesEnum.rp_create_error.value,
                        code=CommandMessagesEnum.rp_create_error.name,
                        success=False,
                        note="Failed to create storage pool in libvirt"
                    )

            # Создаем запись о ресурсном пуле
            pool_data = {
                "name": request.name,
                "cpu_limit": request.cpu_limit,
                "memory_limit": request.memory_limit,
                "storage_limit": request.storage_limit,
                "storage_path": request.storage_path,
                "vms": [],
                "reservations": {},
                "limits": {},
                "usage": {
                    "cpu": 0,
                    "memory": 0,
                    "storage": 0
                }
            }

            # Устанавливаем начальные лимиты, если они указаны
            if request.cpu_limit:
                pool_data["limits"]["cpu"] = request.cpu_limit
            if request.memory_limit:
                pool_data["limits"]["memory"] = request.memory_limit
            if request.storage_limit:
                pool_data["limits"]["storage"] = request.storage_limit

            self._resource_pools[request.name] = pool_data

            pool_info = ResourcePool(name=request.name,
                                     cpu_limit=request.cpu_limit,
                                     memory_limit=request.memory_limit,
                                     storage_limit=request.storage_limit,
                                     vms=[],
                                     reservations={},
                                     limits={})

            return RpMessage(
                request_id=request_id,
                message=CommandMessagesEnum.rp_create_success.value,
                code=CommandMessagesEnum.rp_create_success.name,
                success=True,
                rp_info=pool_info
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
            if request.name not in self._resource_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found"
                )

            pool_data = self._resource_pools[request.name]

            # Проверяем текущее использование ресурсов
            current_usage = pool_data["usage"].get(request.resource_type.value, 0)

            if request.operation == "remove":
                # Проверяем, что не пытаемся удалить больше, чем есть доступно сверх использования
                current_limit = pool_data.get(f"{request.resource_type.value}_limit", 0)
                new_limit = current_limit - request.value

                if new_limit < current_usage:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_in_use.value,
                        code=CommandMessagesEnum.rp_resource_in_use.name,
                        success=False,
                        note=f"Cannot reduce {request.resource_type.value} below current usage ({current_usage})"
                    )

                # Обновляем лимит
                pool_data[f"{request.resource_type.value}_limit"] = new_limit
                note = f"Reduced {request.resource_type.value} limit by {request.value}"

            elif request.operation == "add":
                # Увеличиваем лимит
                current_limit = pool_data.get(f"{request.resource_type.value}_limit", 0)
                pool_data[f"{request.resource_type.value}_limit"] = current_limit + request.value
                note = f"Increased {request.resource_type.value} limit by {request.value}"

            else:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_resource_adjust_error.value,
                    code=CommandMessagesEnum.rp_resource_adjust_error.name,
                    success=False,
                    note=f"Unknown operation: {request.operation}"
                )

            self._resource_pools[request.name] = pool_data
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_resource_adjust_success.value,
                code=CommandMessagesEnum.rp_resource_adjust_success.name,
                success=True,
                rp_info=AdjustResourcePool(name=request.name,
                                           resource_type=request.resource_type.value,
                                           operation=request.operation,
                                           value=request.value,
                                           new_limit=pool_data[f"{request.resource_type.value}_limit"]
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
            if request.pool_name not in self._resource_pools:
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

            pool_data = self._resource_pools[request.pool_name]

            # Проверяем, не добавлена ли уже ВМ
            if request.vm_name in pool_data["vms"]:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_add_error.value,
                    code=CommandMessagesEnum.rp_vm_add_error.name,
                    success=False,
                    note=f"VM '{request.vm_name}' already in pool"
                )

            # Получаем информацию о ресурсах ВМ
            try:
                domain_xml = domain.XMLDesc(0)
                # В реальной реализации здесь нужно парсить XML для получения
                # информации о CPU и памяти ВМ
                vm_cpu = vm_info[3]  # Количество виртуальных CPU
                vm_memory = vm_info[2]  # Память в KB

                # Проверяем доступность ресурсов в пуле
                cpu_limit = pool_data.get("cpu_limit")
                memory_limit = pool_data.get("memory_limit")
                current_cpu_usage = pool_data["usage"].get("cpu", 0)
                current_memory_usage = pool_data["usage"].get("memory", 0)

                if cpu_limit and (current_cpu_usage + vm_cpu > cpu_limit):
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_insufficient_resources.value,
                        code=CommandMessagesEnum.rp_insufficient_resources.name,
                        success=False,
                        note=f"Insufficient CPU in pool. Available: {cpu_limit - current_cpu_usage}, Required: {vm_cpu}"
                    )

                if memory_limit and (current_memory_usage + vm_memory > memory_limit):
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_insufficient_resources.value,
                        code=CommandMessagesEnum.rp_insufficient_resources.name,
                        success=False,
                        note=f"Insufficient memory in pool. Available: {memory_limit - current_memory_usage}, Required: {vm_memory}"
                    )

                # Добавляем ВМ в пул
                pool_data["vms"].append(request.vm_name)

                # Обновляем использование ресурсов
                pool_data["usage"]["cpu"] = current_cpu_usage + vm_cpu
                pool_data["usage"]["memory"] = current_memory_usage + vm_memory

                # В реальной реализации здесь нужно модифицировать XML ВМ
                # для привязки к хранилищу из пула

                self._resource_pools[request.pool_name] = pool_data
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_add_success.value,
                    code=CommandMessagesEnum.rp_vm_add_success.name,
                    success=True,
                    rp_info=AddVMInResourcePool(name=request.pool_name,
                                                vm_name=request.vm_name,
                                                vm_cpu=vm_cpu,
                                                vm_memory=vm_memory,
                                                total_vms=len(pool_data["vms"]),
                                                resource_usage=pool_data["usage"]
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
            if request.pool_name not in self._resource_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.pool_name}' not found"
                )

            pool_data = self._resource_pools[request.pool_name]

            # Проверяем, есть ли ВМ в пуле
            if request.vm_name not in pool_data["vms"]:
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

                # Удаляем ВМ из пула
                pool_data["vms"].remove(request.vm_name)

                # Освобождаем ресурсы
                pool_data["usage"]["cpu"] = max(0, pool_data["usage"].get("cpu", 0) - vm_cpu)
                pool_data["usage"]["memory"] = max(0, pool_data["usage"].get("memory", 0) - vm_memory)

                self._resource_pools[request.pool_name] = pool_data

                # В реальной реализации здесь нужно модифицировать XML ВМ
                # для отвязки от хранилища пула
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_vm_remove_success.value,
                    code=CommandMessagesEnum.rp_vm_remove_success.name,
                    success=True,
                    rp_info=RemoveVMInResourcePool(name=request.pool_name,
                                                   vm_name=request.vm_name,
                                                   freed_cpu=vm_cpu,
                                                   freed_memory=vm_memory,
                                                   total_vms=len(pool_data["vms"]),
                                                   resource_usage=pool_data["usage"]
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
            if request.name not in self._resource_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found"
                )

            pool_data = self._resource_pools[request.name]

            # Устанавливаем резервации
            reservations = pool_data.get("reservations", {})

            if request.cpu_reservation is not None:
                # Проверяем, что резервация не превышает лимит
                cpu_limit = pool_data.get("cpu_limit")
                if cpu_limit and request.cpu_reservation > cpu_limit:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_set_reservation_error.value,
                        code=CommandMessagesEnum.rp_set_reservation_error.name,
                        success=False,
                        note=f"CPU reservation ({request.cpu_reservation}) exceeds limit ({cpu_limit})"
                    )
                reservations["cpu"] = request.cpu_reservation

            if request.memory_reservation is not None:
                # Проверяем, что резервация не превышает лимит
                memory_limit = pool_data.get("memory_limit")
                if memory_limit and request.memory_reservation > memory_limit:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_set_reservation_error.value,
                        code=CommandMessagesEnum.rp_set_reservation_error.name,
                        success=False,
                        note=f"Memory reservation ({request.memory_reservation}) exceeds limit ({memory_limit})"
                    )
                reservations["memory"] = request.memory_reservation

            pool_data["reservations"] = reservations
            self._resource_pools[request.name] = pool_data
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_reservation_success.value,
                code=CommandMessagesEnum.rp_set_reservation_success.name,
                success=True,
                rp_info=ResourcePoolReservation(name=request.name, reservations=reservations)
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
            if request.name not in self._resource_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found"
                )

            pool_data = self._resource_pools[request.name]

            # Устанавливаем лимиты
            limits = pool_data.get("limits", {})
            updates = {}

            if request.cpu_limit is not None:
                # Проверяем, что лимит не меньше текущего использования
                current_usage = pool_data["usage"].get("cpu", 0)
                if request.cpu_limit < current_usage:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_in_use.value,
                        code=CommandMessagesEnum.rp_resource_in_use.name,
                        success=False,
                        note=f"Cannot set CPU limit below current usage ({current_usage})"
                    )
                limits["cpu"] = request.cpu_limit
                pool_data["cpu_limit"] = request.cpu_limit
                updates["cpu"] = request.cpu_limit

            if request.memory_limit is not None:
                # Проверяем, что лимит не меньше текущего использования
                current_usage = pool_data["usage"].get("memory", 0)
                if request.memory_limit < current_usage:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_in_use.value,
                        code=CommandMessagesEnum.rp_resource_in_use.name,
                        success=False,
                        note=f"Cannot set memory limit below current usage ({current_usage})"
                    )
                limits["memory"] = request.memory_limit
                pool_data["memory_limit"] = request.memory_limit
                updates["memory"] = request.memory_limit

            if request.storage_limit is not None:
                limits["storage"] = request.storage_limit
                pool_data["storage_limit"] = request.storage_limit
                updates["storage"] = request.storage_limit

            pool_data["limits"] = limits
            self._resource_pools[request.name] = pool_data
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_set_limit_success.value,
                code=CommandMessagesEnum.rp_set_limit_success.name,
                success=True,
                rp_info=ResourcePoolUpdates(name=request.name, limits=limits, updates=updates)
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

    def delete_resource_pool(self, request: ResourcePoolDeleteRequest) -> RpMessage:
        """
        Удаление пула ресурсов (RP-08, RP-09)

        Args:
            request: Запрос на удаление пула

        Returns:
            RpMessage: Результат операции
        """
        try:
            # Проверяем существование пула
            if request.name not in self._resource_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found"
                )

            pool_data = self._resource_pools[request.name]

            # Проверяем, есть ли ВМ в пуле
            if not request.force and pool_data["vms"]:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_delete_not_empty_error.value,
                    code=CommandMessagesEnum.rp_delete_not_empty_error.name,
                    success=False,
                    note=f"Pool '{request.name}' contains {len(pool_data['vms'])} VMs. Use force=True to delete."
                )

            # Если есть ВМ, перемещаем их из пула (при форсированном удалении)
            if pool_data["vms"] and request.force:
                for vm_name in pool_data["vms"]:
                    # Освобождаем ресурсы ВМ
                    try:
                        domain = self.conn.lookupByName(vm_name)
                        vm_info = domain.info()
                        # В реальной реализации нужно отвязать ВМ от пула
                        self.logger.info(f"VM '{vm_name}' removed from pool '{request.name}' during forced deletion")
                    except:
                        pass

            # Удаляем пул хранения из libvirt, если он существует
            try:
                # Пытаемся найти и удалить пул хранения
                pool_list = self.list_storage_pools()
                if request.name in pool_list:
                    self.delete_storage_pool(request.name, destroy=True)
            except:
                pass

            # Удаляем пул из кэша
            del self._resource_pools[request.name]
            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_delete_success.value,
                code=CommandMessagesEnum.rp_delete_success.name,
                success=True,
                rp_info=DeleteResourcePool(name=request.name, force=request.force, vms_count=len(pool_data["vms"]))
            )

        except Exception as e:
            self.logger.error(f"Ошибка удаления пула ресурсов '{request.name}': {e}")
            return RpMessage(
                request_id=request.request_id,
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
            if request.name not in self._resource_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found"
                )

            pool_data = self._resource_pools[request.name]

            # Получаем информацию о пуле хранения из libvirt, если он существует
            storage_info = None
            try:
                storage_pools = self.list_storage_pools()
                if request.name in storage_pools:
                    storage_info = self.get_pool_info(request.name)
            except:
                pass

            # Формируем детальную информацию об использовании
            cpu_limit = pool_data.get("cpu_limit")
            memory_limit = pool_data.get("memory_limit")
            storage_limit = pool_data.get("storage_limit")

            cpu_usage = pool_data["usage"].get("cpu", 0)
            memory_usage = pool_data["usage"].get("memory", 0)

            # Рассчитываем проценты использования
            cpu_percent = (cpu_usage / cpu_limit * 100) if cpu_limit else 0
            memory_percent = (memory_usage / memory_limit * 100) if memory_limit else 0

            # Для хранилища используем информацию из libvirt
            storage_usage = 0
            storage_available = 0
            storage_percent = 0

            if storage_info:
                storage_usage = storage_info.get("allocation", 0)
                storage_available = storage_info.get("available", 0)
                storage_capacity = storage_info.get("capacity", 1)
                storage_percent = (storage_usage / storage_capacity * 100) if storage_capacity else 0

            usage_info = {
                "pool_name": request.name,
                "vms": pool_data["vms"],
                "vms_count": len(pool_data["vms"]),
                "cpu": {
                    "limit": cpu_limit,
                    "usage": cpu_usage,
                    "available": cpu_limit - cpu_usage if cpu_limit else None,
                    "percent": round(cpu_percent, 2)
                },
                "memory": {
                    "limit": memory_limit,
                    "usage": memory_usage,
                    "available": memory_limit - memory_usage if memory_limit else None,
                    "percent": round(memory_percent, 2)
                },
                "storage": {
                    "limit": storage_limit,
                    "usage": storage_usage,
                    "available": storage_available,
                    "percent": round(storage_percent, 2)
                },
                "reservations": pool_data.get("reservations", {}),
                "limits": pool_data.get("limits", {}),
                "storage_info": storage_info
            }

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_info_success.value,
                code=CommandMessagesEnum.rp_info_success.name,
                success=True,
                rp_info=ResourcePoolUsageInfo(**usage_info)
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
            if request.name not in self._resource_pools:
                return RpMessage(
                    request_id=request.request_id,
                    message=CommandMessagesEnum.rp_not_found.value,
                    code=CommandMessagesEnum.rp_not_found.name,
                    success=False,
                    note=f"Pool '{request.name}' not found"
                )

            pool_data = self._resource_pools[request.name]
            updates = {}

            # Обновляем лимиты с проверками
            if request.cpu_limit is not None:
                current_usage = pool_data["usage"].get("cpu", 0)
                if request.cpu_limit < current_usage:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_in_use.value,
                        code=CommandMessagesEnum.rp_resource_in_use.name,
                        success=False,
                        note=f"Cannot set CPU limit below current usage ({current_usage})"
                    )
                pool_data["cpu_limit"] = request.cpu_limit
                updates["cpu_limit"] = request.cpu_limit

            if request.memory_limit is not None:
                current_usage = pool_data["usage"].get("memory", 0)
                if request.memory_limit < current_usage:
                    return RpMessage(
                        request_id=request.request_id,
                        message=CommandMessagesEnum.rp_resource_in_use.value,
                        code=CommandMessagesEnum.rp_resource_in_use.name,
                        success=False,
                        note=f"Cannot set memory limit below current usage ({current_usage})"
                    )
                pool_data["memory_limit"] = request.memory_limit
                updates["memory_limit"] = request.memory_limit

            if request.storage_limit is not None:
                pool_data["storage_limit"] = request.storage_limit
                updates["storage_limit"] = request.storage_limit

            # Обновляем XML пула хранения, если предоставлен
            if request.storage_xml:
                try:
                    # Редактируем пул хранения в libvirt
                    self.edit_storage_pool(request.name, request.storage_xml)
                    updates["storage_xml_updated"] = True
                except Exception as e:
                    self.logger.error(f"Ошибка обновления XML пула хранения: {e}")
                    updates["storage_xml_updated"] = False
                    updates["storage_xml_error"] = str(e)

            self._resource_pools[request.name] = pool_data

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
            # Запускаем пул хранения в libvirt, если он существует
            storage_pools = self.list_storage_pools()
            storage_started = False

            if request.name in storage_pools:
                storage_started = self.start_storage_pool(request.name)

            # Обновляем статус в кэше
            if request.name in self._resource_pools:
                self._resource_pools[request.name]["status"] = "active"

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_start_success.value,
                code=CommandMessagesEnum.rp_start_success.name,
                success=True,
                rp_info=ResourcePoolState(name=request.name, state="running" if storage_started else "stopped")
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
            # Останавливаем пул хранения в libvirt, если он существует
            storage_pools = self.list_storage_pools()
            storage_stopped = False

            if request.name in storage_pools:
                storage_stopped = self.stop_storage_pool(request.name)

            # Обновляем статус в кэше
            if request.name in self._resource_pools:
                self._resource_pools[request.name]["status"] = "inactive"

            return RpMessage(
                request_id=request.request_id,
                message=CommandMessagesEnum.rp_stop_success.value,
                code=CommandMessagesEnum.rp_stop_success.name,
                success=True,
                rp_info=ResourcePoolState(name=request.name, state="stopped" if storage_stopped else "running")
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

    def create_storage_pool(self, pool_xml: str) -> bool:
        """
        Создание пула хранения из XML описания
        """
        try:
            pool = self.conn.storagePoolCreateXML(pool_xml, 0)
            if pool:
                pool.setAutostart(True)
                self.logger.info(f"Пул хранения успешно создан")
                return True
            return False
        except self.libvirtError as e:
            self.logger.error(f"Ошибка создания пула хранения: {e}")
            return False

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

    def get_pool_info(self, pool_name: str) -> dict | None:
        """
        Получение информации о пуле хранения
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            info = pool.info()
            pool_info = {
                "name": pool_name,
                "state": info[0],
                "capacity": info[1],
                "allocation": info[2],
                "available": info[3],
                "autostart": pool.autostart(),
                "is_active": pool.isActive(),
                "xml": pool.XMLDesc(0)
            }
            return pool_info
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения информации о пуле '{pool_name}': {e}")
            return None

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


if __name__ == "__main__":
    with PoolManager() as mngr:
        print(mngr.list_storage_pools())