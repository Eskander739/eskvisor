# logger_config.py
import logging
import logging.handlers
import os
from datetime import datetime
from typing import Optional


class StorageLogger:
    """
    Конфигурация системы логирования для StorageManager
    """

    def __init__(self, name: str = "StorageManager", log_dir: str = "/var/log/virt-manager"):
        """
        Инициализация логгера

        Args:
            name: Имя логгера
            log_dir: Директория для хранения логов
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Очищаем существующие обработчики
        self.logger.handlers.clear()

        # Создаем форматтер
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Консольный обработчик
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Файловый обработчик
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            log_file = os.path.join(log_dir, f"storage_manager_{datetime.now().strftime('%Y%m')}.log")
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        except Exception as e:
            print(f"Ошибка при настройке файлового логирования: {e}")

    def info(self, message: str, **kwargs):
        """Логирование информационного сообщения"""
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Логирование предупреждения"""
        self.logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        """Логирование ошибки"""
        self.logger.error(message, **kwargs)

    def debug(self, message: str, **kwargs):
        """Логирование отладочной информации"""
        self.logger.debug(message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Логирование критической ошибки"""
        self.logger.critical(message, **kwargs)

    def exception(self, message: str, exc_info: bool = True, **kwargs):
        """Логирование исключения с трассировкой"""
        self.logger.exception(message, exc_info=exc_info, **kwargs)


# Глобальный экземпляр логгера
logger = StorageLogger()