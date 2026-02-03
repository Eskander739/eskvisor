import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware

from agent.client.constants import PROD_ENV
from agent.client.api.routers import ws, system

load_dotenv()
load_dotenv(PROD_ENV)
app = FastAPI(title="Task Manager WebSocket Server", version="1.0.0")
templates = Jinja2Templates(
    directory="/opt/eskvisor/agent/client/task_manager/templates"
)
# templates = Jinja2Templates(
#     directory="/home/eska/eskvisor/agent/client/task_manager/templates"
# )


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

@app.get("/vnc-test", response_class=HTMLResponse)
async def get_vnc_test_page(request: Request):
    """Страница для тестирования VNC WebSocket подключения"""
    return templates.TemplateResponse("vnc.html", {"request": request})


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Для тестирования управления задачами"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

# Подключаем роутеры
app.include_router(ws.router)
app.include_router(system.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")
