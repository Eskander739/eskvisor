from pathlib import Path


class MemortController:

    @staticmethod
    def set_memory_max(cgroup_pool: Path | str, memory_max: int | None = None):
        cgroup_pool = cgroup_pool / "memory.max"
        if memory_max is None:
            cgroup_pool.write_text("max")
        else:
            cgroup_pool.write_text(f"{memory_max}K")  # в килобайтах
        return cgroup_pool.read_text()

    @staticmethod
    def set_memory_reservation(
        cgroup_pool: Path | str, memory_reservation: int | None = None
    ):
        # гарантированный минимум
        cgroup_pool = cgroup_pool / "memory.min"
        if memory_reservation is None:
            cgroup_pool.write_text("0")
        else:
            cgroup_pool.write_text(f"{memory_reservation}K")  # в килобайтах
        return cgroup_pool.read_text()

    @staticmethod
    def set_memory_soft_limit(cgroup_pool: Path | str, memory_soft: int | None = None):
        # мягкий лимит
        cgroup_pool = cgroup_pool / "memory.high"
        if memory_soft is None:
            cgroup_pool.write_text("0")
        else:
            cgroup_pool.write_text(f"{memory_soft}K")  # в килобайтах
        return cgroup_pool.read_text()

    @staticmethod
    def set_memory_low_limit(cgroup_pool: Path | str, memory_low: int | None = None):
        # порог для защиты от давления
        cgroup_pool = cgroup_pool / "memory.low"
        if memory_low is None:
            cgroup_pool.write_text("0")
        else:
            cgroup_pool.write_text(f"{memory_low}K")  # в килобайтах
        return cgroup_pool.read_text()
