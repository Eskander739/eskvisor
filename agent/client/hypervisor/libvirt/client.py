import getpass

import libvirt
import logging

from agent.client.hypervisor.libvirt.models.node import NodeInfo


class LibvirtClient:
    """Класс для управления виртуализацией через libvirt"""

    def __init__(self, connection_uri: str = "qemu:///system",
                 username: str | None = None,
                 password: str | None = None):
        """
        Инициализация менеджера libvirt

        Args:
            connection_uri: URI для подключения к гипервизору
                - qemu:///system: локальный QEMU/KVM (требует прав root)
                - qemu:///session: сессионный QEMU/KVM
                - qemu+ssh://user@host/system: удаленное подключение по SSH
                - xen:/// для Xen
                - lxc:/// для LXC
            username: Имя пользователя для аутентификации
            password: Пароль для аутентификации
        """
        self.connection_uri = connection_uri
        self.username = username
        self.password = password
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
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    @classmethod
    def with_default_user(cls, connection_uri: str = "qemu:///session") -> 'LibvirtClient':
        """
        Создание клиента с дефолтным пользователем eskvisor

        Args:
            connection_uri: URI для подключения

        Returns:
            Экземпляр LibvirtClient с предустановленными учетными данными
        """
        return cls(
            connection_uri=connection_uri,
            username="eskvisor",
            password="P@$$w0rd12A"
        )

    @classmethod
    def with_current_user(cls, connection_uri: str = "qemu:///system") -> 'LibvirtClient':
        """
        Создание клиента с текущим пользователем системы

        Args:
            connection_uri: URI для подключения

        Returns:
            Экземпляр LibvirtClient с текущим пользователем
        """
        return cls(
            connection_uri=connection_uri,
            username=getpass.getuser(),
            password=None  # Пароль запросится при подключении
        )

    @classmethod
    def with_ssh_connection(cls, hostname: str, username: str = "eskvisor",
                            password: str = "P@$$w0rd12A") -> 'LibvirtClient':
        """
        Создание клиента для SSH подключения к удаленному хосту

        Args:
            hostname: Имя или IP удаленного хоста
            username: Имя пользователя на удаленном хосте
            password: Пароль пользователя

        Returns:
            Экземпляр LibvirtClient для SSH подключения
        """
        uri = f"qemu+ssh://{username}@{hostname}/system"
        return cls(
            connection_uri=uri,
            username=username,
            password=password
        )

    def connect(self) -> bool:
        """Подключение к гипервизору"""
        try:
            # Настройка аутентификации, если указаны учетные данные
            auth = None
            if self.username:
                # Определяем тип аутентификации по URI
                if self.connection_uri.startswith("qemu+ssh://"):
                    # Для SSH используем интерактивную аутентификацию
                    self.conn = libvirt.openAuth(
                        self.connection_uri,
                        [
                            [libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_PASSPHRASE],
                            self._auth_callback
                        ],
                        0
                    )
                else:
                    # Для локальных подключений
                    if self.password:
                        # Если есть пароль, используем аутентификацию
                        self.conn = libvirt.openAuth(
                            self.connection_uri,
                            [
                                [libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_PASSPHRASE],
                                self._auth_callback
                            ],
                            0
                        )
                    else:
                        # Если пароля нет, пробуем обычное подключение
                        self.conn = libvirt.open(self.connection_uri)
            else:
                # Подключение без аутентификации
                self.conn = libvirt.open(self.connection_uri)

            if self.conn is None:
                self.logger.error(f"Не удалось подключиться к {self.connection_uri}")
                return False

            if self.password is None:
                self.logger.info(f"Успешное подключение к {self.connection_uri}")
            else:
                self.logger.info(f"Успешное подключение под пользователем {self.username} к {self.connection_uri}")
            self.logger.info(f"Hypervisor: {self.conn.getHostname()}")
            self.logger.info(f"Libvirt version: {self.conn.getLibVersion()}")
            return True

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка подключения: {e}")
            return False

    def _auth_callback(self, credentials, user_data):
        """Callback функция для аутентификации"""
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
                    credential[4] = getpass.getpass(f"Введите пароль для {self.username}: ")
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
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер для автоматического отключения"""
        self.disconnect()


    def get_node_info(self) -> NodeInfo | None:
        """Получение информации о хосте"""
        try:
            info = self.conn.getInfo()
            return NodeInfo(model=info[0],
                            memory=info[1],
                            cpus=info[2],
                            mhz=info[3],
                            nodes=info[4],
                            sockets=info[5],
                            cores=info[6],
                            threads=info[7])

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка получения информации о хосте: {e}")
            return None
