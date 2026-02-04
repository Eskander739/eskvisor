from sqlalchemy import select, update, delete, and_, or_, func
from datetime import datetime

from src.db.models.virtual_networks import VirtualNetworkModel
from src.services.pool.db_pool import DBPool


class VirtualNetworksDB:
    def __init__(self, db_pool: DBPool):
        self.db_pool = db_pool

    async def create_virtual_network(self, data: dict):
        async with self.db_pool.get_connection() as session:
            network = VirtualNetworkModel(**data)
            session.add(network)
            await session.commit()
            return network.id

    async def get_virtual_network(self, network_id: int):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(VirtualNetworkModel).where(VirtualNetworkModel.id == network_id)
            )
            return result.scalar_one_or_none()

    async def get_virtual_network_by_name(self, name: str):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(VirtualNetworkModel).where(VirtualNetworkModel.name == name)
            )
            return result.scalar_one_or_none()

    async def get_virtual_network_by_uuid(self, uuid: str):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(VirtualNetworkModel).where(VirtualNetworkModel.uuid == uuid)
            )
            return result.scalar_one_or_none()

    async def get_virtual_networks_list(
        self,
        cluster_id: int | None = None,
        node_id: int | None = None,
        name: str | None = None,
        network_type: str | None = None,
        active: bool | None = None,
        persistent: bool | None = None,
        autostart: bool | None = None,
        isolated: bool | None = None,
        bridge_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        async with self.db_pool.get_connection() as session:
            query = select(VirtualNetworkModel)

            conditions = []
            if cluster_id is not None:
                conditions.append(VirtualNetworkModel.cluster_id == cluster_id)
            if node_id is not None:
                conditions.append(VirtualNetworkModel.node_id == node_id)
            if name is not None:
                conditions.append(VirtualNetworkModel.name.ilike(f"%{name}%"))
            if network_type is not None:
                conditions.append(VirtualNetworkModel.network_type == network_type)
            if active is not None:
                conditions.append(VirtualNetworkModel.active == active)
            if persistent is not None:
                conditions.append(VirtualNetworkModel.persistent == persistent)
            if autostart is not None:
                conditions.append(VirtualNetworkModel.autostart == autostart)
            if isolated is not None:
                conditions.append(VirtualNetworkModel.isolated == isolated)
            if bridge_name is not None:
                conditions.append(VirtualNetworkModel.bridge_name == bridge_name)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            return result.scalars().all()

    async def update_virtual_network(self, network_id: int, data: dict):
        async with self.db_pool.get_connection() as session:
            data["updated_at"] = datetime.now()
            await session.execute(
                update(VirtualNetworkModel)
                .where(VirtualNetworkModel.id == network_id)
                .values(**data)
            )
            await session.commit()

    async def activate_virtual_network(self, network_id: int):
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(VirtualNetworkModel)
                .where(VirtualNetworkModel.id == network_id)
                .values(active=True, updated_at=datetime.now())
            )
            await session.commit()

    async def deactivate_virtual_network(self, network_id: int):
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(VirtualNetworkModel)
                .where(VirtualNetworkModel.id == network_id)
                .values(active=False, updated_at=datetime.now())
            )
            await session.commit()

    async def delete_virtual_network(self, network_id: int):
        async with self.db_pool.get_connection() as session:
            stmt = delete(VirtualNetworkModel).where(
                VirtualNetworkModel.id == network_id
            )
            await session.execute(stmt)
            await session.commit()

    async def get_virtual_network_stats(
        self, cluster_id: int = None, node_id: int = None
    ):
        async with self.db_pool.get_connection() as session:
            query = select(
                func.count(VirtualNetworkModel.id),
                func.count().filter(VirtualNetworkModel.active == True),
                func.count().filter(VirtualNetworkModel.isolated == True),
                func.count().filter(VirtualNetworkModel.autostart == True),
            )

            if cluster_id:
                query = query.where(VirtualNetworkModel.cluster_id == cluster_id)
            if node_id:
                query = query.where(VirtualNetworkModel.node_id == node_id)

            result = await session.execute(query)
            return result.first()

    async def get_networks_by_state(self, active: bool = True):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(VirtualNetworkModel).where(VirtualNetworkModel.active == active)
            )
            return result.scalars().all()
