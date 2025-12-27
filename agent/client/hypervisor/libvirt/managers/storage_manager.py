import libvirt
import os
import re
import shutil
from datetime import datetime
from typing import List
import logging

from agent.client.hypervisor.libvirt.config import LibvirtConfig
from agent.client.hypervisor.models.disk import (
    Disk, DiskCreate, DiskUpdate, DiskAttach, DiskDetach, DiskQuery,
    DiskFormat, DiskType, DiskStatus, BusType
)
from agent.client.hypervisor.libvirt.client import LibvirtClient


class StorageManager(LibvirtClient):
    def __init__(self, connection_uri: str = "qemu:///session", username: str | None = None,
                 password: str | None = None):
        super().__init__(connection_uri, username, password)
        self.logger = logging.getLogger(__name__)
        self.libvirt_config = LibvirtConfig()

    def create_disk(self, disk_create: DiskCreate) -> Disk | None:
        try:
            self.logger.info(f"Создание диска: {disk_create.name}, размер: {disk_create.size_gb}GB")

            if disk_create.pool is not None:
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
            disk = self.get_disk_info(pool_name=disk_create.pool, disk_name=disk_create.name)

            if disk:
                self.logger.info(f"Диск создан: {disk.name}, размер: {disk.get_effective_size_gb()}GB")
            return disk

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка создания пулового диска: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
            return None

    def _create_file_disk(self, disk_create: DiskCreate) -> Disk | None:
        try:
            disk_path = disk_create.path
            if not disk_path:
                default_dir = "/var/lib/libvirt/images"
                extension = f".{disk_create.format.value}"
                disk_name = f"{disk_create.name}{extension}" if not disk_create.name.endswith(
                    extension) else disk_create.name
                disk_path = os.path.join(default_dir, disk_name)

            disk_dir = os.path.dirname(disk_path)
            if not os.path.exists(disk_dir):
                os.makedirs(disk_dir, exist_ok=True)

            self.logger.info(f"Создание файлового диска: {disk_path}, размер: {disk_create.size_gb}GB")

            pool = self._get_or_create_file_pool(disk_dir)
            size_bytes = int(disk_create.size_gb * 1024 * 1024 * 1024)
            volume_name = re.sub(r'\.(qcow2|raw|img|vmdk|vdi|vhd|vhdx)$', '', os.path.basename(disk_path))

            xml_desc = f'''
            <volume>
                <name>{volume_name}</name>
                <capacity unit="bytes">{size_bytes}</capacity>
                <target>
                    <path>{disk_path}</path>
                    <format type='{disk_create.format.value}'/>
                    <permissions>
                        <mode>0644</mode>
                    </permissions>
                </target>
            </volume>
            '''

            vol = pool.createXML(xml_desc, 0)

            if not disk_create.sparse and disk_create.format == DiskFormat.RAW:
                self._fill_raw_disk_with_zeros(vol, size_bytes)

            disk = self.get_disk_info(pool_name=pool.name(), disk_name=volume_name)

            if disk:
                self.logger.info(f"Файловый диск создан: {disk.name}")
            return disk

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка создания файлового диска: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
            return None

    def _get_or_create_file_pool(self, path: str):
        try:
            pool_name = f"file_pool_{hash(path) % 1000000}"
            try:
                pool = self.conn.storagePoolLookupByName(pool_name)
                return pool
            except libvirt.libvirtError:
                pool_xml = f'''
                <pool type='dir'>
                    <name>{pool_name}</name>
                    <target>
                        <path>{path}</path>
                    </target>
                </pool>
                '''
                pool = self.conn.storagePoolDefineXML(pool_xml, 0)
                pool.create(0)
                return pool
        except Exception as e:
            self.logger.error(f"Ошибка создания пула: {e}")
            raise

    def _fill_raw_disk_with_zeros(self, vol, size_bytes):
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
                self.logger.info(f"Диск {disk_name} удален")
                return True

            elif path:
                disk = self.get_disk_info(path=path)
                if not disk:
                    return False

                if self._is_disk_in_use(path):
                    self.logger.warning(f"Диск {path} используется")
                    return False

                if disk.pool and disk.name:
                    return self.delete_disk(pool_name=disk.pool, disk_name=disk.name)
                else:
                    os.remove(path)
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
            disk = self.get_disk_info(path=path)
            if not disk:
                return None

            if disk_update.name is not None and disk_update.name != disk.name:
                new_path = os.path.join(os.path.dirname(path), disk_update.name)
                shutil.move(path, new_path)
                path = new_path

            if disk_update.new_size_gb is not None and disk.pool and disk.name:
                pool = self.conn.storagePoolLookupByName(disk.pool)
                vol = pool.storageVolLookupByName(disk.name)

                current_size_gb = disk.get_effective_size_gb()
                if disk_update.new_size_gb > current_size_gb:
                    new_size_bytes = int(disk_update.new_size_gb * 1024 * 1024 * 1024)
                    vol.resize(new_size_bytes, 0)
                    self.logger.info(f"Размер изменен на {disk_update.new_size_gb}GB")

            return self.get_disk_info(path=path)

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка изменения файлового диска: {e}")
            return None

    def clone_disk(self, source_path: str, target_path: str, target_name: str = None) -> Disk | None:
        try:
            self.logger.info(f"Клонирование диска: {source_path} -> {target_path}")

            source_disk = self.get_disk_info(path=source_path)
            if not source_disk:
                return None

            target_name = target_name or f"{os.path.basename(source_path)}_clone"
            target_dir = os.path.dirname(target_path)

            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)

            if source_disk.format == DiskFormat.QCOW2:
                pool = self._get_or_create_file_pool(target_dir)

                xml_desc = f'''
                <volume>
                    <name>{target_name}</name>
                    <capacity unit="bytes">{source_disk.capacity_bytes}</capacity>
                    <target>
                        <path>{target_path}</path>
                        <format type='qcow2'/>
                    </target>
                </volume>
                '''

                vol = pool.createXMLFrom(xml_desc, source_disk.path, 0)
            else:
                shutil.copy2(source_path, target_path)

            return self.get_disk_info(path=target_path)

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка клонирования: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
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

    def detach_disk(self, detach_disk: DiskDetach) -> bool:
        try:
            self.logger.info(f"Отключение диска от ВМ {detach_disk.vm_name}")

            vm = self.conn.lookupByName(detach_disk.vm_name)
            xml_desc = vm.XMLDesc()

            disk_xml = None
            for line in xml_desc.split('\n'):
                if '<disk ' in line and detach_disk.target_dev in line:
                    start_idx = xml_desc.find(line)
                    end_idx = xml_desc.find('</disk>', start_idx) + 7
                    disk_xml = xml_desc[start_idx:end_idx]
                    break

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

            source_disk = self.get_disk_info(path=source_path)
            if not source_disk:
                return False

            pool = self._get_or_create_file_pool(target_dir)

            xml_desc = f'''
            <volume>
                <name>{os.path.basename(target_path)}</name>
                <capacity unit="bytes">{source_disk.capacity_bytes}</capacity>
                <target>
                    <path>{target_path}</path>
                    <format type='{target_format.value}'/>
                </target>
            </volume>
            '''

            vol = pool.createXMLFrom(xml_desc, source_path, 0)

            self.logger.info("Конвертация завершена")
            return True

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка конвертации: {e}")
            return False
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
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

            size_bytes = os.path.getsize(path) if file_path_exists else 0

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
                name=os.path.basename(path),
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
            "/var/lib/libvirt/images",
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
        disks = manager.list_disks()
        for current_disk in disks:
            print(f"****************************************************************\n"
                  f"ИМЯ ДИСКА: {current_disk.name}\n"
                  f"ПУТЬ ДИСКА: {current_disk.path}\n"
                  f"TARGET_DEV: {current_disk.target_dev}\n"
                  f"К КАКОЙ ВМ ПОДКЛЮЧЕН ДИСК: {current_disk.vm_name}\n")
        print(f"Всего дисков: {len(disks)}")
