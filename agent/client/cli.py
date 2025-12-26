import getpass
import shlex
import subprocess
import os

from agent.client.constants import DIRECTORIES_FOR_SEARCH, QEMU_EMULATORS


class CLIControl:



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

    @staticmethod
    def is_directory(path_str: str) -> bool:
        """
        Проверяет, является ли строка директорией (или потенциальным путем к директории).

        Args:
            path_str: Путь для проверки

        Returns:
            bool: True если базовый путь существует и является директорией, иначе False
        """
        try:
            # Используем pathlib для более чистой обработки путей
            from pathlib import Path

            # Преобразуем строку в Path объект
            path_obj = Path(path_str)

            # Если путь содержит wildcards, проверяем родительскую директорию
            if '*' in path_str or '?' in path_str:
                # Берем родительскую директорию для проверки
                parent_dir = path_obj.parent
                # Если родительская директория - это текущая директория ('.') или пусто,
                # проверяем текущую рабочую директорию
                if str(parent_dir) == '.':
                    parent_dir = Path.cwd()
                return parent_dir.exists() and parent_dir.is_dir()

            # Для обычных путей - расширяем домашнюю директорию и проверяем
            expanded_path = path_obj.expanduser()
            return expanded_path.exists() and expanded_path.is_dir()

        except Exception as e:
            # Логируем ошибку при необходимости
            # print(f"Error checking directory {path_str}: {e}")
            return False

    def search_emulators(self, new_directories: list[str] | str | None = None, only_name: bool = False):
        installed_emulators = []

        # Создаем список всех имен эмуляторов для поиска
        emulator_names = list(QEMU_EMULATORS.keys())

        # Создаем паттерны для поиска всех эмуляторов одновременно
        # Используем несколько паттернов, чтобы избежать слишком длинной командной строки
        search_patterns = []

        # Разбиваем на группы по 20 эмуляторов для поиска
        group_size = 20
        for i in range(0, len(emulator_names), group_size):
            group = emulator_names[i:i + group_size]
            # Создаем паттерн типа: -name "qemu-system-x86_64" -o -name "qemu-system-i386" ...
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

        # Ищем эмуляторы во всех директориях
        for directory in all_directories:
            if not self.is_directory(directory):
                continue
            # Проверяем, существует ли директория
            if not os.path.isdir(directory):
                continue

            # Для каждого паттерна выполняем поиск
            for pattern in search_patterns:
                # Убираем звездочку из пути для корректной работы find
                dir_path = directory.rstrip('*')

                # Формируем команду find
                # Используем -maxdepth для оптимизации поиска в глубоких путях
                if '*/*' in directory:  # Для сложных путей вроде /nix/store/*/bin
                    # Для путей со звездочками используем другой подход
                    base_dir = directory.split('/*')[0]
                    command = f'find {base_dir} -type d -name "bin" 2>/dev/null | head -20'
                    try:
                        bin_dirs = subprocess.run(command, shell=True, stdout=subprocess.PIPE,
                                                  stderr=subprocess.DEVNULL, text=True).stdout.strip().split('\n')
                        for bin_dir in bin_dirs:
                            if bin_dir:
                                find_command = f'find {bin_dir} \( {pattern} \) -type f -executable 2>/dev/null'
                                finded_emulator = self.execute(find_command).split("\n")
                                finded_emulator = [fe for fe in finded_emulator if fe]
                                installed_emulators.extend(finded_emulator)
                    except:
                        continue
                else:
                    # Обычный поиск
                    find_command = f'find {dir_path} \( {pattern} \) -type f -executable 2>/dev/null'
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
                        installed_emulators[em_index] = emulator.replace(directory, "").replace("/", "").replace("\\",
                                                                                                                 "")
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

    @staticmethod
    def execute(command: list[str] | str, shell: bool = True, by_user: str | None = "eskvisor",
                use_sudo: bool = True, password: str | None = None) -> str:
        """
        Выполняет команду в shell с возможностью запуска от другого пользователя.

        Args:
            command: Команда для выполнения (строка или список)
            shell: Использовать ли shell
            by_user: Имя пользователя, от которого выполнить команду
            use_sudo: Использовать sudo (если не root)
            password: Пароль для sudo (не рекомендуется передавать явно)

        Returns:
            Вывод команды в виде строки
        """
        current_user = getpass.getuser()

        # Преобразуем команду
        if isinstance(command, list):
            cmd_to_run = command
        else:
            cmd_to_run = command if shell else shlex.split(command)

        # Проверяем, нужно ли выполнять от другого пользователя
        if by_user and by_user != current_user:
            # Формируем команду для запуска от другого пользователя
            if os.geteuid() == 0:
                # Мы уже root - используем sudo -u
                prefix = ["sudo", "-u", by_user]
            elif use_sudo:
                # Используем sudo с паролем если нужно
                prefix = ["sudo", "-u", by_user]
                if password:
                    # Внимание: передача пароля командной строке небезопасна!
                    prefix = ["sudo", "-S", "-u", by_user]
            else:
                raise PermissionError(
                    f"Недостаточно прав для выполнения от пользователя '{by_user}'. "
                    f"Требуются права root или используйте use_sudo=True"
                )

            # Формируем финальную команду
            if isinstance(cmd_to_run, str) and shell:
                final_command = f"{' '.join(prefix)} {cmd_to_run}"
            else:
                final_command = prefix + (cmd_to_run if isinstance(cmd_to_run, list) else [cmd_to_run])
        else:
            final_command = cmd_to_run

        try:
            # Подготовка параметров для subprocess
            kwargs = {
                'stdout': subprocess.PIPE,
                'stderr': subprocess.STDOUT,
                'shell': shell,
                'text': True,
                'encoding': 'utf-8'
            }

            # Если нужно передать пароль для sudo
            if password and use_sudo:
                kwargs['input'] = password + '\n'
                kwargs['universal_newlines'] = True

            result = subprocess.run(final_command, **kwargs)
            return result.stdout

        except subprocess.CalledProcessError as e:
            return f"Ошибка выполнения (код {e.returncode}): {e.output}"
        except Exception as e:
            return f"Ошибка: {str(e)}"


if __name__ == "__main__":
    cli = CLIControl()
    print(cli.search_emulators())
    print(cli.default_emulator)