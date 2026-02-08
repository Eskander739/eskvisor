from fastapi import APIRouter, Depends

from agent.client.api.dependencies import get_logger, vm_manager_dependency

router = APIRouter(
    prefix="/api/vm",
    tags=["vm"],
)


@router.get("/list")
async def vm_list(
    logger=Depends(get_logger),
    vm_manager=Depends(vm_manager_dependency),
):
    logger.info("Синхронизация списка ВМ")
    list_vms = vm_manager.list_vms()

    return list_vms


@router.get("/{vm_uuid}")
async def vm(
    vm_uuid: str,
    logger=Depends(get_logger),
    vm_manager=Depends(vm_manager_dependency),
):
    logger.info("Синхронизация ВМ")
    vm = vm_manager.get_vm_by_name(vm_uuid)

    return vm
