from backend.rbac.roles_and_users import User, UserRole, RoleBasedAccessControl


def example_usage():
    # Создаем пользователей с разными ролями
    super_admin = User(
        username="admin",
        email="admin@company.com",
        full_name="Главный Администратор",
        role=UserRole.SUPER_ADMIN
    )

    infra_admin = User(
        username="infra_admin",
        email="infra@company.com",
        full_name="Администратор Инфраструктуры",
        role=UserRole.INFRA_ADMIN
    )

    virtualizator = User(
        username="dev_user",
        email="dev@company.com",
        full_name="Разработчик",
        role=UserRole.VIRTUALIZATOR
    )

    operator = User(
        username="operator",
        email="operator@company.com",
        full_name="Оператор",
        role=UserRole.OPERATOR
    )

    viewer = User(
        username="viewer",
        email="viewer@company.com",
        full_name="Наблюдатель",
        role=UserRole.VIEWER
    )

    # Пример проверки прав
    print("=== Проверка прав ===")

    # Проверка может ли виртуализатор создать ВМ
    print(f"Виртуализатор может создать ВМ: "
          f"{virtualizator.can_manage_vm()}")

    # Проверка может ли оператор перезагрузить ВМ
    print(f"Оператор может перезагрузить ВМ: "
          f"{operator.has_permission('virtual_machine', 'start')}")

    # Проверка может ли инфра-админ управлять сетями
    print(f"Инфра-админ может управлять сетями: "
          f"{infra_admin.can_manage_networks()}")

    # Проверка может ли супер-админ управлять пользователями
    print(f"Супер-админ может управлять пользователями: "
          f"{super_admin.can_manage_users()}")

    print("\n=== Ролевая иерархия ===")

    # Получение информации о ролях
    roles_info = RoleBasedAccessControl.get_all_roles()
    for role_info in roles_info:
        print(f"{role_info['name']}: {role_info['description']}")

    # Проверка возможности назначения ролей
    print(f"\nСупер-админ может назначить инфра-админа: "
          f"{RoleBasedAccessControl.can_assign_role(UserRole.SUPER_ADMIN, UserRole.INFRA_ADMIN)}")

    print(f"Инфра-админ может назначить супер-админа: "
          f"{RoleBasedAccessControl.can_assign_role(UserRole.INFRA_ADMIN, UserRole.SUPER_ADMIN)}")

    print(f"Виртуализатор может назначить оператора: "
          f"{RoleBasedAccessControl.can_assign_role(UserRole.VIRTUALIZATOR, UserRole.OPERATOR)}")


if __name__ == "__main__":
    example_usage()