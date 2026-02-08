import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger
from src.constants import ApiVersion
from src.models.disk import DiskStatus
from src.models.error import Message

router = APIRouter(
    prefix=f"{ApiVersion.V0}/sync/disk",
    tags=["disk-sync"],
)


@router.post("/{disk_id}")
async def sync_disk(
    request: Request,
    disk_id: int,
    logger=Depends(get_logger),
):
    try:
        disk = await request.app.state.disks_db.get_disk_by_id(disk_id)
        if disk is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Диск не найдена"
            )
        node = await request.app.state.nodes_db.get_node(disk.virtual_machine.node_id)
        if node is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден"
            )
        logger.info(f"Синхронизация диска {disk.name}")
        url = f"http://{node.ip_address}/api/disk/{disk.name}/format/{disk.format.value}/pool/{True if disk.pool else False}"
        session = aiohttp.ClientSession()
        async with session.get(
            url=url, timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Хост недоступен"
                )

            disk_data = await response.json()
            if disk_data.get("code") != Message.disk_founded.name:
                await request.app.state.disks_db.update_disk_state(
                    disk_id, DiskStatus.DELETED
                )

                return JSONResponse(
                    content={"node_id": node.id, "code": "Disk successfully updated"},
                    status_code=status.HTTP_200_OK,
                )

            else:
                disk_data = disk_data["disk_info"]
                if disk_data is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Отсутствует информация о диске",
                    )
                await request.app.state.disks_db.update_disk_state(
                    disk_id, disk_data.get("status")
                )

                return JSONResponse(
                    content={"node_id": node.id, "code": "Disk successfully updated"},
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
