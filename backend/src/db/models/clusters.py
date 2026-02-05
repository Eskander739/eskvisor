from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import relationship

from src.db.base import Base


class ClusterModel(Base):
    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text)

    # Основные настройки
    cluster_type = Column(
        String(50), default="standalone"
    )  # standalone, ha, load_balanced
    high_availability = Column(Boolean, default=False)
    load_balancing = Column(Boolean, default=False)

    # Сетевые настройки
    virtual_ip = Column(String(45))
    network_cidr = Column(String(50))

    # Ресурсы кластера (вычисляемые/агрегированные)
    total_hosts = Column(Integer, default=0)
    total_cpu_cores = Column(Integer, default=0)
    total_memory_gb = Column(Integer, default=0)
    total_storage_gb = Column(Integer, default=0)

    # Метаданные
    created = Column(DateTime, default=datetime.now)
    updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    nodes = relationship("NodeModel", back_populates="cluster", lazy="selectin")
