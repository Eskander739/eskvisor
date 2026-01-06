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


class ClonedSnapshot(BaseModel):
    source_vm_name: str
    source_snapshot_name: str
    new_vm_name: str
    new_uuid: str
    vm_started: bool


class CreateSnapshotChainError(BaseModel):
    vm_name: str
    created_snapshots: list[SnapshotWithParent]
    errors: list[str]
    total_requested: int
    successfully_created: int

class CreateMultipleSnapshotsError(BaseModel):
    results: list[SnapshotWithParent]
    total_requested: int
    successful: int
    failed: int

class CreateMultipleSnapshots(BaseModel):
    results: list[SnapshotWithParent]
    total_created: int
    successful: int

class CreateSnapshotChainSuccess(BaseModel):
    vm_name: str
    created_snapshots: list[SnapshotWithParent]
    total_created: int
    chain_depth: int

class SnapshotRevertSuccess(BaseModel):
    vm_name: str
    current_snapshot: str
    parent_snapshot: str
    snapshots_made_inactive: list[str]
    note: str | None = None

class SnapshotsChain(BaseModel):
    vm_name: str
    snapshots: list[SnapshotWithParent]
    snapshot_tree: dict
    chains: list[list[dict]]
    root_snapshots: list[str]
    chain_depth: int


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
