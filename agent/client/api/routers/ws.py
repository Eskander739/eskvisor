from fastapi import APIRouter, Depends
from datetime import datetime

import orjson
from fastapi import WebSocket, WebSocketDisconnect
from agent.client.api.dependencies import (
    get_queue_manager_service,
    get_vm_live_monitor_service,
    get_ws_handler,
    get_task_dispatcher_service,
    get_vnc_manager,
)
from agent.client.hypervisor.libvirt.models.msg import (
    DefaultMessage,
    CommandMessagesEnum,
)
from agent.client.hypervisor.libvirt.models.vm_stats.stats import CpuAndRamUsage
from agent.client.models.general import VNCConnectInfo, VNCStatusInfo, VNCRestartProxy
from agent.client.task_manager.models import Task, TaskType
from agent.client.tools import get_quick_stats, check_vnc_service
from agent.client.api.dependencies import get_logger


router = APIRouter(
    prefix=f"/ws",
    tags=["ws"],
)
active_connections: list[WebSocket] = []


@router.websocket("/task")
async def task(
    websocket: WebSocket,
    logger=Depends(get_logger),
    queue_manager=Depends(get_queue_manager_service),
    ws_handler=Depends(get_ws_handler),
    task_dispatcher=Depends(get_task_dispatcher_service),
):
    """WebSocket task для уведомлений"""
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"Новое WebSocket подключение. Всего: {len(active_connections)}")

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Новый запрос: {logger}")
            try:
                message = orjson.loads(data)
                action = message.get("action")

                if action == "get_tasks":
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

                elif action == "clear_all_tasks":
                    pending_tasks = queue_manager.get_all_tasks()
                    processing_tasks = queue_manager.get_process_tasks()
                    all_tasks = []
                    for task_json in pending_tasks:
                        try:
                            task = orjson.loads(task_json.model_dump_json())
                            all_tasks.append(task.get("request_id"))
                        except Exception:
                            pass

                    for task_json in processing_tasks:
                        try:
                            task = orjson.loads(task_json.model_dump_json())
                            all_tasks.append(task.get("request_id"))
                        except Exception:
                            pass

                    deleted_count = queue_manager.delete_all_tasks()
                    deleted_count_working = queue_manager.delete_all_tasks(
                        queue_manager.processing_queue_name
                    )
                    deleted_count += deleted_count_working
                    logger.info(f"Удалено задач: {deleted_count}")

                    await websocket.send_json(
                        {
                            "deleted": deleted_count,
                            "message": f"Удалено {deleted_count} задач",
                        }
                    )

                else:
                    if isinstance(message.get("params"), str):
                        params = orjson.loads(message.get("params"))
                    else:
                        params = message.get("params")
                    task = Task(
                        request_id=message.get("request_id"),
                        task_type=TaskType(message.get("task_type", "vm")),
                        action=message.get("action"),
                        params=params,
                        created_at=datetime.now(),
                    )

                    task_dispatcher.submit_task(task)

            except orjson.JSONDecodeError as err:
                await websocket.send_json(
                    DefaultMessage(
                        code=CommandMessagesEnum.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        ws_handler.disconnect(websocket)
        logger.info(f"WebSocket отключен. Осталось: {len(active_connections)}")

    except Exception as err:
        logger.error(f"Ошибка в WebSocket: {err}")
        await websocket.send_json(
            DefaultMessage(
                code=CommandMessagesEnum.internal_error.name,
                success=False,
                note=str(err),
            ).model_dump()
        )


@router.websocket("/system-stats")
async def system_stats(
    websocket: WebSocket,
    logger=Depends(get_logger),
    vm_live_monitor=Depends(get_vm_live_monitor_service),
    ws_handler=Depends(get_ws_handler),
):
    """WebSocket system_stats для получения статистики о системе"""
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"Новое WebSocket подключение. Всего: {len(active_connections)}")

    try:
        while True:
            # Обработка сообщений от клиента
            data = await websocket.receive_text()

            try:
                message = orjson.loads(data)
                object = message.get("object")

                if object == "system":
                    await websocket.send_json(get_quick_stats())

                elif object == "vm":
                    vm_name = message.get("vm_name")
                    if not vm_name:
                        await websocket.send_json(
                            {"type": "error", "message": "Неверный формат JSON"}
                        )
                    vm_stats = vm_live_monitor(vm_name).used_ram_and_cpu()
                    await websocket.send_json(
                        vm_stats.model_dump_json()
                        if vm_stats is not None
                        else CpuAndRamUsage(
                            cpu_core_count=0, cpu_usage_percent=0, memory=0
                        ).model_dump_json()
                    )

                elif object == "storage":
                    await websocket.send_json(
                        DefaultMessage(
                            code=CommandMessagesEnum.not_implemented_error.name,
                            success=False,
                            note='{"error": "Не реализовано"}',
                        )
                    )

            except orjson.JSONDecodeError as err:
                await websocket.send_json(
                    DefaultMessage(
                        code=CommandMessagesEnum.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )

    except WebSocketDisconnect:
        active_connections.remove(websocket)
        ws_handler.disconnect(websocket)
        logger.info(f"WebSocket отключен. Осталось: {len(active_connections)}")

    except Exception as err:
        logger.error(f"Ошибка в WebSocket: {err}")
        await websocket.send_json(
            DefaultMessage(
                code=CommandMessagesEnum.internal_error.name,
                success=False,
                note=str(err),
            ).model_dump()
        )


@router.websocket("/notification")
async def notification(
    websocket: WebSocket, logger=Depends(get_logger), ws_handler=Depends(get_ws_handler)
):
    """WebSocket только для уведомлений (без обработки команд)"""

    await ws_handler.connect(websocket)
    active_connections.append(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        ws_handler.disconnect(websocket)

    except Exception as err:
        logger.error(f"Ошибка в WebSocket: {err}")
        await websocket.send_json(
            DefaultMessage(
                code=CommandMessagesEnum.internal_error.name,
                success=False,
                note=str(err),
            ).model_dump()
        )


@router.websocket("/vnc/{vm_name}")
async def vnc(
    websocket: WebSocket,
    vm_name: str,
    logger=Depends(get_logger),
    vnc_manager=Depends(get_vnc_manager),
):
    """
    WebSocket для трансляции VNC конкретной виртуальной машины
    """
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(
        f"Новое VNC WebSocket подключение для VM '{vm_name}'. Всего: {len(active_connections)}"
    )

    try:
        vnc_port = await vnc_manager.get_vnc_port_for_vm(vm_name)
        vnc_available, message = await check_vnc_service(vm_name, vnc_port)

        if not vnc_available:
            logger.warning(f"VNC сервис для {vm_name} недоступен: {message}")
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"VNC сервис для {vm_name} недоступен",
                    "details": message,
                }
            )
            await websocket.close(code=1008)
            return

        ws_port = vnc_manager.start_vnc_proxy(vm_name, vnc_port)
        vnc_connect_info = VNCConnectInfo(
            code=CommandMessagesEnum.vnc_connection_successfully_created.name,
            vm_name=vm_name,
            vnc_port=vnc_port,
            ws_port=ws_port,
            ws_url=f"ws://localhost:{ws_port}",  # TODO: Изменить localhost на наш ip
            note="Используйте полученный WebSocket URL(ws_url) для подключения к VNC",
            success=True,
        )
        await websocket.send_json(vnc_connect_info.model_dump())

        while True:
            data = await websocket.receive_text()

            try:
                message = orjson.loads(data)
                action = message.get("action")

                if action == "get_status":
                    status = vnc_manager.get_vm_proxy_status(vm_name)
                    await websocket.send_json(
                        VNCStatusInfo(
                            code=CommandMessagesEnum.vnc_status_successfully_readed.name,
                            vm_name=vm_name,
                            success=True if status else False,
                            status=status or {"error": "Прокси не найден"},
                        ).model_dump()
                    )

                elif action == "restart_proxy":
                    vnc_manager.stop_vnc_proxy(vm_name)
                    ws_port = vnc_manager.start_vnc_proxy(vm_name, vnc_port)
                    await websocket.send_json(
                        VNCRestartProxy(
                            code=CommandMessagesEnum.vnc_proxy_successfully_restarted.name,
                            vm_name=vm_name,
                            new_ws_port=ws_port,
                            new_ws_url=f"ws://localhost:{ws_port}",  # TODO: Изменить localhost на наш ip
                            success=True,
                        ).model_dump()
                    )

                elif action == "disconnect":
                    await websocket.send_json(
                        DefaultMessage(
                            code=CommandMessagesEnum.vnc_successfully_disconnected.name,
                            success=True,
                        ).model_dump()
                    )
                    break

                else:
                    msg = f"Команда: {action}, available_actions: {['get_status', 'restart_proxy', 'disconnect']}"
                    await websocket.send_json(
                        DefaultMessage(
                            code=CommandMessagesEnum.unknown_command_error.name,
                            success=False,
                            note=msg,
                        ).model_dump()
                    )

            except orjson.JSONDecodeError as err:
                await websocket.send_json(
                    DefaultMessage(
                        code=CommandMessagesEnum.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )

    except WebSocketDisconnect:
        logger.info(f"VNC WebSocket для {vm_name} отключен")
    except Exception as err:
        logger.error(f"Ошибка в VNC WebSocket для {vm_name}: {err}")
        await websocket.send_json(
            DefaultMessage(
                code=CommandMessagesEnum.internal_error.name,
                success=False,
                note=str(err),
            ).model_dump()
        )
