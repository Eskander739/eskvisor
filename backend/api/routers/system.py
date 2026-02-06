from fastapi import APIRouter, Depends, status, Request
from fastapi.responses import JSONResponse

from api.dependencies import get_agent_installer
from src.constants import ApiVersion, DEFAULT_AGENT_DIR
from src.models.agent import ConnectHostRequest, UpdateAgentRequest, DeleteAgentRequest
from src.models.error import Message
from src.models.general import HealthInfo, AgentResponse

router = APIRouter(
    prefix=f"{ApiVersion.V0}/system",
    tags=["system"],
)


@router.post("/install-agent", status_code=status.HTTP_200_OK)
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
        backend_ip=connect_host.backend_ip,
    )
    return AgentResponse(
        ip_address=connect_host.ip,
        username=connect_host.admin,
        code=Message.agent_installation_started.name,
    )


@router.put("/update-agent")
async def update_agent(
    update_host: UpdateAgentRequest, agent_installer=Depends(get_agent_installer)
):
    agent_installer.install_agent_via_ssh_async(
        hostname=update_host.ip,
        agent_package_path=(
            update_host.agent_file
            if update_host.agent_file is not None
            else DEFAULT_AGENT_DIR
        ),
        username=update_host.admin,
        is_update=True,
        backend_ip=update_host.backend_ip,
    )
    return AgentResponse(
        ip_address=update_host.ip,
        username=update_host.admin,
        code=Message.agent_installation_started.name,
    )


@router.delete("/delete-agent")
async def delete_agent(
    delete_host: DeleteAgentRequest, agent_installer=Depends(get_agent_installer)
):
    agent_installer.uninstall_agent_via_ssh_async(
        hostname=delete_host.ip,
        force=True,
        remove_dependencies=True,
        username=delete_host.admin,
        password=delete_host.password,
    )
    return AgentResponse(
        ip_address=delete_host.ip,
        username=delete_host.admin,
        code=Message.agent_deleting_started.name,
    )


@router.get("/health")
async def health(request: Request):
    """Проверка здоровья сервера"""
    health_info = HealthInfo(
        postgres_db=await request.app.state.users_db.check_connection(),
        redis=await request.app.state.redis_service.check_connection(),
    )

    if health_info.postgres_db and health_info.redis:
        return JSONResponse({"status": "healthy", "services": health_info.model_dump()})
    return JSONResponse({"status": "unhealthy", "services": health_info.model_dump()})
