from enum import Enum, StrEnum
from typing import Annotated, Any
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID, uuid4
from datetime import datetime


class ResourceType(StrEnum):
    """Типы ресурсов в системе"""

    VM = "virtual_machine"
    DISK = "disk"
    NETWORK = "network"
    STORAGE = "storage"
    RESOURCE_POOL = "resource_pool"
    SNAPSHOT = "snapshot"
    HOST = "host"
    SYSTEM = "system"
    USER = "user"
    TASK = "task"


class ActionType(StrEnum):
    """Типы действий"""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    MANAGE = "manage"
    ASSIGN = "assign"


class PermissionScope(StrEnum):
    """Область видимости разрешений"""

    GLOBAL = "global"  # Все объекты в системе
    OWNED = "owned"  # Только свои объекты
    GROUP = "group"  # Объекты своей группы
    ASSIGNED = "assigned"  # Явно назначенные объекты
    AVAILABLE = "available"  # Доступные по политике


class VMStateAction(StrEnum):
    """Специфичные действия для ВМ"""

    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    REBOOT = "reboot"
    FORCE_STOP = "force_stop"
    CONSOLE = "console"
    CLONE = "clone"
    MIGRATE = "migrate"
    LIVE_MIGRATE = "live_migrate"
    ATTACH_DISK = "attach_disk"
    DETACH_DISK = "detach_disk"
    CREATE_SNAPSHOT = "create_snapshot"
    RESTORE_SNAPSHOT = "restore_snapshot"


class DiskAction(StrEnum):
    """Специфичные действия для дисков"""

    EXTEND = "extend"
    CONVERT = "convert"
    ATTACH = "attach"
    DETACH = "detach"
    CLONE = "clone"


class NetworkAction(StrEnum):
    """Специфичные действия для сетей"""

    CONFIGURE_DHCP = "configure_dhcp"
    BACKUP = "backup"
    RESTORE = "restore"
    FORCE_DELETE = "force_delete"
    ATTACH_VM = "attach_vm"
    DETACH_VM = "detach_vm"


class ResourcePoolAction(StrEnum):
    """Специфичные действия для ресурсных пулов"""

    ADD_VM = "add_vm"
    REMOVE_VM = "remove_vm"
    ADD_RESOURCE = "add_resource"
    REMOVE_RESOURCE = "remove_resource"
    SET_RESERVATION = "set_reservation"
    SYNC = "sync"
    MIGRATE_POOL = "migrate_pool"


class SystemAction(StrEnum):
    """Системные действия"""

    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    MANAGE_HOSTS = "manage_hosts"
    VIEW_LOGS = "view_logs"
    VIEW_STATS = "view_stats"
    MANAGE_HA = "manage_ha"
    MANAGE_TASKS = "manage_tasks"


class Permission(BaseModel):
    """Базовая модель разрешения"""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    resource_type: ResourceType
    action: (
        ActionType
        | VMStateAction
        | DiskAction
        | NetworkAction
        | ResourcePoolAction
        | SystemAction
    )
    scope: PermissionScope = PermissionScope.GLOBAL
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def check_scope(self, user_id: UUID, resource_owner_id: UUID | None = None) -> bool:
        """Проверяет, соответствует ли разрешение области видимости"""
        if self.scope == PermissionScope.GLOBAL:
            return True
        elif self.scope == PermissionScope.OWNED:
            return resource_owner_id == user_id
        # Для GROUP и ASSIGNED нужна дополнительная логика проверки членства
        return True


