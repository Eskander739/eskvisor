from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship

from src.db.base import Base


class VirtualNetworkModel(Base):
    __tablename__ = "virtual_networks"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    uuid = Column(String(36), nullable=False, unique=True)

    # References
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=True)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=True)

    # Basic configuration
    network_type = Column(String(50), default="nat")
    bridge_name = Column(String(50), nullable=True)
    forward_mode = Column(String(50), default="nat")

    # IP configuration
    ipv4_enabled = Column(Boolean, default=True)
    ipv6_enabled = Column(Boolean, default=False)
    ipv4_address = Column(String(50), nullable=True)
    ipv6_address = Column(String(50), nullable=True)
    gateway = Column(String(50), nullable=True)
    mtu = Column(Integer, default=1500)

    # DHCP configuration
    dhcp_enabled = Column(Boolean, default=True)
    dhcp_ranges = Column(JSON, default=list)
    dhcp_hosts = Column(JSON, default=list)

    # DNS configuration
    dns_forwarders = Column(JSON, default=list)
    dns_hosts = Column(JSON, default=list)
    dns_txts = Column(JSON, default=list)
    domain_name = Column(String(255), nullable=True)

    # Status
    active = Column(Boolean, default=False)
    persistent = Column(Boolean, default=False)
    autostart = Column(Boolean, default=False)
    isolated = Column(Boolean, default=False)
    trust_guest_rx_filters = Column(Boolean, default=False)

    # Metadata
    xml_config = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created = Column(DateTime, default=datetime.now)
    modified = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted = Column(DateTime, nullable=True)

    # Relationships
    cluster = relationship("ClusterModel", backref="virtual_networks", lazy="select")
    node = relationship("NodeModel", backref="virtual_networks", lazy="select")
