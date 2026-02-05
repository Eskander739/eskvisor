import uuid

import orjson
import websockets
from fastapi import APIRouter, Depends, WebSocket
from starlette.websockets import WebSocketDisconnect

from api.dependencies import get_logger
from src.constants import ApiVersion
from src.models.error import DefaultMessage, Message
from src.models.general import NodeWebsocketConnection, SystemStatRequest

router = APIRouter(
    prefix=f"{ApiVersion.V0}/ws",
    tags=["ws"],
)


@router.websocket(f"/task")
async def task(
    websocket: WebSocket,
    logger=Depends(get_logger),
):
    await websocket.accept()
    logger.info(f"Новое WebSocket подключение")
    uri_startswith = "ws://{}/ws/task"
    local_node_connections = []
    for cluster in await websocket.app.state.clusters_db.get_cluster_list():
        for node in cluster.nodes:
            try:
                connect = await websockets.connect(
                    uri_startswith.format(node.ip_address)
                )
                local_node_connections.append(
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
                for current_node in local_node_connections:
                    if (
                        current_node.node_id == node_id
                        and current_node.cluster_id == cluster_id
                    ):
                        await current_node.connection.send(data)

            except orjson.JSONDecodeError as err:
                await websocket.send_json(
                    DefaultMessage(
                        request_id=str(uuid.uuid4()),
                        code=Message.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        logger.info(f"WebSocket отключен")

    except Exception as err:
        logger.error(f"Ошибка в WebSocket: {err}")
        await websocket.send_json(
            DefaultMessage(
                request_id=str(uuid.uuid4()),
                code=Message.internal_error.name,
                success=False,
                note=str(err),
            ).model_dump()
        )


@router.websocket(f"/notification")
async def notification(
    websocket: WebSocket,
    logger=Depends(get_logger),
):
    await websocket.accept()
    logger.info("Новое WebSocket подключение")
    uri_startswith = "ws://{}/ws/notification"
    local_node_connections = []
    for cluster in await websocket.app.state.clusters_db.get_cluster_list():
        for node in cluster.nodes:
            try:
                connect = await websockets.connect(
                    uri_startswith.format(node.ip_address)
                )
                local_node_connections.append(
                    NodeWebsocketConnection(
                        cluster_id=cluster.id, node_id=node.id, connection=connect
                    )
                )
            except OSError:
                pass

    try:
        while True:
            try:
                for current_node in local_node_connections:
                    try:
                        result = await current_node.connection.recv()
                        await websocket.send_json(orjson.dumps(result))
                    except Exception:
                        pass

            except orjson.JSONDecodeError as err:
                await websocket.send_json(
                    DefaultMessage(
                        request_id=str(uuid.uuid4()),
                        code=Message.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        logger.info("WebSocket отключен")
    except Exception as err:
        logger.error(f"Ошибка в WebSocket: {err}")
        await websocket.send_json(
            DefaultMessage(
                request_id=str(uuid.uuid4()),
                code=Message.internal_error.name,
                success=False,
                note=str(err),
            ).model_dump()
        )


@router.websocket("/vnc/{cluster_id}/{node_id}/{vm_uuid}")
async def vnc(
    websocket: WebSocket,
    cluster_id: int,
    node_id: int,
    vm_uuid: str,
    logger=Depends(get_logger),
):
    await websocket.accept()
    logger.info("Новое WebSocket подключение")
    uri_startswith = "ws://{}/ws/vnc/{}"
    connect = None
    for cluster in await websocket.app.state.clusters_db.get_cluster_list():
        for node in cluster.nodes:
            try:
                if node.id == node_id and cluster.id == cluster_id:
                    connect = await websockets.connect(
                        uri_startswith.format(node.ip_address, vm_uuid)
                    )
            except Exception as err:
                logger.error(f"Ошибка в подключении к VNC: {err}")
                await websocket.send_json(
                    DefaultMessage(
                        request_id=str(uuid.uuid4()),
                        code=Message.internal_error.name,
                        success=False,
                        note=str(err),
                    )
                )

    try:
        while True:
            try:
                result = await connect.recv()
                await websocket.send_json(orjson.dumps(result))

            except orjson.JSONDecodeError as err:
                await websocket.send_json(
                    DefaultMessage(
                        request_id=str(uuid.uuid4()),
                        code=Message.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        logger.info("WebSocket отключен")
    except Exception as err:
        logger.error(f"Ошибка в WebSocket: {err}")
        await websocket.send_json(
            DefaultMessage(
                request_id=str(uuid.uuid4()),
                code=Message.internal_error.name,
                success=False,
                note=str(err),
            ).model_dump()
        )


@router.websocket(f"/system-stats")
async def system_stats(
    websocket: WebSocket,
    logger=Depends(get_logger),
):
    await websocket.accept()
    logger.info("Новое WebSocket подключение")
    uri_startswith = "ws://{}/ws/system-stats"
    local_node_connections = []
    for cluster in await websocket.app.state.clusters_db.get_cluster_list():
        for node in cluster.nodes:
            try:
                connect = await websockets.connect(
                    uri_startswith.format(node.ip_address)
                )
                local_node_connections.append(
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

                for current_node in local_node_connections:
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
                        code=Message.incorrect_json_format.value,
                        success=False,
                        note=str(err),
                    ).model_dump_json()
                )
    except WebSocketDisconnect:
        logger.info("WebSocket отключен")
    except Exception as err:
        logger.error(f"Ошибка в WebSocket: {err}")
        await websocket.send_json(
            DefaultMessage(
                request_id=str(uuid.uuid4()),
                code=Message.internal_error.name,
                success=False,
                note=str(err),
            ).model_dump()
        )
