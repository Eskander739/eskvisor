from pathlib import Path

from agent.client.hypervisor.libvirt.managers.resource_pool.balansir.pycgroup.cgroup_cli import (
    CLICGroup,
)


class PidController:
    def __init__(self):
        self.cli = CLICGroup()

    def vm_pid(self, uuid_or_name: str):
        cmd_args = ["pgrep", "-f", uuid_or_name]
        result = self.cli.execute(cmd_args)
        if not result:
            return None
        return result.split("\n")[0]

    def get_pids_from_pool(self, cgroup_pool: Path):
        cgroup_pool = cgroup_pool / "cgroup.procs"
        result = self.cli.execute(["cat", f"{cgroup_pool}"])
        return result

    def add_pid_to_pool(self, cgroup_pool: Path, pid: int):
        cgroup_pool = cgroup_pool / "cgroup.procs"
        self.cli.execute(["sh", "-c", f"echo {pid} > {cgroup_pool}"])
        result = self.cli.execute(["cat", f"{cgroup_pool}"])
        return result

    def delete_pid_from_pool(self, cgroup_pool: Path, pid: int):
        cgroup_pool = cgroup_pool / "cgroup.procs"
        parent_cgroup_pool = cgroup_pool.parent.parent / "cgroup.procs"
        self.cli.execute(["sh", "-c", f"echo {pid} > {parent_cgroup_pool}"])
        result = self.cli.execute(["cat", f"{cgroup_pool}"])
        return result

    def delete_all_pid_from_pool(self, cgroup_pool: Path, pid: int):
        cgroup_pool = cgroup_pool / "cgroup.procs"
        parent_cgroup_pool = cgroup_pool.parent.parent / "cgroup.procs"
        self.cli.execute(["sh", "-c", f"cat {cgroup_pool} > {parent_cgroup_pool}"])
        result = self.cli.execute(["cat", f"{cgroup_pool}"])
        return result


if __name__ == "__main__":
    pid_ctl = PidController()
    print(pid_ctl.vm_pid("2d676b1f-0119-4cc9-8e9e-1faf838810b0"))
    # print(pid_ctl.add_pid_to_pool(Path("/sys/fs/cgroup/RP-TEST-45678"), pid_ctl.vm_pid("8cc94005-2766-4609-98b2-7f07ba652a1d")))
    # print(pid_ctl.add_pid_to_pool(Path("/sys/fs/cgroup/RP-TEST-45678"), pid_ctl.vm_pid("2d676b1f-0119-4cc9-8e9e-1faf838810b0")))
    # print(pid_ctl.delete_pid_from_pool(Path("/sys/fs/cgroup/RP-TEST-45678"), pid_ctl.vm_pid("2d676b1f-0119-4cc9-8e9e-1faf838810b0")))
    # print(pid_ctl.vm_pid("2d676b1f-0119-4cc9-8e9e-1faf838810b0"))
    # 8cc94005-2766-4609-98b2-7f07ba652a1d
