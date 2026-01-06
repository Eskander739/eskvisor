from datetime import datetime

from pydantic import BaseModel

from agent.client.hypervisor.libvirt.models.general import SnapshotState


class DeleteSnapshotInfo(BaseModel):
    snapshot_name: str
    vm_name: str
    remove_children: bool


class Snapshot(BaseModel):
    name: str
    vm_name: str
    description: str | None = None
    created: datetime
    state: SnapshotState
    is_current: bool
    size_bytes: int


class SnapshotWithParent(BaseModel):
    name: str
    vm_name: str
    description: str | None = None
    created: datetime
    state: SnapshotState
    parent: Snapshot | None = None
    is_current: bool
    size_bytes: int | None = None


class SnapshotList(BaseModel):
    vm_name: str
    snapshots: list[SnapshotWithParent]
    count: int
    chain_depth: int


class SnapshotCreateRequest(BaseModel):
    """Модель запроса для создания снапшота"""
    vm_name: str
    snapshot_name: str
    description: str = ""
    disk_only: bool = False
    quiesce: bool = False


class SnapshotDeleteRequest(BaseModel):
    """Модель запроса для удаления снапшота"""
    vm_name: str
    snapshot_name: str
    remove_children: bool = False


class SnapshotRevertRequest(BaseModel):
    """Модель запроса для восстановления из снапшота"""
    vm_name: str
    snapshot_name: str


class SnapshotUpdateRequest(BaseModel):
    """Модель запроса для обновления описания снапшота"""
    vm_name: str
    snapshot_name: str
    new_description: str


class SnapshotCloneRequest(BaseModel):
    """Модель запроса для клонирования ВМ из снапшота"""
    source_vm_name: str
    source_snapshot_name: str
    new_vm_name: str
    generate_new_uuid: bool = True


class SnapshotInfoRequest(BaseModel):
    """Модель запроса для получения информации о снапшоте"""
    vm_name: str
    snapshot_name: str


class SnapshotChainRequest(BaseModel):
    """Модель запроса для получения цепочки снапшотов"""
    vm_name: str


class MultipleSnapshotsRequest(BaseModel):
    """Модель запроса для создания снапшотов нескольких ВМ"""
    snapshots: list[SnapshotCreateRequest]

class SnapshotInfo(BaseModel):
    """
                            "name": snapshot_data.name,
                    "description": snapshot_data.description,
                    "created": snapshot_data.created,
                    "state": snapshot_data.state,
                    "parent": snapshot_data.parent.name if snapshot_data.parent else None,
                    "size_bytes": size,
                    "vm_name": vm_name,
                    "is_current": True
    """
    name: str
    vm_name: str
    description: str | None = None
    created: datetime
    state: SnapshotState
    parent: Snapshot | None