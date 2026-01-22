import orjson
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import uvicorn
from typing import List

from starlette.middleware.cors import CORSMiddleware

from agent.client.logger_config import DefaultLogger
from agent.client.task_manager.ctl_queue import RedisTaskManager
from agent.client.task_manager.models import TaskAdd, TaskType, TaskStatus, TasksInfo
from agent.client.task_manager.ws import WebSocketNotificationHandler

logger = DefaultLogger("TaskManagerServer")

app = FastAPI(title="Task Manager WebSocket Server", version="1.0.0")

# Инициализация менеджеров
queue_manager = RedisTaskManager()
ws_handler = WebSocketNotificationHandler(queue_manager)

# Настройка шаблонов
templates = Jinja2Templates(directory="templates")
# Список активных подключений
active_connections: List[WebSocket] = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Добавьте middleware для CSP заголовков
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    # Разрешаем только локальные скрипты и блокируем document.write
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "object-src 'none';"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.delete("/api/tasks/clear")
async def clear_all_tasks():
    """Очистить все задачи из очереди"""
    try:
        # Получаем все задачи
        pending_tasks = queue_manager.get_all_tasks()
        processing_tasks = queue_manager.get_process_tasks()

        # Преобразуем JSON строки обратно в объекты, если необходимо
        all_tasks = []

        # Обрабатываем pending задачи
        for task_json in pending_tasks:
            try:
                task = orjson.loads(task_json.model_dump_json())
                all_tasks.append(task.get("request_id"))
            except:
                pass

        # Обрабатываем processing задачи
        for task_json in processing_tasks:
            try:
                task = orjson.loads(task_json.model_dump_json())
                all_tasks.append(task.get("request_id"))
            except:
                pass

        deleted_count = queue_manager.delete_all_tasks()
        deleted_count_working = queue_manager.delete_all_tasks(
            queue_manager.processing_queue_name
        )
        deleted_count += deleted_count_working
        logger.info(f"Удалено задач: {deleted_count}")

        return JSONResponse(
            {"deleted": deleted_count, "message": f"Удалено {deleted_count} задач"}
        )

    except Exception as e:
        logger.error(f"Ошибка очистки задач: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Главная страница управления задачами"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/api/tasks")
async def get_tasks():
    """Получить список всех задач"""
    try:
        pending_tasks = queue_manager.get_all_tasks()
        processing_tasks = queue_manager.get_process_tasks()
        return TasksInfo(
            pending=pending_tasks,
            processing=processing_tasks,
            total_pending=len(pending_tasks),
            total_processing=len(processing_tasks),
        )
    except Exception as e:
        logger.error(f"Ошибка получения задач: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/task/{request_id}")
async def get_task_info(request_id: str):
    """Получить информацию о конкретной задаче"""
    try:
        task_info = queue_manager.get_task_info(request_id)

        if task_info:
            return task_info
        else:
            return JSONResponse({"error": "Task not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Ошибка получения задачи: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/tasks")
async def create_task(task_data: dict):
    """Создать новую задачу"""
    try:
        from datetime import datetime

        task = TaskAdd(
            task_type=TaskType(task_data.get("task_type", "vm")),
            action=task_data.get("action"),
            params=task_data.get("params", {}),
            created_at=datetime.now(),
        )

        # Импортируем диспетчер для создания задачи
        from agent.client.task_manager.dispatcher import TaskDispatcher

        dispatcher = TaskDispatcher(queue_manager, worker_count=1)
        dispatcher.submit_task(task)

        return task
    except Exception as e:
        logger.error(f"Ошибка создания задачи: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для уведомлений"""
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"Новое WebSocket подключение. Всего: {len(active_connections)}")

    try:
        while True:
            # Обработка сообщений от клиента
            data = await websocket.receive_text()

            try:
                message = orjson.loads(data)
                action = message.get("action")

                if action == "get_tasks":
                    # Отправляем список задач
                    pending_tasks = [
                        current_task.model_dump_json()
                        for current_task in queue_manager.get_all_tasks()
                    ]
                    processing_tasks = [
                        current_task.model_dump_json()
                        for current_task in queue_manager.get_process_tasks()
                    ]

                    await websocket.send_json(
                        {
                            "type": "tasks_list",
                            "pending": pending_tasks,
                            "processing": processing_tasks,
                        }
                    )

                elif action == "subscribe_task":
                    request_id = message.get("request_id")
                    await websocket.send_json(
                        {
                            "type": "subscription",
                            "message": f"Подписан на задачу {request_id}",
                            "request_id": request_id,
                        }
                    )

            except orjson.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "message": "Неверный формат JSON"}
                )

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info(f"WebSocket отключен. Осталось: {len(active_connections)}")


@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """WebSocket только для уведомлений (без обработки команд)"""
    await ws_handler.connect(websocket)

    try:
        while True:
            # Просто держим соединение открытым
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_handler.disconnect(websocket)


@app.get("/health")
async def health_check():
    """Проверка здоровья сервера"""
    return JSONResponse({"status": "healthy", "service": "task-manager-ws"})


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")
