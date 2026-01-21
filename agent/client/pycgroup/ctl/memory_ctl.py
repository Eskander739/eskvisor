from pathlib import Path


class MemortController:
    """
    В память информацию записываем в килобайтах, а получаем в байтах
    """

    @staticmethod
    def get_memory_max(cgroup_pool: str) -> int | str:
        memory_max = Path(cgroup_pool) / "memory.max"
        memory_max_info = memory_max.read_text(encoding="utf-8")
        memory_max_value = memory_max_info.split(" ")[0].replace("\n", "")
        return (
            "max"
            if memory_max_value == "max"
            else int(memory_max_info.replace("K", ""))
        )

    @staticmethod
    def get_memory_reservation(cgroup_pool: str):
        memory_reservation = Path(cgroup_pool) / "memory.min"
        memory_reservation_info = memory_reservation.read_text(encoding="utf-8")
        return int(memory_reservation_info.replace("K", ""))

    @staticmethod
    def get_memory_allocated(cgroup_pool: str) -> int:
        cgroup_pool = Path(cgroup_pool) / "memory.current"
        memory_allocated = cgroup_pool.read_text(encoding="utf-8")
        return int(memory_allocated)

    def get_memory_available(self, cgroup_pool: str):

        memory_max = self.get_memory_max(cgroup_pool)
        if memory_max == "max":
            return memory_max
        return memory_max - self.get_memory_allocated(cgroup_pool)

    @staticmethod
    def set_memory_max(cgroup_pool: str, memory_max: int | None = None):

        cgroup_pool = Path(cgroup_pool) / "memory.max"
        if memory_max is None:
            return "max"
        else:
            cgroup_pool.write_text(f"{memory_max}K")  # в килобайтах
        return cgroup_pool.read_text(encoding="utf-8")

    @staticmethod
    def set_memory_reservation(cgroup_pool: str, memory_reservation: int | None = None):
        # гарантированный минимум
        cgroup_pool = Path(cgroup_pool) / "memory.min"
        if memory_reservation is None:
            return "0"
        else:
            cgroup_pool.write_text(f"{memory_reservation}K")
        return cgroup_pool.read_text(encoding="utf-8")

    @staticmethod
    def set_memory_soft_limit(cgroup_pool: str, memory_soft: int | None = None):
        # мягкий лимит

        cgroup_pool = Path(cgroup_pool) / "memory.high"
        if memory_soft is None:
            cgroup_pool.write_text("0")
        else:
            cgroup_pool.write_text(f"{memory_soft}K")
        return cgroup_pool.read_text(encoding="utf-8")

    @staticmethod
    def set_memory_low_limit(cgroup_pool: str, memory_low: int | None = None):
        # порог для защиты от давления
        cgroup_pool = Path(cgroup_pool) / "memory.low"
        if memory_low is None:
            cgroup_pool.write_text("0")
        else:
            cgroup_pool.write_text(f"{memory_low}K")  # в килобайтах
        return cgroup_pool.read_text(encoding="utf-8")


if __name__ == "__main__":
    cpu_ctl = MemortController()
    # print(cpu_ctl.set_memory_max("/sys/fs/cgroup/resource_pool_123", 4194304))
    # print(cpu_ctl.get_memory_max("/sys/fs/cgroup/resource_pool_87023"))
    print(cpu_ctl.get_memory_allocated("/sys/fs/cgroup/resource_pool_87023"))
    # print(cpu_ctl.get_memory_available("/sys/fs/cgroup/resource_pool_87023"))
