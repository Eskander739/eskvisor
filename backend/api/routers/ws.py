import uuid

import orjson
import websockets
from fastapi import APIRouter, Depends, WebSocket
from starlette.websockets import WebSocketDisconnect

from api.dependencies import get_clusters_db, get_logger
from src.constants import ApiVersion
from src.models.error import DefaultMessage, ErrorMessage
from src.models.general import NodeWebsocketConnection, SystemStatRequest

router = APIRouter(
    prefix=f"{ApiVersion.V0}/ws",
    tags=["ws"],
)
active_connections_task = []
active_connections_notification = []
active_connections_system_stats = []
node_connections: list[NodeWebsocketConnection] = []


@router.websocket(f"/task")
async def task(
    websocket: WebSocket,
    clusters_db=Depends(get_clusters_db),
    logger=Depends(get_logger),
):
    await websocket.accept()
    active_connections_task.append(websocket)
    logger.info(f"Новое WebSocket подключение. Всего: {len(active_connections_task)}")
    uri_startswith = "ws://{}/ws/task"
    for cluster in clusters_db.get_cluster_list():
        for node in cluster.nodes:
            try:
                connect = await websockets.connect(
                    uri_startswith.format(node.ip_address)
                )
                node_connections.append(
                    NodeWebsocketConnection(
                        cluster_id=cluster.id, node_id=node.id, connection=connect
                    )
                )
            except OSError:
                pass

    try:
        while True:
            data = orjson.loads(await websocket.receive_text())
            try:
                node_id = data["node_id"]
                cluster_id = data["cluster_id"]
                for current_node in node_connections:
                    if (
                        current_node.node_id == node_id
                        and current_node.cluster_id == cluster_id
                    ):
                        await current_node.connection.send(data)

            except orjson.JSONDecodeError as err:
                await websocket.send_json(
                    DefaultMessage(
                        request_id=str(uuid.uuid4()),
                        code=ErrorMessage.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        active_connections_task.remove(websocket)
        logger.info(f"WebSocket отключен. Осталось: {len(active_connections_task)}")


@router.websocket(f"/notification")
async def notification(
    websocket: WebSocket,
    clusters_db=Depends(get_clusters_db),
    logger=Depends(get_logger),
):
    await websocket.accept()
    active_connections_notification.append(websocket)
    logger.info(
        f"Новое WebSocket подключение. Всего: {len(active_connections_notification)}"
    )
    uri_startswith = "ws://{}/ws/notification"
    for cluster in clusters_db.get_cluster_list():
        for node in cluster.nodes:
            try:
                connect = await websockets.connect(
                    uri_startswith.format(node.ip_address)
                )
                node_connections.append(
                    NodeWebsocketConnection(
                        cluster_id=cluster.id, node_id=node.id, connection=connect
                    )
                )
            except OSError:
                pass

    try:
        while True:
            try:
                for current_node in node_connections:
                    try:
                        result = await current_node.connection.recv()
                        await websocket.send_json(orjson.dumps(result))
                    except Exception:
                        pass

            except orjson.JSONDecodeError as err:
                await websocket.send_json(
                    DefaultMessage(
                        request_id=str(uuid.uuid4()),
                        code=ErrorMessage.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        active_connections_notification.remove(websocket)
        logger.info(
            f"WebSocket отключен. Осталось: {len(active_connections_notification)}"
        )


@router.websocket(f"/system-stats")
async def system_stats(
    websocket: WebSocket,
    clusters_db=Depends(get_clusters_db),
    logger=Depends(get_logger),
):
    await websocket.accept()
    active_connections_system_stats.append(websocket)
    logger.info(
        f"Новое WebSocket подключение. Всего: {len(active_connections_system_stats)}"
    )
    uri_startswith = "ws://{}/ws/system-stats"
    for cluster in clusters_db.get_cluster_list():
        for node in cluster.nodes:
            try:
                connect = await websockets.connect(
                    uri_startswith.format(node.ip_address)
                )
                node_connections.append(
                    NodeWebsocketConnection(
                        cluster_id=cluster.id, node_id=node.id, connection=connect
                    )
                )
            except OSError:
                pass

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = SystemStatRequest(**orjson.loads(data))

                for current_node in node_connections:
                    if (
                        current_node.node_id == message.node_id
                        and current_node.cluster_id == message.cluster_id
                    ):
                        await current_node.connection.send(message.model_dump_json())
                        result = await current_node.connection.recv()
                        await websocket.send_json(orjson.dumps(result))

            except orjson.JSONDecodeError as err:
                await websocket.send_json(
                    DefaultMessage(
                        request_id=str(uuid.uuid4()),
                        code=ErrorMessage.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        active_connections_system_stats.remove(websocket)
        logger.info(
            f"WebSocket отключен. Осталось: {len(active_connections_system_stats)}"
        )
