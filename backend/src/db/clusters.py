import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, update, delete
from sqlalchemy import func, select
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

from src.db.node import NodeModel

Base = declarative_base()


class ClusterModel(Base):
    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text)

    # Основные настройки
    cluster_type = Column(
        String(50), default="standalone"
    )  # standalone, ha, load_balanced
    high_availability = Column(Boolean, default=False)
    load_balancing = Column(Boolean, default=False)

    # Сетевые настройки
    virtual_ip = Column(String(45))
    network_cidr = Column(String(50))

    # Ресурсы кластера (вычисляемые/агрегированные)
    total_hosts = Column(Integer, default=0)
    total_cpu_cores = Column(Integer, default=0)
    total_memory_gb = Column(Integer, default=0)
    total_storage_gb = Column(Integer, default=0)

    # Статусы
    status = Column(String(20), default="active")  # active, maintenance, degraded
    enabled = Column(Boolean, default=True)

    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    nodes = relationship("NodeModel", back_populates="cluster")


class ClustersDB:
    def __init__(self):
        self.user = os.environ.get("DB_USER")
        self.password = os.environ.get("DB_PASS")
        self.db_host = os.environ.get("DB_HOST")
        self.db_port = os.environ.get("DB_PORT")

        # Используем асинхронный драйвер asyncpg
        self.engine = create_async_engine(
            f"postgresql+asyncpg://{self.user}:{self.password}@{self.db_host}:{self.db_port}/postgres",
            echo=True,
        )
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def create_cluster(self, data: dict):
        async with self.async_session() as session:
            cluster = ClusterModel(**data)
            session.add(cluster)
            await session.commit()
            return cluster.id

    async def get_cluster(self, cluster_id: int):
        async with self.async_session() as session:
            result = await session.execute(
                select(ClusterModel).where(ClusterModel.id == cluster_id)
            )
            return result.scalar_one_or_none()

    async def get_cluster_list(self):
        async with self.async_session() as session:
            result = await session.execute(select(ClusterModel).where())
            return result.scalar_one_or_none()

    async def delete_cluster_by_id(self, cluster_id: int) -> None:
        """Удаляет cluster по id."""
        async with await self.async_session() as session:
            stmt = delete(ClusterModel).where(ClusterModel.id == cluster_id)
            await session.execute(stmt)
            await session.commit()

    async def update_cluster_stats(self, cluster_id: int):
        """Обновляет агрегированные статистики кластера"""
        async with self.async_session() as session:

            # Получаем суммарные ресурсы всех хостов кластера
            result = await session.execute(
                select(
                    func.count(NodeModel.id),
                    func.sum(NodeModel.cpu_cores),
                    func.sum(NodeModel.total_memory_gb),
                    func.sum(NodeModel.total_storage_gb),
                ).where(NodeModel.cluster_id == cluster_id, NodeModel.enabled == True)
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
                        updated_at=datetime.utcnow(),
                    )
                )
                await session.commit()
