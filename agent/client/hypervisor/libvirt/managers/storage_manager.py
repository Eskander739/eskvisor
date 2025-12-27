import random
import time

import libvirt
import os
import re
import shutil
from datetime import datetime
from typing import List

from agent.client.hypervisor.libvirt.config import LibvirtConfig
from agent.client.hypervisor.models.disk import (
    Disk, DiskCreate, DiskUpdate, DiskAttach, DiskDetach, DiskQuery,
    DiskFormat, DiskType, DiskStatus, BusType
)
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.logger_config import logger


class StorageManager(LibvirtClient):
    """
    Управление хранилищами виртуальных дисков всех типов
    """

    def __init__(self, connection_uri: str = "qemu:///session", username: str | None = None, password: str | None = None):
        """Инициализация StorageManager с логированием"""
        super().__init__(connection_uri, username, password)
        self.logger = logger
        self.libvirt_config = LibvirtConfig()

    def create_disk(self, disk_create: DiskCreate) -> Disk | None:
        """
        Создать новый виртуальный диск в указанном пуле хранилищ или по прямому пути

        Args:
            disk_create: Модель для создания диска

        Returns:
            Disk: Созданный диск или None при ошибке
        """
        try:
            self.logger.info(f"Начало создания диска: {disk_create.name}, размер: {disk_create.size_gb}GB")

            # Если указан пул, работаем через него
            if disk_create.pool:
                self.logger.debug(f"Создание диска в пуле: {disk_create.pool}")
                return self._create_pool_disk(disk_create)
            else:
                self.logger.debug("Создание файлового диска")
                return self._create_file_disk(disk_create)

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при создании диска: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Ошибка при создании диска: {e}")
            return None

    def _create_pool_disk(self, disk_create: DiskCreate) -> Disk | None:
        """Создать диск в пуле libvirt"""
        try:
            pool = self.conn.storagePoolLookupByName(disk_create.pool)
            self.logger.info(f"Найден пул: {disk_create.pool}")

            # Проверяем состояние пула
            pool_info = pool.info()
            if pool_info[0] != libvirt.VIR_STORAGE_POOL_RUNNING:
                self.logger.info(f"Пул {disk_create.pool} неактивен, запускаем...")
                pool.create()

            # Создаем XML для диска в пуле
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
                <backingStore/>
            </volume>
            '''

            # Создаем том в пуле
            self.logger.info(f"Создание тома {disk_create.name} в пуле {disk_create.pool}")
            vol = pool.createXML(xml_desc, 0)
            disk_path = vol.path()
            self.logger.info(f"Том создан, путь: {disk_path}")

            # Если формат RAW и не sparse, заполняем нулями
            if not disk_create.sparse and disk_create.format == DiskFormat.RAW:
                self.logger.info(f"Заполнение диска нулями: {disk_create.name}")
                stream = self.conn.newStream()
                vol.download(stream, 0, 0, 0)
                zero_data = b'\0' * 1024 * 1024  # 1MB блоки
                for _ in range(int(disk_create.size_gb * 1024)):
                    stream.send(zero_data)
                stream.finish()

            disk = self.get_disk_info(pool_name=disk_create.pool, disk_name=disk_create.name)
            if disk:
                self.logger.info(f"Диск успешно создан: {disk.name}, размер: {disk.get_effective_size_gb()}GB")
            return disk

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка при создании пулового диска {disk_create.name}: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка при создании пулового диска: {e}")
            return None

    def _create_file_disk(self, disk_create: DiskCreate) -> Disk | None:
        """Создать файловый диск напрямую в файловой системе"""
        try:
            # Проверяем и создаем директорию
            disk_path = disk_create.path
            if not disk_path:
                # Генерируем путь по умолчанию
                disk_path = f"/var/lib/libvirt/images/disk-{random.randint(100000, 999999)}.{disk_create.format.value}"
                self.logger.debug(f"Сгенерирован путь по умолчанию: {disk_path}")

            disk_dir = os.path.dirname(disk_path)
            if not os.path.exists(disk_dir):
                self.logger.info(f"Создание директории: {disk_dir}")
                os.makedirs(disk_dir, exist_ok=True)

            # Создаем файл нужного размера
            size_bytes = int(disk_create.size_gb * 1024 * 1024 * 1024)
            self.logger.info(f"Создание файлового диска: {disk_path}, размер: {disk_create.size_gb}GB")

            if disk_create.format == DiskFormat.QCOW2:
                # Используем qemu-img для создания qcow2 дисков
                import subprocess
                sparse_flag = [] if disk_create.sparse else ["-f", "preallocation=full"]
                cmd = ["qemu-img", "create", "-f", "qcow2"] + sparse_flag + [disk_path, f"{disk_create.size_gb}G"]
                self.logger.debug(f"Выполнение команды: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"Ошибка qemu-img: {result.stderr}")
            else:
                # Для других форматов создаем файл напрямую
                with open(disk_path, 'wb') as f:
                    if disk_create.sparse:
                        f.seek(size_bytes - 1)
                        f.write(b'\0')
                    else:
                        # Заполняем нулями
                        zero_data = b'\0' * 1024 * 1024  # 1MB блоки
                        for _ in range(int(disk_create.size_gb * 1024)):
                            f.write(zero_data)

            self.logger.info(f"Файловый диск создан: {disk_path}")
            return self.get_disk_info(path=disk_path)

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Ошибка qemu-img при создании диска: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Ошибка при создании файлового диска: {e}")
            return None

    def delete_disk(self, pool_name: str | None = None, disk_name: str | None = None,
                    path: str | None = None) -> bool:
        """
        Удалить виртуальный диск

        Args:
            pool_name: Имя пула хранилищ (для пуловых дисков)
            disk_name: Имя удаляемого диска (для пуловых дисков)
            path: Путь к файлу диска (для файловых дисков)

        Returns:
            bool: Успешность операции
        """
        try:
            self.logger.info(f"Попытка удаления диска: pool={pool_name}, disk={disk_name}, path={path}")

            if pool_name and disk_name:
                # Удаление из пула
                pool = self.conn.storagePoolLookupByName(pool_name)
                vol = pool.storageVolLookupByName(disk_name)
                disk_path = vol.path()

                self.logger.info(f"Удаление пулового диска: {disk_name} из пула {pool_name}")

                # Проверяем, не используется ли диск
                if self._is_disk_in_use(disk_path):
                    self.logger.warning(f"Диск {disk_name} используется и не может быть удален")
                    return False

                vol.delete(0)
                self.logger.info(f"Диск {disk_name} успешно удален из пула {pool_name}")
                return True

            elif path:
                # Удаление файла
                if not os.path.exists(path):
                    self.logger.warning(f"Файл {path} не существует")
                    return False

                self.logger.info(f"Удаление файлового диска: {path}")

                # Проверяем, не используется ли диск
                if self._is_disk_in_use(path):
                    self.logger.warning(f"Диск {path} используется и не может быть удален")
                    return False

                os.remove(path)
                self.logger.info(f"Файл диска {path} успешно удален")
                return True

            else:
                self.logger.error("Не указаны параметры для удаления диска")
                return False

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при удалении диска: {e}")
            return False
        except Exception as e:
            self.logger.exception(f"Ошибка при удалении диска: {e}")
            return False

    def _is_disk_in_use(self, disk_path: str) -> bool:
        """Проверить, используется ли диск виртуальными машинами"""
        try:
            self.logger.debug(f"Проверка использования диска: {disk_path}")

            # Получаем все ВМ
            vm_ids = self.conn.listDomainsID()
            all_vms = []

            # Активные ВМ
            for vm_id in vm_ids:
                vm = self.conn.lookupByID(vm_id)
                all_vms.append(vm)

            # Неактивные ВМ
            for vm_name in self.conn.listDefinedDomains():
                vm = self.conn.lookupByName(vm_name)
                all_vms.append(vm)

            # Проверяем использование диска
            for vm in all_vms:
                try:
                    xml_desc = vm.XMLDesc()
                    if disk_path in xml_desc:
                        self.logger.debug(f"Диск {disk_path} используется ВМ: {vm.name()}")
                        return True
                except libvirt.libvirtError as e:
                    self.logger.debug(f"Ошибка при проверке ВМ {vm.name()}: {e}")
                    continue

            self.logger.debug(f"Диск {disk_path} не используется")
            return False

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при проверке использования диска: {e}")
            return False

    def edit_disk(self, pool_name: str | None = None, disk_name: str | None = None,
                  path: str | None = None, disk_update: DiskUpdate | None = None) -> Disk | None:
        """
        Изменить параметры виртуального диска

        Args:
            pool_name: Имя пула хранилищ (для пуловых дисков)
            disk_name: Имя изменяемого диска (для пуловых дисков)
            path: Путь к файлу диска (для файловых дисков)
            disk_update: Модель обновления диска

        Returns:
            Disk: Обновленный диск или None при ошибке
        """
        if not disk_update:
            self.logger.error("Не предоставлена модель обновления диска")
            return None

        try:
            self.logger.info(f"Попытка изменения диска: pool={pool_name}, disk={disk_name}, path={path}")

            if pool_name and disk_name:
                self.logger.debug(f"Изменение пулового диска: {disk_name}")
                return self._edit_pool_disk(pool_name, disk_name, disk_update)
            elif path:
                self.logger.debug(f"Изменение файлового диска: {path}")
                return self._edit_file_disk(path, disk_update)
            else:
                self.logger.error("Не указаны параметры для изменения диска")
                return None

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при изменении диска: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Ошибка при изменении диска: {e}")
            return None

    def _edit_pool_disk(self, pool_name: str, disk_name: str, disk_update: DiskUpdate) -> Disk | None:
        """Изменить пуловой диск"""
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(disk_name)

            changes = []

            # Изменение размера (только увеличение)
            if disk_update.new_size_gb is not None:
                vol_info = vol.info()
                current_size_gb = vol_info[1] / (1024 ** 3)
                self.logger.info(f"Текущий размер диска {disk_name}: {current_size_gb}GB")

                if disk_update.new_size_gb > current_size_gb:
                    new_size_bytes = int(disk_update.new_size_gb * 1024 * 1024 * 1024)
                    self.logger.info(f"Увеличение размера до {disk_update.new_size_gb}GB")
                    vol.resize(new_size_bytes, 0)
                    changes.append(f"размер изменен на {disk_update.new_size_gb}GB")
                else:
                    self.logger.warning(
                        f"Уменьшение размера диска не поддерживается. Текущий: {current_size_gb}GB, запрошенный: {disk_update.new_size_gb}GB")

            # Переименование
            if disk_update.name is not None and disk_update.name != disk_name:
                self.logger.info(f"Переименование диска с {disk_name} на {disk_update.name}")
                xml_desc = vol.XMLDesc()
                new_xml = xml_desc.replace(f"<name>{disk_name}</name>", f"<name>{disk_update.name}</name>")
                new_vol = pool.createXML(new_xml, 0)
                vol.delete(0)
                changes.append(f"имя изменено на {disk_update.name}")
                disk_name = disk_update.name

            if changes:
                self.logger.info(f"Диск {disk_name} изменен: {', '.join(changes)}")
                return self.get_disk_info(pool_name, disk_name)
            else:
                self.logger.info("Не указано изменений для диска")
                return self.get_disk_info(pool_name, disk_name)

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка при изменении пулового диска {disk_name}: {e}")
            return None

    def _edit_file_disk(self, path: str, disk_update: DiskUpdate) -> Disk | None:
        """Изменить файловый диск"""
        try:
            changes = []

            # Переименование
            if disk_update.name is not None:
                new_path = os.path.join(os.path.dirname(path), disk_update.name)
                self.logger.info(f"Переименование файла {path} в {new_path}")
                shutil.move(path, new_path)
                changes.append(f"имя изменено на {disk_update.name}")
                path = new_path

            # Изменение размера
            if disk_update.new_size_gb is not None:
                import subprocess
                current_size = os.path.getsize(path)
                current_size_gb = current_size / (1024 ** 3)
                self.logger.info(f"Текущий размер файла {path}: {current_size_gb}GB")

                if disk_update.new_size_gb > current_size_gb:
                    # Используем qemu-img для изменения размера
                    self.logger.info(f"Увеличение размера до {disk_update.new_size_gb}GB")
                    cmd = ["qemu-img", "resize", path, f"{disk_update.new_size_gb}G"]
                    self.logger.debug(f"Выполнение команды: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise Exception(f"Ошибка qemu-img: {result.stderr}")
                    changes.append(f"размер изменен на {disk_update.new_size_gb}GB")
                else:
                    self.logger.warning(f"Уменьшение размера диска не поддерживается напрямую")

            if changes:
                self.logger.info(f"Диск {path} изменен: {', '.join(changes)}")
                return self.get_disk_info(path=path)
            else:
                self.logger.info("Не указано изменений для файлового диска")
                return self.get_disk_info(path=path)

        except Exception as e:
            self.logger.exception(f"Ошибка при изменении файлового диска {path}: {e}")
            return None

    def attach_disk_to_vm(self, disk_attach: DiskAttach | None = None) -> dict | None:
        """
        Добавить диск к виртуальной машине

        Args:
            disk_attach: Модель для подключения диска

        Returns:
            dict: Результат подключения или None при ошибке
        """
        target_dev = None
        try:
            if not self.conn:
                self.logger.error("Отсутствует подключение к libvirt")
                return None

            if not disk_attach:
                self.logger.error("Не предоставлена модель подключения диска")
                return None

            self.logger.info(f"Попытка подключения диска {disk_attach.path} к ВМ {disk_attach.vm_name}")

            # Находим ВМ
            vm = self.conn.lookupByName(disk_attach.vm_name)
            self.logger.debug(f"ВМ {disk_attach.vm_name} найдена")

            # Проверяем, существует ли диск
            if not os.path.exists(disk_attach.path):
                self.logger.error(f"Диск {disk_attach.path} не существует")
                return None

            # Проверяем, не подключен ли уже этот диск к ВМ
            if self._is_disk_attached_to_vm(disk_attach.path, disk_attach.vm_name):
                self.logger.warning(f"Диск {disk_attach.path} уже подключен к ВМ {disk_attach.vm_name}")
                return {"target_dev": self._get_disk_target_dev(vm, disk_attach.path), "already_attached": True}

            # Получаем информацию о диске
            disk_info = self.get_disk_info(path=disk_attach.path)
            if not disk_info:
                self.logger.error(f"Не удалось получить информацию о диске {disk_attach.path}")
                return None

            # Создаем конфигурацию подключения
            bus_type = disk_attach.bus_type or BusType.VIRTIO
            cache_mode = disk_attach.cache_mode.value if disk_attach.cache_mode else "writethrough"

            # Находим свободное устройство
            target_dev = disk_attach.target_dev or self._find_free_disk_device(vm, bus_type)

            # Проверяем, что target_dev действительно свободен
            if not self._is_disk_device_free(vm, target_dev):
                self.logger.warning(f"Устройство {target_dev} уже используется, ищем другое...")
                target_dev = self._find_free_disk_device(vm, bus_type)

            self.logger.debug(f"Конфигурация: target_dev={target_dev}, bus_type={bus_type}, cache_mode={cache_mode}")

            # Генерируем уникальный alias для устройства
            import hashlib
            import time
            alias_hash = hashlib.md5(f"{disk_attach.path}_{int(time.time())}".encode()).hexdigest()[:8]
            alias_name = f"ua-{alias_hash}"

            # Создаем XML для устройства диска
            disk_xml = f'''
            <disk type='file' device='disk'>
                <driver name='qemu' type='{disk_info.format.value}' cache='{cache_mode}'/>
                <source file='{disk_attach.path}'/>
                <target dev='{target_dev}' bus='{bus_type.value}'/>
                <alias name='{alias_name}'/>
            </disk>
            '''

            self.logger.debug(f"XML для подключения диска:\n{disk_xml}")

            # Получаем состояние ВМ
            vm_state, vm_reason = vm.state()
            self.logger.debug(f"Состояние ВМ перед подключением: {vm_state}")

            success = False

            if vm_state == libvirt.VIR_DOMAIN_RUNNING:
                # Для работающей ВМ: добавляем в live и в конфигурацию
                try:
                    # Пробуем добавить и в live, и в конфигурацию
                    flags = libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE | libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG
                    vm.attachDeviceFlags(disk_xml, flags=flags)
                    success = True
                    self.logger.info(f"Диск подключен к работающей ВМ (live+config)")
                except libvirt.libvirtError as e:
                    self.logger.warning(f"Комбинированный флаг не сработал: {e}")

                    # Раздельное подключение
                    try:
                        # Live подключение
                        vm.attachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE)
                        self.logger.info("Диск подключен live")

                        # Добавление в конфигурацию
                        vm.attachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)
                        self.logger.info("Диск добавлен в конфигурацию")
                        success = True
                    except libvirt.libvirtError as e2:
                        self.logger.error(f"Раздельное подключение не удалось: {e2}")
            else:
                # Для остановленной ВМ: добавляем только в конфигурацию
                try:
                    vm.attachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)
                    success = True
                    self.logger.info(f"Диск добавлен в конфигурацию остановленной ВМ")
                except libvirt.libvirtError as e:
                    self.logger.error(f"Не удалось добавить диск в конфигурацию: {e}")

            if success:
                # Обновляем объект ВМ после изменений
                try:
                    # Закрываем текущий объект ВМ
                    del vm

                    # Получаем обновленный объект ВМ
                    vm = self.conn.lookupByName(disk_attach.vm_name)

                    # Обновляем конфигурацию ВМ в libvirt
                    new_xml = vm.XMLDesc()
                    self.conn.defineXML(new_xml)
                    self.logger.debug("Конфигурация ВМ обновлена в libvirt")

                    # Принудительно обновляем состояние
                    self._refresh_vm_state(disk_attach.vm_name)

                    self.logger.info(
                        f"Диск {disk_attach.path} успешно добавлен к ВМ {disk_attach.vm_name} как {target_dev}")
                    return {"target_dev": target_dev}
                except Exception as e:
                    self.logger.warning(f"Не удалось обновить состояние ВМ: {e}")
                    return {"target_dev": target_dev,
                            "warning": "ВМ может потребоваться перезагрузка для сохранения изменений"}

            return None

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при добавлении диска к ВМ {disk_attach.vm_name}: {e}")
            return None
        except Exception as e:
            self.logger.exception(
                f"Ошибка при добавлении диска к ВМ {disk_attach.vm_name if disk_attach else 'unknown'}: {e}")
            return None

    def _is_disk_device_free(self, vm, target_dev: str) -> bool:
        """Проверить, свободно ли устройство в ВМ"""
        try:
            xml_desc = vm.XMLDesc()

            # Ищем все target устройства
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_desc)

            for disk in root.findall(".//disk"):
                target = disk.find("target")
                if target is not None and target.get("dev") == target_dev:
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Ошибка при проверке устройства {target_dev}: {e}")
            return False

    def _is_disk_attached_to_vm(self, disk_path: str, vm_name: str) -> bool:
        """Проверить, подключен ли диск к указанной ВМ"""
        try:
            vm = self.conn.lookupByName(vm_name)
            xml_desc = vm.XMLDesc()

            # Простая проверка наличия пути в XML
            if disk_path in xml_desc:
                self.logger.debug(f"Диск {disk_path} уже подключен к ВМ {vm_name}")
                return True

            # Более точная проверка через парсинг XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_desc)

            for disk in root.findall(".//disk"):
                source = disk.find("source")
                if source is not None and source.get("file") == disk_path:
                    return True

            return False

        except libvirt.libvirtError as e:
            self.logger.debug(f"Ошибка при проверке подключения диска {disk_path} к ВМ {vm_name}: {e}")
            return False
        except Exception as e:
            self.logger.debug(f"Неожиданная ошибка при проверке подключения диска: {e}")
            return False

    def _get_used_pci_slots(self, xml_desc: str) -> set[int]:
        """Получить список используемых PCI слотов из XML ВМ"""
        used_slots = set()
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_desc)

            # Ищем все элементы с атрибутом type='pci'
            for elem in root.findall(".//*[@type='pci']"):
                slot_attr = elem.get("slot")
                if slot_attr:
                    try:
                        slot = int(slot_attr, 16)
                        used_slots.add(slot)
                    except ValueError:
                        continue

            # Также ищем все адреса через регулярные выражения
            import re
            slot_patterns = [
                r"slot='0x([0-9a-fA-F]+)'",
                r'slot="0x([0-9a-fA-F]+)"',
                r"slot='([0-9]+)'",
                r'slot="([0-9]+)"'
            ]

            for pattern in slot_patterns:
                matches = re.findall(pattern, xml_desc)
                for match in matches:
                    try:
                        # Если шестнадцатеричное
                        if '0x' in match or all(c in '0123456789ABCDEFabcdef' for c in match):
                            slot = int(match, 16)
                        else:
                            slot = int(match)
                        used_slots.add(slot)
                    except ValueError:
                        continue

            self.logger.debug(f"Используемые PCI слоты: {sorted(used_slots)}")
            return used_slots

        except Exception as e:
            self.logger.error(f"Ошибка при получении PCI слотов: {e}")
            return set()

    def _find_free_pci_slot(self, used_slots: set[int], start_slot: int = 10) -> int:
        """Найти свободный PCI слот"""
        # Ищем свободный слот начиная с указанного
        slot = start_slot

        # Пропускаем зарезервированные слоты (обычно 0-9 зарезервированы для системных устройств)
        while slot in used_slots:
            slot += 1

        # Проверяем, что слот в допустимом диапазоне
        if slot > 31:
            # Пробуем найти любой свободный слот
            for test_slot in range(10, 32):
                if test_slot not in used_slots:
                    slot = test_slot
                    break
            else:
                # Если все слоты заняты, используем максимальный + 1 (libvirt может обработать)
                slot = max(used_slots) + 1 if used_slots else 32

        self.logger.debug(f"Найден свободный PCI слот: {slot} (0x{slot:02x})")
        return slot

    def _find_free_disk_device(self, vm, bus_type: BusType = BusType.VIRTIO) -> str:
        """Найти свободное устройство диска в ВМ"""
        try:
            import xml.etree.ElementTree as ET

            xml_desc = vm.XMLDesc()
            root = ET.fromstring(xml_desc)

            used_devices = set()

            # Собираем все используемые устройства
            for target in root.findall(".//target[@dev]"):
                used_devices.add(target.attrib["dev"])

            self.logger.debug(f"Используемые устройства в ВМ {vm.name()}: {sorted(used_devices)}")

            # Определяем префикс в зависимости от bus type
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

            # Для NVME особый формат
            if bus_type == BusType.NVME:
                for controller in range(8):
                    for namespace in range(1, 32):
                        device = f"nvme{controller}n{namespace}"
                        if device not in used_devices:
                            self.logger.debug(f"Найдено свободное NVME устройство: {device}")
                            return device

            # Для остальных типов стандартный поиск
            # Односимвольные имена (vda, vdb, ...)
            for letter in "abcdefghijklmnopqrstuvwxyz":
                device = f"{prefix}{letter}"
                if device not in used_devices:
                    self.logger.debug(f"Найдено свободное устройство: {device}")
                    return device

            # Двухсимвольные имена (vdaa, vdab, ...)
            import string
            for first in string.ascii_lowercase:
                for second in string.ascii_lowercase:
                    device = f"{prefix}{first}{second}"
                    if device not in used_devices:
                        self.logger.debug(f"Найдено свободное устройство: {device}")
                        return device

            # Если совсем нет свободных
            import random
            device = f"{prefix}z{random.randint(100, 999)}"
            self.logger.warning(f"Все устройства заняты, используем {device}")
            return device

        except Exception as e:
            self.logger.error(f"Ошибка при поиске свободного устройства: {e}")
            return "vdz"  # Запасной вариант

    def detach_disk_by_path(self, vm_name: str, disk_path: str) -> bool:
        """
        Отключить диск от ВМ по пути к диску

        Args:
            vm_name: Имя ВМ
            disk_path: Путь к диску

        Returns:
            bool: Успешность операции
        """
        try:
            self.logger.info(f"Попытка отключения диска {disk_path} от ВМ {vm_name}")

            vm = self.conn.lookupByName(vm_name)
            xml_desc = vm.XMLDesc()

            import xml.etree.ElementTree as ET
            from xml.etree.ElementTree import Element

            root = ET.fromstring(xml_desc)

            # Ищем диск по пути (используем XPath-подобный поиск)
            disk_elem = None

            # Ищем все элементы source с атрибутом file
            for elem in root.findall(".//source"):
                file_path = elem.get("file")
                if file_path == disk_path:
                    # Нашли source элемент с нужным путем
                    # Находим родительский элемент disk
                    parent = elem
                    while parent is not None and parent.tag != 'disk':
                        parent = parent.getparent() if hasattr(parent, 'getparent') else None

                    if parent is not None and parent.tag == 'disk':
                        disk_elem = parent
                        break

            if disk_elem is None:
                # Альтернативный поиск: ищем все disk элементы и проверяем их source
                for disk in root.findall(".//disk"):
                    source = disk.find("source")
                    if source is not None and source.get("file") == disk_path:
                        disk_elem = disk
                        break

            if disk_elem is None:
                self.logger.error(f"Диск {disk_path} не найден в ВМ {vm_name}")

                # Логируем для отладки - какие диски есть в ВМ
                self.logger.debug("Текущие диски в ВМ:")
                for disk in root.findall(".//disk"):
                    source = disk.find("source")
                    if source is not None:
                        self.logger.debug(f"  Путь: {source.get('file')}")

                return False

            # Получаем XML диска
            disk_xml = ET.tostring(disk_elem, encoding='unicode')
            self.logger.debug(f"Найден XML диска для отключения:\n{disk_xml}")

            # Получаем target_dev для логов
            target = disk_elem.find("target")
            target_dev = target.get("dev") if target is not None else "unknown"

            # Пробуем разные методы отключения
            methods = [
                ("legacy", lambda: vm.detachDevice(disk_xml)),
                ("config", lambda: vm.detachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)),
                ("live", lambda: vm.detachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE)),
            ]

            for method_name, method_func in methods:
                try:
                    method_func()
                    self.logger.info(
                        f"Диск {disk_path} (устройство {target_dev}) успешно отключен от ВМ {vm_name} методом {method_name}")
                    return True
                except libvirt.libvirtError as e:
                    self.logger.debug(f"Метод {method_name} не удался: {e}")
                    continue

            self.logger.error(f"Все методы отключения диска {disk_path} не удались")
            return False

        except Exception as e:
            self.logger.exception(f"Ошибка при отключении диска по пути: {e}")
            return False

    def detach_disk_from_vm(self, detach_disk: DiskDetach) -> bool:
        """
        Отключить диск от виртуальной машины

        Args:
            detach_disk: данные для отключения диска

        Returns:
            bool: Успешность операции
        """
        try:
            self.logger.info(f"Попытка отключения диска от ВМ {detach_disk.vm_name}")

            vm = self.conn.lookupByName(detach_disk.vm_name)
            vm_state, vm_reason = vm.state()

            xml_desc = vm.XMLDesc()
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_desc)

            disk_elem = None

            # Поиск диска
            if detach_disk.target_dev:
                self.logger.debug(f"Поиск диска по target_dev: {detach_disk.target_dev}")
                for disk in root.findall(".//disk"):
                    target = disk.find("target")
                    if target is not None and target.get("dev") == detach_disk.target_dev:
                        disk_elem = disk
                        break

            if disk_elem is None and detach_disk.path:
                self.logger.debug(f"Поиск диска по пути: {detach_disk.path}")
                for disk in root.findall(".//disk"):
                    source = disk.find("source")
                    if source is not None and source.get("file") == detach_disk.path:
                        disk_elem = disk
                        break

            if disk_elem is None:
                self.logger.error(f"Диск не найден в ВМ {detach_disk.vm_name}")
                return False

            disk_xml = ET.tostring(disk_elem, encoding='unicode')
            target = disk_elem.find("target")
            actual_target_dev = target.get("dev") if target is not None else detach_disk.target_dev

            self.logger.info(f"Отсоединение диска {actual_target_dev} от ВМ {detach_disk.vm_name}")

            success = False

            if vm_state == libvirt.VIR_DOMAIN_RUNNING:
                # Для работающей ВМ: удаляем из live и из конфигурации
                try:
                    vm.detachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE)
                    vm.detachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)
                    success = True
                    self.logger.info(f"Диск отсоединен от работающей ВМ (live+config)")
                except libvirt.libvirtError as e:
                    self.logger.warning(f"Комбинированный флаг не сработал: {e}")

                    # Раздельное отсоединение
                    try:
                        vm.detachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE)
                        self.logger.info("Диск отсоединен live")

                        vm.detachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)
                        self.logger.info("Диск удален из конфигурации")
                        success = True
                    except libvirt.libvirtError as e2:
                        self.logger.error(f"Раздельное отсоединение не удалось: {e2}")
            else:
                # Для остановленной ВМ: удаляем только из конфигурации
                try:
                    vm.detachDeviceFlags(disk_xml, flags=libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)
                    success = True
                    self.logger.info(f"Диск удален из конфигурации остановленной ВМ")
                except libvirt.libvirtError as e:
                    self.logger.error(f"Не удалось удалить диск из конфигурации: {e}")

            if success:
                # Обновляем конфигурацию
                try:
                    del vm
                    vm = self.conn.lookupByName(detach_disk.vm_name)
                    new_xml = vm.XMLDesc()
                    self.conn.defineXML(new_xml)
                    self._refresh_vm_state(detach_disk.vm_name)
                except Exception as e:
                    self.logger.debug(f"Не удалось явно обновить конфигурацию: {e}")

            return success

        except Exception as e:
            self.logger.exception(f"Ошибка при отключении диска: {e}")
            return False

    def _refresh_vm_state(self, vm_name: str) -> None:
        """
        Принудительно обновить состояние ВМ в libvirt

        Args:
            vm_name: Имя ВМ
        """
        try:
            self.logger.debug(f"Обновление состояния ВМ {vm_name}")

            # Получаем ВМ
            vm = self.conn.lookupByName(vm_name)

            # Способ 1: Получить и переопределить XML
            xml_desc = vm.XMLDesc()
            self.conn.defineXML(xml_desc)
            self.logger.debug(f"ВМ {vm_name} переопределена")

            # Способ 2: Создать новый объект ВМ
            # Просто переполучаем ВМ, чтобы обновить кэш
            new_vm = self.conn.lookupByName(vm_name)
            _ = new_vm.XMLDesc()  # Принудительно читаем конфигурацию

            # Способ 3: Использовать refresh (если доступен)
            try:
                vm.refresh()
                self.logger.debug(f"ВМ {vm_name} обновлена через refresh()")
            except AttributeError:
                self.logger.debug("Метод refresh() не доступен")

            self.logger.debug(f"Состояние ВМ {vm_name} обновлено")

        except Exception as e:
            self.logger.warning(f"Не удалось обновить состояние ВМ {vm_name}: {e}")

    def get_disk_info(self, pool_name: str | None = None, disk_name: str | None = None,
                      path: str | None = None) -> Disk | None:
        """
        Получить информацию о диске

        Args:
            pool_name: Имя пула хранилищ (если диск в пуле)
            disk_name: Имя диска в пуле
            path: Путь к файлу диска (если диск не в пуле)

        Returns:
            Disk: Информация о диске или None при ошибке
        """
        try:
            self.logger.debug(f"Получение информации о диске: pool={pool_name}, disk={disk_name}, path={path}")

            if path:
                # Обработка диска по прямому пути
                return self._get_file_disk_info(path)
            elif pool_name and disk_name:
                # Обработка диска из пула
                return self._get_pool_disk_info(pool_name, disk_name)
            else:
                raise ValueError("Необходимо указать либо путь к файлу, либо пул и имя диска")

        except (libvirt.libvirtError, FileNotFoundError, ValueError) as e:
            self.logger.error(f"Ошибка при получении информации о диске: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка при получении информации о диске: {e}")
            return None

    def _get_file_disk_info(self, path: str) -> Disk | None:
        """Получить информацию о файловом диске"""
        try:
            if not os.path.exists(path):
                file_path_exists = False
            else:
                file_path_exists = True

            # Определяем формат по расширению
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

            # Получаем размер файла
            if file_path_exists:
                size_bytes = os.path.getsize(path)
            else:
                size_bytes = 0

            # Определяем тип диска
            disk_type = DiskType.EXTERNAL_DISK

            vm_name = None

            # Проверяем, используется ли диск
            if self._is_disk_in_use(path):
                # Находим ВМ, к которой подключен диск
                vm_name = self._find_vm_by_disk_path(path)
                if vm_name:
                    disk_type = DiskType.VM_ATTACHED
                    status = DiskStatus.ATTACHED
                    self.logger.debug(f"Диск {path} подключен к ВМ {vm_name}")
                else:
                    status = DiskStatus.DETACHED
            else:
                status = DiskStatus.DETACHED

            # Создаем объект Disk
            disk = Disk(
                name=os.path.basename(path),
                path=path,
                file_path_exists=file_path_exists,
                # target_dev=
                type=disk_type,
                format=disk_format,
                capacity_bytes=size_bytes,
                allocation_bytes=size_bytes,
                status=status,
                vm_name=vm_name
            )
            # Добавляем информацию о ВМ, если диск подключен
            if disk_type == DiskType.VM_ATTACHED:
                disk.vm_name = vm_name

            self.logger.debug(
                f"Информация о файловом диске {path}: формат={disk_format}, размер={size_bytes / (1024 ** 3):.2f}GB")
            return disk

        except Exception as e:
            self.logger.exception(f"Ошибка при получении информации о файловом диске {path}: {e}")
            return None

    def _get_pool_disk_info(self, pool_name: str, disk_name: str) -> Disk | None:
        """Получить информацию о пуловом диске"""
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(disk_name)

            vol_info = vol.info()
            vol_xml = vol.XMLDesc()

            # Определяем формат диска
            disk_format = DiskFormat.UNKNOWN
            if 'type=\'qcow2\'' in vol_xml:
                disk_format = DiskFormat.QCOW2
            elif 'type=\'raw\'' in vol_xml:
                disk_format = DiskFormat.RAW

            # Парсим даты из XML
            created = None
            timestamp_match = re.search(r'<timestamp>(\d+)</timestamp>', vol_xml)
            if timestamp_match:
                timestamp = int(timestamp_match.group(1))
                created = datetime.fromtimestamp(timestamp)

            # Проверяем, используется ли диск
            disk_path = vol.path()
            if self._is_disk_in_use(disk_path):
                vm_name = self._find_vm_by_disk_path(disk_path)
                disk_type = DiskType.VM_ATTACHED
                status = DiskStatus.ATTACHED
                self.logger.debug(f"Пулловой диск {disk_name} подключен к ВМ {vm_name}")
            else:
                disk_type = DiskType.POOL_DISK
                status = DiskStatus.DETACHED
                vm_name = None

            # Создаем объект Disk
            disk = Disk(
                name=disk_name,
                path=disk_path,
                type=disk_type,
                format=disk_format,
                capacity_bytes=vol_info[1],
                allocation_bytes=vol_info[2],
                pool=pool_name,
                status=status,
                created=created
            )

            # Добавляем информацию о ВМ, если диск подключен
            if disk_type == DiskType.VM_ATTACHED:
                disk.vm_name = vm_name

            self.logger.debug(
                f"Информация о пуловом диске {disk_name}: формат={disk_format}, размер={vol_info[1] / (1024 ** 3):.2f}GB")
            return disk

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при получении информации о пуловом диске {disk_name}: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Ошибка при получении информации о пуловом диске {disk_name}: {e}")
            return None

    def _find_vm_by_disk_path(self, disk_path: str) -> str | None:
        """Найти ВМ по пути к диску"""
        try:
            # Получаем все ВМ
            vm_ids = self.conn.listDomainsID()
            all_vms = []

            for vm_id in vm_ids:
                vm = self.conn.lookupByID(vm_id)
                all_vms.append(vm)

            for vm_name in self.conn.listDefinedDomains():
                vm = self.conn.lookupByName(vm_name)
                all_vms.append(vm)

            # Ищем ВМ с этим диском
            for vm in all_vms:
                try:
                    xml_desc = vm.XMLDesc()
                    if disk_path in xml_desc:
                        vm_name = vm.name()
                        self.logger.debug(f"Диск {disk_path} найден в ВМ {vm_name}")
                        return vm_name
                except libvirt.libvirtError as e:
                    self.logger.debug(f"Ошибка при проверке ВМ {vm.name()}: {e}")
                    continue

            self.logger.debug(f"Диск {disk_path} не найден ни в одной ВМ")
            return None

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при поиске ВМ для диска {disk_path}: {e}")
            return None

    def list_disks(self, query: DiskQuery | None = None) -> List[Disk]:
        """
        Получить список всех дисков с фильтрацией

        Args:
            query: Параметры фильтрации

        Returns:
            list[Disk]: Список дисков
        """
        disks = []
        try:
            self.logger.info(f"Получение списка дисков с фильтрацией: {query}")

            # Собираем диски из всех источников
            # pool_disks = self._get_pool_disks(query)
            file_disks = self._get_file_disks(query)
            attached_disks = self._get_attached_disks(query)

            # self.logger.debug(
            #     f"Найдено дисков: пуловых={len(pool_disks)}, файловых={len(file_disks)}, подключенных={len(attached_disks)}")

            # Объединяем списки
            # disks.extend(pool_disks)
            disks.extend(file_disks)
            disks.extend(attached_disks)

            # Удаляем дубликаты (диски могут быть найдены в нескольких источниках)
            disks = self._remove_duplicate_disks(disks)
            self.logger.debug(f"После удаления дубликатов: {len(disks)} дисков")

            # Применяем фильтры
            disks = self._apply_filters(disks, query)
            self.logger.info(f"Итоговый список дисков: {len(disks)} элементов")

            return disks

        except Exception as e:
            self.logger.exception(f"Ошибка при получении списка дисков: {e}")
            return []

    def _get_pool_disks(self, query: DiskQuery | None) -> List[Disk]:
        """Получить диски из пулов хранилищ"""
        disks = []

        try:
            if query and query.pool:
                # Конкретный пул
                try:
                    pools = [self.conn.storagePoolLookupByName(query.pool)]
                    self.logger.debug(f"Поиск дисков в конкретном пуле: {query.pool}")
                except libvirt.libvirtError:
                    pools = []
                    self.logger.warning(f"Пул {query.pool} не найден")
            else:
                # Все пулы
                pools = self.conn.listAllStoragePools()
                self.logger.debug(f"Поиск дисков во всех пулах. Найдено пулов: {len(pools)}")

            for pool in pools:
                try:
                    pool_info = pool.info()
                    # state,  # состояние пула (int)
                    # capacity,  # общая емкость в байтах (int)
                    # allocation,  # использовано байт (int)
                    # available  # доступно байт (int)
                    pool_info_state = pool_info[0]
                    if pool_info_state != libvirt.VIR_STORAGE_POOL_RUNNING:
                        try:
                            pool.create(0)
                            self.logger.debug(f"Пул {pool.name()} запущен")
                        except:
                            self.logger.warning(f"Не удалось запустить пул {pool.name()}")
                            continue

                    pool_name = pool.name()
                    volumes = pool.listAllVolumes()
                    self.logger.debug(f"Пул {pool_name} содержит {len(volumes)} томов")

                    for vol in volumes:
                        try:
                            disk = self._volume_to_disk(vol, pool_name)
                            if disk:
                                disks.append(disk)
                        except libvirt.libvirtError as e:
                            self.logger.debug(f"Ошибка при обработке тома {vol.name()}: {e}")
                            continue

                except libvirt.libvirtError as e:
                    self.logger.debug(f"Ошибка при обработке пула {pool.name()}: {e}")
                    continue

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при получении дисков из пулов: {e}")
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка при получении дисков из пулов: {e}")

        return disks

    def _get_file_disks(self, query: DiskQuery | None) -> List[Disk]:
        """Получить файловые диски из стандартных директорий"""
        disks = []

        # Стандартные директории для поиска дисков
        standard_dirs = [
            "/var/lib/libvirt/images",
            "/var/lib/libvirt/volumes",
            "/opt/vm_disks",
            os.path.expanduser("~/vm_disks")
        ]

        # Добавляем директорию из query если указана
        if query and hasattr(query, 'search_path'):
            standard_dirs.insert(0, query.search_path)
            self.logger.debug(f"Добавлен пользовательский путь поиска: {query.search_path}")

        for dir_path in standard_dirs:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                try:
                    self.logger.debug(f"Поиск дисков в директории: {dir_path}")
                    for file_name in os.listdir(dir_path):
                        file_path = os.path.join(dir_path, file_name)

                        # Проверяем, является ли файлом диска
                        if self._is_disk_file(file_path):
                            self.logger.debug(f"Найден потенциальный диск: {file_name}")
                            disk_info = self._get_file_disk_info(file_path)
                            if disk_info:
                                disks.append(disk_info)
                except Exception as e:
                    self.logger.debug(f"Ошибка при поиске дисков в {dir_path}: {e}")
                    continue

        return disks

    def _is_disk_file(self, file_path: str) -> bool:
        """Проверить, является ли файл виртуальным диском"""
        disk_extensions = {'.qcow2', '.raw', '.img', '.vmdk', '.vdi', '.vhd', '.vhdx'}
        is_disk = (os.path.isfile(file_path) and
                   any(file_path.endswith(ext) for ext in disk_extensions))
        if is_disk:
            self.logger.debug(f"Файл {file_path} идентифицирован как виртуальный диск")
        return is_disk

    def _get_attached_disks(self, query: DiskQuery | None, existing_disks: List[Disk] | None = None) -> List[Disk]:
        """Получить информацию о дисках, подключенных к ВМ"""
        attached_disks = []

        try:
            # Получаем все ВМ
            vm_ids = self.conn.listDomainsID()
            all_vms = []

            # Активные ВМ
            for vm_id in vm_ids:
                vm = self.conn.lookupByID(vm_id)
                all_vms.append(vm)

            # Неактивные ВМ
            for vm_name in self.conn.listDefinedDomains():
                vm = self.conn.lookupByName(vm_name)
                all_vms.append(vm)

            self.logger.debug(f"Всего ВМ для проверки: {len(all_vms)}")

            # Сопоставляем диски из ВМ
            for vm in all_vms:
                try:
                    vm_name = vm.name()

                    # Проверяем фильтр по ВМ
                    if query and query.vm_name and query.vm_name != vm_name:
                        continue

                    # Получаем XML конфигурации ВМ
                    xml_desc = vm.XMLDesc()
                    disk_blocks = self._extract_disk_blocks_from_vm_xml(xml_desc)

                    self.logger.debug(f"ВМ {vm_name} содержит {len(disk_blocks)} дисков")

                    for disk_block in disk_blocks:
                        disk_path = disk_block.get('source_file')
                        if not disk_path:
                            continue

                        # Проверяем, есть ли уже этот диск в списке
                        disk_exists = False
                        if existing_disks:
                            for disk in existing_disks:
                                if disk.path == disk_path:
                                    disk_exists = True
                                    break

                        if not disk_exists:
                            # Создаем новый объект диска
                            disk = self._create_disk_from_vm_attachment(
                                disk_path, vm_name,
                                disk_block.get('target_dev'),
                                disk_block.get('bus_type'),
                                disk_block.get('driver_type')
                            )
                            if disk:
                                attached_disks.append(disk)
                                self.logger.debug(f"Добавлен подключенный диск: {disk_path} для ВМ {vm_name}")

                except libvirt.libvirtError as e:
                    self.logger.debug(f"Ошибка при обработке ВМ {vm.name()}: {e}")
                    continue

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при получении подключенных дисков: {e}")
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка при получении подключенных дисков: {e}")

        return attached_disks

    def _extract_disk_blocks_from_vm_xml(self, xml_desc: str) -> List[dict]:
        """Извлечь информацию о дисках из XML ВМ"""
        disk_blocks = []

        # Парсим XML для поиска блоков дисков
        lines = xml_desc.split('\n')
        i = 0

        while i < len(lines):
            if '<disk ' in lines[i]:
                disk_block = {}
                j = i

                # Читаем до закрывающего тега </disk>
                while j < len(lines) and '</disk>' not in lines[j]:
                    line = lines[j]

                    # Извлекаем путь к файлу диска
                    if 'file=' in line:
                        match = re.search(r"file=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['source_file'] = match.group(1)

                    # Извлекаем целевое устройство
                    if 'target dev=' in line:
                        match = re.search(r"dev=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['target_dev'] = match.group(1)

                    # Извлекаем тип шины
                    if 'bus=' in line:
                        match = re.search(r"bus=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['bus_type'] = match.group(1)

                    # Извлекаем тип драйвера
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
        """Создать объект Disk для диска, подключенного к ВМ"""
        try:
            # Определяем формат диска
            disk_format = DiskFormat.UNKNOWN
            if driver_type:
                try:
                    disk_format = DiskFormat(driver_type)
                except ValueError:
                    self.logger.debug(f"Неизвестный тип драйвера: {driver_type}")

            # Если не удалось определить по driver_type, пробуем по расширению
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

            # Получаем размер файла
            size_bytes = 0
            file_path_exists = False
            if os.path.exists(disk_path):
                size_bytes = os.path.getsize(disk_path)
                file_path_exists = True

            # Преобразуем bus_type
            bus_type = None
            if bus_type_str:
                try:
                    bus_type = BusType(bus_type_str)
                except ValueError:
                    bus_type = None
                    self.logger.debug(f"Неизвестный тип шины: {bus_type_str}")

            disk = Disk(
                name=os.path.basename(disk_path),
                path=disk_path,
                file_path_exists=file_path_exists,
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
            self.logger.exception(f"Ошибка при создании диска из подключения ВМ: {e}")
            return None

    def _volume_to_disk(self, vol, pool_name: str) -> Disk | None:
        """Преобразовать libvirt volume в объект Disk"""
        try:
            vol_info = vol.info()
            vol_xml = vol.XMLDesc()

            # Определяем формат диска
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
        except libvirt.libvirtError as e:
            self.logger.debug(f"Ошибка при преобразовании тома {vol.name()}: {e}")
            return None

    def _remove_duplicate_disks(self, disks: List[Disk]) -> List[Disk]:
        """Удалить дубликаты дисков из списка"""
        unique_disks = {}

        for disk in disks:
            if disk.path not in unique_disks:
                unique_disks[disk.path] = disk
            else:
                # Объединяем информацию из дубликатов
                existing = unique_disks[disk.path]
                if disk.vm_name and not existing.vm_name:
                    existing.vm_name = disk.vm_name
                    existing.status = DiskStatus.ATTACHED
                    existing.type = DiskType.VM_ATTACHED
                    self.logger.debug(f"Обновлена информация о диске {disk.path}: добавлена ВМ {disk.vm_name}")
                if disk.pool and not existing.pool:
                    existing.pool = disk.pool
                    existing.type = DiskType.POOL_DISK
                    self.logger.debug(f"Обновлена информация о диске {disk.path}: добавлен пул {disk.pool}")

        return list(unique_disks.values())

    def _apply_filters(self, disks: List[Disk], query: DiskQuery | None) -> List[Disk]:
        """Применить фильтры к списку дисков"""
        if not query:
            return disks

        filtered_disks = []
        filtered_out = 0

        for disk in disks:
            if self._filter_disk(disk, query):
                filtered_disks.append(disk)
            else:
                filtered_out += 1

        if filtered_out > 0:
            self.logger.debug(f"Фильтрация отбросила {filtered_out} дисков")

        return filtered_disks

    def _filter_disk(self, disk: Disk, query: DiskQuery | None) -> bool:
        """Применить фильтры к диску"""
        if not query:
            return True

        # Фильтр по формату
        if query.format and disk.format != query.format:
            self.logger.debug(f"Диск {disk.name} отфильтрован: формат {disk.format} != {query.format}")
            return False

        # Фильтр по размеру
        size_gb = disk.get_effective_size_gb()
        if query.min_size_gb is not None and size_gb < query.min_size_gb:
            self.logger.debug(f"Диск {disk.name} отфильтрован: размер {size_gb}GB < {query.min_size_gb}GB")
            return False
        if query.max_size_gb is not None and size_gb > query.max_size_gb:
            self.logger.debug(f"Диск {disk.name} отфильтрован: размер {size_gb}GB > {query.max_size_gb}GB")
            return False

        # Фильтр по ВМ (для подключенных дисков)
        if query.vm_name and disk.vm_name != query.vm_name:
            self.logger.debug(f"Диск {disk.name} отфильтрован: ВМ {disk.vm_name} != {query.vm_name}")
            return False

        # Фильтр по пулу (для дисков в пулах)
        if query.pool and disk.pool != query.pool:
            self.logger.debug(f"Диск {disk.name} отфильтрован: пул {disk.pool} != {query.pool}")
            return False

        # Фильтр по подключенным дискам
        if query.attached_only is not None:
            if query.attached_only and disk.status != DiskStatus.ATTACHED:
                self.logger.debug(f"Диск {disk.name} отфильтрован: не подключен")
                return False
            elif not query.attached_only and disk.status == DiskStatus.ATTACHED:
                self.logger.debug(f"Диск {disk.name} отфильтрован: подключен")
                return False

        self.logger.debug(f"Диск {disk.name} прошел фильтрацию")
        return True

    def discover_disks(self, search_path: str | None = None) -> List[Disk]:
        """
        Обнаружить диски в файловой системе

        Args:
            search_path: Путь для поиска дисков (если None, ищет в стандартных директориях)

        Returns:
            List[Disk]: Список обнаруженных дисков
        """
        disks = []

        if search_path:
            search_dirs = [search_path]
            self.logger.info(f"Обнаружение дисков в пользовательской директории: {search_path}")
        else:
            search_dirs = [
                "/var/lib/libvirt/images",
                "/var/lib/libvirt/volumes",
                "/opt/vm_disks",
                os.path.expanduser("~/vm_disks")
            ]
            self.logger.info("Обнаружение дисков в стандартных директориях")

        for dir_path in search_dirs:
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                self.logger.info(f"Поиск дисков в: {dir_path}")

                for root, dirs, files in os.walk(dir_path):
                    for file_name in files:
                        file_path = os.path.join(root, file_name)

                        if self._is_disk_file(file_path):
                            try:
                                disk_info = self._get_file_disk_info(file_path)
                                if disk_info:
                                    disks.append(disk_info)
                                    self.logger.info(f"  Найден диск: {file_name}")
                            except Exception as e:
                                self.logger.error(f"  Ошибка при обработке {file_name}: {e}")

        self.logger.info(f"Обнаружено всего дисков: {len(disks)}")
        return disks

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
            import subprocess

            if not os.path.exists(source_path):
                self.logger.error(f"Исходный файл {source_path} не существует")
                return False

            # Проверяем, что директория для сохранения существует
            target_dir = os.path.dirname(target_path)
            if not os.path.exists(target_dir):
                self.logger.info(f"Создание директории для результата: {target_dir}")
                os.makedirs(target_dir, exist_ok=True)

            # Формируем команду qemu-img
            sparse_flag = [] if sparse else ["-S", "0"]
            cmd = ["qemu-img", "convert"] + sparse_flag + ["-O", target_format.value,
                                                           source_path, target_path]

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

    def get_disks_by_vm(self, vm_name: str, include_system: bool = True) -> List[Disk]:
        """
        Получить все диски, подключенные к указанной виртуальной машине

        Args:
            vm_name: Имя виртуальной машины
            include_system: Включать ли системные диски (загрузочные)

        Returns:
            List[Disk]: Список дисков, подключенных к ВМ
        """
        disks = []
        try:
            self.logger.info(f"Получение дисков ВМ {vm_name}, include_system={include_system}")

            vm = self.conn.lookupByName(vm_name)
            xml_desc = vm.XMLDesc()

            # Извлекаем информацию о дисках из XML ВМ
            disk_blocks = self._extract_disk_blocks_from_vm_xml(xml_desc)

            self.logger.debug(f"ВМ {vm_name} содержит {len(disk_blocks)} дисков")

            for disk_block in disk_blocks:
                disk_path = disk_block.get('source_file')
                if not disk_path:
                    continue

                # Получаем тип устройства
                device_type = disk_block.get('device_type', 'disk')
                if not include_system and device_type == 'cdrom':
                    # Пропускаем CD-ROM если не включены системные диски
                    self.logger.debug(f"Пропущен CD-ROM: {disk_path}")
                    continue

                # Получаем информацию о диске
                disk_info = self.get_disk_info(path=disk_path)
                if disk_info:
                    # Дополняем информацию из XML ВМ
                    disk_info.target_dev = disk_block.get('target_dev')
                    disk_info.vm_name = vm_name
                    disk_info.status = DiskStatus.ATTACHED

                    # Определяем тип шины
                    bus_type_str = disk_block.get('bus_type')
                    if bus_type_str:
                        try:
                            disk_info.bus_type = BusType(bus_type_str)
                        except ValueError:
                            disk_info.bus_type = None

                    disks.append(disk_info)
                    self.logger.debug(f"Добавлен диск ВМ: {disk_path} как {disk_info.target_dev}")

            self.logger.info(f"Найдено {len(disks)} дисков для ВМ {vm_name}")
            return disks

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при получении дисков ВМ {vm_name}: {e}")
            return []
        except Exception as e:
            self.logger.exception(f"Ошибка при обработке дисков ВМ {vm_name}: {e}")
            return []

    def get_disks_by_node(self, node_name: str | None = None) -> List[Disk]:
        """
        Получить все диски, доступные на указанном узле (хосте)

        Args:
            node_name: Имя узла (None для текущего узла)

        Returns:
            List[Disk]: Список дисков на узле
        """
        disks = []
        try:
            # Если node_name не указан, используем информацию о текущем подключении
            if node_name is None:
                # Получаем информацию о текущем подключении
                hostname = self.conn.getHostname()
                node_name = hostname
                self.logger.debug(f"Используется текущий узел: {node_name}")

            self.logger.info(f"Поиск дисков на узле: {node_name}")

            # Получаем все диски с текущего узла
            all_disks = self.list_disks()

            # Фильтруем диски, которые физически находятся на этом узле
            for disk in all_disks:
                # Проверяем путь к диску - если он находится в локальной файловой системе
                if self._is_local_disk(disk.path):
                    disks.append(disk)

            self.logger.info(f"Найдено {len(disks)} локальных дисков на узле {node_name}")
            return disks

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при получении дисков узла {node_name}: {e}")
            return []
        except Exception as e:
            self.logger.exception(f"Ошибка при обработке дисков узла {node_name}: {e}")
            return []

    def get_disks_by_resource_pool(self, pool_name: str, include_attached: bool = True) -> List[Disk]:
        """
        Получить все диски в указанном пуле ресурсов (storage pool)

        Args:
            pool_name: Имя пула ресурсов
            include_attached: Включать ли диски, подключенные к ВМ

        Returns:
            List[Disk]: Список дисков в пуле
        """
        disks = []
        try:
            self.logger.info(f"Получение дисков из пула {pool_name}, include_attached={include_attached}")

            pool = self.conn.storagePoolLookupByName(pool_name)

            # Проверяем состояние пула
            try:
                pool_info = pool.info()
                if pool_info.state != libvirt.VIR_STORAGE_POOL_RUNNING:
                    self.logger.info(f"Активация пула {pool_name}")
                    pool.create(0)
            except Exception as e:
                self.logger.error(f"Не удалось активировать пул {pool_name}: {e}")
                return []

            # Получаем все тома в пуле
            volumes = pool.listAllVolumes()
            self.logger.debug(f"Пул {pool_name} содержит {len(volumes)} томов")

            for vol in volumes:
                try:
                    disk = self._volume_to_disk(vol, pool_name)
                    if disk:
                        # Если нужно проверить, подключен ли диск
                        if include_attached:
                            # Проверяем, используется ли диск
                            if self._is_disk_in_use(disk.path):
                                vm_name = self._find_vm_by_disk_path(disk.path)
                                if vm_name:
                                    disk.vm_name = vm_name
                                    disk.status = DiskStatus.ATTACHED
                                    disk.type = DiskType.VM_ATTACHED
                                    self.logger.debug(f"Диск {disk.name} подключен к ВМ {vm_name}")

                        disks.append(disk)
                except libvirt.libvirtError as e:
                    self.logger.error(f"Ошибка при обработке тома {vol.name()}: {e}")
                    continue

            self.logger.info(f"Найдено {len(disks)} дисков в пуле {pool_name}")
            return disks

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при получении дисков пула {pool_name}: {e}")
            return []
        except Exception as e:
            self.logger.exception(f"Ошибка при обработке дисков пула {pool_name}: {e}")
            return []

    def get_vm_disk_usage(self, vm_name: str) -> dict:
        """
        Получить статистику использования дисков указанной ВМ

        Args:
            vm_name: Имя виртуальной машины

        Returns:
            dict: Статистика использования дисков
        """
        try:
            self.logger.info(f"Получение статистики использования дисков ВМ {vm_name}")

            disks = self.get_disks_by_vm(vm_name, include_system=True)

            total_capacity = 0
            total_allocated = 0
            disk_count = len(disks)
            system_disks = 0
            data_disks = 0

            for disk in disks:
                if disk.capacity_bytes:
                    total_capacity += disk.capacity_bytes
                if disk.allocation_bytes:
                    total_allocated += disk.allocation_bytes

                # Определяем тип диска
                if disk.target_dev and disk.target_dev.startswith(('vd', 'sd')):
                    if disk.target_dev in ['vda', 'sda']:  # Предполагаем, что это системный диск
                        system_disks += 1
                    else:
                        data_disks += 1

            result = {
                'vm_name': vm_name,
                'disk_count': disk_count,
                'system_disks': system_disks,
                'data_disks': data_disks,
                'total_capacity_gb': round(total_capacity / (1024 ** 3), 2),
                'total_allocated_gb': round(total_allocated / (1024 ** 3), 2),
                'usage_percentage': round((total_allocated / total_capacity * 100), 1) if total_capacity > 0 else 0,
                'disks': [
                    {
                        'name': disk.name,
                        'path': disk.path,
                        'target_dev': disk.target_dev,
                        'format': disk.format.value if disk.format else 'unknown',
                        'capacity_gb': disk.get_effective_size_gb(),
                        'allocation_percentage': disk.get_allocation_percentage(),
                        'is_attached': disk.is_attached() if hasattr(disk, 'is_attached') else True
                    }
                    for disk in disks
                ]
            }

            self.logger.info(
                f"Статистика ВМ {vm_name}: {disk_count} дисков, {result['total_capacity_gb']}GB всего, {result['usage_percentage']}% использовано")
            return result

        except Exception as e:
            self.logger.exception(f"Ошибка при получении статистики использования дисков ВМ {vm_name}: {e}")
            return {}

    def get_node_storage_summary(self, node_name: str | None = None) -> dict:
        """
        Получить сводку по хранилищу на узле

        Args:
            node_name: Имя узла (None для текущего узла)

        Returns:
            dict: Сводка по хранилищу
        """
        try:
            self.logger.info(f"Получение сводки по хранилищу узла: {node_name}")

            disks = self.get_disks_by_node(node_name)

            # Группируем по типам
            pool_disks = [d for d in disks if d.type == DiskType.POOL_DISK]
            attached_disks = [d for d in disks if d.status == DiskStatus.ATTACHED]
            detached_disks = [d for d in disks if d.status == DiskStatus.DETACHED]
            external_disks = [d for d in disks if d.type == DiskType.EXTERNAL_DISK]

            # Общая статистика
            total_capacity = sum(d.capacity_bytes for d in disks if d.capacity_bytes)
            total_allocated = sum(d.allocation_bytes for d in disks if d.allocation_bytes)

            # Статистика по форматам
            format_stats = {}
            for disk in disks:
                fmt = disk.format.value if disk.format else 'unknown'
                format_stats[fmt] = format_stats.get(fmt, 0) + 1


            result = {
                'node_name': node_name or self.conn.getHostname(),
                'total_disks': len(disks),
                'pool_disks': len(pool_disks),
                'attached_disks': len(attached_disks),
                'detached_disks': len(detached_disks),
                'external_disks': len(external_disks),
                'format_distribution': format_stats,
                'total_capacity_tb': round(total_capacity / (1024 ** 4), 3),
                'total_allocated_tb': round(total_allocated / (1024 ** 4), 3),
                'free_space_tb': round((total_capacity - total_allocated) / (1024 ** 4), 3),
                'usage_percentage': round((total_allocated / total_capacity * 100), 1) if total_capacity > 0 else 0
            }

            self.logger.info(
                f"Сводка узла {result['node_name']}: {result['total_disks']} дисков, {result['total_capacity_tb']}TB всего, {result['usage_percentage']}% использовано")
            return result

        except Exception as e:
            self.logger.exception(f"Ошибка при получении сводки по хранилищу узла {node_name}: {e}")
            return {}

    # def get_pool_storage_summary(self, pool_name: str) -> PoolInfo | None:
    #     """
    #     Получить сводку по хранилищу в пуле
    #
    #     Args:
    #         pool_name: Имя пула ресурсов
    #
    #     Returns:
    #         dict: Сводка по хранилищу пула
    #     """
    #     try:
    #         self.logger.info(f"Получение сводки по пулу {pool_name}")
    #
    #         disks = self.get_disks_by_resource_pool(pool_name)
    #         attached_disks = [d for d in disks if d.status == DiskStatus.ATTACHED]
    #         detached_disks = [d for d in disks if d.status == DiskStatus.DETACHED]
    #
    #         # Общая статистика
    #         total_capacity = sum(d.capacity_bytes for d in disks if d.capacity_bytes)
    #         total_allocated = sum(d.allocation_bytes for d in disks if d.allocation_bytes)
    #
    #         # Статистика пула
    #         pool = self.conn.storagePoolLookupByName(pool_name)
    #         pool_info = pool.info()
    #
    #
    #         # Статистика по форматам
    #         format_stats = {}
    #         for disk in disks:
    #             fmt = disk.format.value if disk.format else 'unknown'
    #             format_stats[fmt] = format_stats.get(fmt, 0) + 1
    #
    #         result = PoolInfo(pool_name=pool_name,
    #                         pool_state=PoolState.get(pool_info.state, "unknown"),
    #                         pool_capacity_gb=round(pool_info.capacity / (1024 ** 3), 2),
    #                         pool_allocation_gb=round(pool_info.allocation / (1024 ** 3), 2),
    #                         pool_available_gb=round(pool_info.available / (1024 ** 3), 2),
    #                         total_disks=len(disks),
    #                         attached_disks=len(attached_disks),
    #                         detached_disks=len(detached_disks),
    #                         format_distribution=format_stats,
    #                         disks_capacity_gb=round(total_capacity / (1024 ** 3), 2),
    #                         disks_allocated_gb=round(total_allocated / (1024 ** 3), 2),
    #                         disks_usage_percentage=round((total_allocated / total_capacity * 100),
    #                                             1) if total_capacity > 0 else 0)
    #
    #         self.logger.info(
    #             f"Сводка пула {pool_name}: {result['total_disks']} дисков, {result['pool_capacity_gb']}GB всего, {result['pool_available_gb']}GB свободно")
    #         return result
    #
    #     except libvirt.libvirtError as e:
    #         self.logger.error(f"Ошибка libvirt при получении сводки пула {pool_name}: {e}")
    #         return None
    #     except Exception as e:
    #         self.logger.exception(f"Ошибка при обработке сводки пула {pool_name}: {e}")
    #         return None

    def find_disk_by_path_pattern(self, pattern: str) -> list[Disk]:
        """
        Найти диски по шаблону пути

        Args:
            pattern: Регулярное выражение для поиска в путях

        Returns:
            list[Disk]: Найденные диски
        """
        disks = []
        try:
            self.logger.info(f"Поиск дисков по шаблону: {pattern}")

            all_current_disks = self.list_disks()
            regex = re.compile(pattern, re.IGNORECASE)

            for current_disk in all_current_disks:
                if regex.search(current_disk.path):
                    disks.append(current_disk)

            self.logger.info(f"Найдено {len(disks)} дисков по шаблону {pattern}")
            return disks

        except re.error as e:
            self.logger.error(f"Неверное регулярное выражение {pattern}: {e}")
            return []
        except Exception as e:
            self.logger.exception(f"Ошибка при поиске дисков по шаблону {pattern}: {e}")
            return []

    # Вспомогательные методы

    def _is_local_disk(self, path: str) -> bool:
        """
        Проверить, является ли диск локальным (находится на локальной файловой системе)

        Args:
            path: Путь к диску

        Returns:
            bool: True если диск локальный
        """
        try:

            path_lower = path.lower()
            for network_prefix in self.libvirt_config.network_prefixes:
                if path_lower.startswith(network_prefix):
                    self.logger.debug(f"Путь {path} определен как сетевой")
                    return False

            for local_prefix in self.libvirt_config.local_prefixes:
                if path.startswith(local_prefix):
                    self.logger.debug(f"Путь {path} определен как локальный (префикс {local_prefix})")
                    return True

            # Если путь абсолютный и не сетевой, считаем локальным
            is_local = os.path.isabs(path) and not path.startswith('//')
            self.logger.debug(f"Путь {path} определен как локальный: {is_local}")
            return is_local

        except Exception as e:
            self.logger.debug(f"Ошибка при определении типа диска {path}: {e}")
            return False


if __name__ == "__main__":
    # Пример использования
    with StorageManager().with_default_user() as manager:
        # Обнаружение дисков
        logger.info("=== Обнаружение дисков ===")
        discovered_disks = manager.discover_disks()
        logger.info(f"Найдено дисков: {len(discovered_disks)}")
        # '/tmp/vm_storage_test_jq1o9yh5/attached_disks/attach-test-disk.qcow2'
        # print(manager.detach_disk_from_vm(DiskDetach(vm_name="test-vm-03", target_dev="hdb")))
        # Получение списка всех дисков
        logger.info("\n=== Все диски ===")
        all_disks = manager.list_disks()
        logger.info(f"Всего дисков в системе: {len(all_disks)}")
        for disk in all_disks:
            logger.info(f"Статус диска: {disk.name} - {disk.status}, существование диска: {disk.file_path_exists}, target_dev: {disk.target_dev}")

        # Получение дисков ВМ
        logger.info("\n=== Диски ВМ ===")
        for disk in manager.get_disks_by_vm("test-vm-03"):
            logger.info(f"ДИСК ВМ: {disk.name}")

        # Получение дисков хоста
        logger.info("\n=== Диски хоста ===")
        for disk in manager.get_disks_by_node():
            logger.info(f"ДИСК ХОСТА: {disk.name}")

        # print(manager.delete_disk(path="/var/lib/libvirt/images/disk-859480.qcow2"))