# Определения базовых разрешений для каждого типа ресурсов
class PermissionSet:
    """Наборы предопределенных разрешений"""

    # VM разрешения
    VM_VIEW_ALL = Permission(
        resource_type=ResourceType.VM,
        action=ActionType.READ,
        scope=PermissionScope.GLOBAL,
        description="Просмотр всех ВМ",
    )

    VM_CREATE_OWNED = Permission(
        resource_type=ResourceType.VM,
        action=ActionType.CREATE,
        scope=PermissionScope.OWNED,
        description="Создание своей ВМ",
    )

    VM_DELETE_OWNED = Permission(
        resource_type=ResourceType.VM,
        action=ActionType.DELETE,
        scope=PermissionScope.OWNED,
        description="Удаление своей ВМ",
    )

    VM_FORCE_DELETE = Permission(
        resource_type=ResourceType.VM,
        action=ActionType.DELETE,
        scope=PermissionScope.GLOBAL,
        description="Принудительное удаление любой ВМ",
    )

    VM_UPDATE_OWNED = Permission(
        resource_type=ResourceType.VM,
        action=ActionType.UPDATE,
        scope=PermissionScope.OWNED,
        description="Редактирование своей ВМ",
    )

    VM_START_STOP = Permission(
        resource_type=ResourceType.VM,
        action=VMStateAction.START,
        scope=PermissionScope.GLOBAL,
        description="Запуск/остановка ВМ",
    )

    VM_CONSOLE_OWNED = Permission(
        resource_type=ResourceType.VM,
        action=VMStateAction.CONSOLE,
        scope=PermissionScope.OWNED,
        description="Доступ к консоли своей ВМ",
    )

    VM_CONSOLE_GLOBAL = Permission(
        resource_type=ResourceType.VM,
        action=VMStateAction.CONSOLE,
        scope=PermissionScope.GLOBAL,
        description="Доступ к консоли любой ВМ",
    )

    VM_CLONE_OWNED = Permission(
        resource_type=ResourceType.VM,
        action=VMStateAction.CLONE,
        scope=PermissionScope.OWNED,
        description="Клонирование своей ВМ",
    )

    VM_MIGRATE_OWNED = Permission(
        resource_type=ResourceType.VM,
        action=VMStateAction.MIGRATE,
        scope=PermissionScope.OWNED,
        description="Миграция своей ВМ",
    )

    # Диски
    DISK_CREATE = Permission(
        resource_type=ResourceType.DISK,
        action=ActionType.CREATE,
        scope=PermissionScope.OWNED,
        description="Создание диска",
    )

    DISK_DELETE_OWNED = Permission(
        resource_type=ResourceType.DISK,
        action=ActionType.DELETE,
        scope=PermissionScope.OWNED,
        description="Удаление своего диска",
    )

    DISK_DELETE_GLOBAL = Permission(
        resource_type=ResourceType.DISK,
        action=ActionType.DELETE,
        scope=PermissionScope.GLOBAL,
        description="Удаление любого диска",
    )

    DISK_EXTEND_OWNED = Permission(
        resource_type=ResourceType.DISK,
        action=DiskAction.EXTEND,
        scope=PermissionScope.OWNED,
        description="Расширение своего диска",
    )

    DISK_ATTACH_OWNED = Permission(
        resource_type=ResourceType.DISK,
        action=DiskAction.ATTACH,
        scope=PermissionScope.OWNED,
        description="Подключение своего диска к своей ВМ",
    )

    # Сети
    NETWORK_MANAGE = Permission(
        resource_type=ResourceType.NETWORK,
        action=ActionType.MANAGE,
        scope=PermissionScope.GLOBAL,
        description="Полное управление сетями",
    )

    NETWORK_VIEW = Permission(
        resource_type=ResourceType.NETWORK,
        action=ActionType.READ,
        scope=PermissionScope.GLOBAL,
        description="Просмотр сетей",
    )

    NETWORK_ATTACH_VM = Permission(
        resource_type=ResourceType.NETWORK,
        action=NetworkAction.ATTACH_VM,
        scope=PermissionScope.ASSIGNED,
        description="Подключение ВМ к доступным сетям",
    )

    # Ресурсные пулы
    POOL_MANAGE = Permission(
        resource_type=ResourceType.RESOURCE_POOL,
        action=ActionType.MANAGE,
        scope=PermissionScope.GLOBAL,
        description="Полное управление пулами",
    )

    POOL_VIEW = Permission(
        resource_type=ResourceType.RESOURCE_POOL,
        action=ActionType.READ,
        scope=PermissionScope.GLOBAL,
        description="Просмотр пулов",
    )

    POOL_ADD_VM = Permission(
        resource_type=ResourceType.RESOURCE_POOL,
        action=ResourcePoolAction.ADD_VM,
        scope=PermissionScope.ASSIGNED,
        description="Добавление ВМ в доступные пулы",
    )

    # Системные
    SYSTEM_MANAGE_USERS = Permission(
        resource_type=ResourceType.SYSTEM,
        action=SystemAction.MANAGE_USERS,
        scope=PermissionScope.GLOBAL,
        description="Управление пользователями",
    )

    SYSTEM_MANAGE_HOSTS = Permission(
        resource_type=ResourceType.SYSTEM,
        action=SystemAction.MANAGE_HOSTS,
        scope=PermissionScope.GLOBAL,
        description="Управление хостами",
    )

    SYSTEM_VIEW_LOGS = Permission(
        resource_type=ResourceType.SYSTEM,
        action=SystemAction.VIEW_LOGS,
        scope=PermissionScope.GLOBAL,
        description="Просмотр системных логов",
    )

    SYSTEM_VIEW_STATS = Permission(
        resource_type=ResourceType.SYSTEM,
        action=SystemAction.VIEW_STATS,
        scope=PermissionScope.GLOBAL,
        description="Просмотр статистики",
    )

    SYSTEM_MANAGE_HA = Permission(
        resource_type=ResourceType.SYSTEM,
        action=SystemAction.MANAGE_HA,
        scope=PermissionScope.GLOBAL,
        description="Управление HA режимом",
    )


