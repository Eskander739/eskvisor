from pydantic import BaseModel

from agent.client.hypervisor.models.general import VMState


class VirtualMachine(BaseModel):
    """Информация о виртуальной машине"""
    name: str
    state: VMState
    id: int
    uuid: str
    vcpus: int
    memory: int  # в килобайтах
    max_memory: int  # в килобайтах
    cpu_time: int  # в наносекундах
