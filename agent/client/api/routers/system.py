from fastapi import APIRouter, Depends

from agent.client.api.dependencies import get_queue_manager_service, get_cli_service
from agent.client.models.general import HealthState

router = APIRouter(
    prefix="/system",
    tags=["system"],
)


@router.get("/health")
async def health_check(
    queue_manager=Depends(get_queue_manager_service),
    cli_service=Depends(get_cli_service),
):
    """Проверка здоровья сервера"""
    task_manager = await cli_service.execute(
        ["systemctl", "is-active", "eskvisor-task-manager"]
    )
    health_state = HealthState(
        status="healthy",
        redis=queue_manager.check_connection(),
        task_manager=task_manager == "active" or "active" in task_manager,
    )
    if not health_state.redis or not health_state.task_manager:
        health_state.status = "unhealthy"

    return health_state
