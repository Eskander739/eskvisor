import uuid

import orjson
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi import status, Response
from starlette.middleware.cors import CORSMiddleware

from src.services.hash import HashService
from src.agent_installer import AgentInstaller
from src.constants import ApiVersion, DEFAULT_AGENT_DIR, PROD_ENV
from src.db.users import UsersDB
from src.services.jwt import JWTService
from src.logger_config import DefaultLogger
from src.models.agent import ConnectHostRequest
from src.models.error import ErrorMessage, DefaultError
from src.models.user import UserAuth
from src.services.redis_srv import RedisJWTManager
from src.services.ssh_keygen import SSHKeyGenerator

app = FastAPI(title="Eskvisor Backend", version="1.0.0")


load_dotenv()
load_dotenv(PROD_ENV)
logger = DefaultLogger("Eskvisor Backend")
ssh_key_generator = SSHKeyGenerator()
agent_installer = AgentInstaller()
redis_service = RedisJWTManager()
jwt_service = JWTService()
hash_service = HashService()
users_db = UsersDB()
ssh_key_generator.generate_and_save()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_token(request: Request, call_next):
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
    ]:
        return await call_next(request)

    access_token = request.cookies.get("access_token")
    if not access_token:
        error_model = DefaultError(
            request_id=str(uuid.uuid4()),
            code=ErrorMessage.token_not_found.name,
        ).model_dump()
        logger.info(
            f"- StatusCode: {status.HTTP_401_UNAUTHORIZED} - Body: {error_model} - Headers: {dict(request.headers)}"
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content=error_model
        )
    if not jwt_service.validate_token(access_token):
        error_model = DefaultError(
            request_id=str(uuid.uuid4()),
            code=ErrorMessage.token_expired.name,
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
        error_model = DefaultError(
            request_id=str(uuid.uuid4()),
            code=ErrorMessage.token_invalid.name,
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
    # TODO: Реализовать валидацию по ролевой модели

    response = await call_next(request)
    return response



@app.post(f"{ApiVersion.V0}/user/logout", status_code=status.HTTP_200_OK, response_model=bool | dict)
async def logout(request: Request):
    """
    Выход из аккаунта
    """

    logger.info(
        f"{request.method} {request.url} - Headers: {dict(request.headers)}"
    )

    access_token = request.cookies.get("access_token")
    await redis_service.invalidate_token(access_token)
    response = Response(
        status_code=status.HTTP_200_OK,
        content=orjson.dumps({"message": "Выход успешно произведен"}),
        media_type="application/json; charset=utf-8",
    )
    response.delete_cookie(
        key="access_token", secure=True, httponly=True, samesite="lax"
    )
    logger.info(
        f"- StatusCode: {status.HTTP_200_OK} - Body: {orjson.loads(response.body)} - Headers: {dict(response.headers)}"
    )
    return response

@app.post(f"{ApiVersion.V0}/user/login")
async def login(request: Request, response: Response, user_login: UserAuth):
    logger.info(
        f"{request.method} {request.url} - Headers: {dict(request.headers)}"
    )

    user = await users_db.get_user_by_email(user_login.email)
    if user is None:
        error_model = DefaultError(
            request_id=str(uuid.uuid4()),
            code=ErrorMessage.user_not_found.name).model_dump()
        logger.info(
            f"- StatusCode: {status.HTTP_400_BAD_REQUEST} - Body: {error_model} - Headers: {dict(response.headers)}"
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content=error_model
        )

    if not hash_service.check_password(user_login.password, user.pass_hash):
        error_model = (
            DefaultError(
                request_id=str(uuid.uuid4()),
                code=ErrorMessage.wrong_password.name,
            ).model_dump(),
        )
        logger.info(
            f"- StatusCode: {status.HTTP_401_UNAUTHORIZED} - Body: {error_model} - Headers: {dict(response.headers)}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_model,
        )

    data_for_token = {"email": user_login.email, "role": user.role.value}

    tokens = []
    for token in await redis_service.get_all_tokens():
        try:
            current_data_for_token = jwt_service.decode(token)
            if current_data_for_token.get("email") == data_for_token.get("email"):
                tokens.append(token)
        except ValueError as err:
            if err == "Token expired":
                await redis_service.invalidate_token(token)

    for token in tokens:
        await redis_service.invalidate_token(token)

    data_for_token["role"] = user.role.value
    token = jwt_service.encode(data_for_token)
    await redis_service.add_token(token)
    msg = {"message": "Авторизация успешно произведена"}
    response_result = Response(
        status_code=status.HTTP_200_OK,
        content=orjson.dumps(msg),
        media_type="application/json; charset=utf-8",
    )
    logger.info(
        f"- StatusCode: {status.HTTP_200_OK} - Body: {msg} - Headers: {dict(response.headers)}"
    )
    response_result.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,  # Только HTTPS
        samesite="none",
        max_age=86400 * 7,  # неделя
    )

    return response_result


@app.post(f"{ApiVersion.V0}/system/install-agent")
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
