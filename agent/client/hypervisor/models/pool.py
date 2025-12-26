from enum import Enum

import libvirt
from pydantic import Field, model_validator, BaseModel

PoolState = {
    libvirt.VIR_STORAGE_POOL_INACTIVE: 'inactive',
    libvirt.VIR_STORAGE_POOL_BUILDING: 'building',
    libvirt.VIR_STORAGE_POOL_RUNNING: 'running',
    libvirt.VIR_STORAGE_POOL_DEGRADED: 'degraded',
    libvirt.VIR_STORAGE_POOL_INACCESSIBLE: 'inaccessible'
}

class PoolStateEnum(Enum):
    INACTIVE = "inactive"
    BUILDING = "building"
    RUNNING = "running"
    DEGRADED = "degraded"
    INACCESSIBLE = "inaccessible"


class PoolInfo(BaseModel):
    """
    Информация о пуле хранилищ

    Attributes:
        pool_name: Имя пула
        pool_state: Текущее состояние пула
        pool_capacity_gb: Общая емкость пула в гигабайтах
        pool_allocation_gb: Использовано места в гигабайтах
        pool_available_gb: Доступно места в гигабайтах
        total_disks: Общее количество дисков в пуле
        attached_disks: Количество подключенных дисков
        detached_disks: Количество отключенных дисков
        format_distribution: Распределение дисков по форматам
        disks_capacity_gb: Общая емкость всех дисков в гигабайтах
        disks_allocated_gb: Использовано места на всех дисках в гигабайтах
        disks_usage_percentage: Процент использования дисков
    """

    pool_name: str = Field(..., description="Имя пула хранилищ")
    pool_state: PoolStateEnum = Field(..., description="Текущее состояние пула")
    pool_capacity_gb: float = Field(..., ge=0, description="Общая емкость пула в GB")
    pool_allocation_gb: float = Field(..., ge=0, description="Использовано места в GB")
    pool_available_gb: float = Field(..., ge=0, description="Доступно места в GB")
    total_disks: int = Field(..., ge=0, description="Общее количество дисков в пуле")
    attached_disks: int = Field(..., ge=0, description="Количество подключенных дисков")
    detached_disks: int = Field(..., ge=0, description="Количество отключенных дисков")
    format_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Распределение дисков по форматам"
    )
    disks_capacity_gb: float = Field(..., ge=0, description="Общая емкость всех дисков в GB")
    disks_allocated_gb: float = Field(..., ge=0, description="Использовано места на всех дисках в GB")
    disks_usage_percentage: float = Field(..., ge=0, le=100, description="Процент использования дисков")

    @model_validator(mode='after')
    def validate_pool_consistency(self) -> 'PoolInfo':
        """Проверка согласованности данных пула"""

        # Проверка емкости пула
        calculated_available = self.pool_capacity_gb - self.pool_allocation_gb
        if abs(self.pool_available_gb - calculated_available) > 0.01:
            raise ValueError(
                f"Несоответствие данных пула: "
                f"capacity({self.pool_capacity_gb}) - allocation({self.pool_allocation_gb}) = "
                f"{calculated_available:.2f} ≠ available({self.pool_available_gb})"
            )

        # Проверка количества дисков
        if self.total_disks != (self.attached_disks + self.detached_disks):
            raise ValueError(
                f"Несоответствие количества дисков: "
                f"total({self.total_disks}) ≠ attached({self.attached_disks}) + detached({self.detached_disks})"
            )

        # Проверка суммарного распределения форматов
        total_formats = sum(self.format_distribution.values())
        if total_formats != self.total_disks:
            raise ValueError(
                f"Несоответствие распределения форматов: "
                f"sum(format_distribution)={total_formats} ≠ total_disks={self.total_disks}"
            )

        # Проверка использования дисков
        if self.disks_capacity_gb > 0:
            calculated_percentage = (self.disks_allocated_gb / self.disks_capacity_gb) * 100
            if abs(self.disks_usage_percentage - calculated_percentage) > 0.1:
                raise ValueError(
                    f"Несоответствие процента использования дисков: "
                    f"calculated={calculated_percentage:.1f}% ≠ "
                    f"disks_usage_percentage={self.disks_usage_percentage:.1f}%"
                )

        # Проверка, что емкость дисков не превышает емкость пула
        if self.disks_capacity_gb > self.pool_capacity_gb:
            raise ValueError(
                f"Емкость дисков ({self.disks_capacity_gb:.2f} GB) превышает емкость пула "
                f"({self.pool_capacity_gb:.2f} GB)"
            )

        # Проверка, что занятое место на дисках не превышает выделенное в пуле
        if self.disks_allocated_gb > self.pool_allocation_gb:
            raise ValueError(
                f"Занятое место на дисках ({self.disks_allocated_gb:.2f} GB) превышает выделенное в пуле "
                f"({self.pool_allocation_gb:.2f} GB)"
            )

        return self

    # Вычисляемые свойства

    @property
    def pool_usage_percentage(self) -> float:
        """Процент использования пула"""
        if self.pool_capacity_gb > 0:
            return round((self.pool_allocation_gb / self.pool_capacity_gb) * 100, 1)
        return 0.0

    @property
    def pool_free_percentage(self) -> float:
        """Процент свободного места в пуле"""
        return round(100.0 - self.pool_usage_percentage, 1)

    @property
    def attached_percentage(self) -> float:
        """Процент подключенных дисков"""
        if self.total_disks > 0:
            return round((self.attached_disks / self.total_disks) * 100, 1)
        return 0.0

    @property
    def detached_percentage(self) -> float:
        """Процент отключенных дисков"""
        if self.total_disks > 0:
            return round((self.detached_disks / self.total_disks) * 100, 1)
        return 0.0

    @property
    def is_healthy(self) -> bool:
        """Проверка здоровья пула"""
        return self.pool_state in [PoolState.RUNNING, PoolState.BUILDING]

    @property
    def is_degraded(self) -> bool:
        """Проверка деградации пула"""
        return self.pool_state == PoolState.DEGRADED

    @property
    def is_inaccessible(self) -> bool:
        """Проверка недоступности пула"""
        return self.pool_state == PoolState.INACCESSIBLE

    # Методы для работы с форматами

    def get_format_count(self, format_name: str) -> int:
        """Получить количество дисков определенного формата"""
        return self.format_distribution.get(format_name, 0)

    def get_format_percentage(self, format_name: str) -> float:
        """Получить процент дисков определенного формата"""
        if self.total_disks > 0:
            count = self.get_format_count(format_name)
            return round((count / self.total_disks) * 100, 1)
        return 0.0

    def get_top_formats(self, limit: int = 3) -> list[tuple[str, int, float]]:
        """Получить топ-N форматов по количеству дисков"""
        sorted_formats = sorted(
            self.format_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

        result = []
        for format_name, count in sorted_formats:
            percentage = self.get_format_percentage(format_name)
            result.append((format_name, count, percentage))

        return result

    # Методы для сериализации

    def to_dict(self) -> dict:
        """Преобразовать в словарь (обратная совместимость)"""
        return {
            'pool_name': self.pool_name,
            'pool_state': self.pool_state.value,
            'pool_capacity_gb': self.pool_capacity_gb,
            'pool_allocation_gb': self.pool_allocation_gb,
            'pool_available_gb': self.pool_available_gb,
            'total_disks': self.total_disks,
            'attached_disks': self.attached_disks,
            'detached_disks': self.detached_disks,
            'format_distribution': self.format_distribution,
            'disks_capacity_gb': self.disks_capacity_gb,
            'disks_allocated_gb': self.disks_allocated_gb,
            'disks_usage_percentage': self.disks_usage_percentage,
            # Добавляем вычисляемые поля
            'pool_usage_percentage': self.pool_usage_percentage,
            'pool_free_percentage': self.pool_free_percentage,
            'attached_percentage': self.attached_percentage,
            'detached_percentage': self.detached_percentage,
            'is_healthy': self.is_healthy,
            'is_degraded': self.is_degraded,
            'is_inaccessible': self.is_inaccessible
        }

    def summary(self) -> dict:
        """Краткая сводка по пулу"""
        top_formats = self.get_top_formats(3)

        return {
            'name': self.pool_name,
            'state': self.pool_state.value,
            'health': {
                'is_healthy': self.is_healthy,
                'is_degraded': self.is_degraded,
                'is_inaccessible': self.is_inaccessible
            },
            'capacity': {
                'total_gb': self.pool_capacity_gb,
                'allocated_gb': self.pool_allocation_gb,
                'available_gb': self.pool_available_gb,
                'usage_percentage': self.pool_usage_percentage,
                'free_percentage': self.pool_free_percentage
            },
            'disks': {
                'total': self.total_disks,
                'attached': self.attached_disks,
                'detached': self.detached_disks,
                'attached_percentage': self.attached_percentage,
                'detached_percentage': self.detached_percentage,
                'capacity_gb': self.disks_capacity_gb,
                'allocated_gb': self.disks_allocated_gb,
                'usage_percentage': self.disks_usage_percentage
            },
            'top_formats': [
                {
                    'format': name,
                    'count': count,
                    'percentage': percentage
                }
                for name, count, percentage in top_formats
            ]
        }
