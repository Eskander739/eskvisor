from fastapi import APIRouter, Depends

from agent.client.api.dependencies import get_logger, vm_manager_dependency
from agent.client.hypervisor.libvirt.models.volume.disk import DiskFormat

router = APIRouter(
    prefix="/api/disk",
    tags=["disk"],
)


@router.get("/list")
async def disk_list(
    logger=Depends(get_logger),
    vm_manager=Depends(vm_manager_dependency),
):
    logger.info("Синхронизация дисков")
    current_disk_list = vm_manager.storage_manager.list_disks()

    return current_disk_list


@router.get("/{disk_name}/format/{disk_format}/pool/{is_pool}")
async def disk(
    disk_name: str,
    disk_format: DiskFormat,
    is_pool: bool = False,
    logger=Depends(get_logger),
    vm_manager=Depends(vm_manager_dependency),
):
    logger.info("Синхронизация диска")
    current_disk = vm_manager.storage_manager.get_disk_info(
        disk_name, disk_format=disk_format, is_pool=is_pool
    )

    return current_disk
