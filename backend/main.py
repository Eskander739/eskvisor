import uuid

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi import status
from starlette.middleware.cors import CORSMiddleware

from api.dependencies import get_jwt_service, get_redis_service
from api.routers import users, system, vm
from src.constants import ApiVersion, PROD_ENV
from src.logger_config import DefaultLogger
from src.models.error import ErrorMessage, DefaultMessage
from src.services.ssh_keygen import SSHKeyGenerator

app = FastAPI(title="Eskvisor Backend", version="1.0.0")


load_dotenv()
load_dotenv(PROD_ENV)
logger = DefaultLogger("Eskvisor Backend")
ssh_key_generator = SSHKeyGenerator()
ssh_key_generator.generate_and_save()
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
    jwt_service=Depends(get_jwt_service),
    redis_service=Depends(get_redis_service),
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
            code=ErrorMessage.token_not_found.name,
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
            code=ErrorMessage.token_expired.name,
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
            code=ErrorMessage.token_invalid.name,
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
