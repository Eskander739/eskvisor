from sqlalchemy import select, update, delete
from sqlalchemy.inspection import inspect
from sqlalchemy import String
from sqlalchemy.sql.elements import or_
from sqlalchemy.sql.functions import count

from src.db.base import Base
from src.db.models.users import UserModel
from src.models.user import UserInDB, UserAddInDb
from src.rbac.roles_and_users import UserRole
from src.services.pool.db_pool import DBPool


class UsersDB:
    def __init__(self, db_pool: DBPool):
        self.db_pool = db_pool

    async def check_connection(self) -> bool:
        """Проверяет соединение с БД"""
        try:
            async with self.db_pool.get_connection() as session:
                result = await session.execute(select(1))
                value = result.scalar()
                return value == 1
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    @staticmethod
    def _model_to_user(model: UserModel) -> UserInDB:
        """Преобразует модель SQLAlchemy в Pydantic модель."""
        return UserInDB(
            id=model.id,
            role=model.role,
            name=model.name,
            description=model.description,
            pass_hash=model.pass_hash,
            email=model.email,
            created=model.created,
            deleted=model.deleted,
            blocked=model.blocked,
            created_by=model.created_by,
        )

    async def add_user(self, user: UserAddInDb) -> None:
        """Добавляет нового пользователя с использованием SQLAlchemy ORM."""
        async with self.db_pool.get_connection() as session:
            user_model = user.model_dump()
            user_model["role"] = (
                user_model["role"].value
                if isinstance(user_model["role"], UserRole)
                else user_model["role"]
            )
            user_model["blocked"] = False
            user_model = UserModel(**user_model)
            session.add(user_model)
            await session.commit()

    async def get_user_by_email(self, email: str) -> UserInDB:
        """Получает пользователя по email."""
        async with self.db_pool.get_connection() as session:
            stmt = select(UserModel).where(UserModel.email == email)
            result = await session.execute(stmt)
            user = result.scalars().first()
            return self._model_to_user(user) if user else None

    async def get_user_by_id(self, user_id: str) -> UserInDB:
        """Получает пользователя по ID."""
        async with self.db_pool.get_connection() as session:
            stmt = select(UserModel).where(UserModel.id == user_id)
            result = await session.execute(stmt)
            user = result.scalars().first()
            return self._model_to_user(user) if user else None

    async def get_users(
        self,
        limit: int = 10,
        page: int = 1,
        role: UserRole = None,
        blocked: str = None,
        search: str = None,
    ) -> tuple[list[UserInDB], int, int]:
        """Получает список пользователей с пагинацией."""
        async with self.db_pool.get_connection() as session:
            offset = (page - 1) * limit

            # 1. Поиск по всем строковым полям
            conditions = []
            if search:
                inspector = inspect(UserModel)
                columns = inspector.mapper.columns
                for column in columns:
                    if isinstance(column.type, String):
                        conditions.append(column.contains(search))
            search_filter = or_(*conditions) if conditions else True

            # 2. Фильтр по активности
            blocked_filter = True  # по умолчанию (без фильтра)
            if blocked and blocked != "all":
                blocked_filter = UserModel.blocked == (blocked == "banned")

            # 3. Фильтр по роли
            role_filter = True if role is None else UserModel.role == role.value

            # Сборка запроса
            stmt = (
                select(UserModel)
                .filter(
                    search_filter,
                    role_filter,
                    blocked_filter,
                )
                .limit(limit)
                .offset(offset)
            )

            result = await session.execute(stmt)
            users = result.scalars().all()
            users_list = [self._model_to_user(user) for user in users]
            return users_list, limit, page

    async def get_total_users(self) -> int:
        """Получает общее количество пользователей."""
        async with self.db_pool.get_connection() as session:
            stmt = select(count(UserModel.id))
            result = await session.execute(stmt)
            return result.scalar()

    async def activate_user_by_email(self, email: str) -> None:
        """Активирует пользователя по email."""
        async with self.db_pool.get_connection() as session:
            stmt = (
                update(UserModel)
                .where(UserModel.email == email)
                .values(is_active=True, verification_token=None)
            )
            await session.execute(stmt)
            await session.commit()

    async def block_user_by_id(self, user_id: str) -> None:
        """Блокирует пользователя по id."""
        async with self.db_pool.get_connection() as session:
            stmt = update(UserModel).where(UserModel.id == user_id).values(blocked=True)
            await session.execute(stmt)
            await session.commit()

    async def verify_user_by_id(self, user_id: str) -> None:
        """Верифицирует пользователя по id."""
        async with self.db_pool.get_connection() as session:
            stmt = (
                update(UserModel).where(UserModel.id == user_id).values(verified=True)
            )
            await session.execute(stmt)
            await session.commit()

    async def unverify_user_by_id(self, user_id: str) -> None:
        """Отменяет верификацию пользователя по id."""
        async with self.db_pool.get_connection() as session:
            stmt = (
                update(UserModel).where(UserModel.id == user_id).values(verified=False)
            )
            await session.execute(stmt)
            await session.commit()

    async def unblock_user_by_id(self, user_id: str) -> None:
        """Разблокирует пользователя по id."""
        async with self.db_pool.get_connection() as session:
            stmt = (
                update(UserModel).where(UserModel.id == user_id).values(blocked=False)
            )
            await session.execute(stmt)
            await session.commit()

    async def delete_user_by_email(self, email: str) -> None:
        """Удаляет пользователя по email."""
        async with self.db_pool.get_connection() as session:
            stmt = delete(UserModel).where(UserModel.email == email)
            await session.execute(stmt)
            await session.commit()

    async def update_user_email(self, old_email: str, new_email: str) -> None:
        """Обновляет email пользователя."""
        async with self.db_pool.get_connection() as session:
            stmt = (
                update(UserModel)
                .where(UserModel.email == old_email)
                .values(email=new_email)
            )
            await session.execute(stmt)
            await session.commit()

    async def update_name_email(self, old_name: str, new_name: str) -> None:
        """Обновляет имя пользователя."""
        async with self.db_pool.get_connection() as session:
            stmt = (
                update(UserModel)
                .where(UserModel.name == old_name)
                .values(name=new_name)
            )
            await session.execute(stmt)
            await session.commit()

    async def update_password_by_email(self, email: str, new_password: str) -> None:
        """Обновляет пароль пользователя."""
        async with self.db_pool.get_connection() as session:
            stmt = (
                update(UserModel)
                .where(UserModel.email == email)
                .values(pass_hash=new_password)
            )
            await session.execute(stmt)
            await session.commit()

    async def create_tables(self):
        """Создает таблицы в БД (для использования при инициализации)."""
        async with self.db_pool.get_connection() as conn:
            await conn.run_sync(Base.metadata.create_all)


#
# async def main():
#     load_dotenv("/home/eska/eskvisor/backend/.env")
#     users_db = UsersDB()
#     result = await users_db.get_users()
#     print(result)
#     # await users_db.create_tables()
#     # await users_db.add_user(UserAddInDb(
#     #     role=UserRole.SUPER_ADMIN,
#     #     name="Eska",
#     #     pass_hash="$2b$14$x0Wn3HiOl8iPH9SB8t8TqeGfLaTjgmm91DRSnXZkhIhvle4pUWWIm",
#     #     email="egceska@gmail.com",
#     #     created=datetime.datetime.now()
#     # ))
#
#
# if __name__ == "__main__":
#     import asyncio
#
#     asyncio.run(main())
