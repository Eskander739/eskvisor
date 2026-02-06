from sqlalchemy import select, update, delete, and_, or_
from datetime import datetime

from src.db.models.network_adapters import NetAdapterModel
from src.models.network import (
    NetworkAdapterCreate,
    NetworkAdapterFilter,
    NetworkAdapterUpdate,
)
from src.services.pool.db_pool import DBPool


class NetworkAdaptersDB:
    def __init__(self, db_pool: DBPool):
        self.db_pool = db_pool

    async def create_adapter(self, data: NetworkAdapterCreate) -> int:
        """Создание нового сетевого адаптера"""
        async with self.db_pool.get_connection() as session:
            adapter_data = data.model_dump()
            adapter_data["created"] = datetime.now()

            adapter = NetAdapterModel(**adapter_data)
            session.add(adapter)
            await session.commit()
            return adapter.id

    async def get_adapter_by_id(self, adapter_id: int) -> NetAdapterModel | None:
        """Получение сетевого адаптера по ID"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(NetAdapterModel).where(NetAdapterModel.id == adapter_id)
            )
            return result.scalar_one_or_none()

    async def get_adapter_by_source(self, source: str) -> NetAdapterModel | None:
        """Получение сетевого адаптера по source"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(NetAdapterModel).where(NetAdapterModel.source == source)
            )
            return result.scalar_one_or_none()

    async def get_adapters_list(
        self, filters: NetworkAdapterFilter
    ) -> list[NetAdapterModel]:
        """Получение списка сетевых адаптеров с фильтрацией"""
        async with self.db_pool.get_connection() as session:
            query = select(NetAdapterModel)

            conditions = []

            if filters.network_type is not None:
                conditions.append(NetAdapterModel.network_type == filters.network_type)
            if filters.model is not None:
                conditions.append(NetAdapterModel.model == filters.model)
            if filters.mac_address is not None:
                conditions.append(NetAdapterModel.mac_address == filters.mac_address)
            if filters.source is not None:
                conditions.append(NetAdapterModel.source == filters.source)
            if filters.vm_id is not None:
                conditions.append(NetAdapterModel.vm_id == filters.vm_id)
            if filters.created_from is not None:
                conditions.append(NetAdapterModel.created >= filters.created_from)
            if filters.created_to is not None:
                conditions.append(NetAdapterModel.created <= filters.created_to)
            if filters.search_mac is not None:
                conditions.append(
                    NetAdapterModel.mac_address.ilike(f"%{filters.search_mac}%")
                )

            # Добавляем условие для отображения только неудаленных адаптеров
            conditions.append(NetAdapterModel.deleted.is_(None))

            if conditions:
                query = query.where(and_(*conditions))

            query = query.limit(filters.limit).offset(filters.offset)

            result = await session.execute(query)
            return result.scalars().all()

    async def update_adapter(self, adapter_id: int, data: NetworkAdapterUpdate) -> None:
        """Обновление сетевого адаптера"""
        async with self.db_pool.get_connection() as session:
            update_data = data.model_dump(exclude_unset=True)
            update_data["updated"] = datetime.now()

            if update_data:
                await session.execute(
                    update(NetAdapterModel)
                    .where(NetAdapterModel.id == adapter_id)
                    .values(**update_data)
                )
                await session.commit()

    async def delete_adapter(self, adapter_id: int) -> None:
        """Мягкое удаление сетевого адаптера"""
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(NetAdapterModel)
                .where(NetAdapterModel.id == adapter_id)
                .values(deleted=datetime.now())
            )
            await session.commit()

    async def hard_delete_adapter(self, adapter_id: int) -> None:
        """Полное удаление сетевого адаптера из БД"""
        async with self.db_pool.get_connection() as session:
            stmt = delete(NetAdapterModel).where(NetAdapterModel.id == adapter_id)
            await session.execute(stmt)
            await session.commit()

    async def attach_adapter_to_vm(self, adapter_id: int, vm_id: int) -> None:
        """Прикрепление адаптера к виртуальной машине"""
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(NetAdapterModel)
                .where(NetAdapterModel.id == adapter_id)
                .values(vm_id=vm_id, updated=datetime.now())
            )
            await session.commit()

    async def detach_adapter_from_vm(self, adapter_id: int) -> None:
        """Отсоединение адаптера от виртуальной машины"""
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(NetAdapterModel)
                .where(NetAdapterModel.id == adapter_id)
                .values(vm_id=None, updated=datetime.now())
            )
            await session.commit()

    async def get_adapters_by_vm_id(self, vm_id: int) -> list[NetAdapterModel]:
        """Получение всех адаптеров, прикрепленных к виртуальной машине"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(NetAdapterModel).where(
                    NetAdapterModel.vm_id == vm_id, NetAdapterModel.deleted.is_(None)
                )
            )
            return result.scalars().all()

    async def get_orphaned_adapters(self) -> list[NetAdapterModel]:
        """Получение адаптеров, не прикрепленных к виртуальным машинам"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(NetAdapterModel).where(
                    NetAdapterModel.vm_id.is_(None), NetAdapterModel.deleted.is_(None)
                )
            )
            return result.scalars().all()

    async def check_mac_exists(
        self, mac_address: str, exclude_id: int | None = None
    ) -> bool:
        """Проверка существования MAC-адреса в базе"""
        async with self.db_pool.get_connection() as session:
            query = select(NetAdapterModel).where(
                NetAdapterModel.mac_address == mac_address
            )

            if exclude_id is not None:
                query = query.where(NetAdapterModel.id != exclude_id)

            result = await session.execute(query)
            return result.scalar_one_or_none() is not None
