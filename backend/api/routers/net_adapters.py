import json

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger, get_ws_task
from src.constants import ApiVersion
from src.models.error import Message
from src.models.general import CreateTask, TaskType, TaskAction
from src.models.network import (
    NetworkAdapterUpdate,
    NetworkAdapterFilter,
    NetworkAdapterCreate,
)
from src.services.pool.task_ws_pool import TaskWebsocketPool

router = APIRouter(
    prefix=f"{ApiVersion.V0}/net-adapters",
    tags=["net-adapters"],
)


@router.post("/create")
async def create_net_adapter(
    request: Request,
    net_adapter_info: NetworkAdapterCreate,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    logger.info(f"Создание виртуального диска{net_adapter_info.name}")
    net_adapter_model_string = net_adapter_info.model_dump_json()
    net_adapter_model = orjson.loads(net_adapter_model_string)
    net_adapter = await request.app.state.net_adapters_db.get_adapter_by_source(
        net_adapter_info.source
    )
    if net_adapter:
        logger.info(f"Сетевой адаптер {net_adapter_info.name} уже создан")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=Message.net_adapter_already_created.name,
        )
    vm = await request.app.state.virtual_machines_db.get_virtual_machine(
        net_adapter_info.vm_id
    )
    if vm is None:
        logger.info(f"Виртуальная машина {net_adapter_info.vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found.name
        )
    await request.app.state.disks_db.create_disk(net_adapter_model)
    await ws_task.send_json(
        vm.cluster_id,
        vm.node_id,
        CreateTask(
            task_type=TaskType.NETWORK,
            action=TaskAction.CREATE,
            params=net_adapter_model_string,
        ),
    )
    return JSONResponse({"code": "Net adapter successfully created"})


@router.put("/{net_adapter_id}/edit")
async def edit_net_adapter(
    request: Request,
    net_adapter_id: int,
    adapter_info: NetworkAdapterUpdate,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):

    disk = await request.app.state.net_adapters_db.get_adapter_by_id(net_adapter_id)
    if not disk:
        logger.info(f"Сетевой адаптер {net_adapter_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.net_adapter_not_found.name,
        )
    logger.info(f"Редактирование сетевого адаптера {net_adapter_id}")
    request.app.state.net_adapters_db.update_adapter(adapter_info)
    await ws_task.send_json(
        disk.cluster_id,
        disk.node_id,
        CreateTask(
            task_type=TaskType.NETWORK,
            action=TaskAction.EDIT,
            params=adapter_info.model_dump_json(),
        ),
    )
    return JSONResponse({"code": "Net adapter successfully edited"})


@router.get("/list")
async def list_net_adapters(
    request: Request,
    net_adapter_info: NetworkAdapterFilter = NetworkAdapterFilter(),
    logger=Depends(get_logger),
):
    net_adapters_list = await request.app.state.net_adapters_db.get_adapters_list(
        net_adapter_info
    )
    logger.info(f"Получение списка сетевых адаптеров {net_adapters_list}")
    net_adapters = {"net_adapters": net_adapters_list}
    return net_adapters


@router.get("/{net_adapter_id}")
async def net_adapter_by_id(
    request: Request,
    net_adapter_id: int,
    logger=Depends(get_logger),
):
    disk = await request.app.state.net_adapters_db.get_adapter_by_id(net_adapter_id)
    if not disk:
        logger.info(f"Сетевой адаптер {net_adapter_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.net_adapter_not_found.name,
        )
    logger.info(f"Получение сетевого адаптера{net_adapter_id}")
    return disk


@router.delete("/{net_adapter_id}/delete")
async def delete_net_adapter(
    request: Request,
    net_adapter_id: int,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    disk = await request.app.state.net_adapters_db.get_adapter_by_id(net_adapter_id)
    if not disk:
        logger.info(f"Сетевой адаптер {net_adapter_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.net_adapter_not_found.name,
        )
    await request.app.state.net_adapters_db.delete_disk(net_adapter_id)
    await ws_task.send_json(
        disk.cluster_id,
        disk.node_id,
        CreateTask(
            task_type=TaskType.NETWORK,
            action=TaskAction.DELETE,
            params=json.dumps({"disk_name": disk.name, "format": disk.format}),
        ),
    )
    logger.info(f"Удаление сетевого адаптера{net_adapter_id}")
