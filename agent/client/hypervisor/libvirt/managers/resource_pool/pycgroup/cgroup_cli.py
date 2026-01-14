import subprocess

from agent.client.hypervisor.libvirt.managers.resource_pool.pycgroup.pycgroup_logger import (
    PyCGroupLogger,
)


class CLICGroup:
    def __init__(self):
        self.logger = PyCGroupLogger()

    def execute(self, command, user="root", password="root"):
        if isinstance(command, str):
            command = command.split()

        cmd = ["sudo", "-S", "-u", user] + command
        self.logger.info(f"Выполнение команды: '{cmd}'")
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout, stderr = proc.communicate(input=f"{password}\n", timeout=10)
        return stdout if proc.returncode == 0 else stderr
