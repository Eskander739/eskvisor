from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger, get_ws_task
from src.constants import ApiVersion
from src.models.error import Message
from src.models.general import CreateTask, TaskType
from src.services.pool.task_ws_pool import TaskWebsocketPool

router = APIRouter(
    prefix=f"{ApiVersion.V0}/resource-pool",
    tags=["resource-pool"],
)


@router.post("/create")
async def create_resource_pool(
    request: Request,
    pool_data: dict,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    """
    Создание нового ресурсного пула
    """
    logger.info(f"Создание ресурсного пула {pool_data.get('name')}")

    # Проверяем, существует ли пул с таким именем
    existing_pool = await request.app.state.resource_pools_db.get_resource_pool_by_name(
        pool_data.get("name")
    )
    if existing_pool:
        logger.info(f"Ресурсный пул {pool_data.get('name')} уже существует")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=Message.resource_pool_already_exists.name,
        )

    # Создаем ресурсный пул в базе данных
    pool_id = await request.app.state.resource_pools_db.create_resource_pool(pool_data)

    # Отправляем задачу через WebSocket
    await ws_task.send_json(
        pool_data.get("cluster_id"),
        pool_data.get("node_id"),
        CreateTask(
            task_type=TaskType.RESOURCE_POOL,
            action="create",
            params=str(pool_data),
        ),
    )

    logger.info(f"Ресурсный пул {pool_data.get('name')} успешно создан с ID {pool_id}")
    return JSONResponse(
        {"code": "Resource pool successfully created", "pool_id": pool_id}
    )


@router.get("/list")
async def list_resource_pools(
    request: Request,
    cluster_id: int | None = None,
    node_id: int | None = None,
    name: str | None = None,
    enabled: bool | None = True,
    limit: int = 100,
    offset: int = 0,
    logger=Depends(get_logger),
):
    """
    Получение списка ресурсных пулов с фильтрацией
    """
    logger.info("Получение списка ресурсных пулов")

    pools = await request.app.state.resource_pools_db.get_resource_pools_list(
        cluster_id=cluster_id,
        node_id=node_id,
        name=name,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )

    return {"pools": pools, "total": len(pools)}


@router.get("/{pool_id}")
async def get_resource_pool(
    request: Request,
    pool_id: int,
    logger=Depends(get_logger),
):
    """
    Получение ресурсного пула по ID
    """
    logger.info(f"Получение ресурсного пула {pool_id}")

    pool = await request.app.state.resource_pools_db.get_resource_pool(pool_id)
    if not pool:
        logger.info(f"Ресурсный пул {pool_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.resource_pool_not_found.name,
        )

    return pool


