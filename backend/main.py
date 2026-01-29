import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware

from src.agent_installer import AgentInstaller
from src.constants import ApiVersion, DEFAULT_AGENT_DIR
from src.logger_config import DefaultLogger
from src.models.agent import ConnectHostRequest
from src.security.ssh_keygen import SSHKeyGenerator

app = FastAPI(title="Eskvisor Backend", version="1.0.0")
# templates = Jinja2Templates(directory="task_manager/templates")


logger = DefaultLogger("Eskvisor Backend")
ssh_key_generator = SSHKeyGenerator()
agent_installer = AgentInstaller()
ssh_key_generator.generate_and_save()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Добавьте middleware для CSP заголовков
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    # Разрешаем только локальные скрипты и блокируем document.write
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "object-src 'none';"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.post(f"{ApiVersion.V0}/install-agent")
async def connect(request: Request, connect_host: ConnectHostRequest):
    agent_installer.install_agent_via_ssh(
        hostname=connect_host.ip,
        agent_package_path=connect_host.agent_file if connect_host.agent_file is not None else DEFAULT_AGENT_DIR,
        username=connect_host.admin,
        password=connect_host.password,
    )


@app.get(f"{ApiVersion.V0}/health")
async def health_check():
    """Проверка здоровья сервера"""
    return JSONResponse({"status": "healthy", "service": "task-manager-ws"})


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")
