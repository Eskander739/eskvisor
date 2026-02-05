from datetime import datetime

from pydantic import BaseModel, Field

from src.models.node import Node


class Cluster(BaseModel):

    id: int
    name: str = Field(..., max_length=255, min_length=1)
    description: str | None = Field(default=None, max_length=4096, min_length=1)
    cluster_type: str = Field(default="standalone", max_length=50, min_length=1)
    high_availability: bool = Field(default=False)
    load_balancing: bool = Field(default=False)
    total_hosts: int = Field(default=0)
    total_cpu_cores: int = Field(default=0)
    total_storage_gb: int = Field(default=0)

    created: datetime = Field(...)
    updated: datetime = Field(...)
    deleted: datetime = Field(...)

    # Связи
    nodes: list[Node]


class ClusterCreateRequest(BaseModel):
    name: str = Field(..., max_length=255, min_length=1)
    description: str | None = Field(default=None, max_length=4096, min_length=1)
    cluster_type: str = Field(default="standalone", max_length=50, min_length=1)
    high_availability: bool = Field(default=False)
    load_balancing: bool = Field(default=False)


class ClusterUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255, min_length=1)
    description: str | None = Field(default=None, max_length=4096, min_length=1)
    cluster_type: str | None = Field(default=None, max_length=50, min_length=1)
    high_availability: bool | None = Field(default=None)
    load_balancing: bool | None = Field(default=None)
