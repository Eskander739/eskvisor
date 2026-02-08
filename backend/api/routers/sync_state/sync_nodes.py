import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger
from src.constants import ApiVersion
from src.models.node import NodeSyncState

router = APIRouter(
    prefix=f"{ApiVersion.V0}/sync/node",
    tags=["nodes-sync"],
)


@router.post("/sync-state/{node_id}")
async def sync_node(
    request: Request,
    node_id: int,
    logger=Depends(get_logger),
):
    try:
        node = await request.app.state.nodes_db.get_node(node_id)
        if node is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден"
            )
        logger.info(f"Синхронизация хоста {node.ip_address}")
        url = f"http://{node.ip_address}/api/system/state"
        session = aiohttp.ClientSession()
        async with session.get(
            url=url, timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Хост недоступен"
                )
            node_data = NodeSyncState(**await response.json())
            await request.app.state.nodes_db.update_node(node_id, node_data)

            return JSONResponse(
                content={"node_id": node.id, "code": "Node successfully updated"},
                status_code=status.HTTP_200_OK,
            )

    except HTTPException as err:
        raise err

    except Exception as err:
        logger.error(f"Ошибка: {err}")
        return JSONResponse(
            content={"error": str(err), "code": "Internal server error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
