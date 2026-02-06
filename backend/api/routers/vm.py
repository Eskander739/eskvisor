import uuid

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette import status

from api.dependencies import get_logger, get_ws_task
from src.constants import ApiVersion
from src.models.error import Message
from src.models.general import VMState, CreateTask, TaskType
from src.models.vm import VMCreateRequest, VmUpdateRequest, VMListRequest
from src.services.pool.task_ws_pool import TaskWebsocketPool

router = APIRouter(
    prefix=f"{ApiVersion.V0}/vm",
    tags=["vm"],
)


@router.post("/create")
async def create_vm(
    request: Request,
    vm_info: VMCreateRequest,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    logger.info(f"Создание виртуальной машины{vm_info.name}")
    vm_info.uuid = str(uuid.uuid4())
    vm_info.name = str(uuid.uuid4())
    vm_info_model_string = vm_info.model_dump_json()
    vm_info_model = orjson.loads(vm_info_model_string)
    vm = await request.app.state.virtual_machines_db.get_virtual_machine_by_name(
        vm_info.name
    )
    # if vm:
    #     logger.info(f"Виртуальная машина {vm_info.name} уже создана")
    #     raise HTTPException(
    #         status_code=status.HTTP_400_BAD_REQUEST, detail=Message.vm_already_created.name
    #     )
    await request.app.state.virtual_machines_db.create_virtual_machine(vm_info_model)
    await ws_task.send_json(
        vm_info.cluster_id,
        vm_info.node_id,
        CreateTask(task_type=TaskType.VM, action="create", params=vm_info_model_string),
    )
    return JSONResponse({"code": "VM successfully created"})


@router.put("/{vm_id}/edit")
async def edit_vm(
    request: Request,
    vm_id: int,
    vm_info: VmUpdateRequest,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):

    vm = await request.app.state.virtual_machines_db.get_virtual_machine(vm_id)
    if vm is None:
        logger.info(f"Виртуальная машина {vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found.name
        )
    logger.info(f"Редактирование виртуальной машины {vm_info.name}")
    request.app.state.virtual_machines_db.update_virtual_machine_with_request(vm_info)
    await ws_task.send_json(
        vm_info.cluster_id,
        vm_info.node_id,
        CreateTask(
            task_type=TaskType.VM, action="edit", params=vm_info.model_dump_json()
        ),
    )
    return JSONResponse({"code": "VM successfully edited"})


@router.get("/list")
async def list_vm(
    request: Request,
    vm_info: VMListRequest = VMListRequest(),
    logger=Depends(get_logger),
):
    vms = await request.app.state.virtual_machines_db.get_virtual_machines_list(vm_info)
    logger.info(f"Получение списка виртуальных машин {vm_info.name}")
    vms = {"vms": vms}
    return vms


@router.get("/{vm_id}")
async def vm_by_id(
    request: Request,
    vm_id: int,
    logger=Depends(get_logger),
):
    vm = await request.app.state.virtual_machines_db.get_virtual_machine(vm_id)
    if vm is None:
        logger.info(f"Виртуальная машина {vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found.name
        )
    logger.info(f"Получение виртуальной машины{vm_id}")
    return vm


@router.put("/{vm_id}/start")
async def start_vm(
    request: Request,
    vm_id: int,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    vm = await request.app.state.virtual_machines_db.get_virtual_machine(vm_id)
    if vm is None:
        logger.info(f"Виртуальная машина {vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found.name
        )
    await request.app.state.virtual_machines_db.update_state_virtual_machine(
        vm_id, VMState.STARTING
    )
    await ws_task.send_json(
        vm.cluster_id,
        vm.node_id,
        CreateTask(task_type=TaskType.VM, action="resume", params={"vm_name": vm.uuid}),
    )
    logger.info(f"Запуск виртуальной машины{vm_id}")

    return vm


@router.put("/{vm_id}/pause")
async def pause_vm(
    request: Request,
    vm_id: int,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    vm = await request.app.state.virtual_machines_db.get_virtual_machine(vm_id)
    if vm is None:
        logger.info(f"Виртуальная машина {vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found.name
        )
    await request.app.state.virtual_machines_db.update_state_virtual_machine(
        vm_id, VMState.PAUSING
    )
    await ws_task.send_json(
        vm.cluster_id,
        vm.node_id,
        CreateTask(
            task_type=TaskType.VM, action="suspend", params={"vm_name": vm.uuid}
        ),
    )
    logger.info(f"Пристановка виртуальной машины{vm_id}")


@router.put("/{vm_id}/shutoff/{force}")
async def shutoff_vm(
    request: Request,
    vm_id: int,
    force: bool = False,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    vm = await router.state.virtual_machines_db.get_virtual_machine(vm_id)
    if vm is None:
        logger.info(f"Виртуальная машина {vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found.name
        )
    await request.app.state.virtual_machines_db.update_state_virtual_machine(
        vm_id, VMState.SHUTDOWN
    )
    await ws_task.send_json(
        vm.cluster_id,
        vm.node_id,
        CreateTask(
            task_type=TaskType.VM,
            action="shutoff",
            params={"vm_name": vm.uuid, "force": force},
        ),
    )
    logger.info(f"Выключение виртуальной машины{vm_id}")


@router.put("/{vm_id}/reboot")
async def reboot_vm(
    request: Request,
    vm_id: int,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    vm = await request.app.state.virtual_machines_db.get_virtual_machine(vm_id)
    if vm is None:
        logger.info(f"Виртуальная машина {vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found.name
        )
    await request.app.state.virtual_machines_db.update_state_virtual_machine(
        vm_id, VMState.REBOOT
    )
    await ws_task.send_json(
        vm.cluster_id,
        vm.node_id,
        CreateTask(task_type=TaskType.VM, action="reboot", params={"vm_name": vm.uuid}),
    )
    logger.info(f"Перезагрузка виртуальной машины{vm_id}")


@router.delete("/{vm_id}/delete")
async def delete_vm(
    request: Request,
    vm_id: int,
    logger=Depends(get_logger),
    ws_task: TaskWebsocketPool = Depends(get_ws_task),
):
    vm = await request.app.state.virtual_machines_db.get_virtual_machine(vm_id)
    if vm is None:
        logger.info(f"Виртуальная машина {vm_id} не найдена")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=Message.vm_not_found.name
        )
    await request.app.state.virtual_machines_db.update_state_virtual_machine(
        vm_id, VMState.DELETING
    )
    await ws_task.send_json(
        vm.cluster_id,
        vm.node_id,
        CreateTask(task_type=TaskType.VM, action="delete", params={"vm_name": vm.uuid}),
    )
    logger.info(f"Удаление виртуальной машины{vm_id}")
