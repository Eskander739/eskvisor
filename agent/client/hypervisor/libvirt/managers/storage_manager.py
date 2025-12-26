import re
import os
import shutil
import json
import subprocess
from datetime import datetime
from pathlib import Path

from agent.client.cli import CLIControl
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.config import LibvirtConfig
from agent.client.hypervisor.models.disk import (
    Disk, DiskCreate, DiskUpdate, DiskAttach, DiskDetach, DiskQuery,
    DiskFormat, DiskType, DiskStatus, BusType
)
from agent.client.logger_config import logger


class StorageManager(LibvirtClient):
    """
    Управление хранилищами виртуальных дисков через qemu-img
    """

    def __init__(self, connection_uri: str = "qemu:///system"):
        """Инициализация StorageManager с логированием"""
        super().__init__(connection_uri)
        self.logger = logger
        self.cli = CLIControl()
        self.libvirt_config = LibvirtConfig()
        self._validate_qemu_img()

    def _validate_qemu_img(self):
        """Проверить наличие qemu-img"""
        try:
            result = subprocess.run(["qemu-img", "--version"],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError("qemu-img не найден или не работает")
            self.logger.info(f"qemu-img доступен: {result.stdout.splitlines()[0]}")
        except Exception as e:
            self.logger.error(f"Ошибка проверки qemu-img: {e}")
            raise

    def _execute_qemu_img(self, command: list[str], check: bool = True) -> dict:
        """Выполнить команду qemu-img и получить результат"""
        try:
            self.logger.debug(f"Выполнение qemu-img: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True)

            if check and result.returncode != 0:
                raise RuntimeError(f"qemu-img ошибка: {result.stderr}")

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            self.logger.error(f"Ошибка выполнения qemu-img: {e}")
            raise

    def create_disk(self, disk_create: DiskCreate) -> Disk | None:
        """
        Создать новый виртуальный диск через qemu-img

        Args:
            disk_create: Модель для создания диска

        Returns:
            Disk: Созданный диск или None при ошибке
        """
        try:
            self.logger.info(f"Создание диска: {disk_create.name}, размер: {disk_create.size_gb}GB")

            # Определяем путь для диска
            if disk_create.path:
                disk_path = disk_create.path
            else:
                # Генерация пути по умолчанию
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                disk_name = f"{disk_create.name}_{timestamp}.{disk_create.format.value}"
                disk_path = f"/var/lib/libvirt/images/{disk_name}"

            # Проверяем и создаем директорию
            disk_dir = os.path.dirname(disk_path)
            Path(disk_dir).mkdir(parents=True, exist_ok=True)

            # Формируем команду создания диска
            cmd = ["qemu-img", "create", "-f", disk_create.format.value]

            # Добавляем опции для sparse дисков
            if disk_create.sparse:
                cmd.extend(["-o", "preallocation=off"])
            else:
                cmd.extend(["-o", "preallocation=full"])

            cmd.extend([disk_path, f"{disk_create.size_gb}G"])

            # Выполняем создание диска
            self._execute_qemu_img(cmd)

            self.logger.info(f"Диск создан: {disk_path}")
            return self.get_disk_info(path=disk_path)

        except Exception as e:
            self.logger.exception(f"Ошибка при создании диска: {e}")
            return None

    def delete_disk(self, path: str) -> bool:
        """
        Удалить виртуальный диск

        Args:
            path: Путь к файлу диска

        Returns:
            bool: Успешность операции
        """
        try:
            self.logger.info(f"Удаление диска: {path}")

            if not os.path.exists(path):
                self.logger.warning(f"Файл {path} не существует")
                return False

            # Проверяем, не используется ли диск
            if self._is_disk_in_use(path):
                self.logger.warning(f"Диск {path} используется и не может быть удален")
                return False

            # Просто удаляем файл
            os.remove(path)
            self.logger.info(f"Диск удален: {path}")
            return True

        except Exception as e:
            self.logger.exception(f"Ошибка при удалении диска: {e}")
            return False

    def _is_disk_in_use(self, disk_path: str) -> bool:
        """Проверить, используется ли диск (упрощенная версия)"""
        try:
            # В реальном приложении здесь должна быть проверка через libvirt
            # или мониторинг процессов
            self.logger.debug(f"Проверка использования диска: {disk_path}")

            # Проверяем, открыт ли файл каким-либо процессом
            # Это упрощенная проверка для Linux
            if os.name == 'posix':
                cmd = ["lsof", disk_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    self.logger.warning(f"Диск {disk_path} используется процессом")
                    return True

            return False

        except Exception as e:
            self.logger.error(f"Ошибка при проверке использования диска: {e}")
            return True  # В случае ошибки считаем, что диск используется

    def edit_disk(self, path: str, disk_update: DiskUpdate) -> Disk | None:
        """
        Изменить параметры виртуального диска

        Args:
            path: Путь к файлу диска
            disk_update: Модель обновления диска

        Returns:
            Disk: Обновленный диск или None при ошибке
        """
        if not disk_update:
            self.logger.error("Не предоставлена модель обновления диска")
            return None

        try:
            self.logger.info(f"Изменение диска: {path}")

            original_path = path
            changes = []

            # Переименование
            if disk_update.name is not None:
                new_path = os.path.join(os.path.dirname(path), disk_update.name)
                self.logger.info(f"Переименование {path} в {new_path}")
                shutil.move(path, new_path)
                changes.append(f"имя изменено на {disk_update.name}")
                path = new_path

            # Изменение размера
            if disk_update.new_size_gb is not None:
                # Получаем текущий размер
                disk_info = self.get_disk_info(path=path)
                if not disk_info:
                    raise RuntimeError("Не удалось получить информацию о диске")

                current_size_gb = disk_info.get_effective_size_gb()
                self.logger.info(f"Текущий размер: {current_size_gb}GB, новый: {disk_update.new_size_gb}GB")

                # Изменяем размер через qemu-img
                cmd = ["qemu-img", "resize", path, f"{disk_update.new_size_gb}G"]

                # Для уменьшения размера нужен флаг --shrink
                if disk_update.new_size_gb < current_size_gb:
                    cmd.append("--shrink")

                self._execute_qemu_img(cmd)
                changes.append(f"размер изменен на {disk_update.new_size_gb}GB")

            # Конвертация формата
            if disk_update.format is not None:
                disk_info = self.get_disk_info(path=path)
                if disk_info and disk_info.format != disk_update.format:
                    new_path = f"{os.path.splitext(path)[0]}.{disk_update.format.value}"
                    self.logger.info(f"Конвертация {path} в {disk_update.format.value}")

                    if self.convert_disk_format(path, new_path, disk_update.format):
                        if path != original_path:
                            os.remove(path)
                        path = new_path
                        changes.append(f"формат изменен на {disk_update.format.value}")

            if changes:
                self.logger.info(f"Диск изменен: {', '.join(changes)}")
                return self.get_disk_info(path=path)
            else:
                self.logger.info("Не указано изменений для диска")
                return self.get_disk_info(path=path)

        except Exception as e:
            self.logger.exception(f"Ошибка при изменении диска {path}: {e}")
            return None

    def clone_disk(self, source_path: str, target_path: str,
                   target_format: DiskFormat | None = None,
                   sparse: bool = True) -> Disk | None:
        """
        Клонировать виртуальный диск

        Args:
            source_path: Путь к исходному диску
            target_path: Путь для клонированного диска
            target_format: Формат клонированного диска (если None, сохраняет исходный формат)
            sparse: Создать разреженный клон

        Returns:
            Disk: Клонированный диск или None при ошибке
        """
        try:
            self.logger.info(f"Клонирование диска: {source_path} -> {target_path}")

            # Проверяем существование исходного диска
            if not os.path.exists(source_path):
                self.logger.error(f"Исходный диск {source_path} не существует")
                return None

            # Проверяем, что директория для сохранения существует
            target_dir = os.path.dirname(target_path)
            Path(target_dir).mkdir(parents=True, exist_ok=True)

            # Получаем информацию об исходном диске
            source_info = self.get_disk_info(source_path)
            if not source_info:
                self.logger.error(f"Не удалось получить информацию об исходном диске {source_path}")
                return None

            # Определяем формат клона
            if target_format is None:
                target_format = source_info.format

            # Формируем команду клонирования через qemu-img convert
            cmd = ["qemu-img", "convert"]

            # Добавляем опции для sparse дисков
            if sparse:
                cmd.extend(["-S", "0"])
            else:
                cmd.extend(["-S", "4k"])

            # Формат назначения
            cmd.extend(["-O", target_format.value])

            # Источник и назначение
            cmd.extend([source_path, target_path])

            self.logger.debug(f"Выполнение команды клонирования: {' '.join(cmd)}")

            # Выполняем клонирование
            self._execute_qemu_img(cmd)

            self.logger.info(f"Диск успешно клонирован: {target_path}")

            # Получаем информацию о клонированном диске
            return self.get_disk_info(path=target_path)

        except Exception as e:
            self.logger.exception(f"Ошибка при клонировании диска: {e}")
            return None

    def attach_disk_to_vm(self, disk_attach: DiskAttach | None = None) -> Disk | None:
        """
        Добавить диск к виртуальной машине

        Args:
            disk_attach: Модель для подключения диска (опционально)

        Returns:
            Disk: Подключенный диск или None при ошибке
        """
        try:
            if not self.conn:
                self.logger.error("Отсутствует подключение к libvirt")
                return None

            self.logger.info(f"Попытка подключения диска {disk_attach.path} к ВМ {disk_attach.vm_name}")

            # Находим ВМ
            vm = self.conn.lookupByName(disk_attach.vm_name)
            self.logger.debug(f"ВМ {disk_attach.vm_name} найдена")

            # Получаем информацию о диске
            disk_info = self.get_disk_info(path=disk_attach.path)
            if not disk_info:
                self.logger.error(f"Не удалось получить информацию о диске {disk_attach.path}")
                return None

            # Создаем конфигурацию подключения
            if not disk_attach:
                # Автоматически определяем параметры
                target_dev = self._find_free_disk_device(vm)
                bus_type = BusType.VIRTIO
                cache_mode = "writethrough"
                self.logger.debug(f"Автоматическая конфигурация: target_dev={target_dev}, bus_type={bus_type}")
            else:
                target_dev = disk_attach.target_dev
                bus_type = disk_attach.bus_type
                cache_mode = disk_attach.cache_mode.value if disk_attach.cache_mode else "writethrough"
                self.logger.debug(f"Ручная конфигурация: target_dev={target_dev}, bus_type={bus_type}")

            # Создаем XML для устройства диска
            disk_xml = f'''
            <disk type='file' device='disk'>
                <driver name='qemu' type='{disk_info.format.value}' cache='{cache_mode}'/>
                <source file='{disk_attach.path}'/>
                <target dev='{target_dev}' bus='{bus_type.value}'/>
                <address type='pci' domain='0x0000' bus='0x00' slot='0x0a' function='0x0'/>
            </disk>
            '''

            self.logger.debug(f"XML для подключения диска:\n{disk_xml}")

            # Присоединяем диск к ВМ
            vm.attachDevice(disk_xml)
            self.logger.info(f"Диск {disk_attach.path} успешно добавлен к ВМ {disk_attach.vm_name} как {target_dev}")

            # Обновляем информацию о диске
            disk_info.vm_name = disk_attach.vm_name
            disk_info.status = DiskStatus.ATTACHED
            disk_info.target_dev = target_dev
            disk_info.bus_type = bus_type

            return disk_info

        except Exception as e:
            self.logger.exception(f"Ошибка при добавлении диска к ВМ {disk_attach.vm_name}: {e}")
            return None

    def detach_disk_from_vm(self, detach_disk: DiskDetach) -> bool:
        """
        Отключить диск от виртуальной машины

        Args:
            detach_disk: данные для отключения диска

        Returns:
            bool: Успешность операции
        """
        try:
            if not self.conn:
                self.logger.error("Отсутствует подключение к libvirt")
                return False

            self.logger.info(f"Попытка отключения диска {detach_disk.target_dev} от ВМ {detach_disk.vm_name}")

            vm = self.conn.lookupByName(detach_disk.vm_name)

            # Получаем текущую конфигурацию ВМ
            xml_desc = vm.XMLDesc()

            # Находим XML блока диска для данного устройства
            lines = xml_desc.split('\n')
            disk_start = -1
            disk_end = -1

            for i, line in enumerate(lines):
                if f"<target dev='{detach_disk.target_dev}'" in line:
                    # Ищем начало блока диска
                    for j in range(i, -1, -1):
                        if '<disk ' in lines[j]:
                            disk_start = j
                            break
                    # Ищем конец блока диска
                    for j in range(i, len(lines)):
                        if '</disk>' in lines[j]:
                            disk_end = j
                            break
                    break

            if disk_start != -1 and disk_end != -1:
                # Извлекаем XML диска
                disk_xml = '\n'.join(lines[disk_start:disk_end + 1])
                self.logger.debug(f"Найден XML диска:\n{disk_xml}")

                # Отключаем диск
                vm.detachDevice(disk_xml)

                self.logger.info(f"Диск {detach_disk.target_dev} успешно отключен от ВМ {detach_disk.vm_name}")
                return True
            else:
                self.logger.error(
                    f"Устройство {detach_disk.target_dev} не найдено в конфигурации ВМ {detach_disk.vm_name}")
                return False

        except Exception as e:
            self.logger.exception(f"Ошибка при отключении диска от ВМ {detach_disk.vm_name}: {e}")
            return False

    def _find_free_disk_device(self, vm) -> str:
        """Найти свободное устройство диска в ВМ"""
        try:
            xml_desc = vm.XMLDesc()
            used_devices = set()

            # Ищем используемые устройства
            lines = xml_desc.split('\n')
            for line in lines:
                if "target dev=" in line:
                    match = re.search(r"dev=['\"]([vs]d[a-z]+)['\"]", line)
                    if match:
                        used_devices.add(match.group(1))

            self.logger.debug(f"Используемые устройства в ВМ {vm.name()}: {used_devices}")

            # Находим первое свободное устройство
            for letter in "bcdefghijklmnopqrstuvwxyz":
                dev_vd = f"vd{letter}"
                dev_sd = f"sd{letter}"
                if dev_vd not in used_devices:
                    self.logger.debug(f"Найдено свободное устройство: {dev_vd}")
                    return dev_vd
                if dev_sd not in used_devices:
                    self.logger.debug(f"Найдено свободное устройство: {dev_sd}")
                    return dev_sd

            # Если все устройства заняты, используем следующее
            next_device = f"vd{chr(ord('a') + len(used_devices))}"
            self.logger.warning(f"Все стандартные устройства заняты, используем {next_device}")
            return next_device

        except Exception as e:
            self.logger.error(f"Ошибка при поиске свободного устройства: {e}")
            return "vdb"

    def get_disk_info(self, path: str) -> Disk | None:
        """
        Получить информацию о диске через qemu-img info

        Args:
            path: Путь к файлу диска

        Returns:
            Disk: Информация о диске или None при ошибке
        """
        try:
            if not os.path.exists(path):
                self.logger.error(f"Файл {path} не существует")
                return None

            # Получаем информацию через qemu-img
            cmd = ["qemu-img", "info", "--output=json", path]
            result = self._execute_qemu_img(cmd, check=False)

            if result["returncode"] != 0:
                self.logger.error(f"Ошибка получения информации о диске: {result['stderr']}")
                return None

            info = json.loads(result["stdout"])

            # Определяем формат диска
            try:
                disk_format = DiskFormat(info["format"])
            except ValueError:
                disk_format = DiskFormat.UNKNOWN

            # Определяем тип диска
            disk_type = DiskType.EXTERNAL_DISK

            # Проверяем, используется ли диск
            status = DiskStatus.DETACHED
            if self._is_disk_in_use(path):
                status = DiskStatus.ATTACHED
                disk_type = DiskType.VM_ATTACHED

            # Создаем объект Disk
            disk = Disk(
                name=os.path.basename(path),
                path=path,
                type=disk_type,
                format=disk_format,
                capacity_bytes=info.get("virtual-size", 0),
                allocation_bytes=info.get("actual-size", 0),
                status=status,
                created=datetime.fromtimestamp(os.path.getctime(path))
            )

            # Добавляем дополнительную информацию из qemu-img
            # if "snapshots" in info:
            #     disk.snapshot_count = len(info["snapshots"])

            # if "format-specific" in info:
            #     disk.format_specific = info["format-specific"]

            self.logger.debug(
                f"Информация о диске {path}: формат={disk_format}, размер={disk.get_effective_size_gb():.2f}GB")
            return disk

        except Exception as e:
            self.logger.exception(f"Ошибка при получении информации о диске {path}: {e}")
            return None

    def list_disks(self, query: DiskQuery | None = None) -> list[Disk]:
        """
        Получить список всех дисков с фильтрацией

        Args:
            query: Параметры фильтрации

        Returns:
            list[Disk]: Список дисков
        """
        current_disks = []
        try:
            self.logger.info(f"Получение списка дисков с фильтрацией: {query}")

            # Стандартные директории для поиска дисков
            search_dirs = []

            if query and query.search_path:
                if isinstance(query.search_path, str):
                    search_dirs.append(query.search_path)
                elif isinstance(query.search_path, list):
                    search_dirs.extend(query.search_path)
            else:
                search_dirs = self.libvirt_config.search_dirs

            # Ищем диски в директориях
            for dir_path in search_dirs:
                if os.path.exists(dir_path) and os.path.isdir(dir_path):
                    self.logger.debug(f"Поиск дисков в: {dir_path}")

                    for root, dirs, files in os.walk(dir_path):
                        for file_name in files:
                            file_path = os.path.join(root, file_name)

                            # Проверяем расширение файла
                            if self._is_disk_file(file_path):
                                try:
                                    disk_info = self.get_disk_info(file_path)
                                    if disk_info:
                                        # Применяем фильтры
                                        if self._filter_disk(disk_info, query):
                                            current_disks.append(disk_info)
                                except Exception as e:
                                    self.logger.debug(f"Ошибка при обработке {file_name}: {e}")
                                    continue

            self.logger.info(f"Найдено дисков: {len(current_disks)}")
            return current_disks

        except Exception as e:
            self.logger.exception(f"Ошибка при получении списка дисков: {e}")
            return []

    def _is_disk_file(self, file_path: str) -> bool:
        """Проверить, является ли файл виртуальным диском"""

        file_ext = os.path.splitext(file_path)[1].lower()
        return os.path.isfile(file_path) and file_ext in self.libvirt_config.disk_extensions

    def _filter_disk(self, disk: Disk, query: DiskQuery | None) -> bool:
        """Применить фильтры к диску"""
        if not query:
            return True

        # Фильтр по формату
        if query.format and disk.format != query.format:
            return False

        # Фильтр по размеру
        size_gb = disk.get_effective_size_gb()
        if query.min_size_gb is not None and size_gb < query.min_size_gb:
            return False
        if query.max_size_gb is not None and size_gb > query.max_size_gb:
            return False

        # Фильтр по ВМ
        if query.vm_name and disk.vm_name != query.vm_name:
            return False

        # Фильтр по подключенным дискам
        if query.attached_only is not None:
            if query.attached_only and disk.status != DiskStatus.ATTACHED:
                return False
            elif not query.attached_only and disk.status == DiskStatus.ATTACHED:
                return False

        return True

    def convert_disk_format(self, source_path: str, target_path: str,
                            target_format: DiskFormat, sparse: bool = True) -> bool:
        """
        Конвертировать диск из одного формата в другой

        Args:
            source_path: Путь к исходному диску
            target_path: Путь для сохранения конвертированного диска
            target_format: Целевой формат диска
            sparse: Создать разреженный диск

        Returns:
            bool: Успешность операции
        """
        try:
            if not os.path.exists(source_path):
                self.logger.error(f"Исходный файл {source_path} не существует")
                return False

            # Проверяем, что директория для сохранения существует
            target_dir = os.path.dirname(target_path)
            Path(target_dir).mkdir(parents=True, exist_ok=True)

            # Формируем команду конвертации
            cmd = ["qemu-img", "convert", "-O", target_format.value]

            if sparse:
                cmd.extend(["-S", "0"])
            else:
                cmd.extend(["-S", "4k"])

            cmd.extend([source_path, target_path])

            self.logger.info(f"Конвертация диска: {source_path} -> {target_path} ({target_format.value})")
            self._execute_qemu_img(cmd)

            self.logger.info("Конвертация успешно завершена")
            return True

        except Exception as e:
            self.logger.exception(f"Ошибка при конвертации диска: {e}")
            return False

    def create_snapshot(self, disk_path: str, snapshot_name: str) -> bool:
        """
        Создать снапшот диска

        Args:
            disk_path: Путь к диску
            snapshot_name: Имя снапшота

        Returns:
            bool: Успешность операции
        """
        try:
            self.logger.info(f"Создание снапшота {snapshot_name} для диска {disk_path}")

            # Проверяем формат диска (снапшоты поддерживаются только для qcow2)
            disk_info = self.get_disk_info(disk_path)
            if disk_info.format != DiskFormat.QCOW2:
                self.logger.error("Снапшоты поддерживаются только для формата QCOW2")
                return False

            cmd = ["qemu-img", "snapshot", "-c", snapshot_name, disk_path]
            self._execute_qemu_img(cmd)

            self.logger.info(f"Снапшот {snapshot_name} создан")
            return True

        except Exception as e:
            self.logger.exception(f"Ошибка при создании снапшота: {e}")
            return False

    def delete_snapshot(self, disk_path: str, snapshot_name: str) -> bool:
        """
        Удалить снапшот диска

        Args:
            disk_path: Путь к диску
            snapshot_name: Имя снапшота

        Returns:
            bool: Успешность операции
        """
        try:
            self.logger.info(f"Удаление снапшота {snapshot_name} с диска {disk_path}")

            cmd = ["qemu-img", "snapshot", "-d", snapshot_name, disk_path]
            result = self._execute_qemu_img(cmd, check=False)

            if result["returncode"] != 0:
                self.logger.error(f"Ошибка удаления снапшота: {result['stderr']}")
                return False

            self.logger.info(f"Снапшот {snapshot_name} удален")
            return True

        except Exception as e:
            self.logger.exception(f"Ошибка при удалении снапшота: {e}")
            return False

    def list_snapshots(self, disk_path: str) -> list[dict]:
        """
        Получить список снапшотов диска

        Args:
            disk_path: Путь к диску

        Returns:
            list[dict]: Список снапшотов
        """
        try:
            self.logger.debug(f"Получение списка снапшотов для диска {disk_path}")

            cmd = ["qemu-img", "snapshot", "-l", disk_path]
            result = self._execute_qemu_img(cmd, check=False)

            if result["returncode"] != 0:
                return []

            snapshots = []
            lines = result["stdout"].strip().split('\n')

            # Пропускаем заголовок
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    snapshot = {
                        "id": parts[0],
                        "name": parts[1],
                        "date": parts[2] + " " + parts[3] if len(parts) > 3 else parts[2]
                    }
                    snapshots.append(snapshot)

            return snapshots

        except Exception as e:
            self.logger.error(f"Ошибка при получении списка снапшотов: {e}")
            return []

    def check_disk(self, disk_path: str) -> dict:
        """
        Проверить целостность диска

        Args:
            disk_path: Путь к диску

        Returns:
            dict: Результаты проверки
        """
        try:
            self.logger.info(f"Проверка целостности диска: {disk_path}")

            cmd = ["qemu-img", "check", disk_path]
            result = self._execute_qemu_img(cmd, check=False)

            check_result = {
                "path": disk_path,
                "success": result["returncode"] == 0,
                "output": result["stdout"],
                "errors": result["stderr"]
            }

            if check_result["success"]:
                self.logger.info(f"Диск {disk_path} проверен успешно")
            else:
                self.logger.warning(f"Найдены ошибки в диске {disk_path}: {result['stderr']}")

            return check_result

        except Exception as e:
            self.logger.exception(f"Ошибка при проверке диска: {e}")
            return {"path": disk_path, "success": False, "error": str(e)}

    def benchmark_disk(self, disk_path: str) -> dict:
        """
        Запустить бенчмарк диска

        Args:
            disk_path: Путь к диску

        Returns:
            dict: Результаты бенчмарка
        """
        try:
            self.logger.info(f"Запуск бенчмарка диска: {disk_path}")

            # Создаем временный файл для бенчмарка
            temp_file = f"{disk_path}.benchmark.tmp"

            # Измеряем скорость записи
            write_cmd = [
                "qemu-img", "bench", "-w", "-t", "none",
                "-f", "raw", "-c", "1000", temp_file
            ]

            write_result = self._execute_qemu_img(write_cmd, check=False)

            # Измеряем скорость чтения
            read_cmd = [
                "qemu-img", "bench", "-r", "-t", "none",
                "-f", "raw", "-c", "1000", temp_file
            ]

            read_result = self._execute_qemu_img(read_cmd, check=False)

            # Удаляем временный файл
            if os.path.exists(temp_file):
                os.remove(temp_file)

            # Анализируем результаты
            benchmark_result = {
                "path": disk_path,
                "write_speed": self._parse_benchmark_output(write_result["stdout"]),
                "read_speed": self._parse_benchmark_output(read_result["stdout"])
            }

            self.logger.info(
                f"Бенчмарк завершен: запись={benchmark_result['write_speed']}, чтение={benchmark_result['read_speed']}")
            return benchmark_result

        except Exception as e:
            self.logger.exception(f"Ошибка при запуске бенчмарка: {e}")
            return {"path": disk_path, "error": str(e)}

    def _parse_benchmark_output(self, output: str) -> str:
        """Парсить вывод бенчмарка"""
        lines = output.strip().split('\n')
        for line in lines:
            if "throughput" in line.lower():
                return line.strip()
        return "N/A"

    def discover_disks(self, search_path: str | None = None) -> list[Disk]:
        """
        Обнаружить диски в файловой системе

        Args:
            search_path: Путь для поиска дисков

        Returns:
            list[Disk]: Список обнаруженных дисков
        """
        return self.list_disks(DiskQuery(search_path=search_path))

    def find_disk_by_path_pattern(self, pattern: str) -> list[Disk]:
        """
        Найти диски по шаблону пути

        Args:
            pattern: Регулярное выражение для поиска в путях

        Returns:
            list[Disk]: Найденные диски
        """
        current_disks = []
        try:
            self.logger.info(f"Поиск дисков по шаблону: {pattern}")

            regex = re.compile(pattern, re.IGNORECASE)
            all_disks = self.list_disks()

            for disk in all_disks:
                if regex.search(disk.path):
                    current_disks.append(disk)

            self.logger.info(f"Найдено {len(current_disks)} дисков по шаблону {pattern}")
            return current_disks

        except re.error as e:
            self.logger.error(f"Неверное регулярное выражение {pattern}: {e}")
            return []
        except Exception as e:
            self.logger.exception(f"Ошибка при поиске дисков по шаблону {pattern}: {e}")
            return []

    def get_storage_summary(self, directory: str = "/var/lib/libvirt/images") -> dict:
        """
        Получить сводку по хранилищу в директории

        Args:
            directory: Директория для анализа

        Returns:
            dict: Сводка по хранилищу
        """
        try:
            self.logger.info(f"Анализ хранилища в директории: {directory}")

            if not os.path.exists(directory):
                return {"error": f"Директория {directory} не существует"}

            disks = self.list_disks(DiskQuery(search_path=directory))

            total_size = sum(d.capacity_bytes for d in disks)
            total_allocated = sum(d.allocation_bytes for d in disks)

            # Статистика по форматам
            format_stats = {}
            for disk in disks:
                fmt = disk.format.value if disk.format else 'unknown'
                format_stats[fmt] = format_stats.get(fmt, 0) + 1

            summary = {
                "directory": directory,
                "total_disks": len(disks),
                "total_size_gb": round(total_size / (1024 ** 3), 2),
                "total_allocated_gb": round(total_allocated / (1024 ** 3), 2),
                "free_space_gb": round((total_size - total_allocated) / (1024 ** 3), 2),
                "usage_percentage": round((total_allocated / total_size * 100), 1) if total_size > 0 else 0,
                "format_distribution": format_stats,
                "attached_disks": len([d for d in disks if d.status == DiskStatus.ATTACHED]),
                "detached_disks": len([d for d in disks if d.status == DiskStatus.DETACHED])
            }

            self.logger.info(f"Сводка хранилища: {summary['total_disks']} дисков, {summary['total_size_gb']}GB всего")
            return summary

        except Exception as e:
            self.logger.exception(f"Ошибка при анализе хранилища: {e}")
            return {"error": str(e)}


if __name__ == "__main__":
    # Пример использования
    manager = StorageManager()

    # # Создание диска
    # disk_create = DiskCreate(
    #     name="test-disk",
    #     size_gb=10,
    #     format=DiskFormat.QCOW2,
    #     sparse=True
    # )
    #
    # disk = manager.create_disk(disk_create)
    # if disk:
    #     logger.info(f"Создан диск: {disk.name}, путь: {disk.path}")

    # Получение информации о диске
    # if disk:
    #     info = manager.get_disk_info(disk.path)
    #     logger.info(f"Информация о диске: {info}")

    # Список всех дисков
    disks = manager.list_disks()
    logger.info(f"Всего дисков: {len(disks)}")

    # # Конвертация диска
    # if disk:
    #     new_path = disk.path.replace(".qcow2", ".raw")
    #     manager.convert_disk_format(disk.path, new_path, DiskFormat.RAW)
    #
    # # Проверка диска
    # if disk:
    #     check_result = manager.check_disk(disk.path)
    #     logger.info(f"Результат проверки: {check_result}")
    #
    # # Сводка хранилища
    # summary = manager.get_storage_summary()
    # logger.info(f"Сводка хранилища: {summary}")