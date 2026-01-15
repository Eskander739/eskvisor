import os

from dotenv import load_dotenv

from agent.client.hypervisor.pycgroup.cgroup_cli import (
    CLICGroup,
)
from agent.client.hypervisor.pycgroup.ctl.cpu_ctl import (
    CPUController,
)
from agent.client.hypervisor.pycgroup.ctl.io_ctl import (
    IoController,
)
from agent.client.hypervisor.pycgroup.ctl.memory_ctl import (
    MemortController,
)
from agent.client.hypervisor.pycgroup.ctl.pid_ctl import (
    PidController,
)

load_dotenv()


class PYCGroup:
    """
    pool - ресурс пул
    container - виртуальная машина

    в pool ставим ограничения на весь ресурс пул
    в container ставим ограничения на конкретную виртуальную машину

    Вы не можете поставить в дочернем container больше чем разрешено в родительском pool.
    Это ключевой принцип иерархии cgroup v2.
    """

    def __init__(self):
        self.cli = CLICGroup()
        self.system_cgroup_path = os.environ.get("SYSTEM_CGROUP")
        self.cpu_ctl = CPUController()
        self.io_ctrl = IoController()
        self.memory_ctl = MemortController()
        self.pid_ctl = PidController()

    @staticmethod
    def byte_to_mb(byte: int) -> int:
        if isinstance(byte, str):
            byte = int(byte)
        return int(byte / 1024 / 1024)

    @staticmethod
    def byte_to_kb(byte: int) -> int:
        if isinstance(byte, str):
            byte = int(byte)
        return int(byte / 1024)

    @staticmethod
    def kb_to_byte(kb) -> int:
        if isinstance(kb, str):
            kb = int(kb)
        return kb * 1024

    # ______________Контейнер методы______________
    def cgroup_container_path(
        self, pool_name: str, container_name: str, is_created: bool = True
    ):
        cgroup_path = f"{self.system_cgroup_path}/{pool_name}/{container_name}"
        if is_created:
            if not self.cli.is_exists(str(cgroup_path)):
                raise FileNotFoundError(f"{cgroup_path} пул не найден")
            if not self.cli.is_directory(str(cgroup_path)):
                raise ValueError(f"{cgroup_path} не является директорией")
        else:
            if self.cli.is_exists(str(cgroup_path)):
                raise ValueError(f"{cgroup_path} пул уже создан")

        return cgroup_path

    def add_pid_to_container(self, pool_name: str, container_name: str, pid: int) -> str:
        cgroup_path = self.cgroup_container_path(pool_name, container_name)
        is_current_pids = self.pid_ctl.get_pids_from_pool(cgroup_path)
        if is_current_pids:
            raise ValueError("Нельзя добавлять в контейнер больше 1 PID")
        result = self.pid_ctl.add_pid_to_pool(cgroup_path, pid)
        return result

    def delete_pid_from_container(self, pool_name: str, container_name: str) -> str:
        cgroup_path = self.cgroup_container_path(pool_name, container_name)
        vm_pid = self.pid_ctl.get_pids_from_pool(cgroup_path).pop()
        result = self.pid_ctl.delete_pid_from_pool(cgroup_path, vm_pid)
        return result

    def create_cgroup_container(
        self,
        pool_name: str,
        container_name: str,
        max_memory: int | None = None,
        cpu_core_limit: int = None,
        memory_reservation: int | None = None,
    ):
        cgroup_path = self.cgroup_container_path(pool_name, container_name, False)
        self.cli.mkdir(cgroup_path)

        mem_max_result = self.memory_ctl.set_memory_max(cgroup_path, max_memory)
        if self.byte_to_kb(mem_max_result) != max_memory:
            raise ValueError(f"Установлено некорректное значение: '{mem_max_result}'")

        core_max_result = self.cpu_ctl.set_cpu_cores(cgroup_path, cpu_core_limit)

        if core_max_result != cpu_core_limit:
            raise ValueError(f"Установлено некорректное значение: '{cpu_core_limit}'")

        if memory_reservation is not None:
            mem_reserv_result = self.memory_ctl.set_memory_reservation(
                cgroup_path, memory_reservation
            )
            if self.byte_to_kb(mem_reserv_result) != memory_reservation:
                raise ValueError(
                    f"Установлено некорректное значение memory_reservation: '{memory_reservation}'"
                )

    def get_cgroup_container(self,  pool_name: str, container_name: str) -> dict[str, tuple]:
        cgroup_path = self.cgroup_container_path(pool_name, container_name)

        cpu = self.cpu_ctl.get_cpu_cores(cgroup_path)
        cpu_percent = self.cpu_ctl.get_cpu_percent(cgroup_path)
        cpu_allocated = self.cpu_ctl.get_cpu_usage_cores(cgroup_path)
        cpu_available = self.cpu_ctl.get_cpu_available_cores(cgroup_path)
        cpu_weight = self.cpu_ctl.get_cpu_weight(cgroup_path)

        ram_max = self.byte_to_mb(self.memory_ctl.get_memory_max(cgroup_path))
        ram_allocated = self.byte_to_mb(self.memory_ctl.get_memory_allocated(cgroup_path))
        ram_available = self.byte_to_mb(self.memory_ctl.get_memory_available(cgroup_path))
        ram_reservation = self.byte_to_mb(self.memory_ctl.get_memory_reservation(cgroup_path))

        pids = self.pid_ctl.get_pids_from_pool(cgroup_path)
        pid = [int(pid) for pid in pids if pid.isdigit()]
        pid = int(pid.pop()) if pid else pid
        container = {"cpu": (cpu, cpu_percent, cpu_allocated, cpu_available, cpu_weight),
                     "ram": (ram_max, ram_available, ram_allocated, ram_reservation), "pid": pid}

        return container

    def edit_cgroup_container(
        self,
        pool_name: str,
        container_name: str,
        max_memory: int | None = None,
        cpu_core_limit: int = None,
        memory_reservation: int | None = None,
        cpu_weight: int | None = None,
    ):
        cgroup_path = self.cgroup_container_path(pool_name, container_name)

        if max_memory is not None:
            mem_max_result = self.memory_ctl.set_memory_max(cgroup_path, max_memory)
            if self.byte_to_kb(mem_max_result) != max_memory:
                raise ValueError(
                    f"Установлено некорректное значение: '{mem_max_result}', ожидаемое значение: '{max_memory}'"
                )

        if cpu_core_limit is not None:
            core_max_result = self.cpu_ctl.set_cpu_cores(cgroup_path, cpu_core_limit)
            if core_max_result != cpu_core_limit:
                raise ValueError(
                    f"Установлено некорректное значение: '{core_max_result}', ожидаемое значение: '{cpu_core_limit}'"
                )

        if memory_reservation is not None:
            mem_reserv_result = self.memory_ctl.set_memory_reservation(
                cgroup_path, memory_reservation
            )
            if self.byte_to_kb(mem_reserv_result) != memory_reservation:
                raise ValueError(
                    f"Установлено некорректное значение memory_reservation: '{mem_reserv_result}', ожидаемое значение: '{memory_reservation}'"
                )

        if cpu_weight is not None:
            current_cpu_weight = self.cpu_ctl.set_cpu_weight(
                cgroup_path, cpu_weight
            )
            if current_cpu_weight != cpu_weight:
                raise ValueError(
                    f"Установлено некорректное значение current_cpu_weight: '{memory_reservation}', ожидаемое значение: '{cpu_weight}'"
                )

    def delete_cgroup_container(self, pool_name: str, container_name: str):
        cgroup_path = self.cgroup_container_path(pool_name, container_name, False)
        self.delete_pid_from_container(container_name)
        self.cli.rmdir(cgroup_path)
        if self.cli.is_exists(cgroup_path):
            raise ValueError(f"Контейнер {str(cgroup_path)} не был удален")

    # ______________Пул методы______________
    def cgroup_pool_path(self, name: str, is_created: bool = True):
        if self.system_cgroup_path in name:
            cgroup_path = name
        else:
            cgroup_path = f"{self.system_cgroup_path}/{name}"
        if is_created:
            if not self.cli.is_exists(cgroup_path):
                raise FileNotFoundError(f"{cgroup_path} пул не найден")
            if not self.cli.is_directory(cgroup_path):
                raise ValueError(f"{cgroup_path} не является директорией")
        else:
            if self.cli.is_exists(str(cgroup_path)):
                raise ValueError(f"{cgroup_path} пул уже создан")

        return cgroup_path

    @property
    def get_cgroup_pool_names(self):
        cmd_arg = f"ls -d {self.system_cgroup_path}/resource_pool*"
        all_cgroup = self.cli.execute(cmd_arg, shell=True, is_text=True)
        ru_err = "Нет такого файла или каталога"
        eng_err = "No such file or directory"
        cgroup_list = [pool.replace(f"{self.system_cgroup_path}/", "") for pool in all_cgroup.split("\n") if pool]
        if len(cgroup_list) == 1:
            if ru_err in cgroup_list[0] or eng_err in cgroup_list[0]:
                return []
        return cgroup_list

    def get_cgroup_pools(self):
        cgroup_info_list = []
        for cgroup_path in self.get_cgroup_pool_names:
            cgroup_info_list.append(self.get_cgroup_pool(cgroup_path))
        return cgroup_info_list

    def get_cgroup_pool(self,  pool_name: str) -> dict[str, tuple]:
        cgroup_path = self.cgroup_pool_path(pool_name)

        cpu = self.cpu_ctl.get_cpu_cores(cgroup_path)
        cpu_percent = self.cpu_ctl.get_cpu_percent(cgroup_path)
        cpu_allocated = self.cpu_ctl.get_cpu_usage_cores(cgroup_path)
        cpu_available = self.cpu_ctl.get_cpu_available_cores(cgroup_path)
        cpu_weight = self.cpu_ctl.get_cpu_weight(cgroup_path)

        ram_max = self.memory_ctl.get_memory_max(cgroup_path)
        ram_available = self.memory_ctl.get_memory_available(cgroup_path)

        ram_max = ram_max if ram_max != "max" else ram_max
        ram_allocated = self.memory_ctl.get_memory_allocated(cgroup_path)
        ram_available = ram_available if ram_available != "max" else ram_available
        ram_reservation = self.memory_ctl.get_memory_reservation(cgroup_path)

        pids = self.pid_ctl.get_pids_from_pool(cgroup_path)
        pids = [int(pid) for pid in pids if pid] if pids else pids

        name = cgroup_path.replace(self.system_cgroup_path + "/", "")
        pool = {"name": name,
                     "path": cgroup_path,
                     "cpu": (cpu, cpu_percent, cpu_allocated, cpu_available, cpu_weight),
                     "ram": (ram_max, ram_available, ram_allocated, ram_reservation),
                     "pids": pids}

        return pool

    def add_pid_to_pool(self, pool_name: str, pid: int) -> str:
        cgroup_path = self.cgroup_pool_path(pool_name)
        result = self.pid_ctl.add_pid_to_pool(cgroup_path, pid)
        return result

    def delete_pid_from_pool(self, pool_name: str, pid: int) -> str:
        cgroup_path = self.cgroup_pool_path(pool_name)
        result = self.pid_ctl.delete_pid_from_pool(cgroup_path, pid)
        return result

    def delete_pids_list_from_pool(self, pool_name: str, pids: list[int]) -> list[int]:
        cgroup_path = self.cgroup_pool_path(pool_name)
        for pid in pids:
            self.pid_ctl.delete_pid_from_pool(cgroup_path, pid)
        return self.pid_ctl.get_pids_from_pool(pool_name)

    def delete_all_pid_from_pool(self, pool_name: str) -> str:
        cgroup_path = self.cgroup_pool_path(pool_name)
        result = self.pid_ctl.delete_all_pid_from_pool(cgroup_path)
        return result

    def delete_vm_from_pool(self, pool_name: str, vm_name: str) -> str:
        cgroup_path = self.cgroup_pool_path(pool_name)
        vm_pid = self.pid_ctl.vm_pid(vm_name)
        result = self.pid_ctl.delete_pid_from_pool(cgroup_path, vm_pid)
        return result

    def create_cgroup_pool(
        self,
        name: str,
        max_memory: int | None = None,
        cpu_core_limit: int | None = None,
        memory_reservation: int | None = None,
        vms: list[str] | None = None,
    ):
        cgroup_path = self.cgroup_pool_path(name, False)
        self.cli.mkdir(cgroup_path)

        mem_max_result = self.memory_ctl.set_memory_max(cgroup_path, max_memory)
        if max_memory is not None:
            if self.byte_to_kb(mem_max_result) != max_memory:
                raise ValueError(
                    f"Установлено некорректное значение max_memory: '{mem_max_result}'"
                )

        core_max_result = self.cpu_ctl.set_cpu_cores(cgroup_path, cpu_core_limit)
        if cpu_core_limit is not None:
            if core_max_result != cpu_core_limit:
                raise ValueError(
                    f"Установлено некорректное значение cpu_core_limit: '{cpu_core_limit}'"
                )
        if memory_reservation is not None:
            if memory_reservation is not None:
                mem_reserv_result = self.memory_ctl.set_memory_reservation(
                    cgroup_path, memory_reservation
                )
                if self.byte_to_kb(mem_reserv_result) != memory_reservation:
                    raise ValueError(
                        f"Установлено некорректное значение memory_reservation: '{memory_reservation}'"
                    )
        if vms is not None:
            self.add_vms_to_pool(cgroup_path, vms)


    def add_vms_to_pool(self, cgroup_path: str, vms: list[str]):
        cgroup_path = self.cgroup_pool_path(cgroup_path)
        add_vm_pids = []
        if vms is not None:
            for vm_name in vms:
                vm_pid = self.pid_ctl.vm_pid(vm_name)
                add_vm_pids.append(vm_pid)
                self.add_pid_to_pool(cgroup_path, vm_pid)

            pids = self.pid_ctl.get_pids_from_pool(cgroup_path)
            if pids is None:
                raise ValueError("Добавление PID в пул завершилось с ошибкой")
            for added_vm_pid in add_vm_pids:
                if added_vm_pid not in pids:
                    raise ValueError(f"Добавление PID '{added_vm_pid}' в пул завершилось с ошибкой")



    def edit_cgroup_pool(
        self,
        name: str,
        max_memory: int | None = None, # килобайты
        cpu_core_limit: int | None = None,
        memory_reservation: int | None = None,
        cpu_weight: int | None = None,
    ):
        cgroup_path = self.cgroup_pool_path(name)

        if max_memory is not None:
            mem_max_result = self.memory_ctl.set_memory_max(cgroup_path, max_memory)
            new_limit_kb = self.byte_to_kb(mem_max_result)
            if max_memory != new_limit_kb:
                raise ValueError(
                    f"Установлено некорректное значение max_memory: '{new_limit_kb}', ожидаемое значение: '{max_memory}'"
                )

        if cpu_core_limit is not None:
            core_max_result = self.cpu_ctl.set_cpu_cores(cgroup_path, cpu_core_limit)
            if core_max_result != cpu_core_limit:
                raise ValueError(
                    f"Установлено некорректное значение cpu_core_limit: '{cpu_core_limit}', ожидаемое значение: '{cpu_core_limit}'"
                )

        if memory_reservation is not None:
            mem_reserv_result = self.memory_ctl.set_memory_reservation(
                cgroup_path, memory_reservation
            )
            if self.byte_to_kb(mem_reserv_result) != memory_reservation:
                raise ValueError(
                    f"Установлено некорректное значение memory_reservation: '{memory_reservation}', ожидаемое значение: '{memory_reservation}'"
                )

        if cpu_weight is not None:
            current_cpu_weight = self.cpu_ctl.set_cpu_weight(
                cgroup_path, cpu_weight
            )
            if current_cpu_weight != cpu_weight:
                raise ValueError(
                    f"Установлено некорректное значение current_cpu_weight: '{memory_reservation}', ожидаемое значение: '{cpu_weight}'"
                )

    def delete_cgroup_pool(self, name: str, force: bool = False):
        cgroup_path = self.cgroup_pool_path(name)

        result = self.cli.rmdir(cgroup_path)
        ru_err = "Устройство или ресурс занято"
        eng_err = "Device or resource busy"
        if ru_err in result or eng_err in result:
            if not force:
                raise ValueError("В пуле присутствуют процессы, используйте force для удаления")

            pid_list = self.pid_ctl.get_pids_from_pool(cgroup_path)
            for current_pid in pid_list:
                self.pid_ctl.delete_pid_from_pool(cgroup_path, current_pid)

            result = self.cli.rmdir(cgroup_path)
        if self.cli.is_exists(cgroup_path):
            raise ValueError(f"Пул {str(cgroup_path)} не был удален: {result}")


if __name__ == "__main__":
    pycgroup = PYCGroup()
    # pycgroup.create_cgroup_pool("test", 45)
    # pycgroup.edit_cgroup_pool("test", cpu_core_limit=2)
    print(pycgroup.delete_cgroup_pool("resource_pool_123", force=True))
    # print(pycgroup.get_cgroup_pools())