@router.put("/{pool_id}/edit")
async def update_resource_pool(
    request: Request,
    pool_id: int,
    update_data: dict,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    """
    Обновление ресурсного пула
    """
    logger.info(f"Обновление ресурсного пула {pool_id}")

    # Проверяем существование пула
    pool = await request.app.state.resource_pools_db.get_resource_pool(pool_id)
    if not pool:
        logger.info(f"Ресурсный пул {pool_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.resource_pool_not_found.name,
        )

    # Обновляем пул в базе данных
    await request.app.state.resource_pools_db.update_resource_pool(pool_id, update_data)

    # Отправляем задачу через WebSocket
    await ws_task.send_json(
        pool.cluster_id,
        pool.node_id,
        CreateTask(
            task_type=TaskType.RESOURCE_POOL,
            action="edit",
            params=str(update_data),
        ),
    )

    logger.info(f"Ресурсный пул {pool_id} успешно обновлен")
    return JSONResponse({"code": "Resource pool successfully updated"})


@router.delete("/{pool_id}/delete")
async def delete_resource_pool(
    request: Request,
    pool_id: int,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    """
    Удаление ресурсного пула
    """
    logger.info(f"Удаление ресурсного пула {pool_id}")

    # Проверяем существование пула
    pool = await request.app.state.resource_pools_db.get_resource_pool(pool_id)
    if not pool:
        logger.info(f"Ресурсный пул {pool_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.resource_pool_not_found.name,
        )

    # Удаляем пул из базы данных
    await request.app.state.resource_pools_db.delete_resource_pool(pool_id)

    # Отправляем задачу через WebSocket
    await ws_task.send_json(
        pool.cluster_id,
        pool.node_id,
        CreateTask(
            task_type=TaskType.RESOURCE_POOL,
            action="delete",
            params=str({"pool_id": pool_id, "pool_name": pool.name}),
        ),
    )

    logger.info(f"Ресурсный пул {pool_id} успешно удален")
    return JSONResponse({"code": "Resource pool successfully deleted"})


@router.post("/{pool_id}/vm/add")
async def add_vm_to_pool(
    request: Request,
    pool_id: int,
    vm_data: dict,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    """
    Добавление ВМ в список ресурсного пула
    """
    logger.info(f"Добавление ВМ в ресурсный пул {pool_id}")

    # Проверяем существование пула
    pool = await request.app.state.resource_pools_db.get_resource_pool(pool_id)
    if not pool:
        logger.info(f"Ресурсный пул {pool_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.resource_pool_not_found.name,
        )

    # Получаем текущий список ВМ
    current_vms = pool.vms if pool.vms else []

    # Добавляем новую ВМ (предполагаем, что vm_data содержит vm_id)
    vm_id = vm_data.get("vm_id")
    if not vm_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="vm_id is required",
        )

    if vm_id not in current_vms:
        current_vms.append(vm_id)

        # Обновляем пул с новым списком ВМ
        update_data = {"vms": current_vms}
        await request.app.state.resource_pools_db.update_resource_pool(
            pool_id, update_data
        )

        # Отправляем задачу через WebSocket
        await ws_task.send_json(
            pool.cluster_id,
            pool.node_id,
            CreateTask(
                task_type=TaskType.RESOURCE_POOL,
                action="add_vm",
                params=str(vm_data),
            ),
        )

        logger.info(f"ВМ {vm_id} успешно добавлена в ресурсный пул {pool_id}")
        return JSONResponse({"code": "VM successfully added to resource pool"})
    else:
        logger.info(f"ВМ {vm_id} уже находится в ресурсном пуле {pool_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="VM already in resource pool",
        )


@router.post("/{pool_id}/vm/remove")
async def remove_vm_from_pool(
    request: Request,
    pool_id: int,
    vm_data: dict,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    """
    Удаление ВМ из списка ресурсного пула
    """
    logger.info(f"Удаление ВМ из ресурсного пула {pool_id}")

    # Проверяем существование пула
    pool = await request.app.state.resource_pools_db.get_resource_pool(pool_id)
    if not pool:
        logger.info(f"Ресурсный пул {pool_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.resource_pool_not_found.name,
        )

    # Получаем текущий список ВМ
    current_vms = pool.vms if pool.vms else []

    # Удаляем ВМ из списка
    vm_id = vm_data.get("vm_id")
    if not vm_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="vm_id is required",
        )

    if vm_id in current_vms:
        current_vms.remove(vm_id)

        # Обновляем пул с новым списком ВМ
        update_data = {"vms": current_vms}
        await request.app.state.resource_pools_db.update_resource_pool(
            pool_id, update_data
        )

        # Отправляем задачу через WebSocket
        await ws_task.send_json(
            pool.cluster_id,
            pool.node_id,
            CreateTask(
                task_type=TaskType.RESOURCE_POOL,
                action="remove_vm",
                params=str(vm_data),
            ),
        )

        logger.info(f"ВМ {vm_id} успешно удалена из ресурсного пула {pool_id}")
        return JSONResponse({"code": "VM successfully removed from resource pool"})
    else:
        logger.info(f"ВМ {vm_id} не найдена в ресурсном пуле {pool_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VM not found in resource pool",
        )


@router.get("/{pool_id}/stats")
async def get_pool_stats(
    request: Request,
    pool_id: int,
    logger=Depends(get_logger),
):
    """
    Получение статистики ресурсного пула
    """
    logger.info(f"Получение статистики ресурсного пула {pool_id}")

    pool = await request.app.state.resource_pools_db.get_resource_pool(pool_id)
    if not pool:
        logger.info(f"Ресурсный пул {pool_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.resource_pool_not_found.name,
        )

    # Вычисляем использование ресурсов
    stats = {
        "pool_id": pool.id,
        "pool_name": pool.name,
        "cpu_usage": {
            "allocated": pool.cpu_core_allocated,
            "available": pool.cpu_core_available,
            "limit": pool.cpu_core_limit,
            "weight": pool.cpu_weight,
        },
        "ram_usage": {
            "allocated": pool.ram_allocated,
            "available": pool.ram_available,
            "limit": pool.ram_limit_bytes,
            "reservation": pool.ram_reservation_bytes,
        },
        "storage_usage": {
            "allocated": pool.storage_allocated,
            "available": pool.storage_available,
            "limit": pool.storage_limit,
            "type": pool.storage_type,
        },
        "vm_count": len(pool.vms) if pool.vms else 0,
        "enabled": pool.enabled,
    }

    return stats


@router.post("/{pool_id}/disable")
async def disable_resource_pool(
    request: Request,
    pool_id: int,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    """
    Отключение ресурсного пула
    """
    logger.info(f"Отключение ресурсного пула {pool_id}")

    pool = await request.app.state.resource_pools_db.get_resource_pool(pool_id)
    if not pool:
        logger.info(f"Ресурсный пул {pool_id} не найден")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=Message.resource_pool_not_found.name,
        )

    # Отключаем пул
    await request.app.state.resource_pools_db.disable_resource_pool(pool_id)

    # Отправляем задачу через WebSocket
    await ws_task.send_json(
        pool.cluster_id,
        pool.node_id,
        CreateTask(
            task_type=TaskType.RESOURCE_POOL,
            action="disable",
            params=str({"pool_id": pool_id}),
        ),
    )

    logger.info(f"Ресурсный пул {pool_id} успешно отключен")
    return JSONResponse({"code": "Resource pool successfully disabled"})
