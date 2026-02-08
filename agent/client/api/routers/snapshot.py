from fastapi import APIRouter, Depends

from agent.client.api.dependencies import get_logger, vm_manager_dependency

router = APIRouter(
    prefix="/api/snapshot",
    tags=["snapshot"],
)


@router.get("/{snapshot_name}/vm/{vm_name}")
async def snapshot(
    vm_name: str,
    snapshot_name: str,
    logger=Depends(get_logger),
    vm_manager=Depends(vm_manager_dependency),
):
    logger.info("Синхронизация снапшота")
    network = vm_manager.snapshot.snapshot_by_name(vm_name, snapshot_name)

    return network
