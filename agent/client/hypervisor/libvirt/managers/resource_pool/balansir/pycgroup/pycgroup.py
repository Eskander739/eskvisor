import os
from pathlib import Path

from dotenv import load_dotenv

from agent.client.hypervisor.libvirt.managers.resource_pool.balansir.pycgroup.cgroup_cli import (
    CLICGroup,
)
from agent.client.hypervisor.libvirt.managers.resource_pool.balansir.pycgroup.ctl.cpu_ctl import (
    CPUController,
)
from agent.client.hypervisor.libvirt.managers.resource_pool.balansir.pycgroup.ctl.io_ctl import (
    IoController,
)
from agent.client.hypervisor.libvirt.managers.resource_pool.balansir.pycgroup.ctl.memory_ctl import (
    MemortController,
)
from agent.client.hypervisor.libvirt.managers.resource_pool.balansir.pycgroup.ctl.pid_ctl import (
    PidController,
)

load_dotenv()


class PyCGroup:
    """
    pool - ресурс пул
    contaienr - виртуальная машина

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
        cgroup_path = Path(self.system_cgroup_path) / pool_name / container_name
        if is_created:
            if not cgroup_path.exists():
                raise FileNotFoundError(f"{cgroup_path} контейнер не найден")
            if not cgroup_path.is_dir():
                raise ValueError(f"{cgroup_path} не является директорией")

        return cgroup_path

    def create_cgroup_container(
        self,
        pool_name: str,
        container_name: str,
        max_memory: int | None = None,
        cpu_core_limit: int = None,
        memory_reservation: int | None = None,
    ):
        cgroup_path = self.cgroup_container_path(pool_name, container_name, False)
        cgroup_path.mkdir()

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

    def edit_cgroup_container(
        self,
        pool_name: str,
        container_name: str,
        max_memory: int | None = None,
        cpu_core_limit: int = None,
        memory_reservation: int | None = None,
    ):
        cgroup_path = self.cgroup_container_path(pool_name, container_name, True)

        if max_memory is not None:
            mem_max_result = self.memory_ctl.set_memory_max(cgroup_path, max_memory)
            if self.byte_to_kb(mem_max_result) != max_memory:
                raise ValueError(
                    f"Установлено некорректное значение: '{mem_max_result}'"
                )

        if cpu_core_limit is not None:
            core_max_result = self.cpu_ctl.set_cpu_cores(cgroup_path, cpu_core_limit)
            if core_max_result != cpu_core_limit:
                raise ValueError(
                    f"Установлено некорректное значение: '{cpu_core_limit}'"
                )

        if memory_reservation is not None:
            mem_reserv_result = self.memory_ctl.set_memory_reservation(
                cgroup_path, memory_reservation
            )
            if self.byte_to_kb(mem_reserv_result) != memory_reservation:
                raise ValueError(
                    f"Установлено некорректное значение memory_reservation: '{memory_reservation}'"
                )

    def delete_cgroup_container(self, pool_name: str, container_name: str):
        cgroup_path = self.cgroup_container_path(pool_name, container_name, False)
        cgroup_path.rmdir()
        if cgroup_path.exists():
            raise ValueError(f"Контейнер {str(cgroup_path)} не был удален")

    # ______________Пул методы______________
    def cgroup_pool_path(self, name: str, is_created: bool = True):
        cgroup_path = Path(self.system_cgroup_path) / name
        if is_created:
            if not cgroup_path.exists():
                raise FileNotFoundError(f"{cgroup_path} пул не найден")
            if not cgroup_path.is_dir():
                raise ValueError(f"{cgroup_path} не является директорией")

        return cgroup_path

    def create_cgroup_pool(
        self,
        name: str,
        max_memory: int,
        cpu_core_limit: int,
        memory_reservation: int | None = None,
    ):
        cgroup_path = self.cgroup_pool_path(name, False)
        cgroup_path.mkdir()

        mem_max_result = self.memory_ctl.set_memory_max(cgroup_path, max_memory)
        if self.byte_to_kb(mem_max_result) != max_memory:
            raise ValueError(
                f"Установлено некорректное значение max_memory: '{mem_max_result}'"
            )

        core_max_result = self.cpu_ctl.set_cpu_cores(cgroup_path, cpu_core_limit)

        if core_max_result != cpu_core_limit:
            raise ValueError(
                f"Установлено некорректное значение cpu_core_limit: '{cpu_core_limit}'"
            )

        if memory_reservation is not None:
            mem_reserv_result = self.memory_ctl.set_memory_reservation(
                cgroup_path, memory_reservation
            )
            if self.byte_to_kb(mem_reserv_result) != memory_reservation:
                raise ValueError(
                    f"Установлено некорректное значение memory_reservation: '{memory_reservation}'"
                )

    def edit_cgroup_pool(
        self,
        name: str,
        max_memory: int | None = None,
        cpu_core_limit: int | None = None,
        memory_reservation: int | None = None,
    ):
        cgroup_path = self.cgroup_pool_path(name, True)

        if max_memory is not None:
            mem_max_result = self.memory_ctl.set_memory_max(cgroup_path, max_memory)
            if self.byte_to_kb(mem_max_result) != max_memory:
                raise ValueError(
                    f"Установлено некорректное значение max_memory: '{mem_max_result}'"
                )

        if cpu_core_limit is not None:
            core_max_result = self.cpu_ctl.set_cpu_cores(cgroup_path, cpu_core_limit)
            if core_max_result != cpu_core_limit:
                raise ValueError(
                    f"Установлено некорректное значение cpu_core_limit: '{cpu_core_limit}'"
                )

        if memory_reservation is not None:
            mem_reserv_result = self.memory_ctl.set_memory_reservation(
                cgroup_path, memory_reservation
            )
            if self.byte_to_kb(mem_reserv_result) != memory_reservation:
                raise ValueError(
                    f"Установлено некорректное значение memory_reservation: '{memory_reservation}'"
                )

    def delete_cgroup_pool(self, name: str):
        cgroup_path = self.cgroup_pool_path(name, False)
        cgroup_path.rmdir()
        if cgroup_path.exists():
            raise ValueError(f"Пул {str(cgroup_path)} не был удален")


if __name__ == "__main__":
    pycgroup = PyCGroup()
    # pycgroup.create_cgroup_pool("test", 45)
    pycgroup.edit_cgroup_pool("test", cpu_core_limit=2)
