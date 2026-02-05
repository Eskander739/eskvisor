from sqlalchemy import select, update, delete
from datetime import datetime

from src.db.models.nodes import NodeModel
from src.models.node import NodeCreateRequest, NodeSyncStateFromAgent
from src.services.pool.db_pool import DBPool


class NodesDB:
    def __init__(self, db_pool: DBPool):
        self.db_pool = db_pool

    async def add_node(self, data: NodeCreateRequest):
        async with self.db_pool.get_connection() as session:
            node = NodeModel(**data.model_dump())
            session.add(node)
            await session.commit()
            return node.id

    async def get_node(self, node_id: int):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(NodeModel).where(NodeModel.id == node_id)
            )
            return result.scalar_one_or_none()

    async def get_node_by_name(self, name: str):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(NodeModel).where(NodeModel.name == name)
            )
            return result.scalar_one_or_none()

    async def get_node_by_ip_address(self, ip_address: str):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(NodeModel).where(NodeModel.ip_address == ip_address)
            )
            return result.scalar_one_or_none()

    async def get_all_nodes(self, cluster_id=None, enabled=True):
        async with self.db_pool.get_connection() as session:
            query = select(NodeModel)
            if cluster_id:
                query = query.where(NodeModel.cluster_id == cluster_id)
            if enabled is not None:
                query = query.where(NodeModel.enabled == enabled)

            result = await session.execute(query)
            return result.scalars().all()

    async def delete_node_by_id(self, node_id: int) -> None:
        """Удаляет node по id."""
        async with self.db_pool.get_connection() as session:
            stmt = delete(NodeModel).where(NodeModel.id == node_id)
            await session.execute(stmt)
            await session.commit()

    async def update_status(self, node_id: int, status: str, resources: dict = None):
        async with self.db_pool.get_connection() as session:
            update_data = {"status": status, "last_seen": datetime.now()}
            if resources:
                update_data.update(resources)

            await session.execute(
                update(NodeModel).where(NodeModel.id == node_id).values(**update_data)
            )
            await session.commit()

    async def update_node(self, update_data: NodeSyncStateFromAgent):
        async with self.db_pool.get_connection() as session:

            await session.execute(
                update(NodeModel)
                .where(NodeModel.ip_address == update_data.ip_address)
                .values(**update_data.model_dump())
            )
            await session.commit()
