from pydantic import BaseModel, computed_field


class ResourcePoolVirtualCreate(BaseModel):
    name: str
    cpu_core_limit: int  # Сколько ядер установить в качестве лимита
    ram_limit: int  # Какой объем RAM установить в качестве лимита(в байтах)
    vm_uuid_list: list[str] | None = None


class ResourcePoolVirtualEdit(BaseModel):
    name: str
    cpu_core_limit: int | None = None  # Сколько ядер установить в качестве лимита
    ram_limit: int | None = (
        None  # Какой объем RAM установить в качестве лимита(в байтах)
    )
    vm_uuid_list: list[str] | None = None


class ResourcePoolVirtual(BaseModel):
    name: str
    cpu_core_limit: int  # Сколько ядер установлено в качестве лимита
    ram_limit: int  # Какой объем RAM установлено в качестве лимита(в байтах)
    cpu_core_allocated: int  # Сколько ядер уже используется
    cpu_core_available: int  # Сколько ядер свободно для использования
    ram_allocated: int  # Какой объем RAM уже используется(в байтах)
    ram_available: int  # Какой объем RAM свободен для использования(в байтах)
    vm_uuid_list: list[str] | None = None  # Количество ВМ в ресурс пуле

    @computed_field
    @property
    def ram_limit_gb(self) -> float:
        return self.ram_limit / (1024**3)

    @computed_field
    @property
    def ram_allocated_gb(self) -> float:
        return self.ram_allocated / (1024**3)

    @computed_field
    @property
    def ram_available_gb(self) -> float:
        return self.ram_available / (1024**3)
