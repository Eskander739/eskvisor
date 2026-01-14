import time

from agent.client.hypervisor.pycgroup.cgroup_cli import CLICGroup


class CPUController:
    def __init__(self):
        self.cli = CLICGroup()

    @staticmethod
    def current_period_us(cgroup_pool: str) -> int:
        cpu_max_file = f"{cgroup_pool}/cpu.max"
        return int(cpu_max_file.read_text().strip().split(" ").pop())

    def set_cpu_percent(self,
        cgroup_pool: str,
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

        cpu_max_file = f"{cgroup_pool}/cpu.max"

        if cpu_percent is None:
            # Снимаем ограничение
            self.cli.write_text(cpu_max_file, f"max {period_us}")
        else:
            # Конвертируем проценты в микросекунды
            max_us = int(cpu_percent * period_us / 100)

            # Проверяем корректность значения
            if max_us < 1:
                max_us = 1  # Минимальное значение = 1 µs
            elif max_us > 2**63 - 1:  # Максимальное для int64
                raise ValueError(f"Слишком большое значение CPU: {cpu_percent}%")

            self.cli.write_text(cpu_max_file, f"{max_us} {period_us}")

        # Возвращаем установленное значение
        return self.cli.read_text(cpu_max_file).strip()

    def set_cpu_cores(
        self,
        cgroup_pool: str,
        cpu_cores: float | None = None,
        period_us: int = 100000,
    ) -> float | str:
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
            return "max"

        # Конвертируем ядра в проценты (1 ядро = 100%)
        cpu_percent = cpu_cores * 100
        max_cpu_time, period_us_local = self.set_cpu_percent(
            cgroup_pool, cpu_percent, period_us
        ).split(" ")
        return self.cpu_max_to_cores(max_cpu_time, int(period_us_local))

    def get_cpu_percent(self, cgroup_pool: str) -> float | str:
        """
        Получает текущий лимит CPU в процентах

        Returns:
            Если ограничений нет - возвращает "max"
            Иначе - процент CPU (float)
        """
        cpu_max_file = f"{cgroup_pool}/cpu.max"

        if not self.cli.is_exists(cpu_max_file):
            raise FileNotFoundError(f"Файл не найден: {cpu_max_file}")

        value = self.cli.read_text(cpu_max_file).strip()

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

    def get_cpu_cores(self, cgroup_pool: str) -> float | str:
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

    @staticmethod
    def cpu_max_to_cores(max_us: int | str, period_us: int = 100000) -> float | str:
        """
        Конвертирует максимальное время CPU и период в количество ядер
        """
        if max_us == "max" or max_us is None:
            return "max"
        return int(max_us) / period_us

    @staticmethod
    def cores_to_cpu_percent(cores: float) -> float:
        """
        Конвертирует количество ядер в проценты CPU
        """
        return cores * 100.0

    def _read_cpu_stat(self, cgroup_pool: str) -> str | int | dict:
        """
        Читает статистику CPU из cpu.stat
        """
        cpu_stat_file = f"{cgroup_pool}/cpu.stat"

        if not self.cli.is_exists(cpu_stat_file):
            return {}

        stats = {}
        try:
            with open(cpu_stat_file, 'r') as f:
                for line in f:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            stats[parts[0]] = int(parts[1])
        except Exception:
            return {}

        return stats

    def get_cpu_limit_cores(self, cgroup_pool: str) -> float | str:
        """
        Получает максимальный лимит CPU в ядрах (сколько МОЖНО использовать)

        Args:
            cgroup_pool: путь к cgroup

        Returns:
            Максимальный лимит в ядрах (float) или "max" если без ограничений
        """
        cpu_max_file = f"{cgroup_pool}/cpu.max"
        value = None
        if not self.cli.is_exists(cpu_max_file):
            raise FileNotFoundError(f"Файл не найден: {cpu_max_file}")

        try:
            value = self.cli.read_text(cpu_max_file).strip()

            if value.startswith("max"):
                return "max"

            max_us_str, period_us_str = value.split()
            max_us = int(max_us_str)
            period_us = int(period_us_str)

            return self.cpu_max_to_cores(max_us, period_us)
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Некорректный формат в {cpu_max_file}: {value}") from e

    def get_cpu_usage_cores(self, cgroup_pool: str, window_seconds: float = 1.0) -> float:
        """
        Получает текущее использование CPU в ядрах (allocated - сколько УЖЕ используется)

        Args:
            cgroup_pool: путь к cgroup
            window_seconds: временное окно для вычисления скорости использования

        Returns:
            Использование CPU в ядрах (float)

        Examples:
            Используется 1 ядро полностью -> 1.0
            Используется 0.5 ядра -> 0.5
            Не используется -> 0.0
        """
        # Получаем текущее использование из cpu.stat
        stats = self._read_cpu_stat(cgroup_pool)
        usage_usec = stats.get('usage_usec', 0)

        # usage_usec - это общее накопленное использование в микросекундах
        # Для получения текущей скорости использования нам нужно измерить за период времени

        # Сохраняем текущее состояние
        current_time = time.time()
        current_usage = usage_usec

        # Если у нас есть предыдущие измерения, вычисляем скорость
        if hasattr(self, '_prev_measurement'):
            prev_time, prev_usage = self._prev_measurement.get(str(cgroup_pool), (0, 0))

            if prev_time > 0 and current_time > prev_time:
                # Вычисляем использование за прошедшее время
                time_diff = current_time - prev_time
                usage_diff = current_usage - prev_usage

                if time_diff > 0:
                    # Конвертируем микросекунды в ядра:
                    # usage_diff (µs) / 1_000_000 = секунды CPU
                    # делим на time_diff (секунды реального времени) = ядра
                    usage_cores = (usage_diff / 1_000_000) / time_diff

                    # Ограничиваем окно измерений
                    if time_diff > window_seconds * 2:
                        # Слишком большой разрыв, используем непосредственное измерение
                        usage_cores = self._get_instant_usage(cgroup_pool, window_seconds)

                    # Сохраняем текущее измерение для следующего вызова
                    self._prev_measurement[str(cgroup_pool)] = (current_time, current_usage)
                    return round(max(0.0, usage_cores), 3)

        # Если это первый вызов или измерения недоступны
        usage_cores = self._get_instant_usage(cgroup_pool, window_seconds)

        # Инициализируем сохранение измерений
        if not hasattr(self, '_prev_measurement'):
            self._prev_measurement = {}
        self._prev_measurement[str(cgroup_pool)] = (current_time, current_usage)

        return round(usage_cores, 3)

    def _get_instant_usage(self, cgroup_pool: str, window_seconds: float = 1.0) -> float:
        """
        Измеряет мгновенное использование CPU за указанный период
        """
        # Делаем два измерения с интервалом
        stats1 = self._read_cpu_stat(cgroup_pool)
        usage1 = stats1.get('usage_usec', 0)

        time.sleep(min(window_seconds, 0.5))  # Ждем немного

        stats2 = self._read_cpu_stat(cgroup_pool)
        usage2 = stats2.get('usage_usec', 0)

        # Использование за прошедшее время
        # (предполагаем, что sleep был примерно window_seconds)
        usage_diff = usage2 - usage1

        # Конвертируем в ядра
        usage_cores = (usage_diff / 1_000_000) / window_seconds

        return max(0.0, usage_cores)

    def get_cpu_available_cores(self, cgroup_pool: str) -> float | str | None:
        """
        Получает доступное количество ядер CPU (сколько ещё МОЖНО использовать)

        Args:
            cgroup_pool: путь к cgroup

        Returns:
            Доступное количество ядер (float), "max" или None если ошибка

        Formula:
            available = limit - current_usage
        """
        try:
            # Получаем лимит
            limit = self.get_cpu_limit_cores(cgroup_pool)

            # Получаем текущее использование
            usage = self.get_cpu_usage_cores(cgroup_pool)

            if limit == "max":
                # Без ограничений
                return "max"

            # Вычисляем доступное
            available = max(0.0, limit - usage)
            return round(available, 3)

        except Exception as e:
            print(f"Ошибка при вычислении available CPU: {e}")
            return None

    def get_cpu_usage_percent(self, cgroup_pool: str) -> float | str:
        """
        Получает использование CPU в процентах от лимита

        Args:
            cgroup_pool: путь к cgroup

        Returns:
            Использование в процентах (float) или "max" если без ограничений
        """
        limit = self.get_cpu_limit_cores(cgroup_pool)
        usage = self.get_cpu_usage_cores(cgroup_pool)

        if limit == "max":
            return "max"

        if limit == 0:
            return float('inf') if usage > 0 else 0.0

        usage_percent = (usage / limit) * 100
        return round(min(usage_percent, 100.0), 1)

    def get_cpu_throttling_info(self, cgroup_pool: str) -> dict:
        """
        Получает информацию о throttling CPU
        """
        stats = self._read_cpu_stat(cgroup_pool)

        total_usage = stats.get('usage_usec', 0)
        throttled_usec = stats.get('throttled_usec', 0)
        nr_throttled = stats.get('nr_throttled', 0)
        nr_periods = stats.get('nr_periods', 0)

        # Процент времени под throttling
        throttling_percent = 0.0
        if total_usage > 0:
            throttling_percent = (throttled_usec / total_usage) * 100

        # Процент периодов с throttling
        throttled_periods_percent = 0.0
        if nr_periods > 0:
            throttled_periods_percent = (nr_throttled / nr_periods) * 100

        return {
            'throttled_usec': throttled_usec,
            'nr_throttled': nr_throttled,
            'nr_periods': nr_periods,
            'throttling_percent': round(throttling_percent, 2),
            'throttled_periods_percent': round(throttled_periods_percent, 2),
            'total_usage_usec': total_usage
        }

    def get_cpu_summary(self, cgroup_pool: str) -> dict:
        """
        Получает полную сводку по CPU для cgroup
        """
        return {
            'max_limit_cores': self.get_cpu_limit_cores(cgroup_pool),  # сколько МОЖНО использовать
            'allocated_cores': self.get_cpu_usage_cores(cgroup_pool),  # сколько УЖЕ используется
            'available_cores': self.get_cpu_available_cores(cgroup_pool),  # сколько ещё МОЖНО использовать
            'usage_percent': self.get_cpu_usage_percent(cgroup_pool),  # использование в % от лимита
            'throttling': self.get_cpu_throttling_info(cgroup_pool)  # информация о throttling
        }

    # === УТИЛИТАРНЫЕ МЕТОДЫ ДЛЯ ВЫВОДА ===

    def print_cpu_info(self, cgroup_pool: str):
        """
        Выводит информацию о CPU в удобном формате
        """
        summary = self.get_cpu_summary(cgroup_pool)

        print(f"CPU Info for {cgroup_pool}:")
        print(f"  Max limit:      {summary['max_limit_cores']} cores")
        print(f"  Allocated:      {summary['allocated_cores']} cores (currently used)")
        print(f"  Available:      {summary['available_cores']} cores (can still use)")
        print(f"  Usage:          {summary['usage_percent']}% of limit")

        throttling = summary['throttling']
        if throttling['nr_throttled'] > 0:
            print(f"  Throttling:     {throttling['throttling_percent']}% of time")
            print(f"  Throttled for:  {throttling['throttled_usec'] / 1_000_000:.2f}s total")

if __name__ == "__main__":
    cpu_ctl = CPUController()
    print(cpu_ctl.set_cpu_cores("/sys/fs/cgroup/resource_pool_123", 3))
    print(cpu_ctl.print_cpu_info("/sys/fs/cgroup/resource_pool_123"))
