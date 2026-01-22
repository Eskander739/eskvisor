import json
import os

import redis

from agent.client.task_manager.models import TaskStatus, TaskInfo, Task, TaskResponse, TaskNotification, \
    TaskNotificationType, TaskType


class RedisTaskManager:
    """
    Класс для управления задачами в системе Redis


    До обработки:
    main_queue:      [task3, task2, task1]
    processing_queue: []

    execute_task (RPOPLPUSH):
    main_queue:      [task3, task2]
    processing_queue: [task1]  ← задача перемещена сюда

    После обработки (complete_task):
    main_queue:      [task3, task2]
    processing_queue: []  ← задача удалена отсюда
    """

    def __init__(
        self,
    ):
        """
        Инициализация подключения к Redis.

        host: Хост Redis
        port: Порт Redis
        db: Номер базы данных

        """
        self.host = os.environ.get("REDIS_HOST")
        self.port = os.environ.get("REDIS_PORT")
        self.db = os.environ.get("REDIS_DB_NUMBER")
        self.password = None
        # self.password = os.environ.get("REDIS_DB_PASSWORD")
        self.queue_name = "task_queue"
        self.processing_queue_name = "task_processing_queue"
        self.notification_channel = "task_notifications"

    def redis_session(self, db: str | None = None):
        if self.port is None:
            raise ValueError("Порт не может быть пустым")
        password = {"password": self.password} if self.password else {}
        return redis.Redis(
            host=self.host,
            port=int(self.port),
            db=int(db) if db else self.db,
            decode_responses=True,  # Автоматическое декодирование в строки
            **password
        )

    def get_task_len(self, queue_name: str | None = None) -> int:
        """
        Возвращает список всех задач в Redis
        """
        queue_name = self.queue_name if queue_name is None else queue_name
        redis_connect = self.redis_session()
        task_len = redis_connect.llen(queue_name)
        return task_len

    def get_all_tasks(
        self, queue_name: str | None = None, start: int = 0, end: int = -1
    ) -> list[str]:
        """
        Возвращает список всех задач в Redis
        """
        queue_name = self.queue_name if queue_name is None else queue_name
        redis_connect = self.redis_session()
        tasks = redis_connect.lrange(queue_name, start, end)
        return [current_task for current_task in tasks]

    def get_process_tasks(
        self, processing_queue_name: str | None = None, start: int = 0, end: int = -1
    ) -> list[str]:
        """
        Возвращает список всех задач в работе в Redis
        """
        queue_name = (
            self.processing_queue_name
            if processing_queue_name is None
            else processing_queue_name
        )
        redis_connect = self.redis_session()
        tasks = redis_connect.lrange(queue_name, start, end)
        return [current_task for current_task in tasks]

    def get_task_info(self, request_id: str) -> TaskInfo | None:
        status = self.get_task_status(request_id)
        if status is None:
            return None
        result = self.get_task_status(request_id)
        error = self.get_task_error(request_id)
        return TaskInfo(status=status, result=result, error=error)

    def get_task_status(self, request_id: str) -> TaskStatus | None:
        redis_connect = self.redis_session()
        task_status = redis_connect.hget("status", request_id)
        if task_status is not None:
            return TaskStatus(task_status)
        return task_status

    def get_task_result(self, request_id: str) -> str:
        redis_connect = self.redis_session()
        task_result = redis_connect.hget("result", request_id)
        return task_result if task_result else "not_found"

    def get_task_error(self, request_id: str) -> bool | None:
        redis_connect = self.redis_session()
        task_error = redis_connect.hget("error", request_id)
        if task_error is not None:
            return task_error == "true"
        return None

    def set_status(self, request_id: str, task_status: TaskStatus):
        self.redis_session().hset(
            "status", request_id, task_status.value
        )

    def set_result(self, request_id: str, result: str):
        self.redis_session().hset("result", request_id, result)

    def set_error(self, request_id: str, error: bool):
        error = "null" if error else "true"
        self.redis_session().hset("error", request_id, error)

    def add_task(self, task: Task, queue_name: str | None = None):
        """
        Добавляет задачу в очередь и публикует уведомление
        """
        queue_name = self.queue_name if queue_name is None else queue_name
        redis_connect = self.redis_session()

        # Устанавливаем начальные статусы
        self.set_status(task.request_id, TaskStatus.PENDING)
        self.set_result(task.request_id, "null")
        self.set_error(task.request_id, False)

        # Публикуем уведомление о создании задачи
        self.publish_notification(
            notification_type=TaskNotificationType.TASK_CREATED,
            request_id=task.request_id,
            task_type=task.task_type,
            status=TaskStatus.PENDING,
            data={"action": task.action}
        )

        # Добавляем в очередь
        return redis_connect.lpush(queue_name, task.model_dump_json())

    def execute_task(
            self, queue_name: str | None = None, processing_queue_name: str | None = None
    ) -> Task | None:
        """
        Выполнить задачу с публикацией уведомлений
        """
        queue_name = self.queue_name if queue_name is None else queue_name
        processing_queue_name = (
            self.processing_queue_name
            if processing_queue_name is None
            else processing_queue_name
        )
        redis_connect = self.redis_session()
        cached_data = redis_connect.rpoplpush(queue_name, processing_queue_name)

        if cached_data:
            task = Task(**json.loads(json.loads(json.dumps(cached_data))))

            # Устанавливаем статус и публикуем уведомление
            self.set_status(task.request_id, TaskStatus.PROCESSING)
            self.publish_notification(
                notification_type=TaskNotificationType.STATUS_CHANGE,
                request_id=task.request_id,
                task_type=task.task_type,
                status=TaskStatus.PROCESSING
            )

            return task

        return None

    def complete_task(
            self, result: TaskResponse, processing_queue_name: str | None = None
    ) -> int:
        """
        Завершить выполнение задачи с публикацией уведомлений
        """
        if isinstance(result, dict):
            result = json.dumps(result)
        elif result is None:
            result = "null"

        processing_queue_name = (
            self.processing_queue_name
            if processing_queue_name is None
            else processing_queue_name
        )
        redis_connect = self.redis_session()

        # Публикуем уведомление перед завершением
        if result.status == TaskStatus.COMPLETED:
            self.publish_notification(
                notification_type=TaskNotificationType.RESULT_READY,
                request_id=result.request_id,
                task_type=result.task.task_type,
                status=TaskStatus.COMPLETED,
                data={"result": result.result}
            )
        else:
            self.publish_notification(
                notification_type=TaskNotificationType.ERROR_OCCURRED,
                request_id=result.request_id,
                task_type=result.task.task_type,
                status=TaskStatus.FAILED,
                error=str(result.result.get("error", "Unknown error"))
                if result.result and isinstance(result.result, dict)
                else str(result.result)
            )

        # Устанавливаем финальный статус
        if result.status == TaskStatus.COMPLETED:
            self.set_status(result.request_id, TaskStatus.COMPLETED)
        else:
            self.set_status(result.request_id, TaskStatus.FAILED)

        self.set_result(result.request_id, result.model_dump_json())

        # Публикуем финальное уведомление
        self.publish_notification(
            notification_type=TaskNotificationType.TASK_COMPLETED,
            request_id=result.request_id,
            task_type=result.task.task_type,
            status=result.status
        )

        # Удаляем из очереди обработки
        return redis_connect.lrem(processing_queue_name, 1, result.request_id)

    def delete_task(self, request_id: str, queue_name: str | None = None) -> int:
        """
        Удалить задачу(аварийная операция)
        """

        queue_name = self.queue_name if queue_name is None else queue_name
        redis_connect = self.redis_session()
        return redis_connect.lrem(queue_name, 1, request_id)

    def delete_all_tasks(self, queue_name: str | None = None) -> int:
        """
        Удалить все задачи
        """
        queue_name = self.queue_name if queue_name is None else queue_name
        redis_connect = self.redis_session()
        deleted_tasks = redis_connect.delete(queue_name)
        return deleted_tasks

    def publish_notification(
            self,
            notification_type: TaskNotificationType,
            request_id: str,
            task_type: TaskType,
            status: TaskStatus,
            data: dict | None = None,
            error: str | None = None
    ) -> int:
        """
        Публикация уведомления в канал Pub/Sub
        """
        notification = TaskNotification(
            notification_type=notification_type,
            request_id=request_id,
            task_type=task_type,
            status=status,
            data=data,
            error=error
        )

        redis_connect = self.redis_session()
        return redis_connect.publish(
            self.notification_channel,
            notification.model_dump_json()
        )

    def subscribe_to_notifications(self) -> redis.client.PubSub:
        """
        Подписка на уведомления о задачах
        """
        redis_connect = self.redis_session()
        pubsub = redis_connect.pubsub()
        pubsub.subscribe(self.notification_channel)
        return pubsub


# Пример использования новых методов
if __name__ == "__main__":
    rtm = RedisTaskManager()

    # jwt_manager.add_task(ADD_VM)
    # jwt_manager.add_task(START_VM)
    # jwt_manager.add_task(DELETE_VM)
    # rtm.delete_all_tasks("task_processing_queue")
    # rtm.delete_all_tasks()
    for task in rtm.get_process_tasks():
        print("ЗАДАЧА В ПРОЦЕССЕ: ", task)
    for task in rtm.get_all_tasks():
        print("ЗАДАЧА В ОЖИДАНИИ: ", task)
        # rtm.execute_task()
