import subprocess
from typing import Optional
import threading
import socket
import time
import select
import fcntl
import os

from agent.client.logger_config import DefaultLogger

logger = DefaultLogger("VNCLogger")


class VNCWebSocketProxy:
    """
    Класс для управления VNC WebSocket прокси
    """

    def __init__(self, vnc_host: str = "localhost", vnc_port: int = 5900):
        self.vnc_host = vnc_host
        self.vnc_port = vnc_port
        self.process = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
        self.ws_port = None

    def start_proxy(self, ws_port: int = 6080, target_host: str = None, target_port: int = None):
        """
        Запуск WebSocket прокси для VNC

        Args:
            ws_port: Порт для WebSocket соединений
            target_host: Хост VNC сервера (если не указан, используется self.vnc_host)
            target_port: Порт VNC сервера (если не указан, используется self.vnc_port)
        """
        target_host = target_host or self.vnc_host
        target_port = target_port or self.vnc_port
        self.ws_port = ws_port

        # Проверяем, доступен ли порт
        if not self._is_port_available(ws_port):
            logger.error(f"Порт {ws_port} уже занят")
            # Находим свободный порт
            ws_port = self._find_free_port()
            logger.info(f"Используем свободный порт: {ws_port}")
            self.ws_port = ws_port

        # Используем subprocess для запуска websockify
        import subprocess
        import sys

        # Формируем команду для websockify
        cmd = [
            sys.executable, '-m', 'websockify',
            '--verbose',
            str(ws_port),
            f'{target_host}:{target_port}'
        ]

        logger.info(f"Запуск websockify: {' '.join(cmd)}")

        # Запускаем websockify в отдельном потоке
        def run_websockify():
            try:
                self.running = True
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )

                fcntl.fcntl(self.process.stdout, fcntl.F_SETFL, os.O_NONBLOCK)
                fcntl.fcntl(self.process.stderr, fcntl.F_SETFL, os.O_NONBLOCK)

                while self.running and self.process.poll() is None:
                    try:
                        # Читаем stdout
                        ready = select.select([self.process.stdout, self.process.stderr], [], [], 0.1)[0]
                        for stream in ready:
                            line = stream.readline()
                            if line:
                                logger.debug(f"websockify: {line.strip()}")
                    except (IOError, OSError):
                        pass

                    time.sleep(0.1)

                # Читаем оставшийся вывод
                stdout, stderr = self.process.communicate(timeout=1)
                if stdout:
                    logger.debug(f"websockify stdout: {stdout}")
                if stderr:
                    logger.warning(f"websockify stderr: {stderr}")

                logger.info(f"Websockify процесс завершился с кодом: {self.process.returncode}")

            except Exception as e:
                logger.error(f"Ошибка в WebSocket прокси: {e}")
                self.running = False

        self.server_thread = threading.Thread(target=run_websockify, daemon=True)
        self.server_thread.start()

        # Даем время на запуск
        time.sleep(1)

        # Проверяем, запустился ли процесс
        if self.process and self.process.poll() is None:
            logger.info(
                f"Запущен VNC WebSocket прокси на порту {ws_port}, перенаправление на {target_host}:{target_port}")
            return True
        else:
            logger.error("Не удалось запустить WebSocket прокси")
            self.running = False
            return False

    def _is_port_available(self, port: int) -> bool:
        """Проверка доступности порта"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            return result != 0
        except Exception:
            return False

    def _find_free_port(self, start_port: int = 6080) -> int:
        """Поиск свободного порта"""
        for port in range(start_port, start_port + 100):
            if self._is_port_available(port):
                return port
        raise RuntimeError("Не удалось найти свободный порт")

    def stop_proxy(self):
        """Остановка WebSocket прокси"""
        self.running = False
        if self.process:
            try:
                import signal
                self.process.send_signal(signal.SIGTERM)
                self.process.wait(timeout=5)
                logger.info("VNC WebSocket прокси остановлен")
            except subprocess.TimeoutExpired:
                self.process.kill()
                logger.warning("WebSocket прокси принудительно завершен")
            except Exception as e:
                logger.error(f"Ошибка остановки прокси: {e}")
        self.process = None

    def get_proxy_status(self) -> dict:
        """Получение статуса прокси"""
        return {
            "running": self.running and self.process and self.process.poll() is None,
            "vnc_target": f"{self.vnc_host}:{self.vnc_port}",
            "ws_port": self.ws_port,
            "thread_alive": self.server_thread and self.server_thread.is_alive() if self.server_thread else False,
            "process_alive": self.process and self.process.poll() is None if self.process else False
        }


class VNCConnectionManager:
    """
    Менеджер VNC соединений для разных виртуальных машин
    """

    def __init__(self):
        self.proxies: dict[str, VNCWebSocketProxy] = {}
        self.vm_vnc_ports: dict[str, int] = {}  # Соответствие VM -> VNC порт

    async def get_vnc_port_for_vm(self, vm_name: str) -> int:
        """
        Получение VNC порта для виртуальной машины
        В реальной системе здесь должна быть логика получения порта из libvirt
        """
        # TODO: Интегрировать с libvirt для получения реального VNC порта
        # Для тестирования возвращаем стандартный порт 5900
        if vm_name not in self.vm_vnc_ports:
            # Проверяем доступные порты VNC
            for port in [5900, 5901, 5902, 5903, 5904]:
                if self._check_vnc_port(port):
                    self.vm_vnc_ports[vm_name] = port
                    logger.info(f"Используем VNC порт {port} для VM {vm_name}")
                    break
            else:
                # Если не нашли доступный порт, используем 5900
                self.vm_vnc_ports[vm_name] = 5900
                logger.warning(f"Не удалось найти доступный VNC порт для {vm_name}, используем 5900")

        return self.vm_vnc_ports[vm_name]

    def _check_vnc_port(self, port: int) -> bool:
        """Проверка доступности VNC порта"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            return result == 0  # Если порт доступен (VNC сервер слушает)
        except Exception:
            return False

    def start_vnc_proxy(self, vm_name: str, vnc_port: int, ws_port: int = None) -> int:
        """
        Запуск прокси для конкретной VM

        Args:
            vm_name: Имя виртуальной машины
            vnc_port: Порт VNC сервера VM
            ws_port: Порт для WebSocket (если None, будет выбран автоматически)

        Returns:
            Порт WebSocket
        """
        # Генерируем уникальный WebSocket порт для VM если не указан
        if ws_port is None:
            ws_port = 6080 + abs(hash(vm_name)) % 1000

        # Останавливаем существующий прокси если есть
        if vm_name in self.proxies:
            self.stop_vnc_proxy(vm_name)

        # Создаем и запускаем прокси
        proxy = VNCWebSocketProxy("localhost", vnc_port)
        if proxy.start_proxy(ws_port):
            self.proxies[vm_name] = proxy
            logger.info(f"Прокси для {vm_name} запущен на порту {ws_port}")
            return ws_port
        else:
            logger.error(f"Не удалось запустить прокси для {vm_name}")
            # Пробуем другой порт
            new_ws_port = ws_port + 1
            return self.start_vnc_proxy(vm_name, vnc_port, new_ws_port)

    def stop_vnc_proxy(self, vm_name: str):
        """Остановка прокси для VM"""
        if vm_name in self.proxies:
            self.proxies[vm_name].stop_proxy()
            del self.proxies[vm_name]
            logger.info(f"Прокси для {vm_name} остановлен")

    def get_vm_proxy_status(self, vm_name: str) -> Optional[dict]:
        """Получение статуса прокси для VM"""
        if vm_name in self.proxies:
            return self.proxies[vm_name].get_proxy_status()
        return None

    def cleanup(self):
        """Очистка всех прокси"""
        for vm_name in list(self.proxies.keys()):
            self.stop_vnc_proxy(vm_name)
