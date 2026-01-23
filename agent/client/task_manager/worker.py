import logging
import threading
import time
from typing import Any
from datetime import datetime

import orjson

from agent.client.hypervisor.libvirt.models.msg import (
    NetworkMessage,
    SnapshotMessage,
    RpMessage,
    VmMessage,
)
from agent.client.hypervisor.libvirt.models.network import (
    NetworkParameters,
)
from agent.client.hypervisor.libvirt.models.snapshots import (
    SnapshotCreateRequest,
    SnapshotCloneRequest,
)
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest, VmUpdateRequest
from agent.client.hypervisor.libvirt.models.volume.balansir import (
    ResourcePoolVirtualCreate,
    ResourcePoolVirtualEdit,
    ResourcePoolVirtual,
)
from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskCreate,
    DiskAttach,
    DiskDetach,
    Disk,
)
from agent.client.task_manager.ctl_queue import RedisTaskManager
from agent.client.task_manager.models import (
    TaskType,
    TaskResponse,
    TaskStatus,
    TaskNotificationType,
)
from agent.client.hypervisor.libvirt.managers.vm import VmManager
from agent.client.hypervisor.libvirt.managers.network import NetworkManager
from agent.client.hypervisor.libvirt.managers.snapshot import SnapshotManager
from agent.client.hypervisor.libvirt.managers.storage import StorageManager
from agent.client.hypervisor.libvirt.managers.balansir import Balansir
from agent.client.hypervisor.libvirt.managers.vm_stats import VMLiveMonitor

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Worker")


