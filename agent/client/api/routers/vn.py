from fastapi import APIRouter, Depends

from agent.client.api.dependencies import get_logger, vm_manager_dependency

router = APIRouter(
    prefix="/api/network",
    tags=["network"],
)


@router.get("/list")
async def network_list(
    logger=Depends(get_logger),
    vm_manager=Depends(vm_manager_dependency),
):
    logger.info("Синхронизация виртуальных сетей")
    networks = vm_manager.network_manager.list_all_networks()

    return networks


@router.get("/{net_name}")
async def network(
    net_name: str,
    logger=Depends(get_logger),
    vm_manager=Depends(vm_manager_dependency),
):
    logger.info("Синхронизация вирутальной сети")
    network = vm_manager.network_manager.get_network_info(net_name)

    return network
