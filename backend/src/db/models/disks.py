from datetime import datetime

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
    UUID,
)
from sqlalchemy.orm import relationship

from src.db.base import Base
from src.models.disk import DiskFormat, DiskStatus, DiskType


class DiskModel(Base):
    __tablename__ = "disks"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)

    # References
    pool = Column(String(255), nullable=True)  # TODO: В будущем поменять на boolean
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    vm_id = Column(Integer, ForeignKey("virtual_machines.id"), nullable=True)
    resource_pool = Column(String(255), nullable=True)

    # Type and format
    type = Column(SQLEnum(DiskType), default=DiskType.EXTERNAL_DISK)
    format = Column(SQLEnum(DiskFormat), default=DiskFormat.QCOW2)
    status = Column(SQLEnum(DiskStatus), default=DiskStatus.DETACHED)

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
    deleted = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Search and filtering
    search_path = Column(String(500), nullable=True)

    # Relationships
    virtual_machine = relationship(
        "VirtualMachineModel",
        backref="attached_disks",
        lazy="select",
        foreign_keys=[vm_id],
        primaryjoin="DiskModel.vm_id == VirtualMachineModel.id",
    )
