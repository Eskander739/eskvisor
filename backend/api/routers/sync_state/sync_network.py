import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger
from src.constants import ApiVersion
from src.models.error import Message

router = APIRouter(
    prefix=f"{ApiVersion.V0}/sync/network",
    tags=["network-sync"],
)


@router.post("/{network_id}")
async def sync_network(
    request: Request,
    network_id: int,
    logger=Depends(get_logger),
):
    try:
        network = await request.app.state.virtual_networks_db.get_virtual_network(
            network_id
        )
        if network is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Виртуальная сеть не найдена",
            )
        node = await request.app.state.nodes_db.get_node(
            network.virtual_machine.node_id
        )
        if node is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден"
            )
        logger.info(f"Синхронизация диска {network.name}")
        url = f"http://{node.ip_address}/api/network/{network.name}"
        session = aiohttp.ClientSession()
        async with session.get(
            url=url, timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Хост недоступен"
                )

            network_data = await response.json()
            if network_data.get("code") != Message.virtual_network_found.name:
                if network_data.get("code") == Message.virtual_network_not_found.name:
                    await request.app.state.virtual_networks_db.mark_deleted(network_id)

                return JSONResponse(
                    content={
                        "node_id": node.id,
                        "code": "Network successfully updated",
                    },
                    status_code=status.HTTP_200_OK,
                )

            else:
                network_data = network_data["net_info"]
                if network_data is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Отсутствует информация о виртуальной сети",
                    )
                net_data = {
                    "active": network_data["active"],
                    "autostart": network_data["autostart"],
                    "ipv4_address": network_data["ipv4_address"],
                    "network_type": network_data["network_type"],
                    "persistent": network_data["persistent"],
                    "gateway": network_data["gateway"],
                    "dhcp_ranges": network_data["dhcp_ranges"],
                    "dns_forwarders": network_data["dns_forwarders"],
                    "dns_hosts": network_data["dns_hosts"],
                    "dns_txts": network_data["dns_txts"],
                    "bridge_name": network_data["bridge_name"],
                }
                await request.app.state.virtual_networks_db.update_virtual_network(
                    network_id, net_data
                )

                return JSONResponse(
                    content={
                        "node_id": node.id,
                        "code": "Network successfully updated",
                    },
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
