from pydantic import BaseModel, computed_field


class NodeInfo(BaseModel):
    model: str  # архитектура системы
    memory: int  # объем оперативной памяти
    cpus: int  # максимальное количество vCPUs
    mhz: int  # текущая частота процессора
    nodes: int  # NUMA узлы
    sockets: int  # количество мест для установки процессора
    cores: int  # количество ядер
    threads: int  # количество потоков на ядро

    @computed_field
    @property
    def memory_bytes(self) -> float:
        return (self.memory * 1024) * 1024
