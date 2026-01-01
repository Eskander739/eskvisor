from pydantic import BaseModel


class NodeInfo(BaseModel):
    model: str # архитектура системы
    memory: int # объем оперативной памяти
    cpus: int # максимальное количество vCPUs, которые можно назначить ВМ
    mhz: int # текущая частота процессора
    nodes: int # NUMA узлы
    sockets: int # количество мест для установки процессора
    cores: int # количество ядер
    threads: int # количество потоков на ядро