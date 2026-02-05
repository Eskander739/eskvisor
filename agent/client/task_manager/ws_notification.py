import asyncio

import orjson
from fastapi import WebSocket
from agent.client.logger_config import DefaultLogger
from agent.client.task_manager.ctl_queue import RedisTaskManager
from agent.client.task_manager.models import TaskNotification


class WebSocketNotificationHandler:
    """Обработчик WebSocket уведомлений"""

    def __init__(self, queue_manager: RedisTaskManager):
        self.queue_manager = queue_manager
        self.logger = DefaultLogger("WSNotification")
        self.active_connections: set[WebSocket] = set()
        self.pubsub = None
        self.listening_task = None
        self.running = False

    async def connect(self, websocket: WebSocket):
        """Подключение клиента WebSocket"""
        await websocket.accept()
        self.active_connections.add(websocket)

        # Запускаем прослушивание при первом подключении
        if not self.running:
            await self.start_listening()

        self.logger.info(
            f"Новое WebSocket подключение. Всего: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Отключение клиента WebSocket"""
        try:
            self.active_connections.remove(websocket)
            self.logger.info(
                f"WebSocket отключен. Осталось: {len(self.active_connections)}"
            )

            # Если нет активных подключений, останавливаем прослушивание
            if not self.active_connections and self.running:
                self.stop_listening()
        except Exception as err:
            self.logger.info(f"Ошибка отключения WebSocket соединения: {err}")

    async def start_listening(self):
        """Запуск прослушивания уведомлений из Redis"""
        try:
            if self.running:
                return

            self.logger.info("Запуск прослушивания Redis Pub/Sub...")
            self.running = True

            # Создаем PubSub подключение
            self.pubsub = self.queue_manager.subscribe_to_notifications()

            # Запускаем фоновую задачу для обработки сообщений
            self.listening_task = asyncio.create_task(self._process_notifications())
            self.logger.info("Прослушивание Redis Pub/Sub запущено")

        except Exception as e:
            self.logger.error(f"Ошибка запуска прослушивания: {e}")
            self.running = False

    def stop_listening(self):
        """Остановка прослушивания уведомлений"""
        self.logger.info("Остановка прослушивания Redis Pub/Sub...")
        self.running = False

        if self.pubsub:
            try:
                self.pubsub.unsubscribe()
                self.pubsub.close()
            except Exception as e:
                self.logger.error(f"Ошибка при закрытии PubSub: {e}")

        if self.listening_task:
            self.listening_task.cancel()

        self.pubsub = None
        self.logger.info("Прослушивание Redis Pub/Sub остановлено")

    async def _process_notifications(self):
        """Обработка уведомлений из Redis Pub/Sub"""
        try:
            while self.running and self.pubsub:
                try:
                    # Получаем сообщение с таймаутом, чтобы можно было проверить self.running
                    message = self.pubsub.get_message(timeout=1.0)

                    if message and message["type"] == "message":
                        self.logger.debug(f"Получено сообщение из Redis: {message}")

                        try:
                            # Валидируем уведомление через Pydantic
                            notification_data = orjson.loads(message["data"])
                            notification = TaskNotification(**notification_data)

                            # Отправляем всем подключенным клиентам
                            await self.broadcast_notification(notification)

                        except orjson.JSONDecodeError as e:
                            self.logger.error(
                                f"Ошибка декодирования JSON: {e}, данные: {message['data']}"
                            )
                        except Exception as e:
                            self.logger.error(f"Ошибка обработки уведомления: {e}")

                    # Небольшая пауза для предотвращения busy waiting
                    await asyncio.sleep(0.1)

                except Exception as e:
                    self.logger.error(f"Ошибка при получении сообщения: {e}")
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            self.logger.info("Задача прослушивания отменена")
            raise
        except Exception as e:
            self.logger.error(f"Критическая ошибка в задаче прослушивания: {e}")
        finally:
            self.running = False

    async def broadcast_notification(self, notification: TaskNotification):
        """Отправка уведомления всем подключенным клиентам"""
        if not self.active_connections:
            return

        disconnected = set()
        try:
            notification_json = notification.model_dump_json()

            for connection in self.active_connections:
                try:
                    await connection.send_text(notification_json)
                except Exception as e:
                    self.logger.error(f"Ошибка отправки клиенту: {e}")
                    disconnected.add(connection)

            for connection in disconnected:
                self.disconnect(connection)

        except Exception as e:
            self.logger.error(f"Ошибка при подготовке уведомления: {e}")
