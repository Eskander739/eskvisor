import psutil
import time
from datetime import datetime
from pydantic import ValidationError


def wait_while_not(func, timeout=60, interval=2):
    """
    Excecutes func until it returns True or timeout is reached
    :param func: Excecutable function
    :param timeout: Timeout in seconds
    :param interval: Interval between function calls
    :return: result of function if func returned True, False otherwise
    """
    ex = None
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            result = func()
            if result:
                return result
        except ValidationError as ve:
            raise ve
        except Exception as e:
            ex = e
        time.sleep(interval)
    if ex:
        raise ex
    else:
        return False


def get_system_stats():
    """Получение полной статистики системы"""

    stats = {
        "timestamp": datetime.now().isoformat(),
        "cpu": {},
        "memory": {},
        "disk": [],
        "network": {},
        "sensors": {},
        "processes": {},
    }

    # === CPU ===
    # Загрузка CPU в процентах (интервал 1 сек для точности)
    cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
    stats["cpu"] = {
        "percent_total": psutil.cpu_percent(interval=0.1),  # Быстрое получение
        "percent_per_core": cpu_percent,
        "cpu_count": {
            "physical": psutil.cpu_count(logical=False),
            "logical": psutil.cpu_count(logical=True),
        },
        "times": psutil.cpu_times_percent()._asdict(),
        "freq": (
            psutil.cpu_freq()._asdict() if hasattr(psutil.cpu_freq(), "_asdict") else {}
        ),
        "load_avg": psutil.getloadavg() if hasattr(psutil, "getloadavg") else [],
    }

    # === Память ===
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    stats["memory"] = {
        "virtual": {
            "total": mem.total,
            "available": mem.available,
            "percent": mem.percent,
            "used": mem.used,
            "free": mem.free,
            "active": getattr(mem, "active", None),
            "inactive": getattr(mem, "inactive", None),
            "buffers": getattr(mem, "buffers", None),
            "cached": getattr(mem, "cached", None),
            "shared": getattr(mem, "shared", None),
        },
        "swap": {
            "total": swap.total,
            "used": swap.used,
            "free": swap.free,
            "percent": swap.percent,
            "sin": swap.sin,
            "sout": swap.sout,
        },
    }

    # === Диски ===
    disk_stats = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disk_stats.append(
                {
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                }
            )
        except (PermissionError, FileNotFoundError):
            continue

    # IO статистика дисков
    disk_io = psutil.disk_io_counters(perdisk=True)
    for disk_name, io_data in disk_io.items():
        for disk in disk_stats:
            if disk_name in disk["device"]:
                disk["io"] = io_data._asdict()

    stats["disk"] = disk_stats

    # === Сеть ===
    net_io = psutil.net_io_counters(pernic=True)
    net_stats = {}
    for nic, data in net_io.items():
        net_stats[nic] = {
            "bytes_sent": data.bytes_sent,
            "bytes_recv": data.bytes_recv,
            "packets_sent": data.packets_sent,
            "packets_recv": data.packets_recv,
            "errin": data.errin,
            "errout": data.errout,
            "dropin": data.dropin,
            "dropout": data.dropout,
        }

    # Добавляем информацию об интерфейсах
    net_addrs = psutil.net_if_addrs()
    for nic in net_stats:
        net_stats[nic]["addresses"] = []
        if nic in net_addrs:
            for addr in net_addrs[nic]:
                net_stats[nic]["addresses"].append(
                    {
                        "family": str(addr.family),
                        "address": addr.address,
                        "netmask": addr.netmask,
                        "broadcast": addr.broadcast,
                    }
                )

    stats["network"] = net_stats

    # === Датчики ===
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            stats["sensors"]["temperatures"] = temps

        if hasattr(psutil, "sensors_fans"):
            fans = psutil.sensors_fans()
            stats["sensors"]["fans"] = fans

        if hasattr(psutil, "sensors_battery"):
            battery = psutil.sensors_battery()
            if battery:
                stats["sensors"]["battery"] = battery._asdict()
    except Exception:
        pass

    # === Процессы ===
    stats["processes"] = {
        "total": len(psutil.pids()),
        "running": len(
            [
                p
                for p in psutil.process_iter(["status"])
                if p.info["status"] == psutil.STATUS_RUNNING
            ]
        ),
        "zombies": len(
            [
                p
                for p in psutil.process_iter(["status"])
                if p.info["status"] == psutil.STATUS_ZOMBIE
            ]
        ),
    }

    # Топ процессов по CPU и памяти
    top_processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            proc_info = proc.info
            proc_info["cpu_percent"] = proc.cpu_percent(interval=0)
            proc_info["memory_percent"] = proc.memory_percent()
            top_processes.append(proc_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Сортируем по использованию CPU
    top_processes.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
    stats["processes"]["top_by_cpu"] = top_processes[:10]

    # Сортируем по использованию памяти
    top_processes.sort(key=lambda x: x.get("memory_percent", 0), reverse=True)
    stats["processes"]["top_by_memory"] = top_processes[:10]

    return stats


def get_live_monitoring(interval=2, duration=30):
    """Живой мониторинг в реальном времени"""

    end_time = time.time() + duration
    print("Начинаем мониторинг...")
    print("-" * 80)

    while time.time() < end_time:
        stats = get_system_stats()

        # Красивый вывод в консоль
        print(f"\nВремя: {stats['timestamp']}")
        print(
            f"CPU: {stats['cpu']['percent_total']}% | "
            f"Память: {stats['memory']['virtual']['percent']}% | "
            f"Загрузка: {stats['cpu']['load_avg']}"
        )

        # Диски
        for disk in stats["disk"][:3]:  # Показываем первые 3 диска
            print(f"Диск {disk['mountpoint']}: {disk['percent']}%")

        # Топ процесс
        if stats["processes"]["top_by_cpu"]:
            top = stats["processes"]["top_by_cpu"][0]
            print(
                f"Топ процесс: {top['name']} (PID: {top['pid']}) - "
                f"CPU: {top['cpu_percent']:.1f}%, "
                f"Память: {top['memory_percent']:.1f}%"
            )

        print("-" * 80)
        time.sleep(interval)

    return stats


# Быстрое получение конкретных метрик
def get_quick_stats():
    """Быстрые основные метрики"""
    # Получаем загрузку системы
    load_avg = psutil.getloadavg() if hasattr(psutil, "getloadavg") else None

    # Конвертируем load average в проценты
    load_percent = None
    if load_avg and hasattr(psutil, "cpu_count"):
        cpu_count = psutil.cpu_count(logical=True)
        if cpu_count and cpu_count > 0:
            # Используем load за 1 минуту
            load_percent = (load_avg[0] / cpu_count) * 100

    return {
        "cpu": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent,
        "load": load_percent if load_percent is not None else None,
    }


if __name__ == "__main__":
    # Пример использования
    print("Быстрая проверка:")
    quick = get_quick_stats()
    print(f"CPU: {quick['cpu']}%")
    print(f"Память: {quick['memory']}%")
    print(f"Диск /: {quick['disk']}%")

    # # Полная статистика
    # print("\nПолная статистика:")
    # full_stats = get_system_stats()
    #
    # print(json.dumps(full_stats, indent=2, default=str))

    # Живой мониторинг (раскомментировать при необходимости)
    # get_live_monitoring(interval=1, duration=10)
