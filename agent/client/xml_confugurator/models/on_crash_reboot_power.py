from enum import Enum

from pydantic import BaseModel


class XmlOnPowerOffEnum(Enum):
    destroy = "destroy" # Серверная ВМ - уничтожить при выключении
    restart = "restart" # ВМ с сервисом - перезапустить
    preserve = "preserve" # ВМ для отладки - сохранить состояние


class XmlOnRebootEnum(Enum):
    destroy = "destroy"  # Тестовая ВМ - уничтожить после теста
    restart = "restart"  # Обычная ВМ - перезагружать
    preserve = "preserve"  # ВМ с проблемным драйвером - не перезагружать


class XmlOnCrashEnum(Enum):
    destroy = "destroy"  # Уничтожить упавшую ВМ
    restart = "restart"  # Автоматически перезапустить упавшую ВМ
    preserve = "preserve"  # Сохранить состояние для отладки
    coredump_restart = "coredump-restart" # Сохранить core dump + действие(для анализа сбоев)
    coredump_destroy = "coredump-destroy" # Сохранить core dump + действие(для анализа сбоев)


class XmlOnPowerOff(BaseModel):
    value: XmlOnPowerOffEnum = XmlOnPowerOffEnum.destroy


class XmlOnReboot(BaseModel):
    value: XmlOnRebootEnum = XmlOnRebootEnum.restart


class XmlOnCrash(BaseModel):
    value: XmlOnCrashEnum = XmlOnCrashEnum.destroy

