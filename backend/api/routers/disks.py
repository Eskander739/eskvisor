import json

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger, get_ws_task
from src.constants import ApiVersion
from src.models.disk import DiskCreate, DiskUpdate, DiskQuery
from src.models.error import Message
from src.models.general import CreateTask, TaskType, TaskAction
from src.services.pool.task_ws_pool import TaskWebsocketPool

router = APIRouter(
    prefix=f"{ApiVersion.V0}/disk",
    tags=["disk"],
)


@router.post("/create")
async def create_disk(
    request: Request,
    disk_info: DiskCreate,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    logger.info(f"Создание виртуального диска{disk_info.name}")
    disk_info_model_string = disk_info.model_dump_json()
    disk_info_model = orjson.loads(disk_info_model_string)
    disk = await request.app.state.disks_db.get_disk_by_name(disk_info.name)
    if disk:
        logger.info(f"Виртуальный диск {disk_info.name} уже создан")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=Message.disk_already_created.name,
        )
    await request.app.state.disks_db.create_disk(disk_info_model)
    await ws_task.send_json(
        disk_info.cluster_id,
        disk_info.node_id,
        CreateTask(
            task_type=TaskType.STORAGE,
            action=TaskAction.CREATE,
            params=disk_info_model_string,
        ),
    )
    return JSONResponse({"code": "Disk successfully created"})


@router.put("/{disk_id}/edit")
async def edit_disk(
    request: Request,
    disk_id: int,
    disk_info: DiskUpdate,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):

    disk = await request.app.state.disks_db.get_disk_by_id(disk_id)
    if not disk:
        logger.info(f"Виртуальный диск {disk_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.disk_not_found.name,
        )
    logger.info(f"Редактирование виртуального диска {disk_id}")
    request.app.state.disks_db.update_disk(disk_info)
    await ws_task.send_json(
        disk.cluster_id,
        disk.node_id,
        CreateTask(
            task_type=TaskType.STORAGE,
            action=TaskAction.EDIT,
            params=disk_info.model_dump_json(),
        ),
    )
    return JSONResponse({"code": "Disk successfully edited"})


@router.get("/list")
async def list_disks(
    request: Request,
    disk_info: DiskQuery = DiskQuery(),
    logger=Depends(get_logger),
):
    disk_list = await request.app.state.disks_db.get_disks_list(
        **disk_info.model_dump()
    )
    logger.info(f"Получение списка виртуальных дисков {disk_list}")
    disk_list = {"disk_list": disk_list}
    return disk_list


@router.get("/{disk_id}")
async def disk_by_id(
    request: Request,
    disk_id: int,
    logger=Depends(get_logger),
):
    disk = await request.app.state.disks_db.get_disk_by_id(disk_id)
    if not disk:
        logger.info(f"Виртуальный диск {disk_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.disk_not_found.name,
        )
    logger.info(f"Получение виртуального диска{disk_id}")
    return disk


@router.delete("/{disk_id}/delete")
async def delete_disk(
    request: Request,
    disk_id: int,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    disk = await request.app.state.disks_db.get_disk_by_id(disk_id)
    if not disk:
        logger.info(f"Виртуальный диск {disk_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.disk_not_found.name,
        )
    await request.app.state.disks_db.delete_disk(disk_id)
    await ws_task.send_json(
        disk.cluster_id,
        disk.node_id,
        CreateTask(
            task_type=TaskType.STORAGE,
            action=TaskAction.DELETE,
            params=json.dumps({"disk_name": disk.name, "format": disk.format}),
        ),
    )
    logger.info(f"Удаление виртуального диска{disk_id}")
