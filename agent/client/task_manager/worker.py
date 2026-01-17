import logging
import threading
import time
import uuid
from typing import Dict, Any
from datetime import datetime

from agent.client.hypervisor.libvirt.models.network import NetworkParameters
from agent.client.hypervisor.libvirt.models.snapshots import SnapshotCreateRequest, SnapshotCloneRequest
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest, VmUpdateRequest
from agent.client.hypervisor.libvirt.models.volume.balansir import ResourcePoolVirtualCreate, ResourcePoolVirtualEdit
from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate, DiskAttach, DiskDetach
from agent.ctl.proc.models import TaskType, Task
from ctl_queue import RedisTaskManager
from agent.client.hypervisor.libvirt.managers.vm import VmManager
from agent.client.hypervisor.libvirt.managers.network import NetworkManager
from agent.client.hypervisor.libvirt.managers.snapshot import SnapshotManager
from agent.client.hypervisor.libvirt.managers.storage import StorageManager
from agent.client.hypervisor.libvirt.managers.balansir import Balansir
from agent.client.hypervisor.libvirt.managers.vm_stats import VMLiveMonitor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Worker")


class TaskHandler:
    """
    Обработчик задач для выполнения операций с ВМ, сетями и т.д.
    """

    def __init__(self):
        self.handlers = {
            TaskType.VM: self._handle_vm_task,
            TaskType.NETWORK: self._handle_network_task,
            TaskType.SNAPSHOT: self._handle_snapshot_task,
            TaskType.STORAGE: self._handle_storage_task,
            TaskType.RESOURCE_POOL: self._handle_resource_pool_task,
            TaskType.STATS: self._handle_stats_task,
        }

    def handle_task(self, task_type: TaskType, action: str,
                    payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Основной метод обработки задачи

        Args:
            task_type: Тип задачи
            action: Действие (create, delete, update, etc.)
            payload: Данные задачи

        Returns:
            Результат выполнения
        """
        try:
            logger.info(f"Обработка задачи: {task_type.value}.{action}")

            # Получаем обработчик для типа задачи
            handler = self.handlers.get(task_type)
            if not handler:
                raise ValueError(f"No handler for task type: {task_type}")

            # Вызываем обработчик
            # result = handler(action, payload) # TODO: Доработать
            result = None

            return {
                "success": True,
                "result": result,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Ошибка обработки задачи: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def handle_task_async(self, task_type: TaskType, action: str,
                                payload: Dict[str, Any]) -> Dict[str, Any]:
        """Асинхронная версия обработки задачи"""
        # Для простоты используем синхронную версию
        # В реальном приложении можно сделать асинхронные вызовы
        return self.handle_task(task_type, action, payload)

    # ===== Обработчики для разных типов задач =====

    def _handle_vm_task(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка задач ВМ"""

        with VmManager() as vm_manager:

            if action == "create":
                # Создание ВМ
                vm_config = VMCreateRequest(**payload)
                result = vm_manager.create_vm(vm_config)

                if hasattr(result, "model_dump"):
                    return result.model_dump()
                return result

            elif action == "start":
                # Запуск ВМ
                vm_name = payload["vm_name"]
                return vm_manager.start_vm(vm_name).model_dump()

            elif action == "stop":
                # Остановка ВМ
                vm_name = payload["vm_name"]
                force = payload.get("force", False)
                return vm_manager.shutoff_vm(vm_name, force).model_dump()

            elif action == "delete":
                # Удаление ВМ
                vm_name = payload["vm_name"]
                delete_disks = payload.get("delete_disks", False)
                delete_nvram = payload.get("delete_nvram", True)
                return vm_manager.delete_vm(
                    vm_name, delete_disks, delete_nvram
                ).model_dump()

            elif action == "edit":
                # Редактирование ВМ
                vm_name = payload["vm_name"]
                vm_update = VmUpdateRequest(**payload.get("update_params", {}))
                return vm_manager.edit_vm(vm_name, vm_update).model_dump()

            elif action == "clone":
                # Клонирование ВМ
                source_name = payload["source_vm"]
                new_name = payload["new_name"]
                result = vm_manager.clone_vm(source_name, new_name)
                return result

            elif action == "list":
                # Список ВМ
                only_active = payload.get("only_active", False)
                vms = vm_manager.list_vms(only_active)
                return {"vms": [vm.model_dump() for vm in vms]}

            elif action == "info":
                # Информация о ВМ
                vm_name = payload["vm_name"]
                result = vm_manager.get_vm_by_name(vm_name)
                return result.model_dump()

            elif action == "attach_iso":
                # Подключение ISO
                vm_name = payload["vm_name"]
                iso_path = payload["iso_path"]
                bus_type = payload.get("bus_type", "ide")
                target_dev = payload.get("target_dev")
                return vm_manager.attach_iso_to_vm(
                    vm_name, iso_path, bus_type, target_dev
                ).model_dump()

            else:
                raise ValueError(f"Unknown VM action: {action}")

    def _handle_network_task(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка сетевых задач"""

        with NetworkManager() as network_manager:

            if action == "create":
                # Создание сети
                params = NetworkParameters(**payload)
                return network_manager.create_network(params).model_dump()

            elif action == "delete":
                # Удаление сети
                network_name = payload["network_name"]
                force = payload.get("force", False)
                approve_admin = payload.get("approve_admin", False)
                return network_manager.delete_network(
                    network_name, request_id, force, approve_admin
                ).model_dump()

            elif action == "edit":
                # Редактирование сети
                network_name = payload["network_name"]
                params = NetworkParameters(**payload.get("params", {}))
                return network_manager.edit_network(network_name, params).model_dump()

            elif action == "list":
                # Список сетей
                networks = network_manager.list_all_networks()
                return {"networks": [net.model_dump() for net in networks]}

            elif action == "info":
                # Информация о сети
                network_name = payload["network_name"]
                return network_manager.get_network_info(network_name).model_dump()

            elif action == "start":
                # Запуск сети
                network_name = payload["network_name"]
                network_manager.start_network(network_name)
                return {"success": True}

            elif action == "stop":
                # Остановка сети
                network_name = payload["network_name"]
                network_manager.stop_network(network_name)
                return {"success": True}

            elif action == "restart":
                # Перезапуск сети
                network_name = payload["network_name"]
                force = payload.get("force", False)
                return network_manager.restart_network(network_name, force).model_dump()

            else:
                raise ValueError(f"Unknown network action: {action}")

    def _handle_snapshot_task(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка задач снапшотов"""

        with SnapshotManager() as snapshot_manager:

            if action == "create":
                # Создание снапшота
                snapshot_request = SnapshotCreateRequest(**payload)
                return snapshot_manager.create_snapshot(snapshot_request).model_dump()

            elif action == "delete":
                # Удаление снапшота
                vm_name = payload["vm_name"]
                snapshot_name = payload["snapshot_name"]
                remove_children = payload.get("remove_children", False)
                return snapshot_manager.delete_snapshot(
                    vm_name, snapshot_name, request_id
                ).model_dump()

            elif action == "revert":
                # Восстановление снапшота
                vm_name = payload["vm_name"]
                snapshot_name = payload["snapshot_name"]
                return snapshot_manager.revert_to_snapshot(
                    vm_name, snapshot_name
                ).model_dump()

            elif action == "list":
                # Список снапшотов ВМ
                vm_name = payload["vm_name"]
                return snapshot_manager.snapshots_by_vm_name(vm_name).model_dump()

            elif action == "clone":
                # Клонирование ВМ из снапшота
                clone_request = SnapshotCloneRequest(**payload)
                return snapshot_manager.clone_vm_from_snapshot(clone_request).model_dump()

            elif action == "info":
                # Информация о снапшоте
                vm_name = payload["vm_name"]
                snapshot_name = payload["snapshot_name"]
                return snapshot_manager.snapshot_by_name(vm_name, snapshot_name).model_dump()

            else:
                raise ValueError(f"Unknown snapshot action: {action}")

    def _handle_storage_task(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка задач хранилища"""

        with StorageManager() as storage_manager:

            if action == "create_disk":
                # Создание диска
                disk_create = DiskCreate(**payload)
                result = storage_manager.create_disk(disk_create)

                if hasattr(result, "model_dump"):
                    return result.model_dump()
                elif hasattr(result, "disk_info"):
                    return {"disk": result.disk_info.model_dump()}
                return result

            elif action == "delete_disk":
                # Удаление диска
                disk_path = payload["disk_path"]
                success = storage_manager.delete_disk(disk_path)
                return {"success": success}

            elif action == "attach_disk":
                # Подключение диска к ВМ
                disk_attach = DiskAttach(**payload)
                result = storage_manager.attach_disk(disk_attach)
                return result.model_dump()

            elif action == "detach_disk":
                # Отключение диска от ВМ
                disk_detach = DiskDetach(**payload)
                success = storage_manager.detach_disk(disk_detach)
                return {"success": success}

            elif action == "list_disks":
                # Список дисков
                query = payload.get("query", {})
                disks = storage_manager.list_disks(query)
                return {"disks": [disk.model_dump() for disk in disks]}

            elif action == "extend_disk":
                # Расширение диска
                disk_name = payload["disk_name"]
                path = payload.get("path")
                disk_format = payload.get("disk_format")
                new_size_gb = payload["new_size_gb"]

                disk = storage_manager.extend_disk(
                    new_size_gb, path, disk_name, disk_format
                )
                if disk:
                    return disk.model_dump()
                return {"success": False}

            elif action == "clone_disk":
                # Клонирование диска
                disk_name = payload["disk_name"]
                path = payload["path"]
                disk_format = payload["disk_format"]
                target_name = payload["target_name"]

                disk = storage_manager.clone_disk(disk_name, path, disk_format, target_name)
                if disk:
                    return disk.model_dump()
                return {"success": False}

            else:
                raise ValueError(f"Unknown storage action: {action}")

    def _handle_resource_pool_task(self, action: str, payload: Dict[str, Any]) -> Dict[
        str, Any]:
        """Обработка задач ресурсных пулов"""

        with Balansir() as balansir:
            if action == "create":
                # Создание ресурсного пула
                create_rp = ResourcePoolVirtualCreate(**payload)
                result = balansir.create_virtual_resource_pool(create_rp)
                return result.model_dump()

            elif action == "edit":
                # Редактирование ресурсного пула
                edit_rp = ResourcePoolVirtualEdit(**payload)
                result = balansir.edit_virtual_resource_pool(edit_rp)
                return result.model_dump()

            elif action == "delete":
                # Удаление ресурсного пула
                name = payload["name"]
                force = payload.get("force", False)
                result = balansir.delete_virtual_resource_pool(name, force)
                return result.model_dump()

            elif action == "list":
                # Список ресурсных пулов
                name_filter = payload.get("name")
                cpu_filter = payload.get("cpu_core_limit")
                ram_filter = payload.get("ram_limit_bytes")
                storage_filter = payload.get("storage_type")

                pools = balansir.get_virtual_resource_pool_list(
                    name=name_filter,
                    cpu_core_limit=cpu_filter,
                    ram_limit_bytes=ram_filter,
                    storage_type=storage_filter
                )
                return {"pools": [pool.model_dump() for pool in pools]}

            elif action == "info":
                # Информация о ресурсном пуле
                name = payload["name"]
                result = balansir.get_virtual_resource_pool_by_name(name)
                return result.model_dump()

            else:
                raise ValueError(f"Unknown resource pool action: {action}")

    def _handle_stats_task(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
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
                "stats": stats_history
            }

        else:
            raise ValueError(f"Unknown stats action: {action}")


class TaskWorker(threading.Thread):
    """
    Воркер для обработки задач из очереди
    """

    def __init__(self, name: str, task_type: TaskType,
                 queue_manager: RedisTaskManager, task_handler: TaskHandler,
                 stop_event: threading.Event):
        """
        Инициализация воркера

        Args:
            name: Имя воркера
            task_type: Тип задач, которые обрабатывает воркер
            queue_manager: Менеджер очереди
            task_handler: Обработчик задач
            stop_event: Событие для остановки
        """
        super().__init__(name=name, daemon=True) # daemon=True означает что поток будет завершен только при завершении главного потока
        self.task_type = task_type
        self.queue_manager = queue_manager
        self.task_handler = task_handler
        self.stop_event = stop_event
        self.processing_task = False
        self.current_request_id = None

    def run(self):
        """Основной цикл работы воркера"""
        logger.info(f"Воркер {self.name} запущен для типа {self.task_type.value}")

        while not self.stop_event.is_set():
            try:
                # Получаем задачу из очереди
                task_data = self.queue_manager.execute_task(self.task_type)

                if not task_data:
                    # Нет задач, ждем
                    time.sleep(1)
                    continue

                request_id, task = task_data
                self.processing_task = True
                self.current_request_id = request_id

                logger.info(f"Воркер {self.name} обрабатывает задачу {request_id}")

                try:

                    # Обрабатываем задачу
                    result = self.task_handler.handle_task(
                        task_type=self.task_type,
                        action=task.action,
                        payload=task.payload,
                    )

                    # Обновляем прогресс

                    # Сохраняем результат
                    if result.get("success", False):
                        self.queue_manager.complete_task(
                            request_id,
                            result=result.get("result"),
                            error=False
                        )
                        logger.info(f"Задача {request_id} успешно завершена")
                    else:
                        self.queue_manager.complete_task(
                            request_id,
                            result=result.get("error"),
                            error=True
                        )
                        logger.error(f"Задача {request_id} завершена с ошибкой: {result.get('error')}")

                except Exception as e:
                    logger.error(f"Ошибка обработки задачи {request_id}: {e}", exc_info=True)
                    self.queue_manager.complete_task(request_id, result=str(e), error=True)

                finally:
                    self.processing_task = False
                    self.current_request_id = None

            except Exception as e:
                logger.error(f"Ошибка воркера {self.name}: {e}", exc_info=True)
                time.sleep(5)

        logger.info(f"Воркер {self.name} остановлен")


class WorkerPool:
    """
    Пул воркеров для управления несколькими воркерами
    """

    def __init__(self, queue_manager: RedisTaskManager,
                 workers_per_type: int = 3):
        self.queue_manager = queue_manager
        self.workers_per_type = workers_per_type
        self.task_handler = TaskHandler()
        self.stop_event = threading.Event()
        self.workers = {}

    def start(self):
        """Запуск пула воркеров"""
        for task_type in TaskType:
            self.workers[task_type] = []

            for i in range(self.workers_per_type):
                worker = TaskWorker(
                    name=f"Worker-{task_type.value}-{i + 1}",
                    task_type=task_type,
                    queue_manager=self.queue_manager,
                    task_handler=self.task_handler,
                    stop_event=self.stop_event
                )
                self.workers[task_type].append(worker)
                worker.start()

        logger.info(f"Пул воркеров запущен: {len(TaskType)} типов x {self.workers_per_type} воркеров")

    def stop(self):
        """Остановка пула воркеров"""
        logger.info("Остановка пула воркеров...")
        self.stop_event.set()

        for task_type, workers in self.workers.items():
            for worker in workers:
                worker.join(timeout=5)

        logger.info("Пул воркеров остановлен")

    def get_stats(self) -> Dict:
        """Получение статистики пула"""
        stats = {
            "total_workers": 0,
            "active_workers": 0,
            "by_type": {}
        }

        for task_type, workers in self.workers.items():
            active = sum(1 for w in workers if w.processing_task)
            stats["by_type"][task_type.value] = {
                "total": len(workers),
                "active": active,
                "idle": len(workers) - active
            }
            stats["total_workers"] += len(workers)
            stats["active_workers"] += active

        return stats


if __name__ == "__main__":
    # Пример использования воркера
    queue_mgr = RedisTaskManager()

    # Создаем пул воркеров
    worker_pool = WorkerPool(queue_mgr, workers_per_type=2)

    try:
        # Запускаем пул
        worker_pool.start()

        # Пример отправки тестовой задачи
        test_request = str(uuid.uuid4())
        test_task_info = Task(
            task_type=TaskType.VM,
            action="list",
            params={"only_active": True}
        )
        test_task = test_task_info.model_dump()
        test_task["request_id"] = test_request
        test_task["created_at"] = test_task_info.created_at.isoformat()

        # Отправляем задачу
        request_id = queue_mgr.add_task(test_task)
        print(f"Тестовая задача отправлена: {request_id}")

        # Ждем завершения
        while True:
            response = queue_mgr.get_task_info(test_request)
            if response and response.status.value in ["completed", "failed"]:
                print(f"Задача завершена: {response}")
                if response.result:
                    print(f"Результат: {response.result}")
                break
            time.sleep(1)

        # Показываем статистику
        stats = worker_pool.get_stats()
        print(f"Статистика воркеров: {stats}")

        # Держим пул запущенным
        input("Нажмите Enter для остановки...")

    except KeyboardInterrupt:
        print("Остановка по запросу пользователя")
    finally:
        worker_pool.stop()