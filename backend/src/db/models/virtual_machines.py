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
    JSON,
    Enum,
    UUID,
)
from sqlalchemy.orm import relationship

from src.db.base import Base


class VMStateDB(Enum):
    STARTING = "STARTING"  # Запуск
    RUNNING = "RUNNING"  # Работает
    BLOCKED = "BLOCKED"  # Заблокирована
    PAUSED = "PAUSED"  # Приостановлена
    SHUTDOWN = "SHUTDOWN"  # Завершается
    SHUTOFF = "SHUTOFF"  # Выключена
    CRASHED = "CRASHED"  # Аварийно завершена
    PMSUSPENDED = "PMSUSPENDED"  # Приостановлена (PM)
    CLONING = "CLONING"  # Клонируется
    DELETED = "DELETED"  # Удален


class VirtualMachineModel(Base):
    __tablename__ = "virtual_machines"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    uuid: UUID = Column(String(36), nullable=False, unique=True)

    # References
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    resource_pool_id = Column(Integer, ForeignKey("resource_pools.id"), nullable=True)

    # Basic information
    description = Column(Text, nullable=True)
    state = Column(String(50), default=VMStateDB.SHUTOFF)
    template = Column(String(255), nullable=True)

    # Resources
    vcpus = Column(Integer, default=1)
    max_vcpus = Column(Integer, default=1)
    memory_mb = Column(Float, default=512.0)
    video_memory_mb = Column(Float, default=16.0)

    # Configuration
    architecture = Column(String(50), default="x86_64")
    os_type = Column(String(50), default="linux")
    os_variant = Column(String(100), nullable=True)
    machine_type = Column(String(50), default="q35")
    cpu_model = Column(String(100), default="host-model")

    # Graphics and console
    graphics_type = Column(String(50), default="vnc")
    graphics_port = Column(Integer, nullable=True)
    graphics_listen = Column(String(50), default="0.0.0.0")
    console_type = Column(String(50), default="pty")
    video_model = Column(String(50), default="qxl")

    # Boot settings
    boot_uefi = Column(Boolean, default=False)
    secure_boot = Column(Boolean, default=False)
    boot_devices = Column(JSON, default=["hd"])

    # Autostart
    autostart_vm = Column(Boolean, default=False)
    autostart = Column(Boolean, default=False)
    noautoconsole = Column(Boolean, default=True)

    # Infrastructure
    infrastructure = Column(Boolean, default=False)

    # Additional configurations
    controllers = Column(JSON, default=list)
    extra_args = Column(Text, nullable=True)
    net_qemu_commandline = Column(JSON, nullable=True)

    # Status and metadata
    created = Column(DateTime, default=datetime.now)
    modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted = Column(DateTime, nullable=True)

    # Relationships
    cluster = relationship("ClusterModel", backref="virtual_machines", lazy="select")
    node = relationship("NodeModel", backref="virtual_machines", lazy="select")
    resource_pool = relationship(
        "ResourcePoolModel", backref="virtual_machines", lazy="select"
    )
    disks = relationship(
        "DiskModel",
        backref="attached_disks",
        lazy="select",
        primaryjoin="DiskModel.vm_id == VirtualMachineModel.id",
    )
    net_adapters = relationship(
        "NetAdapterModel",  # Имя класса в виде строки
        backref="net_adapters",  # Измененное имя обратной ссылки
        lazy="select",
        primaryjoin="NetAdapterModel.vm_id == VirtualMachineModel.id",
    )


from src.db.models.network_adapters import (
    NetAdapterModel,
)  # не удалять! влияет на работу БД
