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

    def is_exists(self, cgroup_path: str):
        ru_err = "Нет такого файла или каталога"
        eng_err = "No such file or directory"
        cmd_args = ["ls", cgroup_path]
        result = self.execute(cmd_args)
        if ru_err in result or eng_err in result:
            return False
        return True

    def is_directory(self, cgroup_path: str):
        ru_err = "Это каталог"
        eng_err = "Is a directory"
        cmd_args = ["cat", cgroup_path]
        result = self.execute(cmd_args)
        if ru_err in result or eng_err in result:
            return True
        return False

    def mkdir(self, cgroup_path: str):
        cmd_args = ["mkdir", cgroup_path]
        result = self.execute(cmd_args)
        return result

    def rmdir(self, cgroup_path: str):
        cmd_args = ["rmdir", cgroup_path]
        result = self.execute(cmd_args)
        return result

    def write_text(self, file_path: str, text: str):
        cmd_args = ["sh", "-c", f"echo {text} > {file_path}"]
        result = self.execute(cmd_args)
        return result

    def read_text(self, file_path: str):
        cmd_args = ["cat", f"{file_path}"]
        result = self.execute(cmd_args)
        return result


if __name__ == "__main__":
    cli = CLICGroup()
    # print(cli.is_directory("/sys/fs/cgroup/resource_pool_1233"))
