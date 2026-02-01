import uuid

import orjson
from fastapi import Request, HTTPException, APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi import status, Response

from api.dependencies import (
    get_logger,
    get_redis_service,
    get_users_db,
    get_hash_service,
    get_jwt_service,
)
from src.constants import ApiVersion
from src.models.error import ErrorMessage, DefaultMessage
from src.models.user import UserAuth


router = APIRouter(
    prefix=f"{ApiVersion.V0}/user",
    tags=["user"],
)


@router.post(f"/logout", status_code=status.HTTP_200_OK, response_model=bool | dict)
async def logout(
    request: Request,
    logger=Depends(get_logger),
    redis_service=Depends(get_redis_service),
):
    """
    Выход из аккаунта
    """

    logger.info(f"{request.method} {request.url} - Headers: {dict(request.headers)}")

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


@router.post(f"/login")
async def login(
    request: Request,
    response: Response,
    user_login: UserAuth,
    logger=Depends(get_logger),
    redis_service=Depends(get_redis_service),
    users_db=Depends(get_users_db),
    hash_service=Depends(get_hash_service),
    jwt_service=Depends(get_jwt_service),
):
    logger.info(f"{request.method} {request.url} - Headers: {dict(request.headers)}")

    user = await users_db.get_user_by_email(user_login.email)
    if user is None:
        error_model = DefaultMessage(
            request_id=str(uuid.uuid4()),
            code=ErrorMessage.user_not_found.name,
            success=False,
        ).model_dump()
        logger.info(
            f"- StatusCode: {status.HTTP_400_BAD_REQUEST} - Body: {error_model} - Headers: {dict(response.headers)}"
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content=error_model
        )

    if not hash_service.check_password(user_login.password, user.pass_hash):
        error_model = (
            DefaultMessage(
                request_id=str(uuid.uuid4()),
                code=ErrorMessage.wrong_password.name,
                success=False,
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
