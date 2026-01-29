import subprocess

from src.logger_config import DefaultLogger


class ProcessResult:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CLIControl:
    def __init__(self):
        self.logger = DefaultLogger("CLIControl")

    def create_file(self, path: str, info: str | None = None):
        if info is None:
            cmd_args = ["touch", path]
        else:
            cmd_args = ["sh", "-c", f"echo '{info}' > {path}"]
        result = self.execute(cmd_args)
        self.logger.info(f"Результат создания файла: '{result}'")
        return result

    def execute(
        self,
        command,
        user="root",
        password="root",
        timeout: int | None = 10,
        return_proc: bool = False,
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
        # Выполняем
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell,
            text=True,
        )
        # Критически важно: пароль + \n
        if timeout is not None:
            stdout, stderr = proc.communicate(input=f"{password}\n", timeout=timeout)
        else:
            stdout, stderr = proc.communicate(input=f"{password}\n")
        if return_proc:
            return ProcessResult(proc.returncode, stdout, stderr)
        return stdout if proc.returncode == 0 else stderr


if __name__ == "__main__":
    cli = CLIControl()
    # print(cli.search_emulators())
    # print(cli.default_emulator)