class TaskHandler:
    """
    Обработчик задач для выполнения операций с ВМ, сетями и т.д.
    """

    def __init__(self):
        with VmManager() as vm_manager:
            self.vm_manager = vm_manager
            self.net_manager = NetworkManager()
            self.snapshot_manager = SnapshotManager()
            self.storage_manager = StorageManager()
            self.balansir = Balansir()

            self.storage_manager.conn = self.vm_manager.conn
            self.snapshot_manager.conn = self.vm_manager.conn
            self.net_manager.conn = self.vm_manager.conn
            self.balansir.conn = self.vm_manager.conn
            self.balansir.vm_manager = self.vm_manager
            self.balansir.storage_manager = self.storage_manager

    def handle_task(
        self, task_type: TaskType, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Основной метод обработки задачи

        Args:
            task_type: Тип задачи
            action: Действие (create, delete, update, etc.)
            params: Данные задачи

        Returns:
            Результат выполнения
        """
        try:
            logger.info(f"Обработка задачи: {task_type.value}.{action}")
            if task_type == TaskType.VM:
                result = self._handle_vm_task(action, params)
            elif task_type == TaskType.NETWORK:
                result = self._handle_network_task(action, params)
            elif task_type == TaskType.SNAPSHOT:
                result = self._handle_snapshot_task(action, params)
            elif task_type == TaskType.STORAGE:
                result = self._handle_storage_task(action, params)
            elif task_type == TaskType.RESOURCE_POOL:
                result = self._handle_resource_pool_task(action, params)
            elif task_type == TaskType.STATS:
                result = self._handle_stats_task(action, params)
            else:

                return {
                    "success": False,
                    "result": "Unknown task type",
                    "timestamp": datetime.now().isoformat(),
                }

            return {
                "success": True,
                "result": (
                    orjson.dumps(result)
                    if isinstance(result, dict)
                    else result.model_dump_json()
                ),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Ошибка обработки задачи: {e}", exc_info=True)
            return {
                "success": False,
                "result": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def _handle_vm_task(self, action: str, params: dict) -> VmMessage:
        """Обработка задач ВМ"""
        if action == "create":
            # Создание ВМ
            vm_config = VMCreateRequest(**params)
            result = self.vm_manager.create_vm(vm_config)
            if hasattr(result, "model_dump"):
                return result
            return result

        elif action == "start":
            # Запуск ВМ
            vm_name = params["vm_name"]
            return self.vm_manager.start_vm(vm_name)

        elif action == "stop":
            # Остановка ВМ
            vm_name = params["vm_name"]
            force = params.get("force", False)
            return self.vm_manager.shutoff_vm(vm_name, force)

        elif action == "delete":
            # Удаление ВМ
            vm_name = params["vm_name"]
            delete_disks = params.get("delete_disks", False)
            delete_nvram = params.get("delete_nvram", True)
            return self.vm_manager.delete_vm(vm_name, delete_disks, delete_nvram)

        elif action == "edit":
            # Редактирование ВМ
            vm_name = params["vm_name"]
            vm_update = VmUpdateRequest(**params.get("update_params", {}))
            return self.vm_manager.edit_vm(vm_name, vm_update)

        elif action == "clone":
            # Клонирование ВМ
            source_name = params["source_vm"]
            new_name = params["new_name"]
            result = self.vm_manager.clone_vm(source_name, new_name)
            return result

        elif action == "migrate":
            # Миграция ВМ без дисков(ожидаем что используется HA с NFS хранилищем)
            vm_name = params["vm_name"]
            dest_uri = params["dest_uri"]
            live = params.get("live") if params.get("live") else False
            undefine_source = (
                params.get("undefine_source")
                if params.get("undefine_source")
                else False
            )
            result = self.vm_manager.migrate_vm(
                vm_name, dest_uri, live, undefine_source
            )
            return result

        elif action == "list":
            # Список ВМ
            only_active = params.get("only_active", False)
            vms = self.vm_manager.list_vms(only_active)
            return vms

        elif action == "info":
            # Информация о ВМ
            vm_name = params["vm_name"]
            result = self.vm_manager.get_vm_by_name(vm_name)
            return result

        elif action == "attach_iso":
            # Подключение ISO
            vm_name = params["vm_name"]
            iso_path = params["iso_path"]
            bus_type = params.get("bus_type", "ide")
            target_dev = params.get("target_dev")
            return self.vm_manager.attach_iso_to_vm(
                vm_name, iso_path, bus_type, target_dev
            )

        else:
            raise ValueError(f"Unknown VM action: {action}")

    def _handle_network_task(self, action: str, payload: dict) -> NetworkMessage:
        """Обработка сетевых задач"""

        if action == "create":
            # Создание сети
            params = NetworkParameters(**payload)
            return self.net_manager.create_network(params)

        elif action == "delete":
            # Удаление сети
            network_name = payload["network_name"]
            force = payload.get("force", False)
            approve_admin = payload.get("approve_admin", False)
            return self.net_manager.delete_network(network_name, force, approve_admin)

        elif action == "edit":
            # Редактирование сети
            network_name = payload["network_name"]
            params = NetworkParameters(**payload.get("params", {}))
            return self.net_manager.edit_network(network_name, params)

        elif action == "list":
            # Список сетей
            return self.net_manager.list_all_networks()

        elif action == "info":
            # Информация о сети
            network_name = payload["network_name"]
            return self.net_manager.get_network_info(network_name)

        elif action == "start":
            # Запуск сети
            network_name = payload["network_name"]
            result = self.net_manager.start_network(network_name)
            return result

        elif action == "stop":
            # Остановка сети
            network_name = payload["network_name"]
            return self.net_manager.stop_network(network_name)

        elif action == "restart":
            # Перезапуск сети
            network_name = payload["network_name"]
            force = payload.get("force", False)
            return self.net_manager.restart_network(network_name, force)

        else:
            raise ValueError(f"Unknown network action: {action}")

    def _handle_snapshot_task(self, action: str, payload: dict) -> SnapshotMessage:
        """Обработка задач снапшотов"""

        if action == "create":
            # Создание снапшота
            snapshot_request = SnapshotCreateRequest(**payload)
            return self.snapshot_manager.create_snapshot(snapshot_request).model_dump()

        elif action == "delete":
            # Удаление снапшота
            vm_name = payload["vm_name"]
            snapshot_name = payload["snapshot_name"]
            remove_children = payload.get("remove_children", False)
            return self.snapshot_manager.delete_snapshot(
                vm_name, snapshot_name, remove_children
            )

        elif action == "revert":
            # Восстановление снапшота
            vm_name = payload["vm_name"]
            snapshot_name = payload["snapshot_name"]
            return self.snapshot_manager.revert_to_snapshot(vm_name, snapshot_name)

        elif action == "list":
            # Список снапшотов ВМ
            vm_name = payload["vm_name"]
            return self.snapshot_manager.snapshots_by_vm_name(vm_name)

        elif action == "clone":
            # Клонирование ВМ из снапшота
            clone_request = SnapshotCloneRequest(**payload)
            return self.snapshot_manager.clone_vm_from_snapshot(clone_request)

        elif action == "info":
            # Информация о снапшоте
            vm_name = payload["vm_name"]
            snapshot_name = payload["snapshot_name"]
            return self.snapshot_manager.snapshot_by_name(vm_name, snapshot_name)

        else:
            raise ValueError(f"Unknown snapshot action: {action}")

    def _handle_storage_task(
        self, action: str, payload: dict
    ) -> Disk | bool | None | list[Disk]:
        """Обработка задач хранилища"""

        if action == "create_disk":
            # Создание диска
            disk_create = DiskCreate(**payload)
            result = self.storage_manager.create_disk(disk_create)
            return result

        elif action == "delete_disk":
            # Удаление диска
            disk_path = payload["disk_path"]
            success = self.storage_manager.delete_disk(disk_path)
            return success

        elif action == "attach_disk":
            # Подключение диска к ВМ
            disk_attach = DiskAttach(**payload)
            result = self.storage_manager.attach_disk(disk_attach)
            return result.model_dump()

        elif action == "detach_disk":
            # Отключение диска от ВМ
            disk_detach = DiskDetach(**payload)
            success = self.storage_manager.detach_disk(disk_detach)
            return success

        elif action == "list_disks":
            # Список дисков
            query = payload.get("query")
            disks = self.storage_manager.list_disks(query)
            return disks

        elif action == "extend_disk":
            # Расширение диска
            disk_name = payload["disk_name"]
            path = payload.get("path")
            disk_format = payload.get("disk_format")
            new_size_gb = payload["new_size_gb"]

            disk = self.storage_manager.extend_disk(
                new_size_gb, path, disk_name, disk_format
            )
            return disk

        elif action == "clone_disk":
            # Клонирование диска
            disk_name = payload["disk_name"]
            path = payload["path"]
            disk_format = payload["disk_format"]
            target_name = payload["target_name"]

            disk = self.storage_manager.clone_disk(
                disk_name, path, disk_format, target_name
            )
            return disk
        else:
            raise ValueError(f"Unknown storage action: {action}")

    def _handle_resource_pool_task(
        self, action: str, payload: dict
    ) -> RpMessage | list[ResourcePoolVirtual]:
        """Обработка задач ресурсных пулов"""

        if action == "create":
            # Создание ресурсного пула
            create_rp = ResourcePoolVirtualCreate(**payload)
            result = self.balansir.create_virtual_resource_pool(create_rp)
            return result

        elif action == "edit":
            # Редактирование ресурсного пула
            edit_rp = ResourcePoolVirtualEdit(**payload)
            result = self.balansir.edit_virtual_resource_pool(edit_rp)
            return result

        elif action == "delete":
            # Удаление ресурсного пула
            name = payload["name"]
            force = payload.get("force", False)
            result = self.balansir.delete_virtual_resource_pool(name, force)
            return result

        elif action == "list":
            # Список ресурсных пулов
            name_filter = payload.get("name")
            cpu_filter = payload.get("cpu_core_limit")
            ram_filter = payload.get("ram_limit_bytes")
            storage_filter = payload.get("storage_type")

            pools = self.balansir.get_virtual_resource_pool_list(
                name=name_filter,
                cpu_core_limit=cpu_filter,
                ram_limit_bytes=ram_filter,
                storage_type=storage_filter,
            )
            return pools

        elif action == "info":
            # Информация о ресурсном пуле
            name = payload["name"]
            result = self.balansir.get_virtual_resource_pool_by_name(name)
            return result

        else:
            raise ValueError(f"Unknown resource pool action: {action}")

    @staticmethod
    def _handle_stats_task(action: str, payload: dict) -> dict[str, Any]:
        """Обработка задач статистики"""
        if action == "vm_stats":
            # Получение статистики ВМ
            vm_name = payload["vm_name"]
            interval = payload.get("interval", 2)

            monitor = VMLiveMonitor(vm_name, interval)
            stats_data = monitor.used_ram_and_cpu()

            if stats_data:
                return stats_data.model_dump()
            return {"error": "Failed to get VM stats"}

        elif action == "monitor":
            # Мониторинг ВМ в реальном времени
            vm_name = payload["vm_name"]
            duration = payload.get("duration", 60)
            interval = payload.get("interval", 2)

            monitor = VMLiveMonitor(vm_name, interval)

            # Собираем статистику за указанное время
            stats_history = []
            start_time = time.time()

            while time.time() - start_time < duration:
                stats = monitor.used_ram_and_cpu()
                if stats:
                    stats_history.append(stats.model_dump())
                time.sleep(interval)

            return {
                "vm_name": vm_name,
                "duration": duration,
                "interval": interval,
                "stats": stats_history,
            }

        else:
            raise ValueError(f"Unknown stats action: {action}")


class TaskWorker(threading.Thread):
    """
    Воркер для обработки задач из очереди
    """

    def __init__(
        self,
        name: str,
        queue_manager: RedisTaskManager,
        task_handler: TaskHandler,
        stop_event: threading.Event,
    ):
        """
        Инициализация воркера

        Args:
            name: Имя воркера
            queue_manager: Менеджер очереди
            task_handler: Обработчик задач
            stop_event: Событие для остановки
        """
        super().__init__(
            name=name, daemon=True
        )  # daemon=True означает что поток будет завершен только при завершении главного потока
        self.queue_manager = queue_manager
        self.task_handler = task_handler
        self.stop_event = stop_event
        self.processing_task = False
        self.current_request_id = None

    def run(self):
        """Основной цикл работы воркера"""
        logger.info(f"Над вашей задачей трудиться {self.name}")

        while not self.stop_event.is_set():
            try:
                task = self.queue_manager.execute_task()

                if not task:
                    time.sleep(3)
                    continue

                self.processing_task = True
                self.current_request_id = task.request_id

                logger.info(f"Воркер {self.name} обрабатывает задачу {task.request_id}")

                # Публикуем уведомление о начале обработки
                self.queue_manager.publish_notification(
                    notification_type=TaskNotificationType.STATUS_CHANGE,
                    request_id=task.request_id,
                    task_type=task.task_type,
                    status=TaskStatus.PROCESSING,
                    data={"worker": self.name},
                )

                try:
                    result = self.task_handler.handle_task(
                        task_type=task.task_type,
                        action=task.action,
                        params=task.params,
                    )
                    handle_result = (
                        orjson.loads(result.get("result"))
                        if isinstance(result.get("result"), str)
                        else result.get("result")
                    )

                    if result.get("success", False):
                        result = TaskResponse(
                            request_id=task.request_id,
                            task=task,
                            result=(
                                orjson.loads(handle_result)
                                if not isinstance(handle_result, dict)
                                else handle_result
                            ),
                            status=TaskStatus.COMPLETED,
                            started_at=task.created_at,
                            completed_at=datetime.now(),
                        )
                        self.queue_manager.complete_task(result)
                        logger.info(f"Задача {task.request_id} успешно завершена")
                    else:
                        result = TaskResponse(
                            request_id=task.request_id,
                            task=task,
                            result=handle_result,
                            status=TaskStatus.FAILED,
                            started_at=task.created_at,
                            completed_at=datetime.now(),
                        )
                        self.queue_manager.complete_task(result)
                        logger.error(
                            f"Задача {task.request_id} завершена с ошибкой: {result.get('error')}"
                        )

                except Exception as e:
                    result = TaskResponse(
                        request_id=task.request_id,
                        task=task,
                        result={"error": str(e)},
                        status=TaskStatus.FAILED,
                        started_at=task.created_at,
                        completed_at=datetime.now(),
                    )
                    logger.error(
                        f"Ошибка обработки задачи {task.request_id}: {e}", exc_info=True
                    )
                    self.queue_manager.complete_task(result)

                finally:
                    self.processing_task = False
                    self.current_request_id = None

            except Exception as e:
                logger.error(f"Ошибка воркера {self.name}: {e}", exc_info=True)
                time.sleep(5)

        logger.info(f"Воркер {self.name} остановлен")
