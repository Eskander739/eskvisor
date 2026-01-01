from datetime import datetime

from pydantic import BaseModel

from agent.client.hypervisor.libvirt.models.general import VMState


class Snapshot(BaseModel):
    name: str
    description: str
    created: datetime
    state: VMState


class SnapshotWithParent(BaseModel):
    name: str
    description: str | None = None
    created: datetime
    state: VMState
    parent: Snapshot | None = None
