from enum import Enum

from pydantic import BaseModel


class DefaultMessage(BaseModel):
    success: bool
    request_id: str
    code: str
    note: str | None = None


class Message(Enum):
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
    incorrect_json_format = "Некорректный формат JSON"
    internal_error = "Внутренняя ошибка"
    vm_not_found = "Виртуальная машина не найдена"
    vm_already_created = "Виртуальная машина уже создана"
    disk_already_created = "Виртуальный диск уже создан"
    network_already_created = "Виртуальная сеть уже создана"
    network_not_found = "Виртуальная сеть не найдена"
    disk_not_found = "Виртуальный диск не найден"
    net_adapter_already_created = "Сетевой адаптер уже создан"
    net_adapter_not_found = "Сетевой адаптер не найден"
    agent_installation_started = "Установка агента запущена"
    agent_deleting_started = "Удаление агента запущено"
    vm_found_error = "VM found error"
    disk_founded = "Диск найден"
    virtual_network_found = "Виртуальная сеть найдена"
    virtual_network_not_found = "Виртуальная сеть не найдена"
    resource_pool_not_found = "Ресурс пул не найден"
    resource_pool_already_exists = "Ресурс пул уже создан"
