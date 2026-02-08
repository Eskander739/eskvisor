from sqlalchemy import select, update, delete, and_, func
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import selectinload

from src.db.models.balansir import ResourcePoolModel, ResourceReservationVM
from src.services.pool.db_pool import DBPool


class ResourcePoolsRepository:
    """Репозиторий для работы с ресурсными пулами"""

    def __init__(self, db_pool: DBPool):
        self.db_pool = db_pool

    async def create_resource_pool(self, data: dict) -> int:
        """Создать новый ресурсный пул"""
        async with self.db_pool.get_connection() as session:
            resource_pool = ResourcePoolModel(**data)
            session.add(resource_pool)
            await session.commit()
            return resource_pool.id

    async def get_resource_pool(self, pool_id: int) -> Optional[ResourcePoolModel]:
        """Получить ресурсный пул по ID"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ResourcePoolModel).where(ResourcePoolModel.id == pool_id)
            )
            return result.scalar_one_or_none()

    async def get_resource_pool_with_reservations(
        self, pool_id: int
    ) -> Optional[ResourcePoolModel]:
        """Получить ресурсный пул с резервациями ВМ"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ResourcePoolModel)
                .where(ResourcePoolModel.id == pool_id)
                .options(selectinload(ResourcePoolModel.vm_reservations))
            )
            return result.unique().scalar_one_or_none()

    async def get_resource_pool_by_name(self, name: str) -> Optional[ResourcePoolModel]:
        """Получить ресурсный пул по имени"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ResourcePoolModel).where(ResourcePoolModel.name == name)
            )
            return result.scalar_one_or_none()

    async def get_resource_pools_list(
        self,
        cluster_id: Optional[int] = None,
        node_id: Optional[int] = None,
        name: Optional[str] = None,
        enabled: Optional[bool] = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ResourcePoolModel]:
        """Получить список ресурсных пулов с фильтрацией"""
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

    async def update_resource_pool(self, pool_id: int, data: dict) -> None:
        """Обновить ресурсный пул"""
        async with self.db_pool.get_connection() as session:
            data["updated_at"] = datetime.now()
            await session.execute(
                update(ResourcePoolModel)
                .where(ResourcePoolModel.id == pool_id)
                .values(**data)
            )
            await session.commit()

    async def delete_resource_pool(self, pool_id: int) -> None:
        """Удалить ресурсный пул"""
        async with self.db_pool.get_connection() as session:
            stmt = delete(ResourcePoolModel).where(ResourcePoolModel.id == pool_id)
            await session.execute(stmt)
            await session.commit()

    async def get_resource_pool_stats(
        self, cluster_id: Optional[int] = None, node_id: Optional[int] = None
    ) -> tuple:
        """Получить статистику по ресурсным пулам"""
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

    async def add_vm_to_pool(self, pool_id: int, vm_id: int) -> None:
        """Добавить ВМ в ресурсный пул"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ResourcePoolModel).where(ResourcePoolModel.id == pool_id)
            )
            pool = result.scalar_one_or_none()

            if pool:
                if vm_id not in pool.vms:
                    pool.vms.append(vm_id)
                    pool.updated_at = datetime.now()
                    await session.commit()

    async def remove_vm_from_pool(self, pool_id: int, vm_id: int) -> None:
        """Удалить ВМ из ресурсного пула"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ResourcePoolModel).where(ResourcePoolModel.id == pool_id)
            )
            pool = result.scalar_one_or_none()

            if pool and vm_id in pool.vms:
                pool.vms.remove(vm_id)
                pool.updated_at = datetime.now()
                await session.commit()

    # Методы для работы с резервациями ресурсов

    async def create_vm_reservation(
        self,
        pool_id: int,
        vm_id: int,
        vm_name: str,
        cpu_cores: int = 0,
        ram_bytes: int = 0,
        storage_bytes: int = 0,
        vm_pid: Optional[int] = None,
    ) -> int:
        """Создать резервацию ресурсов для ВМ"""
        async with self.db_pool.get_connection() as session:
            reservation = ResourceReservationVM(
                resource_pool_id=pool_id,
                virtual_machine_id=vm_id,
                vm_name=vm_name,
                cpu_core_count=cpu_cores,
                ram_bytes=ram_bytes,
                storage_bytes=storage_bytes,
                vm_pid=vm_pid,
            )
            session.add(reservation)
            await session.commit()
            return reservation.id

    async def update_vm_reservation(
        self,
        reservation_id: int,
        cpu_cores: Optional[int] = None,
        ram_bytes: Optional[int] = None,
        storage_bytes: Optional[int] = None,
        vm_pid: Optional[int] = None,
    ) -> None:
        """Обновить резервацию ресурсов для ВМ"""
        async with self.db_pool.get_connection() as session:
            update_data = {"updated_at": datetime.now()}
            if cpu_cores is not None:
                update_data["cpu_core_count"] = cpu_cores
            if ram_bytes is not None:
                update_data["ram_bytes"] = ram_bytes
            if storage_bytes is not None:
                update_data["storage_bytes"] = storage_bytes
            if vm_pid is not None:
                update_data["vm_pid"] = vm_pid

            await session.execute(
                update(ResourceReservationVM)
                .where(ResourceReservationVM.id == reservation_id)
                .values(**update_data)
            )
            await session.commit()

    async def delete_vm_reservation(self, reservation_id: int) -> None:
        """Удалить резервацию ресурсов для ВМ"""
        async with self.db_pool.get_connection() as session:
            await session.execute(
                delete(ResourceReservationVM).where(
                    ResourceReservationVM.id == reservation_id
                )
            )
            await session.commit()

    async def get_vm_reservation(
        self, vm_id: int, pool_id: int
    ) -> Optional[ResourceReservationVM]:
        """Получить резервацию ресурсов для ВМ"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ResourceReservationVM).where(
                    and_(
                        ResourceReservationVM.virtual_machine_id == vm_id,
                        ResourceReservationVM.resource_pool_id == pool_id,
                    )
                )
            )
            return result.scalar_one_or_none()

    async def get_all_vm_reservations(
        self, pool_id: int
    ) -> List[ResourceReservationVM]:
        """Получить все резервации ресурсов для пула"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(ResourceReservationVM).where(
                    ResourceReservationVM.resource_pool_id == pool_id
                )
            )
            return result.scalars().all()

    async def get_total_reserved_resources(self, pool_id: int) -> dict:
        """Получить общее количество зарезервированных ресурсов в пуле"""
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(
                    func.sum(ResourceReservationVM.cpu_core_count),
                    func.sum(ResourceReservationVM.ram_bytes),
                    func.sum(ResourceReservationVM.storage_bytes),
                ).where(ResourceReservationVM.resource_pool_id == pool_id)
            )
            total_cpu, total_ram, total_storage = result.first() or (0, 0, 0)

            return {
                "cpu_cores": total_cpu or 0,
                "ram_bytes": total_ram or 0,
                "storage_bytes": total_storage or 0,
            }
