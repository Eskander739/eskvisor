from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from api.dependencies import get_agent_installer, get_redis_service, get_users_db
from src.constants import ApiVersion, DEFAULT_AGENT_DIR
from src.models.agent import ConnectHostRequest, UpdateAgentRequest
from src.models.error import Message
from src.models.general import HealthInfo, InstallAgentResponse

router = APIRouter(
    prefix=f"{ApiVersion.V0}/system",
    tags=["system"],
)


@router.post(f"/install-agent", status_code=status.HTTP_200_OK)
async def install_agent(
    connect_host: ConnectHostRequest, agent_installer=Depends(get_agent_installer)
):
    agent_installer.install_agent_via_ssh_async(
        hostname=connect_host.ip,
        agent_package_path=(
            connect_host.agent_file
            if connect_host.agent_file is not None
            else DEFAULT_AGENT_DIR
        ),
        username=connect_host.admin,
        password=connect_host.password,
    )
    return InstallAgentResponse(
        ip_address=connect_host.ip,
        username=connect_host.admin,
        code=Message.agent_installation_started.name,
    )


@router.post(f"/update-agent")
async def update_agent(
    connect_host: UpdateAgentRequest, agent_installer=Depends(get_agent_installer)
):
    agent_installer.install_agent_via_ssh_async(
        hostname=connect_host.ip,
        agent_package_path=(
            connect_host.agent_file
            if connect_host.agent_file is not None
            else DEFAULT_AGENT_DIR
        ),
        username=connect_host.admin,
        is_update=True,
    )
    return InstallAgentResponse(
        ip_address=connect_host.ip,
        username=connect_host.admin,
        code=Message.agent_installation_started.name,
    )


@router.get(f"/health")
async def health(
    redis_service=Depends(get_redis_service), users_db=Depends(get_users_db)
):
    """Проверка здоровья сервера"""
    health_info = HealthInfo(
        postgres_db=await users_db.check_connection(),
        redis=await redis_service.check_connection(),
    )

    if health_info.postgres_db and health_info.redis:
        return JSONResponse({"status": "healthy", "services": health_info.model_dump()})
    return JSONResponse({"status": "errors", "services": health_info.model_dump()})
