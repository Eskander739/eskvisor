import uuid
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi import status
from starlette.middleware.cors import CORSMiddleware
from api.routers import users, system, vm
from src.constants import ApiVersion, PROD_ENV
from src.globals import redis_pool_instance, websocket_pool_instance, db_pool_instance
from src.logger_config import DefaultLogger
from src.models.error import Message, DefaultMessage
from src.services.jwt import JWTService
from src.services.pool.db_pool import DBPool
from src.services.pool.redis_pool import RedisPoolManager
from src.services.pool.task_ws_pool import TaskWebsocketPool
from src.services.redis_srv import RedisJWTManager
from src.services.ssh_keygen import SSHKeyGenerator

# Глобальные экземпляры


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_pool_instance
    global websocket_pool_instance
    global db_pool_instance

    db_pool_instance = DBPool()
    await db_pool_instance.create_connections()
    await db_pool_instance.create_tables()

    websocket_pool_instance = TaskWebsocketPool(db_pool_instance)
    await websocket_pool_instance.create_connections()
    redis_pool_instance = RedisPoolManager()
    await redis_pool_instance.create_connections()

    yield

    if websocket_pool_instance:
        await websocket_pool_instance.close_all()
    if db_pool_instance:
        await db_pool_instance.close_all()
    if redis_pool_instance:
        await redis_pool_instance.close_all()


app = FastAPI(title="Eskvisor Backend", version="0.3", lifespan=lifespan)


load_dotenv()
load_dotenv(PROD_ENV)
logger = DefaultLogger("Eskvisor Backend")
SSHKeyGenerator().generate_and_save()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_main_redis_service() -> RedisJWTManager:
    return RedisJWTManager(redis_pool_instance)


async def get_main_jwt_service() -> JWTService:
    return JWTService()


@app.middleware("http")
async def check_token(
    request: Request,
    call_next,
    jwt_service=Depends(get_main_jwt_service),
    redis_service=Depends(get_main_redis_service),
):
    """
    Проверяет токен на:

    1. Наличие его в cookie
    2. Что токен еще актуален
    3. Что токен имеется в Redis
    """
    jwt_service = await jwt_service.dependency()
    redis_service = await redis_service.dependency()
    if request.method == "OPTIONS":
        return await call_next(request)
    # Пропускаем проверку токена для эндпоинтов, которые не требуют аутентификации
    if request.url.path in [
        "/docs",
        "/openapi.json",
        f"{ApiVersion.V0}/user/login",
        f"{ApiVersion.V0}/user/logout",
    ]:
        return await call_next(request)

    access_token = request.cookies.get("access_token")
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")
