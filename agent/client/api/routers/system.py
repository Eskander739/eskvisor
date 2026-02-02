from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from agent.client.api.dependencies import get_queue_manager_service

router = APIRouter(
    prefix="/system",
    tags=["system"],
)


@router.get("/health")
async def health_check(queue_manager = Depends(get_queue_manager_service)):
    """Проверка здоровья сервера"""
    return JSONResponse(
        {
            "status": "healthy",
            "redis": queue_manager.check_connection(),
        }
    )
