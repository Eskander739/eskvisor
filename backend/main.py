import uuid
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi import status
from starlette.middleware.cors import CORSMiddleware
from api.routers import users, system, vm, ws, nodes, clusters
from api.routers.sync_state import nodes as sync_nodes
from src.constants import ApiVersion, PROD_ENV
from src.db.balansir import ResourcePoolsDB
from src.db.clusters import ClustersDB
from src.db.disks import DisksDB
from src.db.nodes import NodesDB
from src.db.users import UsersDB
from src.db.virtual_machines import VirtualMachinesDB
from src.db.virtual_networks import VirtualNetworksDB
from src.logger_config import DefaultLogger
from src.models.error import Message, DefaultMessage
from src.services.jwt import JWTService
from src.services.pool.db_pool import DBPool
from src.services.pool.redis_pool import RedisPoolManager
from src.services.pool.task_ws_pool import TaskWebsocketPool
from src.services.redis_srv import RedisJWTManager
from src.services.ssh_keygen import SSHKeyGenerator

# Глобальные экземпляры

logger = DefaultLogger("Eskvisor Backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация
    db_pool = DBPool()
    await db_pool.create_tables()

    websocket_pool = TaskWebsocketPool(db_pool)
    await websocket_pool.create_connections()

    redis_pool = RedisPoolManager()
    await redis_pool.create_connections()

    # Сохраняем в состояние приложения
    app.state.db_pool = db_pool
    app.state.websocket_pool = websocket_pool
    app.state.redis_pool = redis_pool
    app.state.clusters_db = ClustersDB(app.state.db_pool)
    app.state.nodes_db = NodesDB(app.state.db_pool)
    app.state.users_db = UsersDB(app.state.db_pool)
    app.state.resource_pools_db = ResourcePoolsDB(app.state.db_pool)
    app.state.virtual_machines_db = VirtualMachinesDB(app.state.db_pool)
    app.state.disks_db = DisksDB(app.state.db_pool)
    app.state.virtual_networks_db = VirtualNetworksDB(app.state.db_pool)
    app.state.redis_service = RedisJWTManager(app.state.redis_pool)

    logger.info("Инициализация всех соединений")
    yield

    # Очистка
    if hasattr(app.state, "websocket_pool"):
        await app.state.websocket_pool.close_all()
    if hasattr(app.state, "db_pool"):
        await app.state.db_pool.close_pool()
    if hasattr(app.state, "redis_pool"):
        await app.state.redis_pool.close_all()


app = FastAPI(title="Eskvisor Backend", version="0.3", lifespan=lifespan)


load_dotenv()
load_dotenv(PROD_ENV)
SSHKeyGenerator().generate_and_save()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_token(
    request: Request,
    call_next,
):
    """
    Проверяет токен на:

    1. Наличие его в cookie
    2. Что токен еще актуален
    3. Что токен имеется в Redis
    """

    if request.method == "OPTIONS":
        return await call_next(request)
    # Пропускаем проверку токена для эндпоинтов, которые не требуют аутентификации
    if request.url.path in [
        "/docs",
        "/openapi.json",
        f"{ApiVersion.V0}/user/login",
        f"{ApiVersion.V0}/user/logout",
        f"{ApiVersion.V0}/sync/node/sync-state",
        f"{ApiVersion.V0}/system/health",
    ]:
        return await call_next(request)

    access_token = request.cookies.get("access_token")
    jwt_service = JWTService()
    redis_service = RedisJWTManager(request.app.state.redis_pool)
    if not access_token:
        error_model = DefaultMessage(
            request_id=str(uuid.uuid4()),
            code=Message.token_not_found.name,
            success=False,
        ).model_dump()
        logger.info(
            f"- StatusCode: {status.HTTP_401_UNAUTHORIZED} - Body: {error_model} - Headers: {dict(request.headers)}"
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content=error_model
        )
    if not jwt_service.validate_token(access_token):
        error_model = DefaultMessage(
            request_id=str(uuid.uuid4()),
            code=Message.token_expired.name,
            success=False,
        ).model_dump()
        logger.info(
            f"- StatusCode: {status.HTTP_401_UNAUTHORIZED} - Body: {error_model} - Headers: {dict(request.headers)}"
        )
        json_response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content=error_model
        )
        json_response.delete_cookie(
            key="access_token", secure=True, httponly=True, samesite="lax"
        )
        return json_response
    if not await redis_service.is_token_valid(access_token):
        error_model = DefaultMessage(
            request_id=str(uuid.uuid4()),
            code=Message.token_invalid.name,
            success=False,
        ).model_dump()
        logger.info(
            f"- StatusCode: {status.HTTP_401_UNAUTHORIZED} - Body: {error_model} - Headers: {dict(request.headers)}"
        )
        json_response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content=error_model
        )
        json_response.delete_cookie(
            key="access_token", secure=True, httponly=True, samesite="lax"
        )
        return json_response

    role = jwt_service.decode(access_token).get("role")
    print("Текущая роль: ", role)
    # TODO: Реализовать валидацию по ролевой модели

    response = await call_next(request)
    return response


# Подключаем роутеры
app.include_router(users.router)
app.include_router(system.router)
app.include_router(vm.router)
app.include_router(ws.router)
app.include_router(clusters.router)
app.include_router(nodes.router)
app.include_router(sync_nodes.router)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")
