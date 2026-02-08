from sqlalchemy import select, update, delete, and_, func
from datetime import datetime

from sqlalchemy.orm import joinedload

from src.db.models.disks import DiskModel
from src.models.disk import DiskFormat, DiskStatus, DiskType, DiskUpdate
from src.services.pool.db_pool import DBPool


class DisksDB:
    def __init__(self, db_pool: DBPool):
        self.db_pool = db_pool

    async def create_disk(self, data: dict):
        async with self.db_pool.get_connection() as session:
            disk = DiskModel(**data)
            session.add(disk)
            await session.commit()
            return disk.id

    async def get_disk(self, disk_id: int):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(DiskModel)
                .where(DiskModel.id == disk_id)
                .options(joinedload(DiskModel.virtual_machine))
            )
            return result.scalar_one_or_none()

    async def get_disk_by_name(self, name: str):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(DiskModel)
                .where(DiskModel.name == name)
                .options(joinedload(DiskModel.virtual_machine))
            )
            return result.scalar_one_or_none()

    async def get_disk_by_id(self, disk_id: int):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(DiskModel)
                .where(DiskModel.id == disk_id)
                .options(joinedload(DiskModel.virtual_machine))
            )
            return result.scalar_one_or_none()

    async def get_disks_list(
        self,
        pool: str | None = None,
        resource_pool: str | None = None,
        disk_type: DiskType | None = None,
        disk_format: DiskFormat | None = None,
        status: DiskStatus | None = None,
        search_path: str | None = None,
        min_size_gb: float | None = None,
        max_size_gb: float | None = None,
        attached_only: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ):
        async with self.db_pool.get_connection() as session:
            query = select(DiskModel)

            conditions = []
            if pool is not None:
                conditions.append(DiskModel.pool == pool)
            if resource_pool is not None:
                conditions.append(DiskModel.resource_pool == resource_pool)
            if disk_type is not None:
                conditions.append(DiskModel.type == disk_type.value)
            if disk_format is not None:
                conditions.append(DiskModel.format == disk_format.value)
            if status is not None:
                conditions.append(DiskModel.status == status.value)
            if search_path is not None:
                conditions.append(DiskModel.search_path.ilike(f"%{search_path}%"))
            if min_size_gb is not None:
                conditions.append(DiskModel.capacity_gb >= min_size_gb)
            if max_size_gb is not None:
                conditions.append(DiskModel.capacity_gb <= max_size_gb)
            if attached_only is not None:
                if attached_only:
                    conditions.append(DiskModel.status == DiskStatus.ATTACHED)
                else:
                    conditions.append(DiskModel.status != DiskStatus.ATTACHED)

            if conditions:
                query = query.where(and_(*conditions))

            query = (
                query.limit(limit)
                .offset(offset)
                .options(joinedload(DiskModel.virtual_machine))
            )

            result = await session.execute(query)
            return result.scalars().all()

    async def update_disk(self, disk_id: int, data: DiskUpdate):
        async with self.db_pool.get_connection() as session:
            data = data.model_dump()
            data["modified"] = datetime.now()

            if data.get("new_name") is None:
                data.pop("new_name")

            if data.get("new_size_gb") is None:
                data.pop("new_size_gb")

            await session.execute(
                update(DiskModel).where(DiskModel.id == disk_id).values(**data)
            )
            await session.commit()

    async def update_disk_state(self, disk_id: int, status: DiskStatus):
        async with self.db_pool.get_connection() as session:
            data = {
                "status": (
                    DiskStatus(status) if not isinstance(status, DiskStatus) else status
                )
            }
            data["modified"] = datetime.now()

            await session.execute(
                update(DiskModel).where(DiskModel.id == disk_id).values(**data)
            )
            await session.commit()

    async def attach_disk_to_vm(self, disk_id: int, vm_name: str):
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(DiskModel)
                .where(DiskModel.id == disk_id)
                .values(
                    vm_name=vm_name,
                    status=DiskStatus.ATTACHED.value,
                    modified=datetime.now(),
                )
            )
            await session.commit()

    async def detach_disk_from_vm(self, disk_id: int):
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(DiskModel)
                .where(DiskModel.id == disk_id)
                .values(
                    vm_name=None,
                    status=DiskStatus.DETACHED.value,
                    modified=datetime.now(),
                )
            )
            await session.commit()

    async def delete_disk(self, disk_id: int):
        async with self.db_pool.get_connection() as session:
            stmt = delete(DiskModel).where(DiskModel.id == disk_id)
            await session.execute(stmt)
            await session.commit()

    async def get_disk_stats(self, pool: str = None, vm_name: str = None):
        async with self.db_pool.get_connection() as session:
            query = select(
                func.count(DiskModel.id),
                func.sum(DiskModel.capacity_bytes),
                func.sum(DiskModel.allocation_gb * 1024**3),
                func.count().filter(DiskModel.status == DiskStatus.ATTACHED.value),
            )

            conditions = []
            if pool is not None:
                conditions.append(DiskModel.pool == pool)
            if vm_name is not None:
                conditions.append(DiskModel.vm_name == vm_name)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.options(joinedload(DiskModel.virtual_machine))
            result = await session.execute(query)
            return result.first()

    async def get_orphaned_disks(self):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(DiskModel).where(
                    DiskModel.type == DiskType.ORPHANED.value,
                    DiskModel.vm_name.is_(None).options(
                        joinedload(DiskModel.virtual_machine)
                    ),
                )
            )
            return result.scalars().all()
