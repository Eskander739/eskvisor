from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger
from src.constants import ApiVersion
from src.models.node import NodeSyncStateFromAgent, NodeSyncState

router = APIRouter(
    prefix=f"{ApiVersion.V0}/sync/vm",
    tags=["vm-sync"],
)


@router.post("/sync-state")
async def sync_vm(
    request: Request,
    node_data: NodeSyncStateFromAgent,
    logger=Depends(get_logger),
):
    raise NotImplementedError
    # try:
    #     logger.info(f"Синхронизация хоста {node_data.ip_address}")
    #     node = await request.app.state.nodes_db.get_node_by_ip_address(
    #         node_data.ip_address
    #     )
    #     if node is None:
    #         raise HTTPException(
    #             status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден"
    #         )
    #     node_data = NodeSyncState(**node_data.model_dump())
    #     await request.app.state.nodes_db.update_node(node_data)
    #
    #     return JSONResponse(
    #         content={"node_id": node.id, "code": "Node successfully updated"},
    #         status_code=status.HTTP_200_OK,
    #     )
    # except Exception as err:
    #     logger.error(f"Ошибка: {err}")
    #     return JSONResponse(
    #         content={"error": str(err), "code": "Internal server error"},
    #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #     )
