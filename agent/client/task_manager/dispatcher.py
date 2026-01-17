import asyncio
import json
import logging
import signal
import sys
import threading
import time

from agent.client.task_manager.models import Task, TaskType
from ctl_queue import RedisTaskManager
from worker import TaskWorker, TaskHandler
import uuid

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Dispatcher")


class TaskDispatcher:
    """
    Диспетчер задач для управления воркерами и распределения задач
    """

    def __init__(self, queue_manager: RedisTaskManager, max_workers_per_type: int = 3):
        """
        Инициализация диспетчера

        Args:
            queue_manager: Менеджер очередей Redis
            max_workers_per_type: Максимальное количество воркеров на тип задачи
        """
        self.queue_manager = queue_manager
        self.max_workers_per_type = max_workers_per_type
        self.workers: dict[TaskType, list[TaskWorker]] = {}
        self.running = False
        self.stop_event = threading.Event()
        self.task_handler = TaskHandler()

    def start(self):
        """Запуск диспетчера и всех воркеров"""
        if self.running:
            logger.warning("Диспетчер уже запущен")
            return

        logger.info("Запуск диспетчера задач...")
        self.running = True
        self.stop_event.clear()

        # Создаем воркеры для каждого типа задач
        for task_type in TaskType:
            self.workers[task_type] = []

            for i in range(self.max_workers_per_type):
                worker_name = f"Worker-{task_type.value}-{i + 1}"
                worker = TaskWorker(
                    name=worker_name,
                    task_type=task_type,
                    queue_manager=self.queue_manager,
                    task_handler=self.task_handler,
                    stop_event=self.stop_event
                )
                self.workers[task_type].append(worker)
                worker.start()
                logger.info(f"Запущен воркер: {worker_name}")

        logger.info(f"Диспетчер запущен с {len(TaskType)} типами задач")

    def stop(self):
        """Остановка диспетчера и всех воркеров"""
        if not self.running:
            return

        logger.info("Остановка диспетчера задач...")
        self.running = False
        self.stop_event.set()

        # Ждем завершения всех воркеров
        for task_type, workers in self.workers.items():
            for worker in workers:
                worker.join(timeout=5)
                if worker.is_alive():
                    logger.warning(f"Воркер {worker.name} не завершился вовремя")

        logger.info("Диспетчер остановлен")

    def get_worker_stats(self) -> dict:
        """Получение статистики по воркерам"""
        stats = {
            "total_workers": 0,
            "active_workers": 0,
            "by_type": {}
        }

        for task_type, workers in self.workers.items():
            active = sum(1 for w in workers if w.is_alive() and w.processing_task)
            stats["by_type"][task_type.value] = {
                "total": len(workers),
                "active": active,
                "workers": [
                    {
                        "name": w.name,
                        "alive": w.is_alive(),
                        "processing": w.processing_task,
                        "current_task": w.current_request_id
                    }
                    for w in workers
                ]
            }
            stats["total_workers"] += len(workers)
            stats["active_workers"] += active

        return stats

    def submit_task(self, task: Task, queue_name: str | None = None) -> str:
        """
        Отправка задачи в очередь
        """
        request_id = f"task_{uuid.uuid4().hex[:16]}"
        params = {"request_id": request_id,
                  "task_type": task.task_type.value,
                  "params": task.params,
                  "action": task.action}
        success = self.queue_manager.add_task(params, queue_name)

        if success:
            logger.info(f"Задача {request_id} типа {task.task_type.value} отправлена в очередь")
            return request_id
        else:
            logger.error(f"Ошибка отправки задачи {request_id} в очередь")
            raise Exception("Failed to enqueue task")

    def cancel_task(self, request_id: str) -> int:
        """Отмена задачи"""
        return self.queue_manager.delete_task(request_id)


class AsyncTaskDispatcher:
    """
    Асинхронный диспетчер задач
    """

    def __init__(self, queue_manager: RedisTaskManager):
        self.queue_manager = queue_manager
        self.task_handler = TaskHandler()
        self.running = False

    async def start(self):
        """Запуск асинхронного диспетчера"""
        self.running = True
        logger.info("Запуск асинхронного диспетчера...")

        # Создаем задачи для каждого типа
        tasks = []
        for task_type in TaskType:
            task = asyncio.create_task(self._process_tasks(task_type))
            tasks.append(task)

        # Ожидаем завершения всех задач
        await asyncio.gather(*tasks)

    async def _process_tasks(self, task_type: TaskType):
        """Обработка задач определенного типа"""
        while self.running:
            try:
                # Получаем задачу из очереди
                task_data = self.queue_manager.execute_task(task_type)

                if not task_data:
                    await asyncio.sleep(1)
                    continue

                request_id, task = task_data
                logger.info(f"Обработка задачи {request_id} типа {task_type.value}")

                # Обрабатываем задачу
                result = await self.task_handler.handle_task_async(
                    task_type=task_type,
                    action=task.action,
                    payload=task.payload,
                )
                error = True if result.get("success") else False
                result = json.dumps(result)

                # Сохраняем результат
                self.queue_manager.complete_task(request_id, result, error)

                logger.info(f"Задача {request_id} завершена")

            except Exception as e:
                logger.error(f"Ошибка обработки задачи: {e}")
                await asyncio.sleep(1)

    def stop(self):
        """Остановка диспетчера"""
        self.running = False


def main():
    """Основная функция запуска диспетчера"""
    # Создаем менеджер очереди
    queue_manager = RedisTaskManager()

    # Создаем диспетчер
    dispatcher = TaskDispatcher(queue_manager, max_workers_per_type=2)

    # Обработка сигналов остановки
    def signal_handler(sig, frame):
        logger.info("Получен сигнал остановки")
        dispatcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Запускаем диспетчер
        dispatcher.start()

        # Пример отправки тестовой задачи
        logger.info("Отправка тестовой задачи...")

        test_task = Task(
            task_type=TaskType.VM,
            action="create",
            params={
                "name": "test-vm-dispatcher",
                "memory_mb": 1024,
                "vcpus": 2
            }
        )

        request_id = dispatcher.submit_task(test_task)
        logger.info(f"Тестовая задача отправлена с ID: {request_id}")

        # Мониторим статус
        while True:
            stats = dispatcher.get_worker_stats()
            logger.info(f"Статистика воркеров: {stats['active_workers']}/{stats['total_workers']} активны")

            # Проверяем статус тестовой задачи
            response = dispatcher.queue_manager.get_task_status(request_id)
            if response and response in ["completed", "failed", "cancelled"]:
                logger.info(f"Тестовая задача завершена со статусом: {response}")
                break

            time.sleep(5)

        # Держим диспетчер запущенным
        logger.info("Диспетчер работает... Нажмите Ctrl+C для остановки")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Остановка по запросу пользователя")
    except Exception as e:
        logger.error(f"Ошибка в работе диспетчера: {e}")
    finally:
        dispatcher.stop()


if __name__ == "__main__":
    main()