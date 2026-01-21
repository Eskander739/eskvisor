from pathlib import Path

from pydantic import BaseModel, IPvAnyNetwork, model_validator, Field


class NFSStorageModel(BaseModel):
    source: str # ip:dir на стороне NFS сервера
    mount: str # точка монтирования на стороне агента(dir)

    @model_validator(mode="after")
    def validate_mode(cls, values):
        source = values.source.split(":")[0]
        IPvAnyNetwork(source)
        Path(values.mount)
        if values.mount.endswith("/"):
            values.mount = values.mount[:-1]

        return values


class NFSStorageForMount(BaseModel):
    source: str # ip:dir на стороне NFS сервера
    nfs_name: str # имя NFS сервера

    @model_validator(mode="after")
    def validate_mode(cls, values):
        ip, source = values.source.split(":")
        IPvAnyNetwork(ip)
        Path(source)

        return values

class NFSStorages(BaseModel):
    nfs_storages: list[NFSStorageModel]

class LoadNFSStorages(BaseModel):
    """
    Получаем список NFS хранилищ со стороны бэкэнда для подключения
    """
    nfs_storages_for_mount: list[NFSStorageForMount] = Field(
        default_factory=list,
        description="Список NFS хранилищ для монтирования"
    )
