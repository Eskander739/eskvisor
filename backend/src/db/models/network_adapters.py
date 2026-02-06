from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from src.db.base import Base


class NetAdapterModel(Base):
    __tablename__ = "net_adapters"
    id = Column(Integer, primary_key=True)
    network_type = Column(String(50), nullable=False)
    model = Column(String(255), nullable=True)
    mac_address = Column(String(45), nullable=True)
    source = Column(String(50), nullable=False)

    created = Column(DateTime, default=datetime.now)
    updated = Column(DateTime)
    deleted = Column(DateTime)

    # Связь с виртуальной машиной
    vm_id = Column(Integer, ForeignKey("virtual_machines.id"), nullable=True)
    virtual_machine = relationship(
        "VirtualMachineModel", back_populates="net_adapters", lazy="select"
    )
