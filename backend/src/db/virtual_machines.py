from sqlalchemy import select, update, delete, and_, func, desc
from datetime import datetime
from typing import Any

from src.db.models.virtual_machines import VirtualMachineModel, VMStateDB
from src.services.pool.db_pool import DBPool
from src.models.vm import VmUpdateRequest, VMListRequest


class VirtualMachinesDB:
    def __init__(self, db_pool: DBPool):
        self.db_pool = db_pool

    async def create_virtual_machine(self, data: dict):
        async with self.db_pool.get_connection() as session:
            vm = VirtualMachineModel(**data)
            session.add(vm)
            await session.commit()
            return vm.id

    async def get_virtual_machine(self, vm_id: int):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(VirtualMachineModel).where(VirtualMachineModel.id == vm_id)
            )
            return result.scalar_one_or_none()

    async def get_virtual_machine_by_name(self, name: str):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(VirtualMachineModel).where(VirtualMachineModel.name == name)
            )
            return result.scalar_one_or_none()

    async def get_virtual_machine_by_uuid(self, uuid: str):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(VirtualMachineModel).where(VirtualMachineModel.uuid == uuid)
            )
            return result.scalar_one_or_none()

    async def get_virtual_machines_list(self, vm_info: VMListRequest):
        async with self.db_pool.get_connection() as session:
            query = select(VirtualMachineModel)

            conditions = []
            if vm_info.cluster_id is not None:
                conditions.append(VirtualMachineModel.cluster_id == vm_info.cluster_id)
            if vm_info.node_id is not None:
                conditions.append(VirtualMachineModel.node_id == vm_info.node_id)
            if vm_info.resource_pool_id is not None:
                conditions.append(
                    VirtualMachineModel.resource_pool_id == vm_info.resource_pool_id
                )
            if vm_info.name is not None:
                conditions.append(VirtualMachineModel.name.ilike(f"%{vm_info.name}%"))
            if vm_info.state is not None:
                conditions.append(VirtualMachineModel.state == vm_info.state)
            if vm_info.enabled is not None:
                conditions.append(VirtualMachineModel.enabled == vm_info.enabled)
            if vm_info.infrastructure is not None:
                conditions.append(
                    VirtualMachineModel.infrastructure == vm_info.infrastructure
                )

            if conditions:
                query = query.where(and_(*conditions))

            # Sorting
            if vm_info.sort_by == "name":
                order_column = VirtualMachineModel.name
            elif vm_info.sort_by == "created":
                order_column = VirtualMachineModel.created
            elif vm_info.sort_by == "modified":
                order_column = VirtualMachineModel.modified
            else:
                order_column = VirtualMachineModel.created

            if vm_info.sort_desc:
                query = query.order_by(desc(order_column))
            else:
                query = query.order_by(order_column)

            query = query.limit(vm_info.limit).offset(vm_info.offset)

            result = await session.execute(query)
            return result.scalars().all()

    async def update_virtual_machine(self, vm_id: int, data: dict):
        async with self.db_pool.get_connection() as session:
            data["modified"] = datetime.now()
            await session.execute(
                update(VirtualMachineModel)
                .where(VirtualMachineModel.id == vm_id)
                .values(**data)
            )
            await session.commit()

    async def update_virtual_machine_with_request(
        self, vm_id: int, update_request: VmUpdateRequest
    ) -> bool:
        """
        Обновляет виртуальную машину на основе VmUpdateRequest.

        Args:
            vm_id: ID виртуальной машины
            update_request: Запрос на обновление

        Returns:
            True если обновление успешно, False в противном случае
        """
        async with self.db_pool.get_connection() as session:
            # Получаем текущую ВМ
            result = await session.execute(
                select(VirtualMachineModel).where(VirtualMachineModel.id == vm_id)
            )
            vm = result.scalar_one_or_none()

            if not vm:
                return False

            # Подготавливаем данные для обновления
            update_data: dict[str, Any] = {"modified": datetime.now()}

            # Обновляем базовые параметры
            if update_request.max_memory_mb is not None:
                update_data["memory_mb"] = update_request.max_memory_mb

            if update_request.vcpus is not None:
                update_data["vcpus"] = update_request.vcpus

            if update_request.max_vcpus is not None:
                update_data["max_vcpus"] = update_request.max_vcpus

            if update_request.cpu_model is not None:
                update_data["cpu_model"] = update_request.cpu_model

            if update_request.cpu_features is not None:
                # Сохраняем CPU features как JSON
                update_data["extra_args"] = (
                    f"{vm.extra_args or ''} "
                    f"--cpu {update_request.cpu_model} "
                    f"features={','.join(update_request.cpu_features)}"
                ).strip()

            if update_request.autostart is not None:
                update_data["autostart"] = update_request.autostart
                update_data["autostart_vm"] = update_request.autostart

            if update_request.description is not None:
                update_data["description"] = update_request.description

            if update_request.name is not None:
                update_data["name"] = update_request.name

            if update_request.graphics is not None:
                # Обновляем графические настройки
                graphics_type = update_request.graphics.get("type")
                graphics_port = update_request.graphics.get("port")
                graphics_listen = update_request.graphics.get("listen")

                if graphics_type:
                    update_data["graphics_type"] = graphics_type
                if graphics_port:
                    update_data["graphics_port"] = graphics_port
                if graphics_listen:
                    update_data["graphics_listen"] = graphics_listen

            if update_request.video_model is not None:
                update_data["video_model"] = (
                    update_request.video_model.value
                    if hasattr(update_request.video_model, "value")
                    else update_request.video_model
                )

            if update_request.machine_type is not None:
                update_data["machine_type"] = update_request.machine_type

            if update_request.os_variant is not None:
                update_data["os_variant"] = update_request.os_variant

            if update_request.boot_devices is not None:
                update_data["boot_devices"] = update_request.boot_devices

            if update_request.features is not None:
                # Объединяем существующие features с новыми
                current_features = vm.extra_args or ""
                new_features = " ".join(
                    [
                        f"--features {key}={value}"
                        for key, value in update_request.features.items()
                    ]
                )
                update_data["extra_args"] = f"{current_features} {new_features}".strip()

            if update_request.memballoon_model is not None:
                update_data["extra_args"] = (
                    f"{update_data.get('extra_args', vm.extra_args or '')} "
                    f"--memballoon model={update_request.memballoon_model}"
                ).strip()

            if update_request.hyperv_features is not None:
                # Добавляем Hyper-V features
                hyperv_args = " ".join(
                    [
                        f"--hyperv {key}={value}"
                        for key, value in update_request.hyperv_features.items()
                    ]
                )
                update_data["extra_args"] = (
                    f"{update_data.get('extra_args', vm.extra_args or '')} "
                    f"{hyperv_args}"
                ).strip()

            if update_request.qemu_agent is not None:
                # QEMU агент добавляется через extra args
                if update_request.qemu_agent:
                    update_data["extra_args"] = (
                        f"{update_data.get('extra_args', vm.extra_args or '')} "
                        f"--channel unix,target_type=virtio,name=org.qemu.guest_agent.0"
                    ).strip()

            # Если включено изменение live конфигурации, отмечаем это
            if update_request.change_live_config:
                update_data["modified"] = datetime.now()
                # Для live изменений может потребоваться дополнительная логика
                # Например, флаг что изменения должны быть применены немедленно

            # Выполняем обновление
            await session.execute(
                update(VirtualMachineModel)
                .where(VirtualMachineModel.id == vm_id)
                .values(**update_data)
            )

            await session.commit()
            return True

    async def update_virtual_machine_state(self, vm_id: int, state: VMStateDB):
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(VirtualMachineModel)
                .where(VirtualMachineModel.id == vm_id)
                .values(state=state.value, modified=datetime.now())
            )
            await session.commit()

    async def delete_virtual_machine(self, vm_id: int):
        async with self.db_pool.get_connection() as session:
            stmt = delete(VirtualMachineModel).where(VirtualMachineModel.id == vm_id)
            await session.execute(stmt)
            await session.commit()

    async def soft_delete_virtual_machine(self, vm_id: int):
        async with self.db_pool.get_connection() as session:
            await session.execute(
                update(VirtualMachineModel)
                .where(VirtualMachineModel.id == vm_id)
                .values(deleted=datetime.now(), enabled=False, modified=datetime.now())
            )
            await session.commit()

    async def get_virtual_machine_stats(
        self, cluster_id: int = None, node_id: int = None
    ):
        async with self.db_pool.get_connection() as session:
            query = select(
                func.count(VirtualMachineModel.id),
                func.sum(VirtualMachineModel.vcpus),
                func.sum(VirtualMachineModel.memory_mb),
                func.count().filter(
                    VirtualMachineModel.state == VMStateDB.RUNNING.value
                ),
            ).where(
                VirtualMachineModel.enabled == True,
                VirtualMachineModel.deleted.is_(None),
            )

            if cluster_id:
                query = query.where(VirtualMachineModel.cluster_id == cluster_id)
            if node_id:
                query = query.where(VirtualMachineModel.node_id == node_id)

            result = await session.execute(query)
            return result.first()

    async def get_virtual_machines_by_resource_pool(self, resource_pool_id: int):
        async with self.db_pool.get_connection() as session:
            result = await session.execute(
                select(VirtualMachineModel).where(
                    VirtualMachineModel.resource_pool_id == resource_pool_id,
                    VirtualMachineModel.enabled == True,
                    VirtualMachineModel.deleted.is_(None),
                )
            )
            return result.scalars().all()
