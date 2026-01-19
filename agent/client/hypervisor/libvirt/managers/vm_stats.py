import os
import subprocess
import time
from datetime import datetime
from collections import deque
import signal
import sys

from agent.client.hypervisor.libvirt.models.vm_stats.stats import (
    MemoryStat,
    VMStats,
    CpuStat,
    MemoryUsageStat,
    CpuAndRamUsage,
)
from agent.client.logger_config import DefaultLogger


class VMLiveMonitor:
    def __init__(self, vm_name: str, interval_seconds=2):
        self.logger = DefaultLogger("VMLiveMonitor")
        self.connection_uri = os.environ.get("CONNECTION_URI")
        self.vm_name = vm_name  # можно передавать и UUID ВМ
        self.interval = interval_seconds
        self.running = True
        self.history_size = 60  # Храним 60 последних измерений
        self.cpu_history = deque(maxlen=self.history_size)
        self.memory_history = deque(maxlen=self.history_size)

        # Предыдущие значения для расчета CPU %
        self.prev_cpu_time = 0
        self.prev_timestamp = None

    def parse_virsh_output(self, output):
        """Парсинг вывода virsh domstats"""
        stats = {}

        for line in output.strip().split("\n"):
            if "=" in line:
                # Убираем префикс 'Domain: ' если есть
                line = line.replace("Domain: '{}' ".format(self.vm_name), "")

                key, value = line.split("=", 1)

                # Конвертируем значения
                if value.isdigit():
                    stats[key.strip()] = int(value)
                elif value.replace(".", "").isdigit():
                    stats[key.strip()] = float(value)
                elif value.lower() in ["yes", "no"]:
                    stats[key.strip()] = value.lower() == "yes"
                else:
                    stats[key.strip()] = value

        return stats

    def get_vm_stats(self):
        """Получение статистики ВМ"""
        try:
            cmd = ["virsh", "-c", self.connection_uri, "domstats", self.vm_name]
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=5
            )
            return self.parse_virsh_output(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error getting stats: {e.stderr}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

    def calculate_cpu_usage(self, stats):
        """Расчет использования CPU в процентах"""
        if not stats or "cpu.time" not in stats:
            return 0

        current_cpu_time = stats["cpu.time"]
        current_timestamp = time.time()

        if self.prev_cpu_time == 0:
            self.prev_cpu_time = current_cpu_time
            self.prev_timestamp = current_timestamp
            return 0

        # Разница во времени
        time_diff_ns = current_cpu_time - self.prev_cpu_time
        real_time_diff_seconds = current_timestamp - self.prev_timestamp

        if real_time_diff_seconds <= 0:
            return 0

        # Количество активных vCPU
        vcpu_count = stats.get("vcpu.current", 1)

        # Максимально возможное время CPU за период
        max_possible_ns = vcpu_count * real_time_diff_seconds * 1e9

        if max_possible_ns <= 0:
            return 0

        # Процент использования
        cpu_percent = (time_diff_ns / max_possible_ns) * 100

        # Обновляем предыдущие значения
        self.prev_cpu_time = current_cpu_time
        self.prev_timestamp = current_timestamp

        return min(cpu_percent, 100.0)

    def calculate_memory_usage(self, stats):
        """Расчет использования памяти"""
        if not stats:
            return {}

        # Значения в килобайтах
        current_kb = stats.get("balloon.current", 0)
        maximum_kb = stats.get("balloon.maximum", 0)
        rss_kb = stats.get("balloon.rss", 0)

        # Конвертация в мегабайты
        current_mb = current_kb / 1024
        maximum_mb = maximum_kb / 1024
        rss_mb = rss_kb / 1024

        # Расчет процентов
        usage_percent = (current_mb / maximum_mb) * 100 if maximum_mb > 0 else 0
        rss_percent = (rss_mb / current_mb) * 100 if current_mb > 0 else 0

        memory_usage_info = MemoryUsageStat(
            current_mb=current_mb,
            maximum_mb=maximum_mb,
            rss_mb=rss_mb,
            usage_percent=usage_percent,
            rss_percent=rss_percent,
            available_mb=maximum_mb - current_mb,
            free_mb=current_mb - rss_mb,
        )
        return memory_usage_info

    def monitor_loop(self):
        """Основной цикл мониторинга"""
        print(f"Starting live monitoring of VM: {self.vm_name}")
        print(f"Interval: {self.interval} seconds")
        print("-" * 80)

        header_printed = False

        while self.running:
            try:
                stats = self.get_vm_stats()

                if not stats:
                    time.sleep(self.interval)
                    continue

                # Расчет метрик
                cpu_percent = self.calculate_cpu_usage(stats)
                memory_usage = self.calculate_memory_usage(stats)

                # Сохраняем в историю
                timestamp = datetime.now()
                self.cpu_history.append(
                    {
                        "timestamp": timestamp,
                        "cpu_percent": cpu_percent,
                        "vcpu_current": stats.get("vcpu.current", 0),
                        "vcpu_maximum": stats.get("vcpu.maximum", 0),
                    }
                )

                self.memory_history.append(
                    {"timestamp": timestamp, **memory_usage.model_dump()}
                )

                # Вывод текущих значений
                if not header_printed:
                    print(
                        f"{'Time':<20} {'CPU %':<10} {'RAM Used':<12} {'RAM RSS':<12} {'RAM %':<8} {'vCPU':<8}"
                    )
                    print("-" * 80)
                    header_printed = True

                current_time = timestamp.strftime("%H:%M:%S")
                cpu_str = f"{cpu_percent:.3f}%"
                ram_used_str = f"{memory_usage.current_mb:.1f}MB"
                ram_rss_str = f"{memory_usage.rss_mb:.3f}MB"
                ram_percent_str = f"{memory_usage.usage_percent:.1f}%"
                vcpu_str = (
                    f"{stats.get('vcpu.current', 0)}/{stats.get('vcpu.maximum', 0)}"
                )

                print(
                    f"{current_time:<20} {cpu_str:<10} {ram_used_str:<12} {ram_rss_str:<12} {ram_percent_str:<8} {vcpu_str:<8}"
                )

                time.sleep(self.interval)

            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                print(f"Error in monitor loop: {e}")
                time.sleep(self.interval)

    def stop(self):
        """Остановка мониторинга"""
        self.running = False

    def get_statistics(self):
        """Получение агрегированной статистики"""
        if not self.cpu_history:
            return None

        # Правильный расчет статистик
        cpu_values = [entry["cpu_percent"] for entry in self.cpu_history]
        vcpu_values = [entry["vcpu_current"] for entry in self.cpu_history]

        memory_current_values = [entry["current_mb"] for entry in self.memory_history]
        memory_rss_values = [entry["rss_mb"] for entry in self.memory_history]
        memory_percent_values = [
            entry["usage_percent"] for entry in self.memory_history
        ]

        return VMStats(
            cpu=CpuStat(
                avg=sum(cpu_values) / len(cpu_values) if cpu_values else 0,
                min=min(cpu_values) if cpu_values else 0,
                max=max(cpu_values) if cpu_values else 0,
                current=cpu_values[-1] if cpu_values else 0,
                vcpu_avg=sum(vcpu_values) / len(vcpu_values) if vcpu_values else 0,
            ),
            memory=MemoryStat(
                current_mb_avg=(
                    sum(memory_current_values) / len(memory_current_values)
                    if memory_current_values
                    else 0
                ),
                current_mb_max=(
                    max(memory_current_values) if memory_current_values else 0
                ),
                rss_mb_avg=(
                    sum(memory_rss_values) / len(memory_rss_values)
                    if memory_rss_values
                    else 0
                ),
                usage_percent_avg=(
                    sum(memory_percent_values) / len(memory_percent_values)
                    if memory_percent_values
                    else 0
                ),
                current=memory_current_values[-1] if memory_current_values else 0,
                rss=memory_rss_values[-1] if memory_rss_values else 0,
                percent=memory_percent_values[-1] if memory_percent_values else 0,
            ),
            samples=len(self.cpu_history),
        )

    def used_ram_and_cpu(self) -> CpuAndRamUsage | None:
        """Получение текущего использования CPU и RAM"""
        self.logger.info(
            "Получение статистики об используемом RAM, количестве ядер, нагрузке CPU"
        )

        # Первое измерение для установки базовых значений
        stats1 = self.get_vm_stats()
        if not stats1:
            self.logger.warning(
                f"Не удалось получить статистику для ВМ: {self.vm_name}"
            )
            return None

        # Ждем для расчета CPU %
        time.sleep(self.interval)  # Используем заданный интервал

        # Второе измерение
        stats2 = self.get_vm_stats()
        if not stats2:
            self.logger.warning("Не удалось получить второе измерение")
            return None

        # Расчет CPU % между двумя измерениями
        cpu_percent = self._calculate_cpu_usage_between(stats1, stats2)

        # Расчет памяти по последнему измерению
        memory_usage = self.calculate_memory_usage(stats2)

        data = CpuAndRamUsage(
            memory=memory_usage.rss_mb,
            cpu_core_count=stats2.get("vcpu.current", 1),
            cpu_usage_percent=cpu_percent,
        )

        self.logger.info(
            f"Статистика: RAM={data.memory:.3f}MB, "
            f"CPU Cores={data.cpu_core_count}, "
            f"CPU Usage={data.cpu_usage_percent:.3f}%"
        )
        return data

    def _calculate_cpu_usage_between(self, stats1, stats2):
        """Расчет CPU % между двумя измерениями"""
        if "cpu.time" not in stats1 or "cpu.time" not in stats2:
            return 0

        time_diff_ns = stats2["cpu.time"] - stats1["cpu.time"]
        vcpu_count = stats2.get("vcpu.current", 1)

        # Предполагаем, что между вызовами прошло self.interval секунд
        max_possible_ns = vcpu_count * self.interval * 1e9

        if max_possible_ns <= 0:
            return 0

        return min((time_diff_ns / max_possible_ns) * 100, 100.0)


def signal_handler(sig, frame):
    print("\nStopping monitor...")
    sys.exit(0)


if __name__ == "__main__":
    vm_name = "VM-TEST-32314"
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    # Обработка Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    # Запуск мониторинга
    monitor = VMLiveMonitor("94df5b49-2da4-44d6-8fe1-9f910b775402", interval)
    # for _ in range(10):
    #     data = monitor.used_ram_and_cpu()
    monitor.monitor_loop()
    # cpu_percent = monitor.calculate_cpu_usage(stats)
    # memory_usage = monitor.calculate_memory_usage(stats)
    # print(cpu_percent)
    # print(memory_usage)

    # try:
    #     monitor.monitor_loop()
    # except KeyboardInterrupt:
    #     monitor.stop()
    #     print("\nMonitoring stopped.")
    #
    #     # Вывод статистики
    #     stats = monitor.get_statistics()
    #     if stats:
    #         print("\n" + "=" * 80)
    #         print("SUMMARY STATISTICS:")
    #         print("=" * 80)
    #         print(
    #             f"CPU Usage: {stats['cpu']['current']:.1f}% (avg: {stats['cpu']['avg']:.1f}%, min: {stats['cpu']['min']:.1f}%, max: {stats['cpu']['max']:.1f}%)")
    #         print(f"Memory Usage: {stats['memory']['current']:.1f}MB (avg: {stats['memory']['current_mb_avg']:.1f}MB)")
    #         print(f"Memory RSS: {stats['memory']['rss']:.1f}MB (avg: {stats['memory']['rss_mb_avg']:.1f}MB)")
    #         print(
    #             f"Memory Usage %: {stats['memory']['percent']:.1f}% (avg: {stats['memory']['usage_percent_avg']:.1f}%)")
    #         print(f"Samples collected: {stats['samples']}")
