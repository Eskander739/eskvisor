from pathlib import Path

from pydantic import BaseModel, IPvAnyNetwork, model_validator, Field

from agent.client.hypervisor.libvirt.models.msg import DefaultMessage


class NFSStorageModel(BaseModel):
    source: str  # ip:dir на стороне NFS сервера
    mount: str  # точка монтирования на стороне агента(dir)

    @model_validator(mode="after")
    def validate_mode(self):
        source = self.source.split(":")[0]
        IPvAnyNetwork(source)
        Path(self.mount)
        if self.mount.endswith("/"):
            self.mount = self.mount[:-1]

        return self


class NFSStorageForMount(BaseModel):
    source: str  # ip:dir на стороне NFS сервера
    nfs_name: str  # имя NFS сервера

    @model_validator(mode="after")
    def validate_mode(self):
        ip, source = self.source.split(":")
        IPvAnyNetwork(ip)
        Path(source)

        return self


class NFSStorages(BaseModel):
    nfs_storages: list[NFSStorageModel]


class LoadNFSStorages(BaseModel):
    """
    Получаем список NFS хранилищ со стороны бэкэнда для подключения
    """

    nfs_storages_for_mount: list[NFSStorageForMount] = Field(
        default_factory=list, description="Список NFS хранилищ для монтирования"
    )


class VNCConnectInfo(DefaultMessage):
    vm_name: str
    vnc_port: int
    ws_port: int
    ws_url: str


class VNCStatusInfo(DefaultMessage):
    vm_name: str
    status: dict


class VNCRestartProxy(DefaultMessage):
    vm_name: str
    new_ws_port: int
    new_ws_url: str


class HealthState(BaseModel):
    status: str
    redis: bool
    task_manager: bool


class NodeSyncStateFromAgent(BaseModel):
    ip_address: str = Field(..., max_length=45, min_length=7)
    hostname: str | None = Field(default=None, max_length=255, min_length=1)
    cpu_cores: int = Field(default=0)
    cpu_model: str | None = Field(default=None, max_length=255)
    total_memory_gb: int = Field(default=0)
    free_memory_gb: int = Field(default=0)
    total_storage_gb: int = Field(default=0)
    free_storage_gb: int = Field(default=0)
