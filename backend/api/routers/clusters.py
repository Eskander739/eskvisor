from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger
from src.constants import ApiVersion
from src.models.cluster import ClusterCreateRequest, ClusterUpdateRequest

router = APIRouter(
    prefix=f"{ApiVersion.V0}/cluster",
    tags=["clusters"],
)


@router.post("/create")
async def create_cluster(
    request: Request,
    cluster_data: ClusterCreateRequest,
    logger=Depends(get_logger),
):
    logger.info(f"Создание кластера {cluster_data.name}")
    cluster = await request.app.state.clusters_db.get_cluster_by_name(cluster_data.name)
    if cluster:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Кластер уже существует"
        )

    cluster_id = await request.app.state.clusters_db.create_cluster(cluster_data)
    await request.app.state.clusters_db.update_cluster_stats(cluster_id)

    return JSONResponse(
        content={"cluster_id": cluster_id, "code": "Cluster successfully created"},
        status_code=status.HTTP_201_CREATED,
    )


@router.post("/{cluster_id}/edit")
async def edit_cluster(
    cluster_id: int,
    cluster_data: ClusterUpdateRequest,
    request: Request,
    logger=Depends(get_logger),
):
    logger.info(f"Редактирование кластера {cluster_id}")

    cluster = await request.app.state.clusters_db.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Кластер не найден"
        )

    await request.app.state.clusters_db.update_cluster_stats(cluster_data)

    return JSONResponse({"code": "Cluster successfully updated"})


@router.get("/list")
async def list_clusters(
    request: Request,
    logger=Depends(get_logger),
):
    logger.info("Получение списка кластеров")

    clusters = await request.app.state.clusters_db.get_cluster_list()
    return {"clusters": clusters}


@router.get("/{cluster_id}")
async def get_cluster_by_id(
    cluster_id: int,
    request: Request,
    logger=Depends(get_logger),
):
    logger.info(f"Получение кластера {cluster_id}")

    cluster = await request.app.state.clusters_db.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Кластер не найден"
        )

    return cluster


@router.delete("/{cluster_id}/delete")
async def delete_cluster(
    cluster_id: int,
    request: Request,
    logger=Depends(get_logger),
):
    logger.info(f"Удаление кластера {cluster_id}")

    cluster = await request.app.state.clusters_db.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Кластер не найден"
        )

    if cluster.nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Необходимо удалить хосты для удаления кластера",
        )

    await request.app.state.clusters_db.delete_cluster_by_id(cluster_id)

    return JSONResponse({"code": "Cluster successfully deleted"})
