import subprocess
from pathlib import Path

from src.logger_config import DefaultLogger
from src.tools.cli import CLIControl
from src.constants import KEY_DIR
from src.constants import KEY_NAME


class AgentInstaller:
    """Класс для удаленной установки агента и настройки SSH доступа"""

    def __init__(self, ssh_key_path=KEY_DIR):
        ssk_key = str(Path(ssh_key_path) / KEY_NAME)
        self.logger = DefaultLogger("AgentInstaller")
        self.ssh_key_path = Path(ssk_key).expanduser()
        self.public_key_path = Path(f"{ssk_key}.pub").expanduser()
        self.cli = CLIControl()

    def install_agent_via_ssh(
        self,
        hostname: str,
        username: str,
        agent_package_path: str,
        password: str | None = None,
        install_key_if_missing: bool = True,
    ) -> bool:
        """
        Установка агента через SSH с использованием ключа или пароля

        Args:
            hostname: хост для установки
            username: пользователь на целевом хосте
            agent_package_path: путь к пакету агента на локальной машине
            password: пароль для SSH (если ключ еще не установлен)
            install_key_if_missing: установить ключ если его нет

        Returns:
            bool: True если установка успешна
        """

        # Проверяем наличие SSH ключа
        has_key_access = self._test_ssh_key_access(hostname, username)

        if not has_key_access and install_key_if_missing:
            if not password:
                self.logger.error(
                    f"Для хоста {hostname} требуется пароль для установки SSH ключа"
                )
                return False

            # Устанавливаем SSH ключ с использованием пароля
            if not self.install_ssh_key_with_password(hostname=hostname, username=username, password=password):
                self.logger.error(f"Не удалось установить SSH ключ на {hostname}")
                return False

        # Теперь устанавливаем агент с использованием ключа
        return self._install_agent_with_key(hostname, username, agent_package_path)

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
        self.logger.info(f"🔑 Установка SSH ключа на {hostname}...")

        # 1. Проверяем наличие публичного ключа
        if not self.public_key_path.exists():
            self.logger.error(f"Публичный ключ не найден: {self.public_key_path}")
            return False

        # 5. Выполняем скрипт на удаленном хосте
        self.logger.info(f"⚙️ Установка ssh ключа {self.public_key_path} на {hostname}...")

        execute_cmd = [f"sshpass", "-p", password, "ssh-copy-id", "-o", "StrictHostKeyChecking=no", "-i", f"{self.public_key_path}",
                       f"{username}@{hostname}"]

        result = self.cli.execute(execute_cmd, return_proc=True)

        if result.returncode != 0:
            self.logger.error(f"Ошибка установки SSH ключа {self.public_key_path} на {hostname}: {result.stderr}")
            return False

        # 7. Проверяем что ключ установлен
        if self._test_ssh_key_access(hostname, username, port):
            self.logger.info(f"✅ SSH ключ успешно установлен на {hostname}")
            return True
        else:
            self.logger.error(f"❌ SSH ключ не работает после установки")
            return False

    def _test_ssh_key_access(
        self, hostname: str, username: str, timeout: int = 5
    ) -> bool:
        """Тестирование SSH доступа с использованием ключа"""
        try:
            test_cmd = [
                "ssh",
                "-i",
                str(self.ssh_key_path),
                f"{username}@{hostname}",
                'echo "SSH key access OK"',
            ]

            result = self.cli.execute(test_cmd, timeout=timeout, return_proc=True)

            return result.returncode == 0

        except (subprocess.TimeoutExpired, Exception) as e:
            self.logger.debug(f"SSH key test failed for {hostname}: {str(e)}")
            return False

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

        except (subprocess.TimeoutExpired, Exception) as e:
            self.logger.debug(f"SSH password test failed for {hostname}: {str(e)}")
            return False

    def _install_agent_with_key(
        self, hostname: str, username: str, agent_package_path: str
    ) -> bool:
        """
        Установка агента с использованием SSH ключа
        """
        if not self.ssh_key_path.exists():
            self.logger.error(f"SSH ключ не найден: {self.ssh_key_path}")
            return False

        # 1. Копируем агент на удаленный хост
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
            f"{username}@{hostname}:/tmp/agent_package.tar.gz",
        ]

        result = self.cli.execute(scp_command, return_proc=True)

        if result.returncode != 0:
            self.logger.error(f"❌ Ошибка копирования: {result.stderr}")
            return False

        self.logger.info("✅ Агент скопирован")

        # 2. Устанавливаем агент на удаленном хосте
        self.logger.info(f"🔧 Установка агента на {hostname}...")

        install_commands = [
            f"tar -xzf /tmp/agent_package.tar.gz -C /tmp",
            "cd /tmp/agent && sudo ./install.sh",
            "rm -f /tmp/agent_package.tar.gz",
            "sudo systemctl start libvirt-agent",
        ]

        ssh_command = [
            "ssh",
            "-i",
            str(self.ssh_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            f"{username}@{hostname}",
            " && ".join(install_commands),
        ]

        result = self.cli.execute(ssh_command, return_proc=True)

        if result.returncode == 0:
            self.logger.info(f"✅ Агент успешно установлен на {hostname}")

            # Проверяем статус службы
            self._check_agent_status(hostname, username)
            return True
        else:
            self.logger.error(f"❌ Ошибка установки: {result.stderr}")
            return False

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

        result = subprocess.run(check_command, capture_output=True, text=True)

        if result.returncode == 0:
            self.logger.info("📊 Статус агента:")
            self.logger.info(result.stdout[:500])
        else:
            self.logger.warning("⚠️ Не удалось проверить статус агента")
