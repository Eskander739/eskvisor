import json

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger, get_ws_task
from src.constants import ApiVersion
from src.models.error import Message
from src.models.general import CreateTask, TaskType, TaskAction
from src.models.network import NetworkListRequest, NetworkParameters
from src.services.pool.task_ws_pool import TaskWebsocketPool

router = APIRouter(
    prefix=f"{ApiVersion.V0}/network",
    tags=["network"],
)


@router.post("/create")
async def create_network(
    request: Request,
    network_info: NetworkParameters,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    logger.info(f"Создание виртуальной сети{network_info.name}")
    network_info_model_string = network_info.model_dump_json()
    network_info_model = orjson.loads(network_info_model_string)
    network = await request.app.state.virtual_networks_db.get_virtual_network_by_name(
        network_info.name
    )
    if network:
        logger.info(f"Виртуальная сеть {network_info.name} уже создана")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=Message.network_already_created.name,
        )
    await request.app.state.virtual_networks_db.create_virtual_network(
        network_info_model
    )
    await ws_task.send_json(
        network_info.cluster_id,
        network_info.node_id,
        CreateTask(
            task_type=TaskType.STORAGE,
            action=TaskAction.CREATE,
            params=network_info_model_string,
        ),
    )
    return JSONResponse({"code": "Network successfully created"})


@router.put("/{network_id}/edit")
async def edit_network(
    request: Request,
    network_id: int,
    network_info: NetworkParameters,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):

    network = await request.app.state.virtual_networks_db.get_virtual_network(
        network_id
    )
    if not network:
        logger.info(f"Виртуальная сеть {network_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.network_not_found.name,
        )
    logger.info(f"Редактирование виртуальной сети {network_id}")
    request.app.state.virtual_networks_db.update_virtual_network(network_info)
    await ws_task.send_json(
        network.cluster_id,
        network.node_id,
        CreateTask(
            task_type=TaskType.STORAGE,
            action=TaskAction.EDIT,
            params=network_info.model_dump_json(),
        ),
    )
    return JSONResponse({"code": "Network successfully edited"})


@router.get("/list")
async def list_networks(
    request: Request,
    network_info: NetworkListRequest = NetworkListRequest(),
    logger=Depends(get_logger),
):
    network_list = (
        await request.app.state.virtual_networks_db.get_virtual_networks_list(
            **network_info.model_dump()
        )
    )
    logger.info(f"Получение списка виртуальных сетей {network_list}")
    network_list = {"network_list": network_list}
    return network_list


@router.get("/{network_id}")
async def network_by_id(
    request: Request,
    network_id: int,
    logger=Depends(get_logger),
):
    network = await request.app.state.virtual_networks_db.get_virtual_network(
        network_id
    )
    if not network:
        logger.info(f"Виртуальный диск {network_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.network_not_found.name,
        )
    logger.info(f"Получение виртуальной сети{network_id}")
    return network


@router.delete("/{network_id}/delete")
async def delete_network(
    request: Request,
    network_id: int,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    network = await request.app.state.virtual_networks_db.get_virtual_network(
        network_id
    )
    if not network:
        logger.info(f"Виртуальный диск {network_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.network_not_found.name,
        )
    await request.app.state.virtual_networks_db.delete_virtual_network(network_id)
    await ws_task.send_json(
        network.cluster_id,
        network.node_id,
        CreateTask(
            task_type=TaskType.STORAGE,
            action=TaskAction.DELETE,
            params=json.dumps({"network_name": network.name, "format": network.format}),
        ),
    )
    logger.info(f"Удаление виртуальной сети{network_id}")
