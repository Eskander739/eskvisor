from datetime import datetime

from pydantic import BaseModel, Field


class Node(BaseModel):
    id: int
    name: str = Field(..., max_length=255, min_length=1)
    hostname: str | None = Field(default=None, max_length=255, min_length=1)
    ip_address: str = Field(..., max_length=45, min_length=7)
    hypervisor_type: str = Field(..., max_length=50)
    port: int = Field(default=22)
    username: str = Field(..., max_length=100)
    password_encrypted: str = Field(..., max_length=255)
    cluster_id: str = Field(..., max_length=255)
    cpu_cores: int = Field(default=0)
    cpu_model: str | None = Field(default=None, max_length=255)
    total_memory_gb: int = Field(default=0)
    free_memory_gb: int = Field(default=0)
    total_storage_gb: int = Field(default=0)
    free_storage_gb: int = Field(default=0)
    status: str = Field(default="offline", max_length=20)
    last_seen: datetime = Field(default=None)
    enabled: str = Field(default=True)
    version: str | None = Field(default=None, max_length=100)
    created: datetime = Field(...)
    updated: datetime = Field(...)
    deleted: datetime = Field(...)


class NodeCreateRequest(BaseModel):
    name: str = Field(..., max_length=255, min_length=1)
    ip_address: str = Field(..., max_length=45, min_length=7)
    hypervisor_type: str = Field(default="KVM", max_length=50)
    port: int = Field(default=22)
    username: str = Field(..., max_length=100)
    password_encrypted: str = Field(..., max_length=255)
    cluster_id: int = Field(...)


class NodeSyncStateFromAgent(BaseModel):
    ip_address: str = Field(..., max_length=45, min_length=7)
    hostname: str | None = Field(default=None, max_length=255, min_length=1)
    cpu_cores: int = Field(default=0)
    cpu_model: str | None = Field(default=None, max_length=255)
    total_memory_gb: int = Field(default=0)
    free_memory_gb: int = Field(default=0)
    total_storage_gb: int = Field(default=0)
    free_storage_gb: int = Field(default=0)


class NodeSyncState(NodeSyncStateFromAgent):
    status: str = Field(default="online", max_length=20)
    updated: datetime = Field(default_factory=lambda: datetime.now())
    last_seen: datetime = Field(default_factory=lambda: datetime.now())


# print(NodeCreateRequest(name="eska_node_01", ip_address="192.168.100.134", username="root", password_encrypted="root", cluster_id=1).model_dump_json())
