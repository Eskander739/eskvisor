import os
from pathlib import Path

from agent.client.pycgroup.cgroup_cli import (
    CLICGroup,
)


class PidController:
    def __init__(self):
        self.cli = CLICGroup()
        self.system_cgroup_path = os.environ.get("SYSTEM_CGROUP")
        self.system_vm_pid_path = os.environ.get("SYSTEM_VM_PID_PATH")

    def vm_pid(self, name: str) -> int | None:
        vm_pid_path = Path(self.system_vm_pid_path) / f"{name}.pid"
        result = vm_pid_path.read_text(encoding="utf-8")
        if not result:
            return None
        return int(result.split("\n")[0])

    def validate_path(self, cgroup_path: str) -> str | None:
        if self.system_cgroup_path not in cgroup_path:
            cgroup_path = f"{self.system_cgroup_path}/{cgroup_path}"
        if not Path(cgroup_path).is_dir():
            raise ValueError("Отсутствует директория в системе")
        return cgroup_path

    def get_vm_names_resource_pool(self, cgroup_pool: str) -> dict[str, int] | None:
        pids = self.get_pids_from_pool(cgroup_pool)
        if pids is None:
            return None
        cmd_arg = "ls -d /run/libvirt/qemu/*.pid"
        vm_with_pids = {}
        resource_pool_vm_with_pids = {}
        pids_from_vm_pid_path = self.cli.execute(
            cmd_arg, shell=True, is_text=True
        ).split("\n")
        pids_from_vm_pid_path.remove(f"{self.system_vm_pid_path}/driver.pid")
        pids_from_vm_pid_path.remove("")
        for vm in pids_from_vm_pid_path:
            vm_pid_path = Path(vm)
            vm_current_pid = int(vm_pid_path.read_text(encoding="utf-8"))
            vm_name = vm.replace(f"{self.system_vm_pid_path}/", "").replace(".pid", "")
            vm_with_pids[vm_name] = vm_current_pid

        for vm_name, vm_current_pid in vm_with_pids.items():
            if vm_current_pid in pids:
                resource_pool_vm_with_pids[vm_name] = vm_current_pid
        return resource_pool_vm_with_pids

    def get_pids_from_pool(self, cgroup_pool: str) -> list[int] | None:
        cgroup_pool = self.validate_path(cgroup_pool)
        cgroup_pool = Path(cgroup_pool) / "cgroup.procs"
        result = cgroup_pool.read_text(encoding="utf-8")
        if result:
            return [int(pid) for pid in result.split("\n") if pid]
        else:
            return None

    def add_pid_to_pool(self, cgroup_pool: str, pid: int) -> str:
        if not isinstance(pid, int):
            raise ValueError("PID может быть только числом")
        self.validate_path(cgroup_pool)
        cgroup_pool = Path(cgroup_pool) / "cgroup.procs"
        cgroup_pool.write_text(str(pid))
        result = cgroup_pool.read_text(encoding="utf-8")
        return result

    def delete_pid_from_pool(self, cgroup_pool: str, pid: int) -> str:
        if not isinstance(pid, int):
            raise ValueError(f"PID может быть только числом, pid: {type(pid)}")
        self.validate_path(cgroup_pool)
        cgroup_pool = Path(cgroup_pool) / "cgroup.procs"
        system_pool = Path(self.system_cgroup_path) / "cgroup.procs"
        system_pool.write_text(str(pid))
        result = cgroup_pool.read_text(encoding="utf-8")
        return result

    def delete_all_pid_from_pool(self, cgroup_pool: str) -> str:
        self.validate_path(cgroup_pool)
        cgroup_pool = f"{cgroup_pool}/cgroup.procs"
        cgroup_pool = Path(cgroup_pool)
        cgroup_system_procs = Path(self.system_cgroup_path) / "cgroup.procs"
        cgroup_system_procs.write_text(cgroup_pool.read_text(encoding="utf-8"))
        result = cgroup_pool.read_text(encoding="utf-8")
        return result


if __name__ == "__main__":
    pid_ctl = PidController()
    vm_pid = pid_ctl.vm_pid("VM-TEST-91553")
    # print("Основной PID: ", vm_pid)
    # print(pid_ctl.add_pid_to_pool("/sys/fs/cgroup/resource_pool_123", vm_pid))
    # print(pid_ctl.add_pid_to_pool(Path("/sys/fs/cgroup/RP-TEST-45678"), pid_ctl.vm_pid("2d676b1f-0119-4cc9-8e9e-1faf838810b0")))
    # print(pid_ctl.delete_pid_from_pool("/sys/fs/cgroup/resource_pool_123", pid_ctl.vm_pid("2d676b1f-0119-4cc9-8e9e-1faf838810b0")))
    print(pid_ctl.delete_all_pid_from_pool("/sys/fs/cgroup/resource_pool_678"))
    # print(pid_ctl.vm_pid("2d676b1f-0119-4cc9-8e9e-1faf838810b0"))
    # 8cc94005-2766-4609-98b2-7f07ba652a1d
    # print(pid_ctl.get_vm_names_resource_pool("/sys/fs/cgroup/resource_pool_123"))
    # print(pid_ctl.get_pids_from_pool("/sys/fs/cgroup/resource_pool_123"))
