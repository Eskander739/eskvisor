import asyncio
import json
import logging
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect
from starlette.templating import Jinja2Templates

from agent.client.task_manager.ctl_queue import RedisTaskManager
from agent.client.task_manager.models import TaskNotification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("WebSocketHandler")
templates = Jinja2Templates(directory="/templates")


class WebSocketNotificationHandler:
    """Обработчик WebSocket уведомлений"""

    def __init__(self, queue_manager: RedisTaskManager):
        self.queue_manager = queue_manager
        self.active_connections: Set[WebSocket] = set()
        self.pubsub = None

    async def connect(self, websocket: WebSocket):
        """Подключение клиента WebSocket"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Новое WebSocket подключение. Всего: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Отключение клиента WebSocket"""
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket отключен. Осталось: {len(self.active_connections)}")

    async def start_listening(self):
        """Запуск прослушивания уведомлений из Redis"""
        if not self.pubsub:
            self.pubsub = self.queue_manager.subscribe_to_notifications()

        # Запускаем фоновую задачу для обработки сообщений
        asyncio.create_task(self._process_notifications())

    async def _process_notifications(self):
        """Обработка уведомлений из Redis Pub/Sub"""
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                try:
                    # Валидируем уведомление через Pydantic
                    notification_data = json.loads(message['data'])
                    notification = TaskNotification(**notification_data)

                    # Отправляем всем подключенным клиентам
                    await self.broadcast_notification(notification)

                except Exception as e:
                    logger.error(f"Ошибка обработки уведомления: {e}")

    async def broadcast_notification(self, notification: TaskNotification):
        """Отправка уведомления всем подключенным клиентам"""
        if not self.active_connections:
            return

        disconnected = set()
        notification_json = notification.model_dump_json()

        for connection in self.active_connections:
            try:
                await connection.send_text(notification_json)
            except Exception as e:
                logger.error(f"Ошибка отправки клиенту: {e}")
                disconnected.add(connection)

        for connection in disconnected:
            self.disconnect(connection)

    async def handle_client(self, websocket: WebSocket):
        """Обработчик клиентского соединения"""
        await self.connect(websocket)

        try:
            while True:
                # Клиент может отправлять команды (например, подписку на конкретную задачу)
                data = await websocket.receive_text()
                await self._handle_client_message(websocket, data)

        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            logger.error(f"Ошибка в обработчике клиента: {e}")
            self.disconnect(websocket)

    async def _handle_client_message(self, websocket: WebSocket, message: str):
        """Обработка сообщений от клиента"""
        try:
            data = json.loads(message)
            action = data.get("action")

            if action == "subscribe_task":
                # Клиент подписывается на конкретную задачу
                request_id = data.get("request_id")
                # Здесь можно добавить логику фильтрации уведомлений
                await websocket.send_text(
                    json.dumps({
                        "status": "subscribed",
                        "request_id": request_id
                    })
                )

            elif action == "get_task_info":
                # Запрос информации о задаче
                request_id = data.get("request_id")
                task_info = self.queue_manager.get_task_info(request_id)

                await websocket.send_text(
                    json.dumps({
                        "action": "task_info",
                        "request_id": request_id,
                        "data": task_info.model_dump() if task_info else None
                    })
                )

        except json.JSONDecodeError:
            await websocket.send_text(
                json.dumps({"error": "Invalid JSON format"})
            )
        except Exception as e:
            await websocket.send_text(
                json.dumps({"error": str(e)})
            )
