import subprocess
import libvirt
import os
import re
import shutil
import uuid
from datetime import datetime
from typing import List
import logging
import xml.etree.ElementTree as ET
from agent.client.hypervisor.libvirt.config import LibvirtConfig
from agent.client.hypervisor.models.disk import (
    Disk, DiskCreate, DiskUpdate, DiskAttach, DiskDetach, DiskQuery,
    DiskFormat, DiskType, DiskStatus, BusType, CacheMode
)
from agent.client.hypervisor.libvirt.client import LibvirtClient


class StorageManager(LibvirtClient):
    def __init__(self, connection_uri: str = "qemu:///session", username: str | None = None,
                 password: str | None = None):
        super().__init__(connection_uri, username, password)
        self.logger = logging.getLogger(__name__)
        self.libvirt_config = LibvirtConfig()
        self._default_storage_dir = "/var/lib/libvirt/images"

    def create_disk(self, disk_create: DiskCreate) -> Disk | None:
        try:
            self.logger.info(f"Создание диска: {disk_create.name}, размер: {disk_create.size_gb}GB")

            if disk_create.pool:
                self.logger.debug(f"Создание в пуле: {disk_create.pool}")
                return self._create_pool_disk(disk_create)
            else:
                self.logger.debug("Создание файлового диска")
                return self._create_file_disk(disk_create)

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Ошибка: {e}")
            return None

    def _create_file_disk(self, disk_create: DiskCreate) -> Disk | None:
        try:
            disk_path = self._get_disk_path(disk_create)
            disk_dir = os.path.dirname(disk_path)

            if not os.path.exists(disk_dir):
                os.makedirs(disk_dir, exist_ok=True)

            self.logger.info(f"Создание файлового диска: {disk_path}, размер: {disk_create.size_gb}GB")

            size_bytes = int(disk_create.size_gb * 1024 * 1024 * 1024)

            if disk_create.format == DiskFormat.QCOW2:
                self._create_qcow2_disk(disk_path, disk_create.size_gb, disk_create.sparse)
                if disk_create.name:
                    self._add_qcow2_metadata(disk_path, disk_create.name)
            else:
                self._create_raw_disk(disk_path, disk_create.size_gb, disk_create.sparse)
                if disk_create.name:
                    self._create_metadata_file(disk_path, disk_create)

            disk = Disk(
                name=disk_create.name or os.path.basename(disk_path),
                path=disk_path,
                file_path_exists=True,
                type=DiskType.EXTERNAL_DISK,
                format=disk_create.format,
                capacity_bytes=size_bytes,
                allocation_bytes=size_bytes,
                status=DiskStatus.DETACHED
            )

            self.logger.info(f"Файловый диск создан: {disk.name}")
            return disk

        except Exception as e:
            self.logger.exception(f"Ошибка создания файлового диска: {e}")
            return None

    def _get_disk_path(self, disk_create: DiskCreate) -> str:
        if disk_create.path:
            path = disk_create.path
            if not os.path.basename(path):
                extension = f".{disk_create.format.value}"
                filename = f"{disk_create.name}{extension}" if disk_create.name else f"disk-{uuid.uuid4().hex[:8]}{extension}"
                path = os.path.join(path, filename)
            return path

        if disk_create.name:
            extension = f".{disk_create.format.value}"
            filename = f"{disk_create.name}{extension}" if not disk_create.name.endswith(
                extension) else disk_create.name
            return os.path.join(self._default_storage_dir, filename)

        return os.path.join(self._default_storage_dir, f"disk-{uuid.uuid4().hex[:8]}.{disk_create.format.value}")

    def _create_qcow2_disk(self, disk_path: str, size_gb: float, sparse: bool = True):

        sparse_flag = [] if sparse else ["-o", "preallocation=full"]
        cmd = ["qemu-img", "create", "-f", "qcow2"] + sparse_flag + [disk_path, f"{size_gb}G"]

        self.logger.debug(f"Выполнение команды: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"Ошибка qemu-img: {result.stderr}")

    def _add_qcow2_metadata(self, disk_path: str, disk_name: str):

        try:
            metadata_cmd = [
                "qemu-img",
                "amend",
                "-f", "qcow2",
                "-o", f"name={disk_name}",
                disk_path
            ]

            self.logger.debug(f"Добавление метаданных: {' '.join(metadata_cmd)}")
            result = subprocess.run(metadata_cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self.logger.info(f"Добавлены метаданные диска: имя={disk_name}")
            else:
                self.logger.warning(f"Не удалось добавить метаданные: {result.stderr}")
        except Exception as e:
            self.logger.warning(f"Ошибка при добавлении метаданных: {e}")

    def _create_raw_disk(self, disk_path: str, size_gb: float, sparse: bool = True):
        """
        Создать RAW диск через qemu-img

        Args:
            disk_path: Путь к файлу диска
            size_gb: Размер в гигабайтах
            sparse: Создать разреженный диск (sparse file)
        """

        # Формируем команду в зависимости от sparse
        if sparse:
            # Для sparse: просто создаем без preallocation (по умолчанию sparse)
            cmd = ["qemu-img", "create", "-f", "raw", disk_path, f"{size_gb}G"]
        else:
            # Для non-sparse: принудительно выделяем все место
            cmd = ["qemu-img", "create", "-f", "raw", "-o", "preallocation=full",
                   disk_path, f"{size_gb}G"]

        self.logger.debug(f"Создание RAW диска: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"Ошибка qemu-img при создании RAW диска: {result.stderr}")

        self.logger.info(f"RAW диск создан: {disk_path}, размер: {size_gb}GB, sparse: {sparse}")

    def _create_metadata_file(self, disk_path: str, disk_create: DiskCreate):
        try:
            metadata_path = f"{disk_path}.meta"
            metadata_content = f"name={disk_create.name}\nformat={disk_create.format.value}\nsize_gb={disk_create.size_gb}"

            with open(metadata_path, 'w') as meta_file:
                meta_file.write(metadata_content)

            self.logger.info(f"Создан файл метаданных: {metadata_path}")
        except Exception as e:
            self.logger.warning(f"Не удалось создать файл метаданных: {e}")

    def _create_pool_disk(self, disk_create: DiskCreate) -> Disk | None:
        try:
            pool = self.conn.storagePoolLookupByName(disk_create.pool)
            pool_info = pool.info()

            if pool_info[0] != libvirt.VIR_STORAGE_POOL_RUNNING:
                self.logger.info(f"Активация пула {disk_create.pool}")
                pool.create()

            size_bytes = int(disk_create.size_gb * 1024 * 1024 * 1024)
            xml_desc = f'''
            <volume>
                <name>{disk_create.name}</name>
                <capacity unit="bytes">{size_bytes}</capacity>
                <target>
                    <format type='{disk_create.format.value}'/>
                    <permissions>
                        <mode>0644</mode>
                    </permissions>
                </target>
            </volume>
            '''

            vol = pool.createXML(xml_desc, 0)

            if not disk_create.sparse and disk_create.format == DiskFormat.RAW:
                self._fill_pool_raw_disk_with_zeros(vol, size_bytes)

            disk = self.get_disk_info(pool_name=disk_create.pool, disk_name=disk_create.name)

            if disk:
                self.logger.info(f"Пулловой диск создан: {disk.name}, размер: {disk.get_effective_size_gb()}GB")
            return disk

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка создания пулового диска: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
            return None

    def _fill_pool_raw_disk_with_zeros(self, vol, size_bytes: int):
        try:
            stream = self.conn.newStream()
            vol.upload(stream, 0, size_bytes, 0)

            chunk_size = 1024 * 1024
            zero_data = b'\0' * chunk_size

            for offset in range(0, size_bytes, chunk_size):
                if offset + chunk_size > size_bytes:
                    zero_data = b'\0' * (size_bytes - offset)
                stream.send(zero_data)

            stream.finish()
        except Exception as e:
            self.logger.warning(f"Не удалось заполнить диск нулями: {e}")

    def delete_disk(self, pool_name: str | None = None, disk_name: str | None = None,
                    path: str | None = None) -> bool:
        try:
            self.logger.info(f"Удаление диска: pool={pool_name}, disk={disk_name}, path={path}")

            if pool_name and disk_name:
                pool = self.conn.storagePoolLookupByName(pool_name)
                vol = pool.storageVolLookupByName(disk_name)

                if self._is_disk_in_use(vol.path()):
                    self.logger.warning(f"Диск {disk_name} используется")
                    return False

                vol.delete(0)
                self.logger.info(f"Диск {disk_name} удален из пула")
                return True

            elif path:
                if not os.path.exists(path):
                    self.logger.warning(f"Файл {path} не существует")
                    return False

                if self._is_disk_in_use(path):
                    self.logger.warning(f"Диск {path} используется")
                    return False

                os.remove(path)

                metadata_path = f"{path}.meta"
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)

                self.logger.info(f"Файл диска {path} удален")
                return True

            return False

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt: {e}")
            return False
        except Exception as e:
            self.logger.exception(f"Ошибка: {e}")
            return False

    def edit_disk(self, pool_name: str | None = None, disk_name: str | None = None,
                  path: str | None = None, disk_update: DiskUpdate | None = None) -> Disk | None:
        if not disk_update:
            self.logger.error("Не указана модель обновления")
            return None

        try:
            if pool_name and disk_name:
                return self._edit_pool_disk(pool_name, disk_name, disk_update)
            elif path:
                return self._edit_file_disk(path, disk_update)
            else:
                return None

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Ошибка: {e}")
            return None

    def _edit_pool_disk(self, pool_name: str, disk_name: str, disk_update: DiskUpdate) -> Disk | None:
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(disk_name)

            if disk_update.new_size_gb is not None:
                vol_info = vol.info()
                current_size_gb = vol_info[1] / (1024 ** 3)

                if disk_update.new_size_gb > current_size_gb:
                    new_size_bytes = int(disk_update.new_size_gb * 1024 * 1024 * 1024)
                    vol.resize(new_size_bytes, 0)
                    self.logger.info(f"Размер изменен на {disk_update.new_size_gb}GB")

            if disk_update.name is not None and disk_update.name != disk_name:
                xml_desc = vol.XMLDesc()
                new_xml = xml_desc.replace(f"<name>{disk_name}</name>", f"<name>{disk_update.name}</name>")
                new_vol = pool.createXML(new_xml, 0)
                vol.delete(0)
                disk_name = disk_update.name

            return self.get_disk_info(pool_name, disk_name)

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка изменения пулового диска: {e}")
            return None

    def _edit_file_disk(self, path: str, disk_update: DiskUpdate) -> Disk | None:
        try:
            current_disk = self.get_disk_info(path=path)
            if not current_disk:
                return None

            if disk_update.name is not None and disk_update.name != current_disk.name:
                new_path = os.path.join(os.path.dirname(path), disk_update.name)
                shutil.move(path, new_path)

                old_metadata = f"{path}.meta"
                new_metadata = f"{new_path}.meta"
                if os.path.exists(old_metadata):
                    shutil.move(old_metadata, new_metadata)

                path = new_path

            if disk_update.new_size_gb is not None:
                current_size_gb = current_disk.get_effective_size_gb()

                if disk_update.new_size_gb > current_size_gb:
                    self.logger.info(f"Увеличение размера до {disk_update.new_size_gb}GB")
                    cmd = ["qemu-img", "resize", path, f"{disk_update.new_size_gb}G"]

                    self.logger.debug(f"Выполнение команды: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True)

                    if result.returncode != 0:
                        raise Exception(f"Ошибка qemu-img: {result.stderr}")

            return self.get_disk_info(path=path)

        except Exception as e:
            self.logger.exception(f"Ошибка изменения файлового диска: {e}")
            return None

    def clone_disk(self, source_path: str, target_path: str, target_name: str = None) -> Disk | None:
        try:
            self.logger.info(f"Клонирование диска: {source_path} -> {target_path}")

            source_disk = self.get_disk_info(path=source_path)
            if not source_disk:
                return None

            target_dir = os.path.dirname(target_path)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)

            if source_disk.format == DiskFormat.QCOW2:
                cmd = ["qemu-img", "convert", "-f", "qcow2", "-O", "qcow2", source_path, target_path]
                self.logger.debug(f"Выполнение команды: {' '.join(cmd)}")

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"Ошибка qemu-img: {result.stderr}")
            else:
                shutil.copy2(source_path, target_path)

            target_name = target_name or source_disk.name
            if source_disk.format == DiskFormat.QCOW2:
                self._add_qcow2_metadata(target_path, target_name)
            elif source_disk.format == DiskFormat.RAW:
                self._create_metadata_file(target_path, DiskCreate(
                    name=target_name,
                    format=source_disk.format,
                    size_gb=source_disk.get_effective_size_gb()
                ))

            return self.get_disk_info(path=target_path)

        except Exception as e:
            self.logger.exception(f"Ошибка клонирования: {e}")
            return None

    def attach_disk(self, disk_attach: DiskAttach) -> bool:
        try:
            if not disk_attach:
                return False

            self.logger.info(f"Подключение диска {disk_attach.path} к ВМ {disk_attach.vm_name}")

            vm = self.conn.lookupByName(disk_attach.vm_name)

            if self._is_disk_attached_to_vm(disk_attach.path, disk_attach.vm_name):
                self.logger.warning(f"Диск уже подключен")
                return True

            disk_info = self.get_disk_info(path=disk_attach.path)
            if not disk_info:
                return False

            bus_type = disk_attach.bus_type or BusType.VIRTIO
            cache_mode = disk_attach.cache_mode.value if disk_attach.cache_mode else "writethrough"
            target_dev = disk_attach.target_dev or self._find_free_disk_device(vm, bus_type)

            disk_xml = f'''
            <disk type='file' device='disk'>
                <driver name='qemu' type='{disk_info.format.value}' cache='{cache_mode}'/>
                <source file='{disk_attach.path}'/>
                <target dev='{target_dev}' bus='{bus_type.value}'/>
            </disk>
            '''

            vm_state, _ = vm.state()

            if vm_state == libvirt.VIR_DOMAIN_RUNNING:
                vm.attachDeviceFlags(disk_xml,
                                     libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE | libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)
            else:
                vm.attachDeviceFlags(disk_xml, libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)

            self.logger.info(f"Диск успешно подключен как {target_dev}")
            return True

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка подключения: {e}")
            return False
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
            return False

    def get_disks_by_vm(self, vm_name: str) -> List[Disk]:
        """
        Получить все диски, подключенные к указанной ВМ
        """
        disks = []
        try:
            vm = self.conn.lookupByName(vm_name)
            xml_desc = vm.XMLDesc()
            root = ET.fromstring(xml_desc)

            for disk_element in root.findall(".//disk"):
                target = disk_element.find("target")
                if target is None:
                    continue

                target_dev = target.get("dev")
                if target_dev:
                    try:
                        disk = self.get_disk_info_by_target_dev(vm_name, target_dev)
                        disks.append(disk)
                    except Exception as e:
                        self.logger.warning(f"Не удалось получить диск {target_dev}: {e}")
                        continue

            self.logger.info(f"Найдено {len(disks)} дисков для ВМ {vm_name}")
            return disks

        except Exception as e:
            self.logger.exception(f"Ошибка при получении дисков ВМ {vm_name}: {e}")
            return []

    def get_disk_info_by_target_dev(self, vm_name: str, target_dev: str) -> Disk:
        """
        Получить информацию о диске по target_dev в конкретной ВМ
        """
        self.logger.info(f"Получение информации о диске {target_dev} для ВМ {vm_name}")

        try:
            vm = self.conn.lookupByName(vm_name)
            xml_desc = vm.XMLDesc()

            # Используем ElementTree для надежного парсинга XML
            root = ET.fromstring(xml_desc)

            # Ищем диск с указанным target_dev
            disk_element = None
            for disk in root.findall(".//disk"):
                target = disk.find("target")
                if target is not None and target.get("dev") == target_dev:
                    disk_element = disk
                    break

            if disk_element is None:
                raise ValueError(f"Диск с target_dev='{target_dev}' не найден в ВМ {vm_name}")

            # Извлекаем данные из XML
            source = disk_element.find("source")
            driver = disk_element.find("driver")
            target = disk_element.find("target")

            disk_path = source.get("file") if source is not None else None
            if not disk_path:
                raise ValueError(f"Не найден путь к диску для устройства {target_dev}")

            # Получаем формат диска
            disk_format = DiskFormat.UNKNOWN
            if driver is not None:
                driver_type = driver.get("type")
                if driver_type:
                    try:
                        disk_format = DiskFormat(driver_type)
                    except ValueError:
                        self.logger.warning(f"Неизвестный формат диска: {driver_type}")

            # Определяем имя диска из пути
            disk_name = os.path.basename(disk_path)

            # Проверяем существование файла
            file_path_exists = os.path.exists(disk_path)

            # Получаем размер файла если он существует
            capacity_bytes = None
            allocation_bytes = None
            if file_path_exists:
                capacity_bytes = os.path.getsize(disk_path)
                allocation_bytes = capacity_bytes

            # Определяем тип диска
            disk_type = DiskType.VM_ATTACHED

            # Извлекаем тип шины
            bus_type = None
            if target is not None:
                bus_str = target.get("bus")
                if bus_str:
                    try:
                        bus_type = BusType(bus_str)
                    except ValueError:
                        self.logger.debug(f"Неизвестный тип шины: {bus_str}")

            # Извлекаем режим кэширования
            cache_mode = None
            if driver is not None:
                cache_str = driver.get("cache")
                if cache_str:
                    try:
                        cache_mode = CacheMode(cache_str)
                    except ValueError:
                        self.logger.debug(f"Неизвестный режим кэширования: {cache_str}")

            # Извлекаем дополнительные параметры
            address = disk_element.find("address")
            device_type = disk_element.get("device", "disk")

            # Для QCOW2 пытаемся получить дополнительные метаданные
            backing_file = None
            if disk_format == DiskFormat.QCOW2 and file_path_exists:
                try:
                    cmd = ["qemu-img", "info", "--output=json", disk_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        import json
                        info = json.loads(result.stdout)
                        if "backing-file" in info and info["backing-file"]:
                            backing_file = info["backing-file"]
                except Exception as e:
                    self.logger.debug(f"Не удалось получить метаданные QCOW2: {e}")

            # Создаем объект Disk
            disk = Disk(
                name=disk_name,
                path=disk_path,
                file_path_exists=file_path_exists,
                type=disk_type,
                format=disk_format,
                capacity_bytes=capacity_bytes,
                allocation_bytes=allocation_bytes,
                capacity_gb=capacity_bytes / (1024 ** 3) if capacity_bytes else None,
                allocation_gb=allocation_bytes / (1024 ** 3) if allocation_bytes else None,
                vm_name=vm_name,
                status=DiskStatus.ATTACHED,
                bus_type=bus_type,
                target_dev=target_dev,
                cache_mode=cache_mode,
                backing_file=backing_file,
                readonly=(device_type == "cdrom"),
                created=datetime.fromtimestamp(os.path.getctime(disk_path)) if file_path_exists else None,
                modified=datetime.fromtimestamp(os.path.getmtime(disk_path)) if file_path_exists else None,
            )

            self.logger.info(f"Информация о диске {target_dev} получена: {disk_name}")
            return disk

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при получении диска {target_dev}: {e}")
            raise
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка при получении диска {target_dev}: {e}")
            raise

    def detach_disk(self, detach_disk: DiskDetach) -> bool:
        try:
            self.logger.info(f"Отключение диска от ВМ {detach_disk.vm_name}")

            vm = self.conn.lookupByName(detach_disk.vm_name)
            xml_desc = vm.XMLDesc()

            disk_xmls = []
            for line in xml_desc.split('\n'):
                if detach_disk.target_dev in line:
                    start_idx = xml_desc.find(line) - 176
                    end_idx = xml_desc.find('</disk>', start_idx) + 7
                    disk_xml = xml_desc[start_idx:end_idx]
                    disk_xmls.append(disk_xml)

            for current_disk in disk_xmls:
                if detach_disk.target_dev in current_disk:
                    disk_xml = current_disk
                    break
            else:
                raise ValueError(f"Не найден диск с target_dev: {detach_disk.target_dev}")
            if not disk_xml:
                self.logger.error(f"Диск не найден")
                return False

            vm_state, _ = vm.state()

            if vm_state == libvirt.VIR_DOMAIN_RUNNING:
                vm.detachDeviceFlags(disk_xml,
                                     libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE | libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)
            else:
                vm.detachDeviceFlags(disk_xml, libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)

            self.logger.info(f"Диск успешно отключен")
            return True

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка отключения: {e}")
            return False
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
            return False

    def list_disks(self, query: DiskQuery | None = None) -> List[Disk]:
        disks = []
        try:
            # disks.extend(self._get_pool_disks(query))
            disks.extend(self._get_file_disks(query))
            disks.extend(self._get_attached_disks(query))

            disks = self._remove_duplicate_disks(disks)
            disks = self._apply_filters(disks, query)

            return disks

        except Exception as e:
            self.logger.exception(f"Ошибка получения списка: {e}")
            return []

    def convert_disk_format(self, source_path: str, target_path: str,
                            target_format: DiskFormat, sparse: bool = True) -> bool:
        try:
            if not os.path.exists(source_path):
                self.logger.error(f"Исходный файл не существует")
                return False

            target_dir = os.path.dirname(target_path)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)

            sparse_flag = [] if sparse else ["-S", "0"]
            cmd = ["qemu-img", "convert"] + sparse_flag + ["-O", target_format.value, source_path, target_path]

            self.logger.info(f"Конвертация диска: {source_path} -> {target_path} ({target_format.value})")
            self.logger.debug(f"Выполнение команды: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                self.logger.error(f"Ошибка при конвертации: {result.stderr}")
                return False

            self.logger.info("Конвертация успешно завершена")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Ошибка qemu-img при конвертации: {e}")
            return False
        except Exception as e:
            self.logger.exception(f"Ошибка при конвертации диска: {e}")
            return False

    # Вспомогательные методы

    def _is_disk_in_use(self, disk_path: str) -> bool:
        try:
            vm_ids = self.conn.listDomainsID()
            all_vms = []

            for vm_id in vm_ids:
                vm = self.conn.lookupByID(vm_id)
                all_vms.append(vm)

            for vm_name in self.conn.listDefinedDomains():
                vm = self.conn.lookupByName(vm_name)
                all_vms.append(vm)

            for vm in all_vms:
                try:
                    xml_desc = vm.XMLDesc()
                    if disk_path in xml_desc:
                        return True
                except libvirt.libvirtError:
                    continue

            return False

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка проверки использования: {e}")
            return False

    def _is_disk_attached_to_vm(self, disk_path: str, vm_name: str) -> bool:
        try:
            vm = self.conn.lookupByName(vm_name)
            xml_desc = vm.XMLDesc()
            return disk_path in xml_desc
        except libvirt.libvirtError:
            return False

    def _find_free_disk_device(self, vm, bus_type: BusType = BusType.VIRTIO) -> str:
        try:
            xml_desc = vm.XMLDesc()

            prefix_map = {
                BusType.IDE: "hd",
                BusType.SCSI: "sd",
                BusType.VIRTIO: "vd",
                BusType.SATA: "sd",
                BusType.USB: "sd",
                BusType.NVME: "nvme",
                BusType.XEN: "xvd"
            }

            prefix = prefix_map.get(bus_type, "vd")
            used_devices = set()

            lines = xml_desc.split('\n')
            for line in lines:
                if 'target dev=' in line:
                    match = re.search(r"dev=['\"]([^'\"]+)['\"]", line)
                    if match:
                        used_devices.add(match.group(1))

            for letter in "abcdefghijklmnopqrstuvwxyz":
                device = f"{prefix}{letter}"
                if device not in used_devices:
                    return device

            return f"{prefix}z1"

        except Exception as e:
            self.logger.error(f"Ошибка поиска устройства: {e}")
            return "vdz"

    # def get_disk_size(self, path: str):

    def get_disk_info(self, pool_name: str | None = None, disk_name: str | None = None,
                      path: str | None = None) -> Disk | None:
        try:
            if path:
                return self._get_file_disk_info(path)
            elif pool_name and disk_name:
                return self._get_pool_disk_info(pool_name, disk_name)
            else:
                return None

        except (libvirt.libvirtError, FileNotFoundError) as e:
            self.logger.error(f"Ошибка получения информации: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
            return None

    def _get_file_disk_info(self, path: str) -> Disk | None:
        try:
            file_path_exists = os.path.exists(path)

            disk_format = DiskFormat.UNKNOWN
            if path.endswith('.qcow2'):
                disk_format = DiskFormat.QCOW2
            elif path.endswith(('.raw', '.img')):
                disk_format = DiskFormat.RAW
            elif path.endswith('.vmdk'):
                disk_format = DiskFormat.VMDK
            elif path.endswith('.vdi'):
                disk_format = DiskFormat.VDI
            elif path.endswith('.vhd') or path.endswith('.vhdx'):
                disk_format = DiskFormat.VHDX

            if file_path_exists:
                cmd = ["qemu-img", "info", path]
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode != 0:
                    raise Exception(f"Ошибка qemu-img при чтении диска: {result.stderr}")
                size_type = result.stdout.split("\n")[3].split(":")[1].split(" ")[2]
                size_data = int(result.stdout.split("\n")[3].split(":")[1].split(" ")[1])
                if size_type == "MiB":
                    size_bytes = (size_data *1024)*1024
                elif size_type == "KiB":
                    size_bytes = size_data * 1024
                elif size_type == "GiB":
                    size_bytes = ((size_data *1024)*1024)*1024
                elif size_type == "TiB":
                    size_bytes = (((size_data *1024)*1024)*1024)*1024
            else:
                size_bytes = 0

            disk_name = os.path.basename(path)

            metadata_path = f"{path}.meta"
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r') as f:
                        for line in f:
                            if line.startswith('name='):
                                print("МЕТА ДАТА: ", disk_name, "^^^", line)
                                disk_name = line.strip().split('=', 1)[1]
                                break
                except Exception:
                    pass

            disk_type = DiskType.EXTERNAL_DISK
            vm_name = None

            if self._is_disk_in_use(path):
                vm_name = self._find_vm_by_disk_path(path)
                if vm_name:
                    disk_type = DiskType.VM_ATTACHED
                    status = DiskStatus.ATTACHED
                else:
                    status = DiskStatus.DETACHED
            else:
                status = DiskStatus.DETACHED

            disk = Disk(
                name=disk_name,
                path=path,
                file_path_exists=file_path_exists,
                type=disk_type,
                format=disk_format,
                capacity_bytes=size_bytes,
                allocation_bytes=size_bytes,
                status=status,
                vm_name=vm_name
            )

            return disk

        except Exception as e:
            self.logger.exception(f"Ошибка получения файловой информации: {e}")
            return None

    def _get_pool_disk_info(self, pool_name: str, disk_name: str) -> Disk | None:
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(disk_name)

            vol_info = vol.info()
            vol_xml = vol.XMLDesc()

            disk_format = DiskFormat.UNKNOWN
            if 'type=\'qcow2\'' in vol_xml:
                disk_format = DiskFormat.QCOW2
            elif 'type=\'raw\'' in vol_xml:
                disk_format = DiskFormat.RAW

            disk_path = vol.path()
            if self._is_disk_in_use(disk_path):
                vm_name = self._find_vm_by_disk_path(disk_path)
                disk_type = DiskType.VM_ATTACHED
                status = DiskStatus.ATTACHED
            else:
                disk_type = DiskType.POOL_DISK
                status = DiskStatus.DETACHED
                vm_name = None

            disk = Disk(
                name=disk_name,
                path=disk_path,
                type=disk_type,
                format=disk_format,
                capacity_bytes=vol_info[1],
                allocation_bytes=vol_info[2],
                pool=pool_name,
                status=status,
                vm_name=vm_name
            )

            return disk

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка получения пуловой информации: {e}")
            return None

    def _find_vm_by_disk_path(self, disk_path: str) -> str | None:
        try:
            vm_ids = self.conn.listDomainsID()
            all_vms = []

            for vm_id in vm_ids:
                vm = self.conn.lookupByID(vm_id)
                all_vms.append(vm)

            for vm_name in self.conn.listDefinedDomains():
                vm = self.conn.lookupByName(vm_name)
                all_vms.append(vm)

            for vm in all_vms:
                try:
                    xml_desc = vm.XMLDesc()
                    if disk_path in xml_desc:
                        return vm.name()
                except libvirt.libvirtError:
                    continue

            return None

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка поиска ВМ: {e}")
            return None

    def _get_pool_disks(self, query: DiskQuery | None) -> List[Disk]:
        disks = []
        try:
            if query and query.pool:
                try:
                    pools = [self.conn.storagePoolLookupByName(query.pool)]
                except libvirt.libvirtError:
                    pools = []
            else:
                pools = self.conn.listAllStoragePools()

            for pool in pools:
                try:
                    pool_info = pool.info()
                    if pool_info[0] != libvirt.VIR_STORAGE_POOL_RUNNING:
                        try:
                            pool.create(0)
                        except:
                            continue

                    volumes = pool.listAllVolumes()
                    for vol in volumes:
                        try:
                            disk = self._volume_to_disk(vol, pool.name())
                            if disk:
                                disks.append(disk)
                        except libvirt.libvirtError:
                            continue

                except libvirt.libvirtError:
                    continue

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка получения пуловых дисков: {e}")
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")

        return disks

    def _get_file_disks(self, query: DiskQuery | None) -> List[Disk]:
        disks = []
        standard_dirs = [
            self._default_storage_dir,
            "/var/lib/libvirt/volumes",
            "/opt/vm_disks",
            os.path.expanduser("~/vm_disks")
        ]

        if query and hasattr(query, 'search_path'):
            standard_dirs.insert(0, query.search_path)

        for dir_path in standard_dirs:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                try:
                    for file_name in os.listdir(dir_path):
                        file_path = os.path.join(dir_path, file_name)
                        if self._is_disk_file(file_path):
                            disk_info = self._get_file_disk_info(file_path)
                            if disk_info:
                                disks.append(disk_info)
                except Exception:
                    continue

        return disks

    def _is_disk_file(self, file_path: str) -> bool:
        disk_extensions = {'.qcow2', '.raw', '.img', '.vmdk', '.vdi', '.vhd', '.vhdx'}
        return (os.path.isfile(file_path) and
                any(file_path.endswith(ext) for ext in disk_extensions))

    def _get_attached_disks(self, query: DiskQuery | None, existing_disks: List[Disk] | None = None) -> List[Disk]:
        attached_disks = []
        try:
            vm_ids = self.conn.listDomainsID()
            all_vms = []

            for vm_id in vm_ids:
                vm = self.conn.lookupByID(vm_id)
                all_vms.append(vm)

            for vm_name in self.conn.listDefinedDomains():
                vm = self.conn.lookupByName(vm_name)
                all_vms.append(vm)

            for vm in all_vms:
                try:
                    vm_name = vm.name()

                    if query and query.vm_name and query.vm_name != vm_name:
                        continue

                    xml_desc = vm.XMLDesc()
                    disk_blocks = self._extract_disk_blocks_from_vm_xml(xml_desc)

                    for disk_block in disk_blocks:
                        disk_path = disk_block.get('source_file')
                        if not disk_path:
                            continue

                        disk_exists = False
                        if existing_disks:
                            for disk in existing_disks:
                                if disk.path == disk_path:
                                    disk_exists = True
                                    break

                        if not disk_exists:
                            disk = self._create_disk_from_vm_attachment(
                                disk_path, vm_name,
                                disk_block.get('target_dev'),
                                disk_block.get('bus_type'),
                                disk_block.get('driver_type')
                            )
                            if disk:
                                attached_disks.append(disk)

                except libvirt.libvirtError:
                    continue

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка получения подключенных дисков: {e}")
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")

        return attached_disks

    def _extract_disk_blocks_from_vm_xml(self, xml_desc: str) -> List[dict]:
        disk_blocks = []
        lines = xml_desc.split('\n')
        i = 0

        while i < len(lines):
            if '<disk ' in lines[i]:
                disk_block = {}
                j = i

                while j < len(lines) and '</disk>' not in lines[j]:
                    line = lines[j]

                    if 'file=' in line:
                        match = re.search(r"file=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['source_file'] = match.group(1)

                    if 'target dev=' in line:
                        match = re.search(r"dev=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['target_dev'] = match.group(1)

                    if 'bus=' in line:
                        match = re.search(r"bus=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['bus_type'] = match.group(1)

                    if 'type=' in line and 'driver' in line:
                        match = re.search(r"type=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['driver_type'] = match.group(1)

                    j += 1

                if disk_block:
                    disk_blocks.append(disk_block)

                i = j + 1
            else:
                i += 1

        return disk_blocks

    def _create_disk_from_vm_attachment(self, disk_path: str, vm_name: str,
                                        target_dev: str | None, bus_type_str: str | None,
                                        driver_type: str | None) -> Disk | None:
        try:
            disk_format = DiskFormat.UNKNOWN
            if driver_type:
                try:
                    disk_format = DiskFormat(driver_type)
                except ValueError:
                    pass

            if disk_format == DiskFormat.UNKNOWN:
                if disk_path.endswith('.qcow2'):
                    disk_format = DiskFormat.QCOW2
                elif disk_path.endswith('.raw') or disk_path.endswith('.img'):
                    disk_format = DiskFormat.RAW
                elif disk_path.endswith('.vmdk'):
                    disk_format = DiskFormat.VMDK
                elif disk_path.endswith('.vdi'):
                    disk_format = DiskFormat.VDI
                elif disk_path.endswith('.vhd') or disk_path.endswith('.vhdx'):
                    disk_format = DiskFormat.VHDX

            size_bytes = os.path.getsize(disk_path) if os.path.exists(disk_path) else 0

            bus_type = None
            if bus_type_str:
                try:
                    bus_type = BusType(bus_type_str)
                except ValueError:
                    bus_type = None

            disk = Disk(
                name=os.path.basename(disk_path),
                path=disk_path,
                file_path_exists=os.path.exists(disk_path),
                type=DiskType.VM_ATTACHED,
                format=disk_format,
                capacity_bytes=size_bytes,
                allocation_bytes=size_bytes,
                vm_name=vm_name,
                status=DiskStatus.ATTACHED,
                target_dev=target_dev,
                bus_type=bus_type
            )

            return disk
        except Exception as e:
            self.logger.exception(f"Ошибка создания диска: {e}")
            return None

    def _volume_to_disk(self, vol, pool_name: str) -> Disk | None:
        try:
            vol_info = vol.info()
            vol_xml = vol.XMLDesc()

            disk_format = DiskFormat.UNKNOWN
            if 'type=\'qcow2\'' in vol_xml:
                disk_format = DiskFormat.QCOW2
            elif 'type=\'raw\'' in vol_xml:
                disk_format = DiskFormat.RAW

            disk = Disk(
                name=vol.name(),
                path=vol.path(),
                type=DiskType.POOL_DISK,
                format=disk_format,
                capacity_bytes=vol_info[1],
                allocation_bytes=vol_info[2],
                pool=pool_name,
                status=DiskStatus.DETACHED
            )

            return disk
        except libvirt.libvirtError:
            return None

    def _remove_duplicate_disks(self, disks: List[Disk]) -> List[Disk]:
        unique_disks = {}
        for disk in disks:
            if disk.path not in unique_disks:
                unique_disks[disk.path] = disk
            else:
                existing = unique_disks[disk.path]
                if disk.vm_name and not existing.vm_name:
                    existing.vm_name = disk.vm_name
                    existing.status = DiskStatus.ATTACHED
                    existing.type = DiskType.VM_ATTACHED
                if disk.pool and not existing.pool:
                    existing.pool = disk.pool
                    existing.type = DiskType.POOL_DISK

        return list(unique_disks.values())

    def _apply_filters(self, disks: List[Disk], query: DiskQuery | None) -> List[Disk]:
        if not query:
            return disks

        filtered_disks = []
        for disk in disks:
            if self._filter_disk(disk, query):
                filtered_disks.append(disk)

        return filtered_disks

    def _filter_disk(self, disk: Disk, query: DiskQuery | None) -> bool:
        if not query:
            return True

        if query.format and disk.format != query.format:
            return False

        size_gb = disk.get_effective_size_gb()
        if query.min_size_gb is not None and size_gb < query.min_size_gb:
            return False
        if query.max_size_gb is not None and size_gb > query.max_size_gb:
            return False

        if query.vm_name and disk.vm_name != query.vm_name:
            return False

        if query.pool and disk.pool != query.pool:
            return False

        if query.attached_only is not None:
            if query.attached_only and disk.status != DiskStatus.ATTACHED:
                return False
            elif not query.attached_only and disk.status == DiskStatus.ATTACHED:
                return False

        return True

if __name__ == "__main__":
    """
    Пример использования StorageManager:
    1. Создание диска в пуле
    2. Создание файлового диска
    3. Подключение диска к ВМ
    4. Получение списка дисков
    5. Конвертация формата диска
    """

    with StorageManager().with_default_user() as manager:
        # Создание диска в пуле
        # disk_create = DiskCreate(
        #     name="test_disk",
        #     size_gb=10,
        #     format=DiskFormat.QCOW2,
        #     pool="default"
        # )
        # disk = manager.create_disk(disk_create)
        # if disk:
        #     print(f"Диск создан: {disk.name}, размер: {disk.get_effective_size_gb()}GB")

        # Получение списка всех дисков

        for vm_disk in manager.get_disks_by_vm("test-vm-03"):
            print(vm_disk)
        disks = manager.list_disks()
        for current_disk in disks:
            print(f"****************************************************************\n"
                  f"ИМЯ ДИСКА: {current_disk.name}\n"
                  f"ПУТЬ ДИСКА: {current_disk.path}\n"
                  f"TARGET_DEV: {current_disk.target_dev}\n"
                  f"К КАКОЙ ВМ ПОДКЛЮЧЕН ДИСК: {current_disk.vm_name}\n")
        print(f"Всего дисков: {len(disks)}")
