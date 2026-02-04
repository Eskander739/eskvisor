from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship

from src.db.base import Base


class StoragePoolTypeDB(PyEnum):
    LOGICAL = "logical"
    DIRECTORY = "directory"
    NETFS = "netfs"
    ISCSI = "iscsi"
    SCSI = "scsi"
    MPATH = "mpath"
    RBD = "rbd"
    SHEEPDOG = "sheepdog"
    GLUSTER = "gluster"
    ZFS = "zfs"
    VSTORAGE = "vstorage"


class ResourcePoolModel(Base):
    __tablename__ = "resource_pools"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)

    # CPU settings
    cpu_core_limit = Column(Integer, default=-1)  # -1 means unlimited
    cpu_core_allocated = Column(Float, default=0.0)
    cpu_core_available = Column(Float, default=0.0)
    cpu_weight = Column(Integer, default=100)

    # RAM settings
    ram_limit_bytes = Column(Integer, default=-1)  # -1 means unlimited
    ram_reservation_bytes = Column(Integer, default=0)
    ram_allocated = Column(Float, default=0.0)
    ram_available = Column(Float, default=0.0)

    # Storage settings
    storage_limit = Column(Integer, default=-1)  # -1 means unlimited
    storage_allocated = Column(Integer, default=0)
    storage_available = Column(Integer, default=0)
    storage_type = Column(String(50), default=StoragePoolTypeDB.LOGICAL.value)

    # VM list (stored as JSON for simplicity, could be normalized)
    vms = Column(JSON, default=list)
    vm_reservation_list = Column(JSON, default=list)

    # Status and metadata
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    cluster = relationship("ClusterModel", backref="resource_pools", lazy="select")
    node = relationship("NodeModel", backref="resource_pools", lazy="select")
