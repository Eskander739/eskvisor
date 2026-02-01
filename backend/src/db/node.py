import os
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import select, update, delete
from datetime import datetime

Base = declarative_base()


class NodeModel(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    hostname = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=False)
    hypervisor_type = Column(String(50), nullable=False)  # KVM, ESXi, Hyper-V
    port = Column(Integer, default=22)
    username = Column(String(100))
    password_encrypted = Column(String(255))  # Или ссылка на vault
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=True)

    # Ресурсы
    cpu_cores = Column(Integer, default=0)
    cpu_model = Column(String(255))
    total_memory_gb = Column(Integer, default=0)
    free_memory_gb = Column(Integer, default=0)
    total_storage_gb = Column(Integer, default=0)
    free_storage_gb = Column(Integer, default=0)

    # Статусы
    status = Column(String(20), default="offline")  # online, offline, maintenance
    last_seen = Column(DateTime)
    enabled = Column(Boolean, default=True)

    # Метаданные
    version = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    cluster = relationship("ClusterModel", back_populates="nodes")


class NodesDB:
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

    async def add_node(self, data: dict):
        async with self.async_session() as session:
            node = NodeModel(**data)
            session.add(node)
            await session.commit()
            return node.id

    async def get_node(self, node_id: int):
        async with self.async_session() as session:
            result = await session.execute(
                select(NodeModel).where(NodeModel.id == node_id)
            )
            return result.scalar_one_or_none()

    async def get_all_nodes(self, cluster_id=None, enabled=True):
        async with self.async_session() as session:
            query = select(NodeModel)
            if cluster_id:
                query = query.where(NodeModel.cluster_id == cluster_id)
            if enabled is not None:
                query = query.where(NodeModel.enabled == enabled)

            result = await session.execute(query)
            return result.scalars().all()

    async def delete_node_by_id(self, node_id: int) -> None:
        """Удаляет node по id."""
        async with await self.async_session() as session:
            stmt = delete(NodeModel).where(NodeModel.id == node_id)
            await session.execute(stmt)
            await session.commit()

    async def update_status(self, node_id: int, status: str, resources: dict = None):
        async with self.async_session() as session:
            update_data = {"status": status, "last_seen": datetime.now()}
            if resources:
                update_data.update(resources)

            await session.execute(
                update(NodeModel).where(NodeModel.id == node_id).values(**update_data)
            )
            await session.commit()
