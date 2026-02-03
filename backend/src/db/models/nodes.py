from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship

from src.db.base import Base


class NodeModel(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    hostname = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=False)
    hypervisor_type = Column(String(50), nullable=False)  # KVM, ESXi, Hyper-V
    port = Column(Integer, default=22)
    username = Column(String(100))
    password_encrypted = Column(String(255))  # Или ссылка на vault
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=True)

    # Ресурсы
    cpu_cores = Column(Integer, default=0)
    cpu_model = Column(String(255))
    total_memory_gb = Column(Integer, default=0)
    free_memory_gb = Column(Integer, default=0)
    total_storage_gb = Column(Integer, default=0)
    free_storage_gb = Column(Integer, default=0)

    # Статусы
    status = Column(String(20), default="offline")  # online, offline, maintenance
    last_seen = Column(DateTime)
    enabled = Column(Boolean, default=True)

    # Метаданные
    version = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    cluster = relationship("ClusterModel", backref="clusters", lazy="select")
