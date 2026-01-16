from agent.client.pycgroup.cgroup_cli import CLICGroup


class MemortController:
    """
    В память информацию записываем в килобайтах, а получаем в байтах
    """

    def __init__(self):
        self.cli = CLICGroup()

    def write_text(self, file_path: str, text: str):
        cmd_args = ["sh", "-c", f"echo {text} > {file_path}"]
        result = self.cli.execute(cmd_args)
        return result

    def read_text(self, file_path: str):
        cmd_args = ["cat", f"{file_path}"]
        result = self.cli.execute(cmd_args)
        return result

    def get_memory_max(self, cgroup_pool: str) -> int | str:
        memory_max = f"{cgroup_pool}/memory.max"
        memory_max_info = self.read_text(memory_max)
        memory_max_value = memory_max_info.split(" ")[0].replace("\n", "")
        return (
            "max"
            if memory_max_value == "max"
            else int(memory_max_info.replace("K", ""))
        )

    def get_memory_reservation(self, cgroup_pool: str):
        memory_reservation = f"{cgroup_pool}/memory.min"
        memory_reservation_info = self.read_text(memory_reservation)
        return int(memory_reservation_info.replace("K", ""))

    def get_memory_allocated(self, cgroup_pool: str) -> int:

        cgroup_pool = f"{cgroup_pool}/memory.current"
        memory_allocated = self.read_text(cgroup_pool)
        return int(memory_allocated)

    def get_memory_available(self, cgroup_pool: str):

        memory_max = self.get_memory_max(cgroup_pool)
        if memory_max == "max":
            return memory_max
        return memory_max - self.get_memory_allocated(cgroup_pool)

    def set_memory_max(self, cgroup_pool: str, memory_max: int | None = None):

        cgroup_pool = f"{cgroup_pool}/memory.max"
        if memory_max is None:
            return "max"
        else:
            self.write_text(cgroup_pool, f"{memory_max}K")  # в килобайтах
        return self.cli.read_text(cgroup_pool)

    def set_memory_reservation(
        self, cgroup_pool: str, memory_reservation: int | None = None
    ):
        # гарантированный минимум
        cgroup_pool = f"{cgroup_pool}/memory.min"
        if memory_reservation is None:
            return "0"
        else:
            self.write_text(cgroup_pool, f"{memory_reservation}K")  # в килобайтах
        return self.cli.read_text(cgroup_pool)

    def set_memory_soft_limit(self, cgroup_pool: str, memory_soft: int | None = None):
        # мягкий лимит

        cgroup_pool = f"{cgroup_pool}/memory.high"
        if memory_soft is None:
            self.write_text(cgroup_pool, "0")
        else:
            self.write_text(cgroup_pool, f"{memory_soft}K")  # в килобайтах
        return self.cli.read_text(cgroup_pool)

    def set_memory_low_limit(self, cgroup_pool: str, memory_low: int | None = None):
        # порог для защиты от давления
        cgroup_pool = f"{cgroup_pool}/memory.low"
        if memory_low is None:
            self.write_text(cgroup_pool, "0")
        else:
            self.write_text(cgroup_pool, f"{memory_low}K")  # в килобайтах
        return self.cli.read_text(cgroup_pool)


if __name__ == "__main__":
    cpu_ctl = MemortController()
    # print(cpu_ctl.set_memory_max("/sys/fs/cgroup/resource_pool_123", 4194304))
    # print(cpu_ctl.get_memory_max("/sys/fs/cgroup/resource_pool_87023"))
    print(cpu_ctl.get_memory_allocated("/sys/fs/cgroup/resource_pool_87023"))
    # print(cpu_ctl.get_memory_available("/sys/fs/cgroup/resource_pool_87023"))
