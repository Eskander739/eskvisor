from enum import Enum

from pydantic import BaseModel


class MemoryUnitEnum(Enum):
    """
    Важные особенности:
      Максимум, но не гарантия: ВМ может использовать меньше
      Резервирование: может резервироваться хостом (зависит от настроек)
      Ballooning: можно динамически менять (если драйвер установлен)
      Ограничения: не может превышать память хоста минус overhead
    """

    KiB = "KiB" # Килобайты
    MiB = "MiB" # Мегабайты
    GiB = "GiB" # Гигабайты
    none = "none" # Без unit (байты по умолчанию)


class MemoryXml(BaseModel):
    unit: MemoryUnitEnum = MemoryUnitEnum.MiB
    value: int = 256

class CurrentMemory(BaseModel):
    unit: MemoryUnitEnum = MemoryUnitEnum.MiB
    value: int = 256