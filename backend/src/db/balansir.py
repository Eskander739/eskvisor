from sqlalchemy import select, update, delete, and_, or_, func
from datetime import datetime

from src.db.models.balansir import ResourcePoolModel
from src.services.pool.db_pool import DBPool


class ResourcePoolsDB:
    def __init__(self, db_pool: DBPool):
        self.db_pool = db_pool

    async def create_resource_pool(self, data: dict):
        async with self.db_pool.get_connection() as session:
            resource_pool = ResourcePoolModel(**data)
            session.add(resource_pool)
            await session.commit()
            return resource_pool.id

    async def get_resource_pool(self, pool_id: int):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ResourcePoolModel).where(ResourcePoolModel.id == pool_id)
            )
            return result.scalar_one_or_none()

    async def get_resource_pool_by_name(self, name: str):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ResourcePoolModel).where(ResourcePoolModel.name == name)
            )
            return result.scalar_one_or_none()

    async def get_resource_pools_list(
        self,
        cluster_id: int | None = None,
        node_id: int | None = None,
        name: str | None = None,
        enabled: bool | None = True,
        limit: int = 100,
        offset: int = 0,
    ):
        async with self.db_pool.get_connection() as session:
            query = select(ResourcePoolModel)

            conditions = []
            if cluster_id is not None:
                conditions.append(ResourcePoolModel.cluster_id == cluster_id)
            if node_id is not None:
                conditions.append(ResourcePoolModel.node_id == node_id)
            if name is not None:
                conditions.append(ResourcePoolModel.name.ilike(f"%{name}%"))
            if enabled is not None:
                conditions.append(ResourcePoolModel.enabled == enabled)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            return result.scalars().all()

    async def update_resource_pool(self, pool_id: int, data: dict):
        async with self.db_pool.get_connection() as session:
            data["updated_at"] = datetime.now()
            await session.execute(
                update(ResourcePoolModel)
                .where(ResourcePoolModel.id == pool_id)
                .values(**data)
            )
            await session.commit()

    async def delete_resource_pool(self, pool_id: int):
        async with self.db_pool.get_connection() as session:
            stmt = delete(ResourcePoolModel).where(ResourcePoolModel.id == pool_id)
            await session.execute(stmt)
            await session.commit()

    async def disable_resource_pool(self, pool_id: int):
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(ResourcePoolModel)
                .where(ResourcePoolModel.id == pool_id)
                .values(enabled=False, updated_at=datetime.now())
            )
            await session.commit()

    async def get_resource_pool_stats(
        self, cluster_id: int = None, node_id: int = None
    ):
        async with self.db_pool.get_connection() as session:
            query = select(
                func.count(ResourcePoolModel.id),
                func.sum(ResourcePoolModel.cpu_core_available),
                func.sum(ResourcePoolModel.ram_available),
                func.sum(ResourcePoolModel.storage_available),
            ).where(ResourcePoolModel.enabled == True)

            if cluster_id:
                query = query.where(ResourcePoolModel.cluster_id == cluster_id)
            if node_id:
                query = query.where(ResourcePoolModel.node_id == node_id)

            result = await session.execute(query)
            return result.first()