# Наборы разрешений для ролей
class RolePermissions:
    """Предопределенные наборы разрешений для ролей"""

    SUPER_ADMIN = {
        # VM
        PermissionSet.VM_VIEW_ALL,
        PermissionSet.VM_CREATE_OWNED,
        PermissionSet.VM_DELETE_OWNED,
        PermissionSet.VM_FORCE_DELETE,
        PermissionSet.VM_UPDATE_OWNED,
        PermissionSet.VM_START_STOP,
        PermissionSet.VM_CONSOLE_GLOBAL,
        PermissionSet.VM_CLONE_OWNED,
        PermissionSet.VM_MIGRATE_OWNED,
        # Disks
        PermissionSet.DISK_CREATE,
        PermissionSet.DISK_DELETE_GLOBAL,
        PermissionSet.DISK_EXTEND_OWNED,
        PermissionSet.DISK_ATTACH_OWNED,
        # Networks
        PermissionSet.NETWORK_MANAGE,
        PermissionSet.NETWORK_VIEW,
        PermissionSet.NETWORK_ATTACH_VM,
        # Resource Pools
        PermissionSet.POOL_MANAGE,
        PermissionSet.POOL_VIEW,
        PermissionSet.POOL_ADD_VM,
        # System
        PermissionSet.SYSTEM_MANAGE_USERS,
        PermissionSet.SYSTEM_MANAGE_HOSTS,
        PermissionSet.SYSTEM_VIEW_LOGS,
        PermissionSet.SYSTEM_VIEW_STATS,
        PermissionSet.SYSTEM_MANAGE_HA,
    }

    INFRA_ADMIN = {
        # VM - только просмотр и принудительные действия
        PermissionSet.VM_VIEW_ALL,
        PermissionSet.VM_FORCE_DELETE,
        # Disks - управление всеми
        PermissionSet.DISK_CREATE._replace(scope=PermissionScope.GLOBAL),
        PermissionSet.DISK_DELETE_GLOBAL,
        PermissionSet.DISK_EXTEND_OWNED._replace(scope=PermissionScope.GLOBAL),
        # Networks - полное управление
        PermissionSet.NETWORK_MANAGE,
        PermissionSet.NETWORK_VIEW,
        # Resource Pools - полное управление
        PermissionSet.POOL_MANAGE,
        PermissionSet.POOL_VIEW,
        # System - управление хостами
        PermissionSet.SYSTEM_MANAGE_HOSTS,
        PermissionSet.SYSTEM_VIEW_LOGS,
        PermissionSet.SYSTEM_VIEW_STATS,
    }

    VIRTUALIZATOR = {
        # VM - только свои
        PermissionSet.VM_VIEW_ALL,
        PermissionSet.VM_CREATE_OWNED,
        PermissionSet.VM_DELETE_OWNED,
        PermissionSet.VM_UPDATE_OWNED,
        PermissionSet.VM_START_STOP._replace(scope=PermissionScope.OWNED),
        PermissionSet.VM_CONSOLE_OWNED,
        PermissionSet.VM_CLONE_OWNED,
        PermissionSet.VM_MIGRATE_OWNED,
        # Disks - только свои
        PermissionSet.DISK_CREATE,
        PermissionSet.DISK_DELETE_OWNED,
        PermissionSet.DISK_EXTEND_OWNED,
        PermissionSet.DISK_ATTACH_OWNED,
        # Networks - просмотр и использование доступных
        PermissionSet.NETWORK_VIEW,
        PermissionSet.NETWORK_ATTACH_VM,
        # Resource Pools - просмотр и использование доступных
        PermissionSet.POOL_VIEW,
        PermissionSet.POOL_ADD_VM,
        # System - просмотр статистики
        PermissionSet.SYSTEM_VIEW_STATS,
    }

    OPERATOR = {
        # VM - просмотр всех + управление состоянием
        PermissionSet.VM_VIEW_ALL,
        PermissionSet.VM_START_STOP._replace(scope=PermissionScope.GLOBAL),
        PermissionSet.VM_CONSOLE_GLOBAL,
        # Disks - только просмотр
        Permission(
            resource_type=ResourceType.DISK,
            action=ActionType.READ,
            scope=PermissionScope.GLOBAL,
            description="Просмотр дисков",
        ),
        # Networks - просмотр
        PermissionSet.NETWORK_VIEW,
        # Resource Pools - просмотр
        PermissionSet.POOL_VIEW,
        # System - просмотр статистики и логов
        PermissionSet.SYSTEM_VIEW_LOGS,
        PermissionSet.SYSTEM_VIEW_STATS,
    }

    VIEWER = {
        # Все только для чтения
        Permission(
            resource_type=ResourceType.VM,
            action=ActionType.READ,
            scope=PermissionScope.GLOBAL,
            description="Просмотр ВМ",
        ),
        Permission(
            resource_type=ResourceType.DISK,
            action=ActionType.READ,
            scope=PermissionScope.GLOBAL,
            description="Просмотр дисков",
        ),
        Permission(
            resource_type=ResourceType.NETWORK,
            action=ActionType.READ,
            scope=PermissionScope.GLOBAL,
            description="Просмотр сетей",
        ),
        Permission(
            resource_type=ResourceType.RESOURCE_POOL,
            action=ActionType.READ,
            scope=PermissionScope.GLOBAL,
            description="Просмотр пулов",
        ),
        PermissionSet.SYSTEM_VIEW_STATS,
    }
