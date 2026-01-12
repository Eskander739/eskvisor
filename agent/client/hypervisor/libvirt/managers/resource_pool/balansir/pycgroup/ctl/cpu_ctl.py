from pathlib import Path


class CPUController:

    @staticmethod
    def cpu_max_to_cores(max_us: int | str, period_us: int = 100000) -> float | str:
        """
        Конвертирует максимальное время CPU и период в количество ядер

        Args:
            max_us: максимальное время CPU в микросекундах или "max"
            period_us: период в микросекундах (по умолчанию 100000)

        Returns:
            Количество ядер (float) или "max" если без ограничений

        Examples:
            cpu_max_to_cores(100000, 100000) -> 1.0
            cpu_max_to_cores(50000, 100000) -> 0.5
            cpu_max_to_cores(250000, 100000) -> 2.5
            cpu_max_to_cores("max", 100000) -> "max"
        """
        if max_us == "max" or max_us is None:
            return "max"

        # Ядра = (max_us / period_us)
        return int(max_us) / period_us

    @staticmethod
    def cores_to_cpu_percent(cores: float) -> float:
        """
        Конвертирует количество ядер в проценты CPU

        Args:
            cores: количество ядер (1.0 = 1 ядро)

        Returns:
            Проценты CPU

        Examples:
            cores_to_cpu_percent(1.0) -> 100.0
            cores_to_cpu_percent(0.5) -> 50.0
            cores_to_cpu_percent(2.5) -> 250.0
        """
        return cores * 100.0

    @staticmethod
    def set_cpu_percent(
        cgroup_pool: Path | str,
        cpu_percent: float | None = None,
        period_us: int = 100000,
    ) -> str:
        """
        Устанавливает лимит CPU в процентах для cgroup

        Args:
            cgroup_pool: путь к cgroup (директория)
            cpu_percent: процент CPU (100% = 1 ядро, 200% = 2 ядра и т.д.)
                         Если None - снимает ограничение
            period_us: период в микросекундах (по умолчанию 100000 µs = 100ms)

        Returns:
            Строка с установленными значениями (формат: "MAX PERIOD")

        Examples:
            set_cpu_percent("/sys/fs/cgroup/vm1", 50.0)    # 50% CPU = 0.5 ядра
            set_cpu_percent("/sys/fs/cgroup/vm2", 200.0)   # 200% CPU = 2 ядра
            set_cpu_percent("/sys/fs/cgroup/vm3", None)    # снимает ограничение
        """

        cgroup_pool = Path(cgroup_pool)
        cpu_max_file = cgroup_pool / "cpu.max"

        if cpu_percent is None:
            # Снимаем ограничение
            cpu_max_file.write_text(f"max {period_us}")
        else:
            # Конвертируем проценты в микросекунды
            max_us = int(cpu_percent * period_us / 100)

            # Проверяем корректность значения
            if max_us < 1:
                max_us = 1  # Минимальное значение = 1 µs
            elif max_us > 2**63 - 1:  # Максимальное для int64
                raise ValueError(f"Слишком большое значение CPU: {cpu_percent}%")

            cpu_max_file.write_text(f"{max_us} {period_us}")

        # Возвращаем установленное значение
        return cpu_max_file.read_text().strip()

    def set_cpu_cores(
        self,
        cgroup_pool: Path | str,
        cpu_cores: float | None = None,
        period_us: int = 100000,
    ) -> float:
        """
        Устанавливает лимит CPU в количестве ядер

        Args:
            cgroup_pool: путь к cgroup (директория)
            cpu_cores: количество ядер CPU (1.0 = 1 ядро, 0.5 = пол-ядра, 2.5 = 2.5 ядра)
                       Если None - снимает ограничение
            period_us: период в микросекундах

        Returns:
            Строка с установленными значениями
        """
        if cpu_cores is None:
            max_cpu_time, period_us_local = self.set_cpu_percent(
                cgroup_pool, None, period_us
            ).split(" ")
            return self.cpu_max_to_cores(max_cpu_time, int(period_us_local))

        # Конвертируем ядра в проценты (1 ядро = 100%)
        cpu_percent = cpu_cores * 100
        max_cpu_time, period_us_local = self.set_cpu_percent(
            cgroup_pool, cpu_percent, period_us
        ).split(" ")
        return self.cpu_max_to_cores(max_cpu_time, int(period_us_local))

    def get_cpu_percent(self, cgroup_pool: Path | str) -> float | str:
        """
        Получает текущий лимит CPU в процентах

        Returns:
            Если ограничений нет - возвращает "max"
            Иначе - процент CPU (float)
        """
        cgroup_pool = Path(cgroup_pool)
        cpu_max_file = cgroup_pool / "cpu.max"

        if not cpu_max_file.exists():
            raise FileNotFoundError(f"Файл не найден: {cpu_max_file}")

        value = cpu_max_file.read_text().strip()

        if value.startswith("max"):
            return "max"

        try:
            max_us_str, period_us_str = value.split()
            max_us = int(max_us_str)
            period_us = int(period_us_str)

            # Конвертируем обратно в проценты
            return (max_us / period_us) * 100
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Некорректный формат в {cpu_max_file}: {value}") from e

    def get_cpu_cores(self, cgroup_pool: Path | str) -> float | str:
        """
        Получает текущий лимит CPU в количестве ядер

        Returns:
            Если ограничений нет - возвращает "max"
            Иначе - количество ядер (float)
        """
        result = self.get_cpu_percent(cgroup_pool)

        if result == "max":
            return "max"

        # Конвертируем проценты в ядра (100% = 1 ядро)
        return result / 100
