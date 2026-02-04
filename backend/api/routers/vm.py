from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger, get_ws_task, get_virtual_machines_db
from src.constants import ApiVersion
from src.models.error import Message
from src.models.vm import VMCreateRequest, VmUpdateRequest, VMListRequest
from src.services.pool.task_ws_pool import TaskWebsocketPool

router = APIRouter(
    prefix=f"{ApiVersion.V0}/vm",
    tags=["vm"],
)


@router.post("/create")
async def create_vm(
    vm_info: VMCreateRequest,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
    virtual_machines_db=Depends(get_virtual_machines_db),
):
    logger.info(f"Создание виртуальной машины{vm_info.name}")
    virtual_machines_db.create_virtual_machine(vm_info.model_dump())
    await ws_task.send_json(
        vm_info.cluster_id, vm_info.node_id, vm_info.model_dump_json()
    )
    return JSONResponse({"code": "VM successfully created"})


@router.post("/{vm_id}/edit")
async def edit_vm(
    vm_id: int,
    vm_info: VmUpdateRequest,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
    virtual_machines_db=Depends(get_virtual_machines_db),
):

    vm = await virtual_machines_db.get_virtual_machine(vm_id)
    if vm is None:
        logger.info(f"Виртуальная машина {vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found
        )
    logger.info(f"Редактирование виртуальной машины{vm_info.name}")
    virtual_machines_db.update_virtual_machine_with_request(vm_info)
    await ws_task.send_json(
        vm_info.cluster_id, vm_info.node_id, vm_info.model_dump_json()
    )
    return JSONResponse({"code": "VM successfully edited"})


@router.get("/list")
async def list_vm(
    vm_info: VMListRequest,
    logger=Depends(get_logger),
    virtual_machines_db=Depends(get_virtual_machines_db),
):
    vms = await virtual_machines_db.get_virtual_machines_list(vm_info)
    logger.info(f"Редактирование виртуальной машины{vm_info.name}")
    vms = {"vms": vms}
    return vms


@router.get("/{vm_id}")
async def vm_by_id(
    vm_id: int,
    vm_info: VmUpdateRequest,
    logger=Depends(get_logger),
    virtual_machines_db=Depends(get_virtual_machines_db),
):
    vm = await virtual_machines_db.get_virtual_machine(vm_id)
    if vm is None:
        logger.info(f"Виртуальная машина {vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found
        )
    logger.info(f"Редактирование виртуальной машины{vm_info.name}")
    return vm


@router.put("/{vm_id}/start")
async def start_vm():
    return JSONResponse({"code": "VM successfully started"})


@router.put("/{vm_id}/stop")
async def stop_vm():
    return JSONResponse({"code": "VM successfully started"})


@router.put("/{vm_id}/reboot")
async def reboot_vm():
    return JSONResponse({"code": "VM successfully rebooted"})


@router.delete("/{vm_id}/delete")
async def delete_vm():
    return JSONResponse({"code": "VM successfully deleted"})
