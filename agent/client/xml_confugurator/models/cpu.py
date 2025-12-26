from enum import Enum

from pydantic import BaseModel

from agent.client import CpuModelAMD, CpuModelARM, CpuModelPowerPC, CpuModelS390X, CpuModelRiscV, \
    CpuModelMIPS, CpuModelIntel


class VCpuPlacement(Enum):
    """
    static
    * Фиксированное количество vCPU
    * Нельзя изменить без перезапуска ВМ
    * Процессоры закрепляются за физическими ядрами

    auto
    * Libvirt сам выбирает оптимальное размещение.
    * Учитывает топологию процессоров и нагрузку
    * Лучше для миграции между разными хостами
    """

    static = "static" # жёсткая привязка к ядрам
    auto = "auto" # гипервизор сам выбирает размещение


class XmlVCpu(BaseModel):
    placement: VCpuPlacement | None = None
    current: int | None = None # для горячего добавления
    value: int = 2
    cpuset: str | None = None
    # TODO: match='exact'/'strict'/'minimum' — политика проверки CPU хоста (обычно не нужно). - добавить поддержку
    # TODO: check='none'/'partial' — уровень проверки совместимости CPU. - добавить поддержку

class CpuTopology(BaseModel):
    sockets: int = 1
    cores: int = 2
    threads: int = 2

class CpuModeEnum(Enum):
    """
    host-passthrough
      Виртуальная машина получает точную копию физического CPU хоста.
      Все флаги и возможности процессора передаются напрямую. Это даёт максимальную производительность,
      но не гарантирует миграцию ВМ между разными физическими серверами.

    host-model
      Libvirt определяет наиболее подходящую модель CPU, близкую к хосту, и эмулирует её.
      Поддерживает большинство функций хоста, но с лучшей совместимостью для миграции.
      Рекомендуется по умолчанию, если не нужны особые настройки.

    custom
      Позволяет указать конкретную модель CPU вручную (например, qemu64, kvm64, core2duo, Nehalem, Penryn и др.).
      Полезно для совместимости со старыми ОС или приложениями. Пример:


    maximum
      Использует максимально возможный набор функций, поддерживаемых гипервизором и хостом.
      Реже используется, так как может вызывать проблемы при миграции.
    """
    host_passthrough = "host-passthrough"
    host_model = "host-model"
    custom = "custom"
    maximum = "maximum"


class XmlCpuModelFallbackEnum(Enum):
    allow = "allow" # для совместимости, миграции между разными хостами
    forbid = "forbid" # для гарантии конкретных CPU фич (AVX-512, TSX и т.д.)

class XmlCpuFeaturePolicyEnum(Enum):
    require = "require" # обязательно
    optional = "optional" # опционально
    disable = "disable" # отключить
    forbid = "forbid" # запретить


class XmlCpuFeature(BaseModel):
    policy: XmlCpuFeaturePolicyEnum
    name: str # полный список фич невозможно пропихнуть, он слишком огромен


class XmlCpuModel(BaseModel):
    fallback: XmlCpuModelFallbackEnum | None = None
    vendor_id: str | None = None
    value: CpuModelIntel | CpuModelAMD | CpuModelARM | CpuModelPowerPC | CpuModelS390X | CpuModelRiscV | CpuModelMIPS


class XmlCpuCheckEnum(Enum):
    """
    Проверка совместимости CPU при миграции/старте
    """

    none = "none" # Что делает: Никаких проверок
    partial = "partial" # Что делает: Проверяет только основные фичи, игнорирует незначительные
    full = "full" # Что делает: Проверяет ВСЕ фичи CPU.



class XmlCpuMatchEnum(Enum):
    """
    Как сопоставлять CPU хоста и гостя
    """

    minimum = "minimum" # то делает: Хост должен иметь как минимум эти фичи
    exact = "exact" # Хост должен иметь точно такие же фичи
    strict = "strict" #  Самый строгий режим. Проверяет ВСЁ, включая микроархитектуру


class XmlCpu(BaseModel):
    """
    4. Правильные комбинации:
    ┌------------------------------------------------┐
    ▯ Режим (mode)	      ▯<model> внутри	▯Валидно?▯
    ▯---------------------▯-----------------▯--------▯
    ▯custom	              ▯       Да	    ▯   Да   ▯
    ▯custom	              ▯       Нет	    ▯   Нет  ▯
    ▯host-passthrough     ▯       Да	    ▯   Нет  ▯
    ▯host-model	          ▯       Да	    ▯   Нет  ▯
    ▯maximum	          ▯       Да	    ▯   Нет  ▯
    ▯(не указан)	      ▯       Да	    ▯   Нет  ▯
    └------------------------------------------------┘
    """

    mode: CpuModeEnum | None = None
    check: XmlCpuCheckEnum | None = None
    match: XmlCpuMatchEnum | None = None
    model: XmlCpuModel | None = None
    topology: CpuTopology | None = None
    features: list[XmlCpuFeature] | None = None