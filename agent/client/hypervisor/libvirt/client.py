import getpass
import logging
import os
from xml.etree import ElementTree

import libvirt
from agent.client.hypervisor.libvirt.models.node import NodeInfo


class LibvirtClient:
    """Класс для управления виртуализацией через libvirt"""

    def __init__(self):
        """
        Инициализация менеджера libvirt

        Args:
            CONNECTION_URI - URI для подключения к гипервизору
                - qemu:///system: локальный QEMU/KVM (требует прав root)
                - qemu:///session: сессионный QEMU/KVM
                - qemu+ssh://user@host/system: удаленное подключение по SSH
                - xen:/// для Xen
                - lxc:/// для LXC
            USERNAME - Имя пользователя для аутентификации
            PASSWORD - Пароль для аутентификации
        """
        self.connection_uri = os.environ.get("CONNECTION_URI")
        self.username = os.environ.get("USERNAME")
        self.password = os.environ.get("PASSWORD")
        self.conn = None
        self.logger = self._setup_logger()
        self.libvirtError = libvirt.libvirtError

    @staticmethod
    def _setup_logger() -> logging.Logger:
        """Настройка логгера"""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    @staticmethod
    def xml_string_from_object(element_tree_object: ElementTree.Element) -> str:
        xml_string = ElementTree.tostring(element_tree_object).decode("utf-8")
        return xml_string

    def connect_classic(self, uri: str = "qemu:///system") -> libvirt.virConnect:
        """
        Классическое подключение к локальному гипервизору

        Args:
            uri: URI подключения (по умолчанию qemu:///system)

        Returns:
            bool: True если подключение успешно, иначе False
        """
        try:
            self.conn = libvirt.open(uri)

            if self.conn is None:
                self.logger.error(f"Не удалось подключиться к {uri}")
                raise ValueError(f"Не удалось подключиться к {uri}")

            self.logger.info(f"Успешное классическое подключение к {uri}")
            self.logger.info(f"Hypervisor: {self.conn.getHostname()}")
            self.logger.info(f"Libvirt version: {self.conn.getLibVersion()}")
            return self.conn

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка подключения: {e}")
            raise ValueError(f"Ошибка подключения: {e}")

    def connect_ssh_with_password(
        self, host: str, username: str = None, password: str = None
    ) -> libvirt.virConnect:
        """
        Подключение по SSH с использованием пароля

        Args:
            host: Хост для подключения
            username: Имя пользователя (если None, будет запрошено)
            password: Пароль (если None, будет запрошен)

        Returns:
            bool: True если подключение успешно, иначе False
        """
        if username is None:
            username = input("Введите имя пользователя для SSH: ")

        self.username = username
        self.password = password

        uri = f"qemu+ssh://{username}@{host}/system"

        try:
            self.conn = libvirt.openAuth(
                uri,
                [
                    [libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_PASSPHRASE],
                    self._ssh_password_auth_callback,
                ],
                0,
            )

            if self.conn is None:
                self.logger.error(f"Не удалось подключиться к {uri}")
                raise ValueError(f"Не удалось подключиться к {uri}")

            self.logger.info(f"Успешное подключение по SSH (с паролем) к {uri}")
            self.logger.info(f"Hypervisor: {self.conn.getHostname()}")
            self.logger.info(f"Libvirt version: {self.conn.getLibVersion()}")
            return self.conn

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка подключения: {e}")
            raise ValueError(f"Ошибка подключения: {e}")

    def connect_ssh_with_key(
        self, host: str, username: str = None, keyfile: str = None
    ) -> libvirt.virConnect:
        """
        Подключение по SSH с использованием SSH-ключа

        Args:
            host: Хост для подключения
            username: Имя пользователя (если None, будет запрошено)
            keyfile: Путь к файлу SSH-ключа (если None, используется стандартный)

        Returns:
            bool: True если подключение успешно, иначе False
        """
        if username is None:
            username = input("Введите имя пользователя для SSH: ")

        # Формируем URI для подключения с SSH-ключом
        if keyfile:
            # Если указан ключ, добавляем его в URI
            uri = f"qemu+ssh://{username}@{host}/system?keyfile={keyfile}&no_verify=1"
        else:
            # Используем стандартный ключ из ~/.ssh/
            uri = f"qemu+ssh://{username}@{host}/system?no_verify=1"

        try:
            self.conn = libvirt.open(uri)

            if self.conn is None:
                self.logger.error(f"Не удалось подключиться к {uri}")
                raise ValueError(f"Не удалось подключиться к {uri}")

            self.logger.info(f"Успешное подключение по SSH (с ключом) к {uri}")
            self.logger.info(f"Hypervisor: {self.conn.getHostname()}")
            self.logger.info(f"Libvirt version: {self.conn.getLibVersion()}")
            return self.conn

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка подключения: {e}")
            raise ValueError(f"Ошибка подключения: {e}")

    def _ssh_password_auth_callback(self, credentials):
        """Callback функция для аутентификации по SSH с паролем"""
        for credential in credentials:
            if credential[0] == libvirt.VIR_CRED_AUTHNAME:
                # Запрос имени пользователя
                if self.username:
                    credential[4] = self.username
                else:
                    credential[4] = getpass.getuser()
            elif credential[0] == libvirt.VIR_CRED_PASSPHRASE:
                # Запрос пароля
                if self.password:
                    credential[4] = self.password
                else:
                    # Если пароль не указан, запрашиваем у пользователя
                    credential[4] = getpass.getpass(
                        f"Введите пароль для {self.username}: "
                    )
            else:
                return -1  # Неподдерживаемый тип аутентификации
        return 0

    def disconnect(self):
        """Отключение от гипервизора"""
        if self.conn:
            self.conn.close()
            self.logger.info("Отключение от гипервизора")

    def __enter__(self):
        """Контекстный менеджер для автоматического подключения"""
        # По умолчанию используем классическое подключение
        self.connect_classic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер для автоматического отключения"""
        self.disconnect()

    def get_node_info(self) -> NodeInfo | None:
        """Получение информации о хосте"""
        try:
            info = self.conn.getInfo()
            return NodeInfo(
                model=info[0],
                memory=info[1],
                cpus=info[2],
                mhz=info[3],
                nodes=info[4],
                sockets=info[5],
                cores=info[6],
                threads=info[7],
            )

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка получения информации о хосте: {e}")
            return None


if __name__ == "__main__":
    # Пример использования разных режимов подключения
    lib_client = LibvirtClient()

    # 1. Классическое подключение
    print("1. Тестирование классического подключения:")
    if lib_client.connect_classic():
        print(lib_client.get_node_info())
    lib_client.disconnect()

    print("\n" + "=" * 50 + "\n")

    # 2. Подключение по SSH с ключом
    print("2. Тестирование подключения по SSH с ключом:")
    host = input("Введите хост для SSH подключения: ")
    if lib_client.connect_ssh_with_key(host=host):
        print(lib_client.get_node_info())
    lib_client.disconnect()

    print("\n" + "=" * 50 + "\n")

    # 3. Подключение по SSH с паролем
    print("3. Тестирование подключения по SSH с паролем:")
    host = input("Введите хост для SSH подключения: ")
    if lib_client.connect_ssh_with_password(host=host):
        print(lib_client.get_node_info())
    lib_client.disconnect()
