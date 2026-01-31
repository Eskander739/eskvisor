from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from src.rbac.permissions import Permission, RolePermissions


class UserStatus(Enum):
    """Статус пользователя"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class UserRole(Enum):
    """Роли пользователей в системе"""

    SUPER_ADMIN = "super_admin"
    INFRA_ADMIN = "infrastructure_admin"
    VIRTUALIZATOR = "virtualizator"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Group(BaseModel):
    """Группа пользователей"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=2, max_length=100)
    description: str = ""
    is_system: bool = False  # Системная группа (нельзя удалить)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class User(BaseModel):
    """Модель пользователя"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    username: str = Field(
        ..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-\.]+$"
    )
    email: str
    full_name: str = Field("", max_length=200)
    role: UserRole = UserRole.VIEWER
    status: UserStatus = UserStatus.ACTIVE

    # Принадлежность к группам
    group_ids: list[UUID] = Field(default_factory=list)

    # Метаданные
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime | None = None

    # Внешние ID (например, из LDAP, OAuth)
    external_id: str | None = None
    external_source: str | None = None

    @property
    def is_active(self) -> bool:
        """Проверка, активен ли пользователь"""
        return self.status == UserStatus.ACTIVE

    @property
    def is_super_admin(self) -> bool:
        """Проверка, является ли супер-админом"""
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_infra_admin(self) -> bool:
        """Проверка, является ли инфраструктурным админом"""
        return self.role == UserRole.INFRA_ADMIN

    def get_role_permissions(self) -> set[Permission]:
        """Получить разрешения, соответствующие роли пользователя"""
        role_permissions = {
            UserRole.SUPER_ADMIN: RolePermissions.SUPER_ADMIN,
            UserRole.INFRA_ADMIN: RolePermissions.INFRA_ADMIN,
            UserRole.VIRTUALIZATOR: RolePermissions.VIRTUALIZATOR,
            UserRole.OPERATOR: RolePermissions.OPERATOR,
            UserRole.VIEWER: RolePermissions.VIEWER,
        }
        return role_permissions.get(self.role, set())

    def has_permission(
        self, resource_type: str, action: str, resource_owner_id: UUID | None = None
    ) -> bool:
        """Проверяет, есть ли у пользователя право на действие"""
        permissions = self.get_role_permissions()

        for perm in permissions:
            if (
                perm.resource_type.value == resource_type
                and perm.action.value == action
            ):
                # Проверяем область видимости
                return perm.check_scope(self.id, resource_owner_id)

        return False

    def can_manage_vm(self, vm_owner_id: UUID | None = None) -> bool:
        """Может ли управлять ВМ (создавать, редактировать, удалять свои)"""
        return self.has_permission("virtual_machine", "create", vm_owner_id)

    def can_view_all_vms(self) -> bool:
        """Может ли просматривать все ВМ"""
        return self.has_permission("virtual_machine", "read")

    def can_manage_networks(self) -> bool:
        """Может ли управлять сетями"""
        return self.has_permission("network", "manage")

    def can_manage_resource_pools(self) -> bool:
        """Может ли управлять ресурсными пулами"""
        return self.has_permission("resource_pool", "manage")

    def can_manage_users(self) -> bool:
        """Может ли управлять пользователями"""
        return self.has_permission("system", "manage_users")


class UserCreate(BaseModel):
    """Модель для создания пользователя"""

    username: str = Field(
        ..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-\.]+$"
    )
    email: str
    full_name: str = Field("", max_length=200)
    password: str = Field(..., min_length=8)  # В реальном приложении - хэш
    role: UserRole = UserRole.VIEWER
    group_ids: list[UUID] = Field(default_factory=list)

    @field_validator("password")
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdate(BaseModel):
    """Модель для обновления пользователя"""

    email: str | None = None
    full_name: str | None = None
    role: UserRole | None = None
    status: UserStatus | None = None
    group_ids: list[UUID] | None = None


class UserSession(BaseModel):
    """Сессия пользователя"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    token: str  # JWT или другой токен
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    ip_address: str | None = None
    user_agent: str | None = None

    @property
    def is_expired(self) -> bool:
        """Проверяет, истекла ли сессия"""
        return datetime.utcnow() > self.expires_at

    def refresh(self, expires_in_hours: int = 24) -> None:
        """Обновляет время жизни сессии"""
        self.expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
        self.last_activity = datetime.utcnow()


class ResourceAccess(BaseModel):
    """Назначение доступа к ресурсам для пользователей/групп"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    resource_type: str  # Тип ресурса (vm, disk, network, pool)
    resource_id: UUID  # ID конкретного ресурса
    user_id: UUID | None = None  # Если None - доступ для группы
    group_id: UUID | None = None
    permission_level: str  # Например: "read", "write", "manage"
    granted_by: UUID  # Кто выдал доступ
    granted_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Активен ли доступ"""
        if self.expires_at:
            return datetime.utcnow() < self.expires_at
        return True


