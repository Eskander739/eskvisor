from enum import Enum


class VMState(Enum):
    """Состояния виртуальной машины"""
    NOSTATE = 0  # Нет состояния
    RUNNING = 1  # Работает
    BLOCKED = 2  # Заблокирована
    PAUSED = 3  # Приостановлена
    SHUTDOWN = 4  # Завершается
    SHUTOFF = 5  # Выключена
    CRASHED = 6  # Аварийно завершена
    PMSUSPENDED = 7  # Приостановлена (PM)

