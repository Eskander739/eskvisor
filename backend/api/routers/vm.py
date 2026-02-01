from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.constants import ApiVersion

router = APIRouter(
    prefix=f"{ApiVersion.V0}/vm",
    tags=["vm"],
)


@router.post("/create")
async def create_vm():
    return JSONResponse({"code": "VM successfully created"})


@router.post("/{vm_id}/edit")
async def edit_vm():
    return JSONResponse({"code": "VM successfully edited"})


@router.get("/list")
async def list_vm():
    return JSONResponse({"code": "VM successfully founded"})


@router.get("/{vm_id}")
async def vm_by_id(vm_id: int):
    return JSONResponse({"code": f"VM successfully founded by id: {vm_id}"})


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