class AuthService:
    """Сервис для работы с аутентификацией и авторизацией"""

    @staticmethod
    def get_role_permissions(role: UserRole) -> set[Permission]:
        """Получить разрешения для роли"""
        return {
            UserRole.SUPER_ADMIN: RolePermissions.SUPER_ADMIN,
            UserRole.INFRA_ADMIN: RolePermissions.INFRA_ADMIN,
            UserRole.VIRTUALIZATOR: RolePermissions.VIRTUALIZATOR,
            UserRole.OPERATOR: RolePermissions.OPERATOR,
            UserRole.VIEWER: RolePermissions.VIEWER,
        }[role]

    @staticmethod
    def check_permission(
        user: User,
        resource_type: str,
        action: str,
        resource_owner_id: UUID | None = None,
    ) -> bool:
        """Проверка прав пользователя на действие"""
        return user.has_permission(resource_type, action, resource_owner_id)

    @staticmethod
    def filter_resources_by_permission(
        user: User, resources: list[Any], resource_type: str, action: str = "read"
    ) -> list[Any]:
        """Фильтрует ресурсы по правам пользователя"""
        if user.has_permission(resource_type, action):
            # Если есть глобальный доступ
            return resources

        # Для OWNED scope фильтруем по владельцу
        filtered = []
        for resource in resources:
            # Предполагаем, что у ресурса есть поле owner_id
            if hasattr(resource, "owner_id"):
                if user.has_permission(resource_type, action, resource.owner_id):
                    filtered.append(resource)

        return filtered


# Глобальная конфигурация ролевой модели
class RoleBasedAccessControl:
    """Глобальная конфигурация RBAC системы"""

    # Доступные роли в системе
    AVAILABLE_ROLES: dict[UserRole, dict[str, Any]] = {
        UserRole.SUPER_ADMIN: {
            "name": "Супер-Администратор",
            "description": "Полный доступ ко всем функциям системы",
            "permissions": RolePermissions.SUPER_ADMIN,
            "is_system": True,
            "max_users": 2,  # Ограничение количества супер-админов
        },
        UserRole.INFRA_ADMIN: {
            "name": "Администратор Инфраструктуры",
            "description": "Управление инфраструктурой: сети, хранилища, пулы, хосты",
            "permissions": RolePermissions.INFRA_ADMIN,
            "is_system": True,
        },
        UserRole.VIRTUALIZATOR: {
            "name": "Виртуализатор",
            "description": "Создание и управление своими ВМ, дисками, снапшотами",
            "permissions": RolePermissions.VIRTUALIZATOR,
            "is_system": False,
        },
        UserRole.OPERATOR: {
            "name": "Оператор",
            "description": "Просмотр всех ВМ, управление состоянием, доступ к консоли",
            "permissions": RolePermissions.OPERATOR,
            "is_system": False,
        },
        UserRole.VIEWER: {
            "name": "Только чтение",
            "description": "Просмотр всех сущностей без возможности изменений",
            "permissions": RolePermissions.VIEWER,
            "is_system": False,
        },
    }

    # Иерархия ролей (роли выше имеют права ролей ниже)
    ROLE_HIERARCHY: dict[UserRole, list[UserRole]] = {
        UserRole.SUPER_ADMIN: [
            UserRole.INFRA_ADMIN,
            UserRole.VIRTUALIZATOR,
            UserRole.OPERATOR,
            UserRole.VIEWER,
        ],
        UserRole.INFRA_ADMIN: [
            UserRole.VIRTUALIZATOR,
            UserRole.OPERATOR,
            UserRole.VIEWER,
        ],
        UserRole.VIRTUALIZATOR: [UserRole.VIEWER],
        UserRole.OPERATOR: [UserRole.VIEWER],
        UserRole.VIEWER: [],
    }

    @classmethod
    def get_role_info(cls, role: UserRole) -> dict[str, Any]:
        """Получить информацию о роли"""
        return cls.AVAILABLE_ROLES.get(role, {})

    @classmethod
    def get_all_roles(cls) -> list[dict[str, Any]]:
        """Получить список всех доступных ролей"""
        return [{"role": role, **info} for role, info in cls.AVAILABLE_ROLES.items()]

    @classmethod
    def can_assign_role(cls, assigner_role: UserRole, target_role: UserRole) -> bool:
        """Может ли пользователь с ролью assigner_role назначить роль target_role"""
        if assigner_role == UserRole.SUPER_ADMIN:
            return True

        # Проверяем иерархию
        return target_role in cls.ROLE_HIERARCHY.get(assigner_role, [])

    @classmethod
    def is_role_allowed_for_user(cls, user: User, target_role: UserRole) -> bool:
        """Может ли пользователь получить указанную роль"""
        if user.is_super_admin:
            return True

        # Инфра-админ не может стать супер-админом
        if target_role == UserRole.SUPER_ADMIN:
            return False

        # Виртуализатор не может стать инфра-админом
        if target_role == UserRole.INFRA_ADMIN and user.role != UserRole.SUPER_ADMIN:
            return False

        return True
