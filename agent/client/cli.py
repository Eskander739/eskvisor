import os
import subprocess

from agent.client.constants import DIRECTORIES_FOR_SEARCH, QEMU_EMULATORS
from agent.client.logger_config import DefaultLogger


class ProcessResult:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CLIControl:
    def __init__(self):
        self.logger = DefaultLogger("CLIControl")

    def virsh_net_data(self, params: str | None = None):
        """
        Получение информации о сети

        --inactive - список неактивных сетей
        --all - список неактивных и активных сетей
        --persistent - список постоянных сетей
        --transient - список временных сетей
        --autostart - список сетей с включёнными функциями автозапуска
        --no-autostart - список сетей с отключёнными функциями автозапуска
        --uuid - показать только UUID
        --name - список имён сетей
        --table - показать таблицу (по умолчанию)
        --title - show network title

        """
        if params is None:
            params = ""
        result = self.execute(f"virsh net-list {params}")

        return result

    def is_exists(self, path: str):
        ru_err = "Нет такого файла или каталога"
        eng_err = "No such file or directory"
        cmd_args = ["ls", path]
        result = self.execute(cmd_args)
        if ru_err in result or eng_err in result:
            return False
        return True

    def is_directory(self, path: str):
        ru_err = "Это каталог"
        eng_err = "Is a directory"
        cmd_args = ["cat", path]
        result = self.execute(cmd_args)
        if ru_err in result or eng_err in result:
            return True
        return False

    def mkdir(self, path: str):
        cmd_args = ["mkdir", "-p", path]
        result = self.execute(cmd_args)
        return result

    def create_file(self, path: str, info: str | None = None):
        if info is None:
            cmd_args = ["touch", path]
        else:
            cmd_args = ["sh", "-c", f"echo '{info}' > {path}"]
        result = self.execute(cmd_args)
        self.logger.info(f"Результат создания файла: '{result}'")
        return result

    def delete_file_or_path(self, path: str):
        cmd_args = ["rm", "-r", path]
        result = self.execute(cmd_args)
        self.logger.info(f"Результат удаления файла/директории: '{result}'")
        return result

    def search_emulators(
        self, new_directories: list[str] | str | None = None, only_name: bool = False
    ):
        installed_emulators = []

        # Создаем список всех имен эмуляторов для поиска
        emulator_names = list(QEMU_EMULATORS.keys())

        # Создаем паттерны для поиска всех эмуляторов одновременно
        # Используем несколько паттернов, чтобы избежать слишком длинной командной строки
        search_patterns = []

        # Разбиваем на группы по 20 эмуляторов для поиска
        group_size = 20
        for i in range(0, len(emulator_names), group_size):
            group = emulator_names[i : i + group_size]
            # Создаем паттерн типа: -name "qemu-system-x86_64" -o -name
            # "qemu-system-i386" ...
            pattern_parts = []
            for emulator in group:
                pattern_parts.append(f'-name "{emulator}"')
            search_pattern = " -o ".join(pattern_parts)
            search_patterns.append(search_pattern)

        all_directories = []
        all_directories.extend(DIRECTORIES_FOR_SEARCH)
        if new_directories:
            if isinstance(new_directories, str):
                all_directories.append(new_directories)
            else:
                all_directories.extend(new_directories)

        for directory in all_directories:
            if not self.is_directory(directory):
                continue
            if not os.path.isdir(directory):
                continue

            for pattern in search_patterns:
                dir_path = directory.rstrip("*")

                if "*/*" in directory:  # Для сложных путей вроде /nix/store/*/bin
                    base_dir = directory.split("/*")[0]
                    command = (
                        f'find {base_dir} -type d -name "bin" 2>/dev/null | head -20'
                    )
                    try:
                        bin_dirs = (
                            subprocess.run(
                                command,
                                shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                text=True,
                            )
                            .stdout.strip()
                            .split("\n")
                        )
                        for bin_dir in bin_dirs:
                            if bin_dir:
                                find_command = f"find {bin_dir} \\( {pattern} \\) -type f -executable 2>/dev/null"
                                finded_emulator = self.execute(find_command).split("\n")
                                finded_emulator = [fe for fe in finded_emulator if fe]
                                installed_emulators.extend(finded_emulator)
                    except BaseException:
                        continue
                else:
                    # Обычный поиск
                    find_command = f"find {dir_path} \\( {pattern} \\) -type f -executable 2>/dev/null"
                    finded_emulator = self.execute(find_command).split("\n")
                    finded_emulator = [fe for fe in finded_emulator if fe]
                    installed_emulators.extend(finded_emulator)

        # Удаляем дубликаты и возвращаем результат

        installed_emulators = list(set(installed_emulators))

        if only_name:
            for emulator in installed_emulators:
                for directory in all_directories:
                    if emulator.count(directory) >= 1:
                        em_index = installed_emulators.index(emulator)
                        installed_emulators[em_index] = (
                            emulator.replace(directory, "")
                            .replace("/", "")
                            .replace("\\", "")
                        )
        return installed_emulators

    @property
    def default_emulator(self):
        if os.environ.get("DEFAULT_EMULATOR"):
            return os.environ.get("DEFAULT_EMULATOR")
        else:
            emulators = self.search_emulators()
            for emulator in emulators:
                if "qemu-system-x86_64" in emulator:
                    return emulator

            return emulators[0]

    def execute(
        self,
        command,
        user="root",
        password="root",
        timeout: int = 10,
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
        stdout, stderr = proc.communicate(input=f"{password}\n", timeout=timeout)
        if return_proc:
            return ProcessResult(proc.returncode, stdout, stderr)
        return stdout if proc.returncode == 0 else stderr


if __name__ == "__main__":
    cli = CLIControl()
    # print(cli.search_emulators())
    # print(cli.default_emulator)
