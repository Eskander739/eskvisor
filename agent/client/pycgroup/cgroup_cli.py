import subprocess

from agent.client.pycgroup.pycgroup_logger import (
    PyCGroupLogger,
)


class CLICGroup:
    def __init__(self):
        self.logger = PyCGroupLogger()

    def execute(
        self,
        command,
        user="root",
        password="root",
        shell: bool = False,
        is_text: bool = False,
    ):
        if not is_text:
            if isinstance(command, str):
                command = command.split()

        if is_text:
            cmd = f"sudo -S -u {user} " + command
        else:
            cmd = ["sudo", "-S", "-u", user] + command
        self.logger.info(f"Выполнение команды: '{cmd}'")
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=shell,
        )

        stdout, stderr = proc.communicate(input=f"{password}\n", timeout=10)
        return stdout if proc.returncode == 0 else stderr


if __name__ == "__main__":
    cli = CLICGroup()
    # print(cli.is_directory("/sys/fs/cgroup/resource_pool_1233"))
