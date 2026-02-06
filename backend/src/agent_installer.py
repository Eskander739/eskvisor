from pathlib import Path
import threading
from typing import Callable, Optional

from src.logger_config import DefaultLogger
from src.tools.cli import CLIControl
from src.constants import KEY_DIR, TMP_AGENT_DIR, SCRIPT_INSTALL_DIR, SCRIPT_UPDATE_DIR
from src.constants import KEY_NAME
from src.tools.my_ip import MyIp


class AgentInstaller:
    """Класс для удаленной установки, обновления и удаления агента"""

    def __init__(self, ssh_key_path=KEY_DIR):
        ssk_key = str(Path(ssh_key_path) / KEY_NAME)
        self.logger = DefaultLogger("AgentInstaller")
        self.ssh_key_path = Path(ssk_key).expanduser()
        self.public_key_path = Path(f"{ssk_key}.pub").expanduser()
        self.my_ip = MyIp()
        self.cli = CLIControl()
        self._active_threads = []

    def install_agent_via_ssh(
        self,
        hostname: str,
        username: str,
        agent_package_path: str,
        password: str | None = None,
        install_key_if_missing: bool = True,
        is_update: bool = False,
        backend_ip: str | None = None,
    ) -> bool:
        """
        Установка агента через SSH с использованием ключа или пароля

        Args:
            hostname: хост для установки
            username: пользователь на целевом хосте
            agent_package_path: путь к пакету агента на локальной машине
            password: пароль для SSH (если ключ еще не установлен)
            install_key_if_missing: установить ключ если его нет
            is_update: является ли запрос обновлением агента
            backend_ip: ip центрального бэкэнда, если не указан, передается приватный(локальный) ip


        Returns:
            bool: True если установка успешна
        """

        # Проверяем наличие SSH ключа
        has_key_access, info = self._test_ssh_key_access(hostname, username)
        self.logger.warning(f"Результат проверки SSH ключа: {info}")
        if not has_key_access and install_key_if_missing and not is_update:
            if not password:
                self.logger.error(
                    f"Для хоста {hostname} требуется пароль для установки SSH ключа"
                )
                return False

            # Устанавливаем SSH ключ с использованием пароля
            if not self.install_ssh_key_with_password(
                hostname=hostname, username=username, password=password
            ):
                self.logger.error(f"Не удалось установить SSH ключ на {hostname}")
                return False

        if backend_ip is None:
            backend_ip = self.my_ip.private
        # Выбираем метод установки в зависимости от типа операции
        if is_update:
            return self._update_agent_with_key(
                hostname, username, agent_package_path, backend_ip=backend_ip
            )
        else:
            return self._install_agent_with_key(
                hostname, username, agent_package_path, backend_ip=backend_ip
            )

    def install_agent_via_ssh_async(
        self,
        hostname: str,
        username: str,
        agent_package_path: str,
        callback: Optional[Callable[[bool, str, Optional[str]], None]] = None,
        password: str | None = None,
        install_key_if_missing: bool = True,
        is_update: bool = False,
        backend_ip: str | None = None,
    ) -> threading.Thread:
        """
        Асинхронная установка агента через SSH

        Args:
            hostname: хост для установки
            username: пользователь на целевом хосте
            agent_package_path: путь к пакету агента на локальной машине
            callback: функция обратного вызова (success: bool, hostname: str, error: str | None)
            password: пароль для SSH (если ключ еще не установлен)
            install_key_if_missing: установить ключ если его нет
            is_update: является ли запрос обновлением агента
            backend_ip: ip центрального бэкэнда, если не указан, передается приватный(локальный) ip

        Returns:
            threading.Thread: поток выполнения установки
        """

        def install_thread(local_backend_ip: str | None = None):
            """Внутренняя функция для запуска в потоке"""
            try:

                success = self.install_agent_via_ssh(
                    hostname=hostname,
                    username=username,
                    agent_package_path=agent_package_path,
                    password=password,
                    install_key_if_missing=install_key_if_missing,
                    is_update=is_update,
                    backend_ip=local_backend_ip,
                )

                error_msg = (
                    None if success else f"Ошибка установки агента на {hostname}"
                )

                if callback:
                    callback(success, hostname, error_msg)

            except Exception as e:
                self.logger.error(f"Ошибка в потоке установки для {hostname}: {str(e)}")
                if callback:
                    callback(False, hostname, str(e))

        thread = threading.Thread(
            target=install_thread,
            name=(
                f"AgentInstall-{hostname}"
                if not is_update
                else f"AgentUpdate-{hostname}"
            ),
            daemon=True,
            args={"local_backend_ip": backend_ip},
        )

        thread.start()
        self._active_threads.append(thread)

        # Очистка завершенных потоков
        self._cleanup_finished_threads()

        return thread

    def uninstall_agent_via_ssh(
        self,
        hostname: str,
        username: str,
        force: bool = False,
        remove_dependencies: bool = False,
        password: str | None = None,
    ) -> bool:
        """
        Удаление агента с удаленного хоста через SSH

        Args:
            hostname: хост с установленным агентом
            username: пользователь на целевом хосте
            force: пропустить подтверждение удаления
            remove_dependencies: удалить все зависимости (nginx, redis, libvirt и др.)
            password: пароль для SSH (если требуется аутентификация)

        Returns:
            bool: True если удаление успешно
        """
        self.logger.info(f"🧹 Удаление агента с {hostname}...")

        # Проверяем доступность хоста
        has_key_access, info = self._test_ssh_key_access(hostname, username)

        # Если ключ не работает, пробуем пароль если он предоставлен
        if not has_key_access and password:
            self.logger.warning(f"SSH ключ не работает, пробуем пароль для {hostname}")
            if not self._test_password_access(hostname, username, password):
                self.logger.error(
                    f"Не удалось подключиться к {hostname} ни по ключу, ни по паролю"
                )
                return False
        elif not has_key_access and not password:
            self.logger.error(
                f"Нет доступа к {hostname} по SSH ключу и пароль не предоставлен"
            )
            return False

        # Подготовка параметров для скрипта удаления
        uninstall_params = []
        if force:
            uninstall_params.append("--force")
        if remove_dependencies:
            uninstall_params.append("--remove-deps")

        # Команды для удаления
        uninstall_commands = [
            # Скачиваем скрипт удаления если его нет
            (
                "if [ ! -f /tmp/uninstall_agent.sh ]; then "
                "curl -s -o /tmp/uninstall_agent.sh https://raw.githubusercontent.com/eskvisor/agent/main/scripts/uninstall_agent.sh || "
                "wget -q -O /tmp/uninstall_agent.sh https://raw.githubusercontent.com/eskvisor/agent/main/scripts/uninstall_agent.sh || "
                "echo 'Не удалось скачать скрипт удаления'; "
                "fi"
            ),
            # Делаем скрипт исполняемым
            "chmod +x /tmp/uninstall_agent.sh 2>/dev/null || true",
            # Проверяем существование агента перед удалением
            (
                "if [ -d /opt/eskvisor ] || "
                "[ -f /etc/systemd/system/eskvisor.service ] || "
                "[ -f /etc/systemd/system/eskvisor-state.service ] || "
                "[ -f /etc/systemd/system/eskvisor-task-manager.service ]; then "
                f"sudo /tmp/uninstall_agent.sh {' '.join(uninstall_params)}; "
                "else "
                "echo 'Агент не найден на системе'; "
                "fi"
            ),
            # Очистка временных файлов
            "rm -f /tmp/uninstall_agent.sh",
            # Дополнительная проверка удаления
            (
                "echo '=== ПРОВЕРКА УДАЛЕНИЯ ==='; "
                "echo 'Директории:'; "
                "ls -la /opt/ 2>/dev/null | grep -i eskvisor || echo '  /opt/eskvisor не найден'; "
                "echo 'Сервисы:'; "
                "systemctl list-units --all 2>/dev/null | grep -i eskvisor || echo '  Сервисы eskvisor не найдены'; "
                "echo 'Процессы:'; "
                "ps aux 2>/dev/null | grep -i '[e]skvisor' || echo '  Процессы eskvisor не найдены'"
            ),
        ]

        # Определяем команду SSH в зависимости от доступности ключа
        if has_key_access:
            ssh_command = [
                "ssh",
                "-i",
                str(self.ssh_key_path),
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                f"{username}@{hostname}",
                " && ".join(uninstall_commands),
            ]
        else:
            # Используем sshpass для аутентификации по паролю
            ssh_command = [
                "sshpass",
                "-p",
                password,
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                f"{username}@{hostname}",
                " && ".join(uninstall_commands),
            ]

        self.logger.info(f"Выполнение удаления на {hostname}...")
        result = self.cli.execute(
            ssh_command, return_proc=True, timeout=300
        )  # 5 минут таймаут

        if result.returncode == 0:
            self.logger.info(f"✅ Агент успешно удален с {hostname}")
            self.logger.debug(f"Вывод удаления: {result.stdout[:1000]}...")
            return True
        else:
            self.logger.error(
                f"❌ Ошибка удаления агента с {hostname}: {result.stderr}"
            )
            return False

    def uninstall_agent_via_ssh_async(
        self,
        hostname: str,
        username: str,
        force: bool = False,
        remove_dependencies: bool = False,
        password: str | None = None,
    ) -> threading.Thread:
        """
        Асинхронное удаление агента с удаленного хоста

        Args:
            hostname: хост с установленным агентом
            username: пользователь на целевом хосте
            force: пропустить подтверждение удаления
            remove_dependencies: удалить все зависимости
            password: пароль для SSH (если требуется)

        Returns:
            threading.Thread: поток выполнения удаления
        """

        def uninstall_thread():
            """Внутренняя функция для запуска в потоке"""
            try:
                success = self.uninstall_agent_via_ssh(
                    hostname=hostname,
                    username=username,
                    force=force,
                    remove_dependencies=remove_dependencies,
                    password=password,
                )

            except Exception as e:
                self.logger.error(f"Ошибка в потоке удаления для {hostname}: {str(e)}")

        thread = threading.Thread(
            target=uninstall_thread,
            name=f"AgentUninstall-{hostname}",
            daemon=True,
        )

        thread.start()
        self._active_threads.append(thread)

        # Очистка завершенных потоков
        self._cleanup_finished_threads()

        return thread

    def install_ssh_key_with_password(
        self, hostname: str, username: str, password: str, port: int = 22
    ) -> bool:
        """
        Установка SSH ключа на удаленный хост с использованием пароля

        Args:
            hostname: целевой хост
            username: пользователь на целевом хосте
            password: пароль для аутентификации
            port: SSH порт

        Returns:
            bool: True если ключ успешно установлен
        """
        self.logger.info(f"Установка SSH ключа на {hostname}...")

        # 1. Проверяем наличие публичного ключа
        if not self.public_key_path.exists():
            self.logger.error(f"Публичный ключ не найден: {self.public_key_path}")
            return False

        # 2. Выполняем скрипт на удаленном хосте
        self.logger.info(
            f"⚙Установка ssh ключа {self.public_key_path} на {hostname}..."
        )

        execute_cmd = [
            f"sshpass",
            "-p",
            password,
            "ssh-copy-id",
            "-o",
            "StrictHostKeyChecking=no",
            "-i",
            f"{self.public_key_path}",
            f"{username}@{hostname}",
        ]

        result = self.cli.execute(execute_cmd, return_proc=True)

        if result.returncode != 0:
            self.logger.error(
                f"Ошибка установки SSH ключа {self.public_key_path} на {hostname}: {result.stderr}"
            )
            return False

        # 3. Проверяем что ключ установлен
        has_key_access, info = self._test_ssh_key_access(hostname, username)
        if has_key_access:
            self.logger.warning(f"Результат проверки SSH ключа: {info}")
            self.logger.info(f"SSH ключ успешно установлен на {hostname}")
            return True
        else:
            self.logger.error(f"SSH ключ не работает после установки")
            return False

    def _test_ssh_key_access(
        self, hostname: str, username: str, timeout: int | None = 5
    ) -> tuple[bool, str]:
        """Тестирование SSH доступа с использованием ключа"""
        try:
            test_cmd = f'ssh -i {str(self.ssh_key_path)} -o StrictHostKeyChecking=no -o PasswordAuthentication=no {username}@{hostname} echo "SSH key access OK"'

            result = self.cli.execute(
                test_cmd, timeout=timeout, return_proc=True, is_text=True, shell=True
            )
            if result.returncode == 0:
                return result.returncode == 0, result.stdout
            else:
                return result.returncode == 0, result.stderr

        except Exception as err:
            self.logger.debug(f"SSH key test failed for {hostname}: {str(err)}")
            return False, str(err)

    def _test_password_access(
        self, hostname: str, username: str, password: str, port: int = 22
    ) -> bool:
        """Тестирование SSH доступа с использованием пароля"""
        try:
            test_cmd = [
                "sshpass",
                "-p",
                password,
                "ssh",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "BatchMode=no",
                "-o",
                "StrictHostKeyChecking=no",
                "-p",
                str(port),
                f"{username}@{hostname}",
                'echo "SSH password access OK"',
            ]

            result = self.cli.execute(test_cmd, return_proc=True, timeout=7)

            return result.returncode == 0

        except Exception as err:
            self.logger.debug(f"SSH password test failed for {hostname}: {str(err)}")
            return False

    def _install_agent_with_key(
        self,
        hostname: str,
        username: str,
        agent_package_path: str,
        backend_ip: str | None = None,
    ) -> bool:
        """
        Установка агента с использованием SSH ключа
        """
        if not self.ssh_key_path.exists():
            self.logger.error(f"SSH ключ не найден: {self.ssh_key_path}")
            return False

        self.logger.info(f"📦 Копирование агента на {hostname}...")

        scp_command = [
            "scp",
            "-i",
            str(self.ssh_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            agent_package_path,
            f"{username}@{hostname}:{TMP_AGENT_DIR}",
        ]

        result = self.cli.execute(scp_command, return_proc=True)

        if result.returncode != 0:
            self.logger.error(f"Ошибка копирования: {result.stderr}")
            return False

        self.logger.info("Агент скопирован")

        # 2. Устанавливаем агент на удаленном хосте
        self.logger.info(f"Установка агента на {hostname}...")

        install_commands = [
            "dnf install tar -y",
            f"tar -xzf {TMP_AGENT_DIR} -C /tmp",
            f"mv /tmp/eskvisor /opt/eskvisor && sudo bash {SCRIPT_INSTALL_DIR} {hostname} {backend_ip}",
            f"rm -f {TMP_AGENT_DIR}",
            "rm -r /tmp/eskvisor",
        ]

        ssh_command = [
            "ssh",
            "-i",
            str(self.ssh_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"{username}@{hostname}",
            " && ".join(install_commands),
        ]

        result = self.cli.execute(ssh_command, return_proc=True, timeout=None)

        if result.returncode == 0:
            self.logger.info(f"Агент успешно установлен на {hostname}")

            # Проверяем статус службы
            self._check_agent_status(hostname, username)
            return True
        else:
            self.logger.error(f"Ошибка установки: {result.stderr}")
            return False

    def _update_agent_with_key(
        self,
        hostname: str,
        username: str,
        agent_package_path: str,
        backend_ip: str | None = None,
    ) -> bool:
        """
        Обновление агента с использованием SSH ключа
        """
        if not self.ssh_key_path.exists():
            self.logger.error(f"SSH ключ не найден: {self.ssh_key_path}")
            return False

        self.logger.info(f"🔄 Обновление агента на {hostname}...")

        # 1. Копируем новый пакет агента
        self.logger.info(f"📦 Копирование нового агента на {hostname}...")

        scp_command = [
            "scp",
            "-i",
            str(self.ssh_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            agent_package_path,
            f"{username}@{hostname}:{TMP_AGENT_DIR}",
        ]

        result = self.cli.execute(scp_command, return_proc=True)

        if result.returncode != 0:
            self.logger.error(f"Ошибка копирования нового агента: {result.stderr}")
            return False

        self.logger.info("Новый агент скопирован")

        # 2. Запускаем скрипт обновления на удаленном хосте
        self.logger.info(f"Запуск скрипта обновления на {hostname}...")

        update_commands = [
            f"tar -xzf {TMP_AGENT_DIR} -C /tmp",
            f"mv /tmp/eskvisor /tmp/eskvisor_new",
            (
                f"bash {SCRIPT_UPDATE_DIR} {hostname}" + " " + backend_ip
                if backend_ip is not None
                else ""
            ),
            f"rm -f {TMP_AGENT_DIR}",
            "rm -rf /tmp/eskvisor_new",
        ]

        ssh_command = [
            "ssh",
            "-i",
            str(self.ssh_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"{username}@{hostname}",
            " && ".join(update_commands),
        ]

        result = self.cli.execute(ssh_command, return_proc=True, timeout=None)

        if result.returncode == 0:
            self.logger.info(f"Агент успешно обновлен на {hostname}")

            # Проверяем статус службы после обновления
            self._check_agent_status(hostname, username)
            return True
        else:
            self.logger.error(f"Ошибка обновления: {result.stderr}")
            return False

    def _install_agent_with_key_async(
        self,
        hostname: str,
        username: str,
        agent_package_path: str,
        callback: Optional[Callable[[bool, str], None]] = None,
    ) -> threading.Thread:
        """
        Асинхронная установка агента с использованием SSH ключа в отдельном потоке

        Args:
            hostname: целевой хост
            username: пользователь на целевом хосте
            agent_package_path: путь к пакету агента
            callback: функция обратного вызова (success: bool, hostname: str)

        Returns:
            threading.Thread: поток выполнения установки
        """

        def install_in_thread():
            """Функция, выполняемая в отдельном потоке"""
            try:
                success = self._install_agent_with_key(
                    hostname, username, agent_package_path
                )
                if callback:
                    callback(success, hostname)
            except Exception as e:
                self.logger.error(
                    f"Ошибка при асинхронной установке на {hostname}: {e}"
                )
                if callback:
                    callback(False, hostname)

        thread = threading.Thread(
            target=install_in_thread, name=f"AgentInstall-{hostname}", daemon=True
        )

        thread.start()
        self._active_threads.append(thread)

        # Очистка завершенных потоков
        self._cleanup_finished_threads()

        return thread

    def _cleanup_finished_threads(self):
        """Очистка списка завершенных потоков"""
        self._active_threads = [t for t in self._active_threads if t.is_alive()]

    def wait_for_all_installations(self, timeout: Optional[float] = None):
        """
        Ожидание завершения всех запущенных установок

        Args:
            timeout: максимальное время ожидания в секундах
        """
        for thread in self._active_threads:
            thread.join(timeout)

    def _check_agent_status(self, hostname, username):
        """Проверка статуса установленного агента"""
        check_command = [
            "ssh",
            "-i",
            str(self.ssh_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            f"{username}@{hostname}",
            "sudo systemctl status libvirt-agent --no-pager",
        ]

        result = self.cli.execute(check_command, return_proc=True)

        if result.returncode == 0:
            self.logger.info("Статус агента:")
            self.logger.info(result.stdout[:500])
        else:
            self.logger.warning("Не удалось проверить статус агента")
