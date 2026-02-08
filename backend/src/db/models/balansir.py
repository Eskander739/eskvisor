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
    ARRAY,
)
from sqlalchemy.orm import relationship, Mapped

from src.db.base import Base


class StoragePoolTypeDB(PyEnum):
    LOGICAL = "logical"


class ResourceReservationVM(Base):
    """Модель для хранения резервации ресурсов для конкретной ВМ в пуле"""

    __tablename__ = "resource_reservation_vm"

    id = Column(Integer, primary_key=True)
    resource_pool_id = Column(Integer, ForeignKey("resource_pools.id"), nullable=False)
    virtual_machine_id = Column(
        Integer, ForeignKey("virtual_machines.id"), nullable=False
    )

    # Ресурсы, зарезервированные для ВМ
    cpu_core_count = Column(Integer, default=0, nullable=False)
    ram_bytes = Column(Integer, default=0, nullable=False)
    storage_bytes = Column(Integer, default=0, nullable=False)

    # Дополнительная информация
    vm_pid = Column(Integer, nullable=True)  # PID процесса ВМ (если доступен)
    vm_name = Column(String(255), nullable=False)  # Имя ВМ для удобства

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    resource_pool = relationship("ResourcePoolModel", back_populates="vm_reservations")
    virtual_machine = relationship(
        "VirtualMachineModel", back_populates="resource_reservations"
    )


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

    # Список ID виртуальных машин, связанных с пулом
    vms = Column(ARRAY(Integer), default=[], nullable=False)

    # Резервации ресурсов для ВМ (связь один-ко-многим)
    vm_reservations: Mapped[list[ResourceReservationVM]] = relationship(
        "ResourceReservationVM",
        back_populates="resource_pool",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # Status and metadata
    enabled = Column(Boolean, default=True)
    created = Column(DateTime, default=datetime.now)
    updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    cluster = relationship("ClusterModel", backref="resource_pools", lazy="select")
    node = relationship("NodeModel", backref="resource_pools", lazy="select")
