from sqlalchemy import update, delete
from sqlalchemy import func, select
from datetime import datetime

from sqlalchemy.orm import joinedload

from src.db.models.clusters import ClusterModel
from src.db.models.nodes import NodeModel
from src.models.cluster import ClusterCreateRequest
from src.services.pool.db_pool import DBPool


class ClustersDB:
    def __init__(self, db_pool: DBPool):
        self.db_pool = db_pool

    async def create_cluster(self, data: ClusterCreateRequest):
        async with self.db_pool.get_connection() as session:
            cluster = ClusterModel(**data.model_dump())
            session.add(cluster)
            await session.commit()
            return cluster.id

    async def get_cluster(self, cluster_id: int):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ClusterModel).where(ClusterModel.id == cluster_id)
            )
            result_list = result.scalar_one_or_none()
            return [] if result_list is None else result_list

    async def get_cluster_by_name(self, name: str):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ClusterModel).where(ClusterModel.name == name)
            )
            result = result.scalar_one_or_none()
            return None if result is None else result

    # async def get_cluster_list(self):
    #     async with self.db_pool.get_connection() as session:
    #         result = await session.execute(select(ClusterModel))
    #         result_list = result.all()
    #         return [] if result_list is None else result_list

    async def get_cluster_list(self):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ClusterModel)
                .options(joinedload(ClusterModel.nodes))
                .order_by(ClusterModel.id)
            )
            # Обязательно используем unique() при joinedload с коллекциями
            clusters = result.scalars().unique().all()
            return [] if not clusters else list(clusters)

    async def delete_cluster_by_id(self, cluster_id: int) -> None:
        """Удаляет cluster по id."""
        async with self.db_pool.get_connection() as session:
            stmt = delete(ClusterModel).where(ClusterModel.id == cluster_id)
            await session.execute(stmt)
            await session.commit()

    async def update_cluster_stats(self, cluster_id: int):
        """Обновляет агрегированные статистики кластера"""
        async with self.db_pool.get_connection() as session:
            # Получаем суммарные ресурсы всех хостов кластера
            result = await session.execute(
                select(
                    func.count(NodeModel.id),
                    func.sum(NodeModel.cpu_cores),
                    func.sum(NodeModel.total_memory_gb),
                    func.sum(NodeModel.total_storage_gb),
                ).where(NodeModel.cluster_id == cluster_id)
            )

            stats = result.first()
            if stats:
                await session.execute(
                    update(ClusterModel)
                    .where(ClusterModel.id == cluster_id)
                    .values(
                        total_hosts=stats[0] or 0,
                        total_cpu_cores=stats[1] or 0,
                        total_memory_gb=stats[2] or 0,
                        total_storage_gb=stats[3] or 0,
                        updated=datetime.now(),
                    )
                )
                await session.commit()
