import logging
import random
import signal
import sys
import threading
import time

from agent.client.task_manager.ctl_queue import RedisTaskManager
from agent.client.task_manager.models import (
    Task,
    TaskType,
    TaskAdd,
    WorkerModel,
    WorkerStats,
)
import uuid

from agent.client.task_manager.worker import TaskWorker, TaskHandler

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Dispatcher")
GAME_OF_THRONES = [
    "Петир Бейлиш Мизинец",
    "Ходор",
    "Сандор Пёс Клиган",
    "Санса Старк",
    "Сэмвелл Тарли",
    "Эддард Нед Старк",
    "Джон Сноу",
    "Роберт Баратеон",
    "Станис Баратеон",
    "Дейенерис Таргариен",
    "Тормунд Великанья Смерть",
]
random.shuffle(GAME_OF_THRONES)


class TaskDispatcher:
    """
    Диспетчер задач для управления воркерами и распределения задач
    """

    def __init__(self, queue_manager: RedisTaskManager, worker_count: int = 12):
        """
        Инициализация диспетчера

        Args:
            queue_manager: Менеджер очередей Redis
            worker_count: количество работников
        """
        self.queue_manager = queue_manager
        self.worker_count = worker_count
        self.workers: list[TaskWorker] = []
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

        for i in range(self.worker_count):
            worker_name = GAME_OF_THRONES[i]
            worker = TaskWorker(
                name=worker_name,
                queue_manager=self.queue_manager,
                task_handler=self.task_handler,
                stop_event=self.stop_event,
            )
            self.workers.append(worker)
            worker.start()

        logger.info(f"Диспетчер запущен с {len(TaskType)} типами задач")

    def stop(self):
        """Остановка диспетчера и всех воркеров"""
        if not self.running:
            return

        logger.info("Остановка диспетчера задач...")
        self.running = False
        self.stop_event.set()

        # Ждем завершения всех воркеров
        for worker in self.workers:
            worker.join(timeout=5)
            if worker.is_alive():
                logger.warning(f"Воркер {worker.name} не завершился вовремя")

        logger.info("Диспетчер остановлен")

    def get_worker_stats(self) -> WorkerStats:
        """Получение статистики по воркерам"""

        stats = WorkerStats(total_workers=len(self.workers))

        for worker in self.workers:
            stats.workers.append(
                WorkerModel(
                    name=worker.name,
                    alive=worker.is_alive(),
                    processing=worker.processing_task,
                    current_task=worker.current_request_id,
                )
            )
            if worker.is_alive():
                stats.active_workers += 1

        return stats

    def submit_task(self, task: TaskAdd, queue_name: str | None = None) -> str:
        """
        Отправка задачи в очередь
        """
        task = Task(
            request_id=str(uuid.uuid4()),
            task_type=task.task_type,
            action=task.action,
            params=task.params,
            created_at=task.created_at,
        )
        success = self.queue_manager.add_task(task, queue_name)

        if success:
            logger.info(
                f"Задача {task.request_id} типа {task.task_type.value} отправлена в очередь"
            )
            return task.request_id
        else:
            logger.error(f"Ошибка отправки задачи {task.request_id} в очередь")
            raise Exception("Failed to enqueue task")

    def cancel_task(self, request_id: str) -> int:
        """Отмена задачи"""
        return self.queue_manager.delete_task(request_id)


def main():
    """Основная функция запуска диспетчера"""
    queue_manager = RedisTaskManager()
    dispatcher = TaskDispatcher(queue_manager, worker_count=5)

    def signal_handler(sig, frame):
        logger.info("Получен сигнал остановки")
        dispatcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    try:

        dispatcher.start()
        logger.info("Отправка тестовой задачи...")
        while True:
            stats = dispatcher.get_worker_stats()
            logger.info(f"Всего работников: {stats.total_workers}")
            logger.info(f"Активные работники: {stats.active_workers}")

            for worker in stats.workers:
                logger.info(f"Работник: {worker.name}")
                logger.info(f"Активность: {worker.alive}")
                logger.info(f"Текущая задача: {worker.processing}")
                logger.info(f"Текущая задача: {worker.current_task}")
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Остановка по запросу пользователя")
    except Exception as e:
        logger.error(f"Ошибка в работе диспетчера: {e}")
    finally:
        dispatcher.stop()


if __name__ == "__main__":
    main()
    # request_id = dispatcher.submit_task(task) -> дергать для выполнения задач
