from pathlib import Path

from agent.client.logger_config import DefaultLogger


class CGroupsManager:
    """
    Класс для управления CPU и RAM ресурсами через CGroups

    Реализует управление лимитами CPU и памяти для пулов ресурсов
    через механизм CGroups Linux.
    """

    def __init__(self):
        self.cgroup_root = Path("/home/eska/cgroup")
        self.cgroup_version = self._detect_cgroup_version()
        self.logger = DefaultLogger()

    def _detect_cgroup_version(self) -> str:
        """Определяет версию CGroups системы"""
        if (self.cgroup_root / "cgroup.controllers").exists():
            return "v2"
        return "v1"

    def create_pool_cgroup(self, pool_name: str) -> bool:
        """
        Создает cgroup для пула ресурсов

        Args:
            pool_name: Имя пула ресурсов

        Returns:
            bool: Успешность операции
        """
        try:
            cgroup_path = self._get_cgroup_path(pool_name)

            if self.cgroup_version == "v2":
                # Создаем директорию cgroup
                cgroup_path.mkdir(parents=True, exist_ok=True)

                # Включаем необходимые контроллеры
                controllers_file = cgroup_path / "cgroup.controllers"
                if controllers_file.exists():
                    controllers = controllers_file.read_text().strip().split()
                    for controller in ["cpu", "memory"]:
                        if controller in controllers:
                            subtree_control = cgroup_path / "cgroup.subtree_control"
                            subtree_control.write_text(f"+{controller}")

                    if self.logger:
                        self.logger.debug(
                            f"Создан cgroup v2 для пула {pool_name}: {cgroup_path}"
                        )
                    return True
            else:
                # Для CGroups v1 создаем в каждой подсистеме
                for subsystem in ["cpu", "cpuacct", "memory"]:
                    subsystem_path = self.cgroup_root / subsystem / pool_name
                    subsystem_path.mkdir(parents=True, exist_ok=True)

                if self.logger:
                    self.logger.debug(f"Создан cgroup v1 для пула {pool_name}")
                return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Ошибка создания cgroup для пула {pool_name}: {e}")
            return False

    def delete_pool_cgroup(self, pool_name: str) -> bool:
        """
        Удаляет cgroup пула ресурсов

        Args:
            pool_name: Имя пула ресурсов

        Returns:
            bool: Успешность операции
        """
        try:
            cgroup_path = self._get_cgroup_path(pool_name)

            if cgroup_path.exists():
                # Удаляем директорию cgroup
                import shutil

                shutil.rmtree(cgroup_path)

                if self.logger:
                    self.logger.debug(
                        f"Удален cgroup для пула {pool_name}: {cgroup_path}"
                    )
                return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Ошибка удаления cgroup для пула {pool_name}: {e}")
            return False

    def set_cpu_limit(self, pool_name: str, cpu_cores: float) -> bool:
        """
        Устанавливает лимит CPU для пула

        Args:
            pool_name: Имя пула ресурсов
            cpu_cores: Количество ядер CPU (например, 2.5)

        Returns:
            bool: Успешность операции
        """
        try:
            # Конвертируем ядра в микросекунды для CGroups
            # Формула: quota = cores * period (обычно period = 100000 мкс)
            period_us = 100000
            quota_us = int(cpu_cores * period_us)

            if self.cgroup_version == "v2":
                cgroup_path = self._get_cgroup_path(pool_name)
                cpu_max_file = cgroup_path / "cpu.max"
                cpu_max_file.write_text(f"{quota_us} {period_us}")

                if self.logger:
                    self.logger.debug(
                        f"Установлен лимит CPU для пула {pool_name}: {cpu_cores} ядер"
                    )
                return True
            else:
                # Для CGroups v1
                cpu_path = self.cgroup_root / "cpu" / pool_name
                (cpu_path / "cpu.cfs_quota_us").write_text(str(quota_us))
                (cpu_path / "cpu.cfs_period_us").write_text(str(period_us))

                if self.logger:
                    self.logger.debug(
                        f"Установлен лимит CPU для пула {pool_name}: {cpu_cores} ядер (v1)"
                    )
                return True

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Ошибка установки лимита CPU для пула {pool_name}: {e}"
                )
            return False

    def set_cpu_shares(self, pool_name: str, shares: int) -> bool:
        """
        Устанавливает вес CPU (shares) для пула

        Args:
            pool_name: Имя пула ресурсов
            shares: Вес CPU (1024 = нормальный вес)

        Returns:
            bool: Успешность операции
        """
        try:
            if self.cgroup_version == "v2":
                cgroup_path = self._get_cgroup_path(pool_name)
                cpu_weight_file = cgroup_path / "cpu.weight"
                # В v2 weight от 1 до 10000, 100 = нормальный вес
                weight = max(1, min(10000, shares * 100 // 1024))
                cpu_weight_file.write_text(str(weight))
            else:
                # Для CGroups v1
                cpu_path = self.cgroup_root / "cpu" / pool_name
                (cpu_path / "cpu.shares").write_text(str(shares))

            if self.logger:
                self.logger.debug(f"Установлен вес CPU для пула {pool_name}: {shares}")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Ошибка установки веса CPU для пула {pool_name}: {e}"
                )
            return False

    def set_memory_limit(self, pool_name: str, memory_mb: int) -> bool:
        """
        Устанавливает лимит памяти для пула

        Args:
            pool_name: Имя пула ресурсов
            memory_mb: Лимит памяти в мегабайтах

        Returns:
            bool: Успешность операции
        """
        try:
            memory_bytes = memory_mb * 1024 * 1024

            if self.cgroup_version == "v2":
                cgroup_path = self._get_cgroup_path(pool_name)
                memory_max_file = cgroup_path / "memory.max"
                memory_max_file.write_text(str(memory_bytes))
            else:
                # Для CGroups v1
                memory_path = self.cgroup_root / "memory" / pool_name
                (memory_path / "memory.limit_in_bytes").write_text(str(memory_bytes))

            if self.logger:
                self.logger.debug(
                    f"Установлен лимит памяти для пула {pool_name}: {memory_mb} MB"
                )
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Ошибка установки лимита памяти для пула {pool_name}: {e}"
                )
            return False

    def set_memory_reservation(self, pool_name: str, memory_mb: int) -> bool:
        """
        Устанавливает гарантированную память (reservation) для пула

        Args:
            pool_name: Имя пула ресурсов
            memory_mb: Гарантированная память в мегабайтах

        Returns:
            bool: Успешность операции
        """
        try:
            memory_bytes = memory_mb * 1024 * 1024

            if self.cgroup_version == "v2":
                cgroup_path = self._get_cgroup_path(pool_name)
                memory_min_file = cgroup_path / "memory.min"
                memory_min_file.write_text(str(memory_bytes))
            else:
                # Для CGroups v1 - используем memory.soft_limit_in_bytes
                memory_path = self.cgroup_root / "memory" / pool_name
                (memory_path / "memory.soft_limit_in_bytes").write_text(
                    str(memory_bytes)
                )

            if self.logger:
                self.logger.debug(
                    f"Установлена гарантированная память для пула {pool_name}: {memory_mb} MB"
                )
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Ошибка установки гарантированной памяти для пула {pool_name}: {e}"
                )
            return False

    def add_vm_to_cgroup(self, pool_name: str, vm_pid: int) -> bool:
        """
        Добавляет процесс VM в cgroup пула

        Args:
            pool_name: Имя пула ресурсов
            vm_pid: PID процесса VM

        Returns:
            bool: Успешность операции
        """
        try:
            if self.cgroup_version == "v2":
                cgroup_path = self._get_cgroup_path(pool_name)
                procs_file = cgroup_path / "cgroup.procs"
                procs_file.write_text(str(vm_pid))
            else:
                # Для CGroups v1 добавляем во все подсистемы
                for subsystem in ["cpu", "cpuacct", "memory"]:
                    subsystem_path = self.cgroup_root / subsystem / pool_name
                    tasks_file = subsystem_path / "tasks"
                    tasks_file.write_text(str(vm_pid))

            if self.logger:
                self.logger.debug(
                    f"Добавлен процесс {vm_pid} в cgroup пула {pool_name}"
                )
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Ошибка добавления процесса в cgroup пула {pool_name}: {e}"
                )
            return False

    def remove_vm_from_cgroup(self, pool_name: str, vm_pid: int) -> bool:
        """
        Удаляет процесс VM из cgroup пула

        Args:
            pool_name: Имя пула ресурсов
            vm_pid: PID процесса VM

        Returns:
            bool: Успешность операции
        """
        try:
            # Перемещаем процесс в корневой cgroup
            if self.cgroup_version == "v2":
                root_procs = self.cgroup_root / "cgroup.procs"
                root_procs.write_text(str(vm_pid))
            else:
                # Для CGroups v1
                for subsystem in ["cpu", "cpuacct", "memory"]:
                    root_tasks = self.cgroup_root / subsystem / "tasks"
                    root_tasks.write_text(str(vm_pid))

            if self.logger:
                self.logger.debug(f"Удален процесс {vm_pid} из cgroup пула {pool_name}")
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Ошибка удаления процесса из cgroup пула {pool_name}: {e}"
                )
            return False

    def get_cgroup_stats(self, pool_name: str) -> dict[str, object]:
        """
        Получает статистику использования ресурсов из cgroup

        Args:
            pool_name: Имя пула ресурсов

        Returns:
            dict: Статистика использования ресурсов
        """
        stats = {
            "cpu_usage": 0,
            "cpu_usage_seconds": 0,
            "cpu_limit_cores": 0,
            "cpu_limit_period_us": 0,
            "cpu_limit_quota_us": 0,
            "cpu_shares": 1024,
            "memory_usage": 0,
            "memory_limit": 0,
            "memory_reservation": 0,
            "process_count": 0,
        }

        try:
            cgroup_path = self._get_cgroup_path(pool_name)

            if not cgroup_path.exists():
                return stats

            if self.cgroup_version == "v2":
                # CPU usage
                cpu_stat_file = cgroup_path / "cpu.stat"
                if cpu_stat_file.exists():
                    content = cpu_stat_file.read_text()
                    for line in content.splitlines():
                        if line.startswith("usage_usec"):
                            usage_usec = int(line.split()[1])
                            stats["cpu_usage"] = usage_usec
                            stats["cpu_usage_seconds"] = (
                                usage_usec / 1000000
                            )  # Конвертируем в секунды

                # CPU limits
                cpu_max_file = cgroup_path / "cpu.max"
                if cpu_max_file.exists():
                    cpu_max_content = cpu_max_file.read_text().strip()
                    if cpu_max_content != "max":
                        quota_str, period_str = cpu_max_content.split()
                        quota_us = int(quota_str)
                        period_us = int(period_str)
                        stats["cpu_limit_quota_us"] = quota_us
                        stats["cpu_limit_period_us"] = period_us
                        if quota_us > 0 and period_us > 0:
                            stats["cpu_limit_cores"] = quota_us / period_us

                # CPU shares (weight in v2)
                cpu_weight_file = cgroup_path / "cpu.weight"
                if cpu_weight_file.exists():
                    weight_str = cpu_weight_file.read_text().strip()
                    if weight_str.isdigit():
                        weight = int(weight_str)
                        # Конвертируем weight обратно в shares (100 = 1024 shares)
                        stats["cpu_shares"] = (
                            weight * 1024 // 100 if weight > 0 else 1024
                        )

                # Memory usage
                memory_current_file = cgroup_path / "memory.current"
                if memory_current_file.exists():
                    stats["memory_usage"] = int(memory_current_file.read_text().strip())

                # Memory limit
                memory_max_file = cgroup_path / "memory.max"
                if memory_max_file.exists():
                    limit = memory_max_file.read_text().strip()
                    if limit != "max":
                        stats["memory_limit"] = int(limit)

                # Memory reservation
                memory_min_file = cgroup_path / "memory.min"
                if memory_min_file.exists():
                    min_limit = memory_min_file.read_text().strip()
                    if min_limit != "0":
                        stats["memory_reservation"] = int(min_limit)

                # Process count
                procs_file = cgroup_path / "cgroup.procs"
                if procs_file.exists():
                    content = procs_file.read_text().strip()
                    stats["process_count"] = len(content.splitlines()) if content else 0

            else:
                # Для CGroups v1
                # CPU usage
                cpuacct_path = self.cgroup_root / "cpuacct" / pool_name
                cpuacct_usage_file = cpuacct_path / "cpuacct.usage"
                if cpuacct_usage_file.exists():
                    usage_nsec = int(cpuacct_usage_file.read_text().strip())
                    stats["cpu_usage"] = (
                        usage_nsec / 1000
                    )  # Конвертируем в микросекунды
                    stats["cpu_usage_seconds"] = (
                        usage_nsec / 1000000000
                    )  # Наносекунды в секунды

                # CPU limits
                cpu_path = self.cgroup_root / "cpu" / pool_name

                # CPU quota and period
                cpu_quota_file = cpu_path / "cpu.cfs_quota_us"
                cpu_period_file = cpu_path / "cpu.cfs_period_us"
                if cpu_quota_file.exists() and cpu_period_file.exists():
                    quota_str = cpu_quota_file.read_text().strip()
                    period_str = cpu_period_file.read_text().strip()
                    if quota_str.isdigit() and period_str.isdigit():
                        quota_us = int(quota_str)
                        period_us = int(period_str)
                        stats["cpu_limit_quota_us"] = quota_us
                        stats["cpu_limit_period_us"] = period_us
                        if quota_us > 0 and period_us > 0:
                            stats["cpu_limit_cores"] = quota_us / period_us

                # CPU shares
                cpu_shares_file = cpu_path / "cpu.shares"
                if cpu_shares_file.exists():
                    shares_str = cpu_shares_file.read_text().strip()
                    if shares_str.isdigit():
                        stats["cpu_shares"] = int(shares_str)

                # Memory usage
                memory_path = self.cgroup_root / "memory" / pool_name
                memory_usage_file = memory_path / "memory.usage_in_bytes"
                if memory_usage_file.exists():
                    stats["memory_usage"] = int(memory_usage_file.read_text().strip())

                # Memory limit
                memory_limit_file = memory_path / "memory.limit_in_bytes"
                if memory_limit_file.exists():
                    limit = memory_limit_file.read_text().strip()
                    if limit != "-1":
                        stats["memory_limit"] = int(limit)

                # Memory reservation (soft limit)
                memory_soft_limit_file = memory_path / "memory.soft_limit_in_bytes"
                if memory_soft_limit_file.exists():
                    soft_limit = memory_soft_limit_file.read_text().strip()
                    if soft_limit != "0":
                        stats["memory_reservation"] = int(soft_limit)

                # Process count
                tasks_file = memory_path / "tasks"
                if tasks_file.exists():
                    content = tasks_file.read_text().strip()
                    stats["process_count"] = len(content.splitlines()) if content else 0

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Ошибка получения статистики cgroup для пула {pool_name}: {e}"
                )

        return stats

    def get_cpu_limit_info(self, pool_name: str) -> dict[str, object]:
        """
        Получает информацию о лимитах CPU для пула

        Args:
            pool_name: Имя пула ресурсов

        Returns:
            dict: Информация о лимитах CPU
        """
        try:
            cgroup_path = self._get_cgroup_path(pool_name)

            if not cgroup_path.exists():
                return {
                    "cpu_limit_cores": 0,
                    "cpu_limit_period_us": 0,
                    "cpu_limit_quota_us": 0,
                }

            if self.cgroup_version == "v2":
                cpu_max_file = cgroup_path / "cpu.max"
                if cpu_max_file.exists():
                    cpu_max_content = cpu_max_file.read_text().strip()
                    if cpu_max_content == "max":
                        return {
                            "cpu_limit_cores": 0,
                            "cpu_limit_period_us": 0,
                            "cpu_limit_quota_us": 0,
                        }

                    quota_str, period_str = cpu_max_content.split()
                    quota_us = int(quota_str)
                    period_us = int(period_str)

                    if quota_us <= 0 or period_us <= 0:
                        return {
                            "cpu_limit_cores": 0,
                            "cpu_limit_period_us": period_us,
                            "cpu_limit_quota_us": quota_us,
                        }

                    cpu_cores = quota_us / period_us
                    return {
                        "cpu_limit_cores": cpu_cores,
                        "cpu_limit_period_us": period_us,
                        "cpu_limit_quota_us": quota_us,
                    }

            else:
                # Для CGroups v1
                cpu_path = self.cgroup_root / "cpu" / pool_name

                if not cpu_path.exists():
                    return {
                        "cpu_limit_cores": 0,
                        "cpu_limit_period_us": 0,
                        "cpu_limit_quota_us": 0,
                    }

                cpu_quota_file = cpu_path / "cpu.cfs_quota_us"
                cpu_period_file = cpu_path / "cpu.cfs_period_us"

                if cpu_quota_file.exists() and cpu_period_file.exists():
                    quota_str = cpu_quota_file.read_text().strip()
                    period_str = cpu_period_file.read_text().strip()

                    if quota_str.isdigit() and period_str.isdigit():
                        quota_us = int(quota_str)
                        period_us = int(period_str)

                        if quota_us <= 0 or period_us <= 0:
                            return {
                                "cpu_limit_cores": 0,
                                "cpu_limit_period_us": period_us,
                                "cpu_limit_quota_us": quota_us,
                            }

                        cpu_cores = quota_us / period_us
                        return {
                            "cpu_limit_cores": cpu_cores,
                            "cpu_limit_period_us": period_us,
                            "cpu_limit_quota_us": quota_us,
                        }

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Ошибка получения информации о лимитах CPU для пула {pool_name}: {e}"
                )

        return {"cpu_limit_cores": 0, "cpu_limit_period_us": 0, "cpu_limit_quota_us": 0}

    def _get_cgroup_path(self, pool_name: str) -> Path:
        """Возвращает путь к cgroup пула"""
        if self.cgroup_version == "v2":
            return self.cgroup_root / "libvirt" / pool_name
        else:
            # Для v1 возвращаем путь к одной из подсистем
            return self.cgroup_root / "cpu" / pool_name

    def get_vm_pid(self, vm_name: str) -> int | None:
        """
        Получает PID процесса VM

        Args:
            vm_name: Имя виртуальной машины

        Returns:
            int | None: PID процесса или None если не найден
        """
        try:
            # Пробуем найти PID через virsh domstats
            import subprocess

            result = subprocess.run(
                ["virsh", "domstats", vm_name], capture_output=True, text=True
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "balloon.maximum=" in line:
                        # Извлекаем PID из вывода
                        parts = line.split()
                        for part in parts:
                            if part.startswith("state.state="):
                                state = int(part.split("=")[1])
                                if state != 1:  # 1 = запущена
                                    return None

                    if "vcpu.0.pid=" in line:
                        pid_str = line.split("=")[1].strip()
                        if pid_str.isdigit():
                            return int(pid_str)

            # Альтернативный метод: ищем в процессах QEMU
            import psutil

            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = proc.info["cmdline"]
                    if cmdline and vm_name in " ".join(cmdline):
                        return proc.info["pid"]
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except Exception as e:
            if self.logger:
                self.logger.error(f"Ошибка получения PID для VM {vm_name}: {e}")

        return None
