
import libvirt
import logging

from agent.client.hypervisor.models.node import NodeInfo


class LibvirtClient:
    """Класс для управления виртуализацией через libvirt"""

    def __init__(self, connection_uri: str = "qemu:///system"):
        """
        Инициализация менеджера libvirt

        Args:
            connection_uri: URI для подключения к гипервизору
                - qemu:///system: локальный QEMU/KVM (требует прав root)
                - qemu:///session: сессионный QEMU/KVM
                - xen:/// для Xen
                - lxc:/// для LXC
        """
        self.connection_uri = connection_uri
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

    def connect(self) -> bool:
        """Подключение к гипервизору"""
        try:
            self.conn = libvirt.open(self.connection_uri)
            if self.conn is None:
                self.logger.error(f"Не удалось подключиться к {self.connection_uri}")
                return False

            self.logger.info(f"Успешное подключение к {self.connection_uri}")
            self.logger.info(f"Hypervisor: {self.conn.getHostname()}")
            self.logger.info(f"Libvirt version: {self.conn.getLibVersion()}")
            return True

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка подключения: {e}")
            return False

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
