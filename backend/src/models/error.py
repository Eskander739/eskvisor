from enum import Enum

from pydantic import BaseModel


class DefaultError(BaseModel):
    request_id: str
    code: str


class ErrorMessage(Enum):
    user_not_found = "Пользователь не найден"
    user_is_not_registered = "Пользователя не зарегистрирован"
    user_is_not_updated = "Пользователь не был обновлен"
    wrong_password = "Неверный пароль"
    permission_denied = "Доступ запрещен"
    can_not_block_admin = "Нельзя заблокировать администратора"
    can_not_verify_admin = "Нельзя верифицировать администратора"
    can_not_unverify_admin = "Нельзя снять верификацию администратора"
    user_is_not_blocked = "Пользователь не заблокирован"
    user_is_not_verified = "Пользователь не верифицирован"
    user_is_verified = "Пользователь верифицирован"
    user_is_blocked = "Пользователь заблокирован"
    only_admin_have_access = "Доступ разрешен только для администратора"
    user_is_already_registered = "Пользователя уже зарегистрирован"
    wrong_email = "Некорректная почта"
    link_invalid = "Ссылка не актуальна, повторите процесс регистрации"
    email_already_confirmed = "Почта уже подтверждена"
    user_image_is_not_deleted = "Изображение пользователя не удалено"
    user_image_is_not_updated = "Изображение пользователя не обновлено"
    invalid_password = "Неправильный пароль"
    token_not_found = "Токен не найден"
    token_expired = "Срок токена истек"
    token_invalid = "Некорректный токен"