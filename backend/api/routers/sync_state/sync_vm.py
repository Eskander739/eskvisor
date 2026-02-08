import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger
from src.constants import ApiVersion
from src.models.error import Message
from src.models.vm import VirtualMachineFromAgent
from src.tools.general import convert_vm_state

router = APIRouter(
    prefix=f"{ApiVersion.V0}/sync/vm",
    tags=["vm-sync"],
)


@router.post("/{vm_id}")
async def sync_vm(
    request: Request,
    vm_id: int,
    logger=Depends(get_logger),
):
    try:
        vm = await request.app.state.virtual_machines_db.get_virtual_machine(vm_id)
        if vm is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="ВМ не найдена"
            )
        node = await request.app.state.nodes_db.get_node(vm.node_id)
        if node is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден"
            )
        logger.info(f"Синхронизация ВМ {vm.name}")
        url = f"http://{node.ip_address}/api/vm/{vm.uuid}"
        session = aiohttp.ClientSession()
        async with session.get(
            url=url, timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Хост недоступен"
                )

            vm_data = await response.json()
            if vm_data.get("code") == Message.vm_found_error.name:
                await request.app.state.virtual_machines_db.update_state_virtual_machine(
                    vm_id, convert_vm_state(-1)
                )

                return JSONResponse(
                    content={"node_id": node.id, "code": "VM successfully updated"},
                    status_code=status.HTTP_200_OK,
                )

            else:
                vm_data = vm_data["vm_info"]
                if vm_data is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Отсутствует информация о ВМ",
                    )
                vm_data = VirtualMachineFromAgent.model_validate(vm_data)
                await request.app.state.virtual_machines_db.update_state_virtual_machine(
                    vm_id, convert_vm_state(vm_data.state)
                )

                return JSONResponse(
                    content={"node_id": node.id, "code": "VM successfully updated"},
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
