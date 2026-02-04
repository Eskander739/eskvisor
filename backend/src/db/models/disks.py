from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

from src.db.base import Base


class DiskFormatDB(PyEnum):
    QCOW2 = "qcow2"
    RAW = "raw"
    UNKNOWN = "unknown"


class DiskStatusDB(PyEnum):
    ATTACHED = "attached"
    DETACHED = "detached"
    ERROR = "error"
    PENDING = "pending"


class DiskTypeDB(PyEnum):
    POOL_DISK = "pool_disk"
    ORPHANED = "orphaned"
    SNAPSHOT = "snapshot"
    TEMPLATE = "template"
    BACKUP = "backup"
    CACHE = "cache"
    SWAP = "swap"
    CDROM = "cdrom"
    NETWORK = "network"
    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"
    EXTERNAL_DISK = "external_disk"


class DiskModel(Base):
    __tablename__ = "disks"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)

    # References
    pool = Column(String(255), nullable=True)
    vm_name = Column(String(255), ForeignKey("virtual_machines.name"), nullable=True)
    resource_pool = Column(String(255), nullable=True)

    # Type and format
    type = Column(SQLEnum(DiskTypeDB), default=DiskTypeDB.PERSISTENT)
    format = Column(SQLEnum(DiskFormatDB), default=DiskFormatDB.QCOW2)
    status = Column(SQLEnum(DiskStatusDB), default=DiskStatusDB.DETACHED)

    # Size information
    capacity_bytes = Column(Integer, nullable=True)
    capacity_gb = Column(Float, nullable=True)
    allocation_gb = Column(Float, default=0.0)

    # Configuration
    encrypted = Column(Boolean, default=False)
    readonly = Column(Boolean, default=False)
    sparse = Column(Boolean, default=True)
    cache_mode = Column(String(50), default="none")
    file_path_exists = Column(Boolean, default=False)

    # Metadata
    description = Column(Text, nullable=True)
    created = Column(DateTime, default=datetime.now)
    modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Search and filtering
    search_path = Column(String(500), nullable=True)

    # Relationships
    virtual_machine = relationship(
        "VirtualMachineModel",
        backref="attached_disks",
        lazy="select",
        foreign_keys=[vm_name],
        primaryjoin="DiskModel.vm_name == VirtualMachineModel.name",
    )
