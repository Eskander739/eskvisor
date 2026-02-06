from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger
from src.constants import ApiVersion
from src.models.node import NodeCreateRequest

router = APIRouter(
    prefix=f"{ApiVersion.V0}/node",
    tags=["nodes"],
)


@router.post("/create")
async def create_node(
    request: Request,
    node_data: NodeCreateRequest,
    logger=Depends(get_logger),
):
    logger.info(f"Создание хоста {node_data.name}")
    node = await request.app.state.nodes_db.get_node_by_name(node_data.name)
    if node:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Хост уже существует"
        )

    node_id = await request.app.state.nodes_db.add_node(node_data)

    if node_data.cluster_id:
        await request.app.state.clusters_db.update_cluster_stats(node_data.cluster_id)

    return JSONResponse(
        content={"node_id": node_id, "code": "Node successfully created"},
        status_code=status.HTTP_201_CREATED,
    )


@router.put("/{node_id}/edit")
async def edit_node(
    node_id: int,
    node_data: dict,
    request: Request,
    logger=Depends(get_logger),
):
    logger.info(f"Редактирование хоста {node_id}")

    node = await request.app.state.nodes_db.get_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден"
        )

    cluster_id_before = node.cluster_id
    cluster_id_after = node_data.get("cluster_id")

    if "id" in node_data:
        del node_data["id"]

    if cluster_id_before != cluster_id_after:
        if cluster_id_before:
            await request.app.state.clusters_db.update_cluster_stats(cluster_id_before)
        if cluster_id_after:
            await request.app.state.clusters_db.update_cluster_stats(cluster_id_after)

    return JSONResponse({"code": "Node successfully updated"})


@router.get("/list")
async def list_nodes(
    request: Request,
    cluster_id: int | None = None,
    enabled: bool | None = None,
    logger=Depends(get_logger),
):
    logger.info("Получение списка хостов")

    nodes = await request.app.state.nodes_db.get_all_nodes(
        cluster_id=cluster_id, enabled=enabled
    )
    return {"nodes": nodes}


@router.get("/{node_id}")
async def get_node_by_id(
    node_id: int,
    request: Request,
    logger=Depends(get_logger),
):
    logger.info(f"Получение хоста {node_id}")

    node = await request.app.state.nodes_db.get_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден"
        )

    return node


@router.delete("/{node_id}/delete")
async def delete_node(
    node_id: int,
    request: Request,
    logger=Depends(get_logger),
):
    logger.info(f"Удаление хоста {node_id}")

    node = await request.app.state.nodes_db.get_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден"
        )

    cluster_id = node.cluster_id
    await request.app.state.nodes_db.delete_node_by_id(node_id)

    if cluster_id:
        await request.app.state.clusters_db.update_cluster_stats(cluster_id)

    return JSONResponse({"code": "Node successfully deleted"})
