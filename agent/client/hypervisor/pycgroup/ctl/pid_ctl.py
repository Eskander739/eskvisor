import os

from dotenv import load_dotenv

from agent.client.hypervisor.pycgroup.cgroup_cli import (
    CLICGroup,
)

load_dotenv()

class PidController:
    def __init__(self):
        self.cli = CLICGroup()
        self.system_cgroup_path = os.environ.get("SYSTEM_CGROUP")
        self.system_vm_pid_path = os.environ.get("SYSTEM_VM_PID_PATH")

    def vm_pid(self, name: str) -> int:
        cmd_args = ["cat", f"{self.system_vm_pid_path}/{name}.pid"]
        result = self.cli.execute(cmd_args)
        if not result:
            return None
        return int(result.split("\n")[0])

    def validate_path(self, cgroup_path: str) -> list[str] | None:
        if not self.cli.is_directory(cgroup_path):
            raise ValueError("Отсутствует директория в системе")

    def get_vm_names_resource_pool(self, cgroup_pool: str) -> dict[str, int]:
        pids = self.get_pids_from_pool(cgroup_pool)
        if pids is None:
            return None
        cmd_arg = "ls -d /run/libvirt/qemu/*.pid"
        vm_with_pids = {}
        resource_pool_vm_with_pids = {}
        pids_from_vm_pid_path = self.cli.execute(cmd_arg, shell=True, is_text=True).split("\n")
        pids_from_vm_pid_path.remove(f"{self.system_vm_pid_path}/driver.pid")
        pids_from_vm_pid_path.remove("")
        for vm in pids_from_vm_pid_path:
            vm_current_pid = int(self.cli.execute(["cat", vm]))
            vm_name = vm.replace(f"{self.system_vm_pid_path}/", "").replace(".pid", "")
            vm_with_pids[vm_name] = vm_current_pid

        for vm_name, vm_current_pid in vm_with_pids.items():
            if vm_current_pid in pids:
                resource_pool_vm_with_pids[vm_name] = vm_current_pid
        return resource_pool_vm_with_pids
    def get_pids_from_pool(self, cgroup_pool: str) -> list[int] | None:
        self.validate_path(cgroup_pool)
        cgroup_pool = f"{cgroup_pool}/cgroup.procs"
        result = self.cli.execute(["cat", f"{cgroup_pool}"])
        if result:
            return [int(pid) for pid in result.split("\n") if pid]
        else:
            return None

    def add_pid_to_pool(self, cgroup_pool: str, pid: int) -> str:
        if not isinstance(pid, int):
            raise ValueError("PID может быть только числом")
        self.validate_path(cgroup_pool)
        cgroup_pool = f"{cgroup_pool}/cgroup.procs"
        self.cli.execute(["sh", "-c", f"echo {pid} > {cgroup_pool}"])
        result = self.cli.execute(["cat", f"{cgroup_pool}"])
        return result

    def delete_pid_from_pool(self, cgroup_pool: str, pid: int) -> str:
        if not isinstance(pid, int):
            raise ValueError(f"PID может быть только числом, pid: {type(pid)}")
        self.validate_path(cgroup_pool)
        cgroup_pool = f"{cgroup_pool}/cgroup.procs"
        self.cli.execute(["sh", "-c", f"echo {pid} > {self.system_cgroup_path}/cgroup.procs"])
        result = self.cli.execute(["cat", f"{cgroup_pool}"])
        return result

    def delete_all_pid_from_pool(self, cgroup_pool: str) -> str:
        self.validate_path(cgroup_pool)
        cgroup_pool = f"{cgroup_pool}/cgroup.procs"
        self.cli.execute(["sh", "-c", f"cat {cgroup_pool} > {self.system_cgroup_path}/cgroup.procs"])
        result = self.cli.execute(["cat", f"{cgroup_pool}"])
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
