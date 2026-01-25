import logging
import os
import re
import shutil
from xml.etree import ElementTree
from datetime import datetime
from pathlib import Path
from subprocess import TimeoutExpired

import libvirt
import orjson

from agent.client.cli import CLIControl
from agent.client.hypervisor.ha.controller import HAController
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.config import LibvirtConfig
from agent.client.hypervisor.libvirt.models.volume.disk import (
    BusType,
    CacheMode,
    Disk,
    DiskAttach,
    DiskCreate,
    DiskDetach,
    DiskFormat,
    DiskQuery,
    DiskStatus,
    DiskType,
    DiskUpdate,
    QemuDisk,
)
from agent.client.hypervisor.libvirt.models.msg import (
    CommandMessagesEnum,
    StorageMessage,
)
from agent.client.lvm.group import VolumeGroupManager
from agent.client.lvm.logical import LogicalVolumeManager


class StorageManager(LibvirtClient):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.libvirt_config = LibvirtConfig()
        self.cli = CLIControl()
        self.system_volume_group_name = os.environ.get("VOLUME_GROUP")
        self.system_disk_path = os.environ.get("SYSTEM_DISK_PATH")
        self.volume_group_manager = VolumeGroupManager()
        self.logic_volume_manager = LogicalVolumeManager()
        self.ha_controller = HAController()

    def create_disk(self, disk_create: DiskCreate) -> StorageMessage:
        ha_nfs_storages = self.ha_controller.loaded_ha_nfs_storages.nfs_storages
        if ha_nfs_storages and disk_create.path is None:
            ha_nfs_storage = ha_nfs_storages.pop()
            disk_create.path = ha_nfs_storage.mount
        elif disk_create.path is None:
            disk_create.path = self.system_disk_path
        try:
            if disk_create.resource_pool:
                create_resource_pool_disk_result = self._create_lv_in_resource_pool(
                    disk_create
                )
                return create_resource_pool_disk_result
            else:
                create_file_disk_result = self._create_file_disk(disk_create)
                return create_file_disk_result

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt: {e}")
            return StorageMessage(
                code=CommandMessagesEnum.disk_create_error.name,
                note=str(e),
            )
        except Exception as e:
            self.logger.exception(f"Ошибка: {e}")
            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_create_error.name,
                note=str(e),
            )

    def mount_lv_to_system(self, source: str, point: str):
        # Монтируем LV в файловую систему нашей OS
        cmd_args = [
            "mount",
            source,
            point,
        ]
        result = self.cli.execute(cmd_args)
        self.logger.info(f"Результат монтирования диска: '{result}'")

        return result

    def _create_lv_in_resource_pool(  # TODO: Разобраться почему нету
        self, disk_create: DiskCreate
    ) -> StorageMessage:
        current_lv = self.logic_volume_manager.get_volume_by_name(
            disk_create.name, self.system_volume_group_name
        )
        if current_lv is None:
            result_create_lv = self.logic_volume_manager.create_volume_in_thin_pool(
                logic_volume_name=disk_create.name,
                logic_volume_size=disk_create.size_gb,
                volume_group_name=self.system_volume_group_name,
                logic_tp_volume_name=disk_create.resource_pool,
                sparse=disk_create.sparse,
            )
            if (
                f'Logical volume "{disk_create.resource_pool}" created'
                not in result_create_lv
                and "Thin pool" in result_create_lv
            ):
                self.logger.error(
                    f"Не удалось создать LVM пул {disk_create.resource_pool} в VG {self.system_volume_group_name}: {result_create_lv}"
                )
                return StorageMessage(
                    success=False,
                    code=CommandMessagesEnum.virtual_rp_create_logic_volume_error.name,
                )
        if disk_create.format.value == DiskFormat.QCOW2.value:
            disk_create.path = (
                disk_create.path
                + "/"
                + disk_create.resource_pool
                + "/"
                + disk_create.name
            )
            self.logic_volume_manager.convert_file_system_from_raw_to_ext4(
                disk_create.name, self.system_volume_group_name
            )

            # Создаем директорию для точки монтирования
            if not Path(disk_create.path).exists():
                rp_path = Path(disk_create.path)
                rp_path.parent.mkdir()
                rp_path.mkdir()
                self.logger.info("Результат создания директории для точки монтирования")

            source = f"/dev/{self.system_volume_group_name}/{disk_create.name}"
            self.mount_lv_to_system(source, disk_create.path)

        return self._create_file_disk(disk_create)

    def _create_file_disk_in_resource_pool(self, disk_create: DiskCreate):
        try:
            if disk_create.resource_pool is None:
                return StorageMessage(
                    success=False,
                    code=CommandMessagesEnum.rp_virtual_not_found.name,
                    note=str("Отсутствует ресурс пул для создания дисков в нем"),
                )
            disk_path = str(
                Path(disk_create.path)
                / f"{disk_create.name}.{disk_create.format.value}"
            )
            self.logger.info(
                f"Создание файлового диска: {disk_path}, размер: {disk_create.size_gb}GB, ресурс пул: '{disk_create.resource_pool}'"
            )
            if disk_create.format.value == DiskFormat.QCOW2.value:
                if Path(disk_path).exists():
                    self.logger.info(f"Файл уже существует: {disk_path}")
                    return StorageMessage(
                        success=False,
                        code=CommandMessagesEnum.disk_already_created.name,
                    )
                disk_info = self._create_qcow2_disk(
                    disk_path, disk_create.size_gb, disk_create.sparse
                )
                disk_type = (
                    DiskType.EXTERNAL_DISK
                    if disk_create.resource_pool is None
                    else DiskType.POOL_DISK
                )
                disk = Disk(
                    name=disk_create.name,
                    path=disk_path,
                    file_path_exists=True,
                    type=disk_type,
                    format=disk_create.format,
                    capacity_bytes=disk_create.size_bytes,
                    allocation_bytes=disk_create.size_bytes,
                    status=DiskStatus.DETACHED,
                    pool=disk_create.resource_pool,
                )
                disk_info.disk_info = disk

                self.logger.info(f"Файловый диск создан: {disk.name}")
                return disk_info
            elif disk_create.format.value == DiskFormat.RAW.value:
                current_lv = self.logic_volume_manager.get_volume_by_name(
                    disk_create.name, self.system_volume_group_name
                )
                if current_lv is None:
                    return StorageMessage(
                        success=False,
                        code=CommandMessagesEnum.disk_create_error.name,
                    )
                self.logger.info(
                    f"Для RAW диска был создан LV {current_lv.logic_volume_path}"
                )
                vm_name = None
                if self._is_disk_in_use(current_lv.logic_volume_path):
                    vm_name = self._find_vm_by_disk_path(current_lv.logic_volume_path)
                    if vm_name:
                        status = DiskStatus.ATTACHED
                    else:
                        status = DiskStatus.DETACHED
                else:
                    status = DiskStatus.DETACHED

                disk_info = Disk(
                    name=current_lv.logic_volume_name,
                    path=current_lv.logic_volume_path,
                    file_path_exists=True,
                    status=status,
                    type=DiskType.POOL_DISK,
                    format=DiskFormat.RAW,
                    capacity_bytes=current_lv.volume_size,
                    pool=current_lv.logic_volume_pool,
                    allocation_bytes=current_lv.volume_size
                    - current_lv.available_volume_size,
                    vm_name=vm_name,
                    readonly=False,
                )
                return StorageMessage(
                    success=True,
                    code=CommandMessagesEnum.disk_successfully_created.name,
                    disk_info=disk_info,
                )

        except Exception as e:
            self.logger.exception(f"Ошибка создания файлового диска: {e}")
            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_create_error.name,
                note=str(e),
            )

    def _create_file_disk(self, disk_create: DiskCreate) -> StorageMessage:
        try:
            disk_info = None
            if disk_create.format not in (DiskFormat.ISO, DiskFormat.IMG):
                disk_path = str(
                    Path(
                        f"{disk_create.path}/{disk_create.name}.{disk_create.format.value}"
                    )
                )
            else:
                disk_type = (
                    disk_create.disk_type.CDROM
                    if disk_create.resource_pool is None
                    else DiskType.POOL_DISK
                )
                disk = Disk(
                    name=disk_create.name,
                    path=disk_create.path,
                    file_path_exists=True,
                    type=disk_type,
                    format=disk_create.format,
                    capacity_bytes=disk_create.size_bytes,
                    allocation_bytes=disk_create.size_bytes,
                    status=DiskStatus.DETACHED,
                    pool=disk_create.resource_pool,
                )
                return StorageMessage(
                    success=True,
                    code=CommandMessagesEnum.disk_successfully_created.name,
                    disk_info=disk,
                )
            self.logger.info(
                f"Создание файлового диска: {disk_path}, размер: {disk_create.size_gb}GB, ресурс пул: '{disk_create.resource_pool}'"
            )
            if disk_create.resource_pool is not None:
                return self._create_file_disk_in_resource_pool(disk_create)
            else:
                if disk_create.disk_type != DiskType.CDROM and Path(disk_path).exists():
                    self.logger.info(f"Файл уже существует: {disk_path}")
                    return StorageMessage(
                        success=False,
                        code=CommandMessagesEnum.disk_already_created.name,
                    )
            if (
                disk_create.format.value in (DiskFormat.ISO.value, DiskFormat.IMG.value)
                or disk_create.disk_type.value == DiskType.CDROM.value
            ):
                disk_info = StorageMessage(
                    success=True,
                    code=CommandMessagesEnum.disk_successfully_attached.name
                )
            elif disk_create.format.value == DiskFormat.QCOW2.value:
                disk_info = self._create_qcow2_disk(
                    disk_path, disk_create.size_gb, disk_create.sparse
                )
            elif disk_create.format.value == DiskFormat.RAW.value:
                disk_info = self._create_raw_disk(
                    disk_path, disk_create.size_gb, disk_create.sparse
                )

            disk_type = (
                (
                    DiskType.CDROM
                    if disk_create.disk_type == DiskType.CDROM
                    else DiskType.EXTERNAL_DISK
                )
                if disk_create.resource_pool is None
                else DiskType.POOL_DISK
            )
            disk = Disk(
                name=disk_create.name,
                path=disk_path,
                file_path_exists=True,
                type=disk_type,
                format=disk_create.format,
                capacity_bytes=disk_create.size_bytes,
                allocation_bytes=disk_create.size_bytes,
                status=DiskStatus.DETACHED,
                pool=disk_create.resource_pool,
            )
            disk_info.disk_info = disk

            self.logger.info(f"Файловый диск создан: {disk.name}")
            return disk_info

        except Exception as e:
            self.logger.exception(f"Ошибка создания файлового диска: {e}")
            return StorageMessage(
                code=CommandMessagesEnum.disk_create_error.name,
                note=str(e),
            )

    def _create_qcow2_disk(
        self, disk_path: str, size_gb: float, sparse: bool = True
    ) -> StorageMessage:

        sparse_flag = [] if sparse else ["-o", "preallocation=full"]
        cmd = (
            ["qemu-img", "create", "-f", "qcow2"]
            + sparse_flag
            + [disk_path, f"{size_gb}G"]
        )
        try:
            self.logger.info(f"Выполнение команды: {' '.join(cmd)}")
            result = self.cli.execute(cmd, return_proc=True)
            self.logger.info(f"Результат выполнения команды: {result.stderr}")
            if result.returncode != 0:
                return StorageMessage(
                    success=False,
                    code=CommandMessagesEnum.disk_create_error.name,
                    stderr=result.stderr,
                    stdout=result.stdout,
                )
            return StorageMessage(
                success=True,
                code=CommandMessagesEnum.disk_successfully_created.name,
            )
        except TimeoutExpired as e:
            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_create_error.name,
                note=str(e),
            )

    def _create_raw_disk(
        self, disk_path: str, size_gb: float, sparse: bool = True
    ) -> StorageMessage:
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
            cmd = [
                "qemu-img",
                "create",
                "-f",
                "raw",
                "-o",
                "preallocation=full",
                disk_path,
                f"{size_gb}G",
            ]

        self.logger.info(f"Создание RAW диска: {' '.join(cmd)}")
        result = self.cli.execute(cmd, return_proc=True)
        if result.returncode != 0:
            self.delete_disk(disk_path=disk_path)
            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_create_error.name,
                stderr=result.stderr,
                stdout=result.stdout,
            )

        self.logger.info(
            f"RAW диск создан: {disk_path}, размер: {size_gb}GB, sparse: {sparse}"
        )
        return StorageMessage(
            success=True,
            code=CommandMessagesEnum.disk_successfully_created.name,
        )

    def delete_pool_disk_qcow2(self, disk_name: str):
        # Получить монтированную точку
        cmd_arg = (
            f"df --output=source,target | grep {disk_name} | awk " + "'{print $2}'"
        )
        disk_path = self.cli.execute(cmd_arg, shell=True, is_text=True).split("\n")[0]
        self.logger.info(
            f"Результат получения точки монтирования: {disk_path} по имени диска: {disk_name}"
        )

        # Отмонтировать
        umount_cmd_args = ["umount", disk_path]
        result = self.cli.execute(umount_cmd_args, return_proc=True)
        if result.returncode != 0:
            self.logger.info(f"Результат отмонтирования точки: {result.stderr}")
            return False

        # Удалить lv
        current_lv = self.logic_volume_manager.get_volume_by_name(
            disk_name, self.system_volume_group_name
        )
        if current_lv is None:
            return False
        self.logic_volume_manager.delete_logical_volume(
            disk_name, self.system_volume_group_name
        )
        current_lv = self.logic_volume_manager.get_volume_by_name(
            disk_name, self.system_volume_group_name
        )
        if current_lv is not None:
            return False

        # Удалить путь
        disk_path = Path(disk_path)
        shutil.rmtree(disk_path)
        if disk_path.exists():
            self.logger.warning(f"Файл диска {disk_path} не удален")
            return False

        return True

    def delete_pool_disk_raw(self, disk_name: str):
        current_lv = self.logic_volume_manager.get_volume_by_name(
            disk_name, self.system_volume_group_name
        )
        if current_lv is None:
            return False
        self.logic_volume_manager.delete_logical_volume(
            disk_name, self.system_volume_group_name
        )
        current_lv = self.logic_volume_manager.get_volume_by_name(
            disk_name, self.system_volume_group_name
        )
        if current_lv is not None:
            return False

        return True

    def delete_disk_with_msg(self, disk_path: str | None = None) -> StorageMessage:
        delete_disk_result = self.delete_disk(disk_path)

        if delete_disk_result:
            return StorageMessage(code=CommandMessagesEnum.disk_successfully_deleted.name,
                                  success=True)
        else:
            return StorageMessage(code=CommandMessagesEnum.disk_delete_error.name,
                                  success=True)

    def delete_disk(
        self,
        disk_path: str | None = None,
    ) -> bool:
        try:
            if self.system_disk_path == disk_path:
                raise ValueError("Нельзя удалять системную папку")
            self.logger.info(f"Удаление диска '{disk_path}'")
            if not Path(disk_path).exists():
                self.logger.warning(f"Файл {disk_path} не существует")
                return False

            if self._is_disk_in_use(disk_path):
                self.logger.warning(f"Диск {disk_path} используется")
                return False

            os.remove(disk_path)
            if Path(disk_path).exists():
                self.logger.warning(f"Файл диска {disk_path} не удален")
                return False
            self.logger.info(f"Файл диска {disk_path} удален")
            return True

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt: {e}")
            return False
        except Exception as e:
            self.logger.exception(f"Ошибка: {e}")
            return False

    def extend_disk(
        self,
        new_size_gb: int,
        path: str,
        disk_name: str,
        disk_format: DiskFormat,
    ) -> StorageMessage:
        """
        Расширение размера диска
        """

        try:
            if path:
                disk_extend_result = self._edit_file_disk(disk_name, path, disk_format, new_size_gb)
                if isinstance(disk_extend_result, Disk):
                    return StorageMessage(code=CommandMessagesEnum.disk_successfully_extended.name, disk_info=disk_extend_result, success=True)
                elif disk_extend_result is not None and disk_extend_result.code == CommandMessagesEnum.disk_founded.name:
                    return StorageMessage(code=CommandMessagesEnum.disk_successfully_extended.name,
                                          disk_info=disk_extend_result.disk_info, success=True)
                else:
                    return StorageMessage(code=CommandMessagesEnum.disk_extend_error.name, success=False)
            else:
                return StorageMessage(code=CommandMessagesEnum.disk_extend_error.name, success=False)

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt: {e}")
            return StorageMessage(code=CommandMessagesEnum.disk_extend_error.name, success=False, note=str(e))
        except Exception as e:
            self.logger.exception(f"Ошибка: {e}")
            return StorageMessage(code=CommandMessagesEnum.disk_extend_error.name, success=False, note=str(e))

    def edit_disk(
        self,
        pool_name: str | None = None,
        disk_name: str | None = None,
        path: str | None = None,
        disk_update: DiskUpdate | None = None,
    ) -> Disk | None:
        raise NotImplementedError
        # if not disk_update:
        #     self.logger.error("Не указана модель обновления")
        #     return None
        #
        # try:
        #     if pool_name and disk_name:
        #         return self._edit_pool_disk(pool_name, disk_name, disk_update)
        #     elif path:
        #         return self._edit_file_disk(path, disk_update)
        #     else:
        #         return None
        #
        # except libvirt.libvirtError as e:
        #     self.logger.error(f"Ошибка libvirt: {e}")
        #     return None
        # except Exception as e:
        #     self.logger.exception(f"Ошибка: {e}")
        #     return None

    def _edit_file_disk(
        self, disk_name: str, path: str, disk_format: DiskFormat, new_size_gb: int
    ) -> Disk | None:
        try:
            disk_path = f"{path}/{disk_name}.{disk_format.value}"
            if new_size_gb is not None:
                current_size_bytes = self.get_qemu_disk_info(disk_path)
                current_size_gb = round(current_size_bytes.actual_size / (1024**3), 2)
                if new_size_gb > current_size_gb:
                    self.logger.info(f"Увеличение размера до {new_size_gb}GB")
                    cmd = ["qemu-img", "resize", disk_path, f"{new_size_gb}G"]

                    self.logger.info(f"Выполнение команды: {' '.join(cmd)}")
                    result = self.cli.execute(cmd, return_proc=True)
                    if result.returncode != 0:
                        raise Exception(f"Ошибка qemu-img: {result.stderr}")
            return self.get_disk_info(disk_name, path, disk_format)

        except Exception as e:
            self.logger.warning(f"Ошибка изменения файлового диска: {e}")
            return None

    def clone_disk(
        self, disk_name: str, path: str, disk_format: DiskFormat, target_name: str
    ) -> StorageMessage:
        try:
            self.logger.info(
                f"Клонирование диска: {path}/{disk_name}.{disk_format.value} -> {path}/{target_name}.{disk_format.value}"
            )
            source_path = Path(f"{path}/{disk_name}.{disk_format.value}")
            target_path = Path(f"{path}/{target_name}.{disk_format.value}")
            if not source_path.exists():
                return StorageMessage(code=CommandMessagesEnum.disk_not_found.name, success=False)
            if disk_format == DiskFormat.QCOW2:
                cmd = [
                    "qemu-img",
                    "convert",
                    "--force-share",
                    "-f",
                    "qcow2",
                    "-O",
                    "qcow2",
                    str(source_path),
                    str(target_path),
                ]
                self.logger.info(f"Выполнение команды: {' '.join(cmd)}")

                result = self.cli.execute(cmd, return_proc=True)
                self.logger.warning(
                    f"Результат клонирования QCOW2 диска: '{result.stdout if result.returncode == 0 else result.stderr}'"
                )
                if result.returncode != 0:
                    raise Exception(f"Ошибка qemu-img: {result.stderr}")
            else:
                shutil.copy2(source_path, target_path)

            disk_info = self.get_disk_info(
                disk_name=target_name, path=path, disk_format=disk_format
            )
            if isinstance(disk_info, Disk):
                return StorageMessage(code=CommandMessagesEnum.disk_successfully_cloned.name, success=True, disk_info=disk_info)
            elif disk_info.code == CommandMessagesEnum.disk_founded.name:
                return StorageMessage(code=CommandMessagesEnum.disk_successfully_cloned.name, success=True,
                                      disk_info=disk_info.disk_info)
            return disk_info

        except Exception as e:
            self.logger.exception(f"Ошибка клонирования: {e}")
            return StorageMessage(code=CommandMessagesEnum.disk_clone_error.name, success=False, note=str(e))

    def attach_disk(self, disk_attach: DiskAttach) -> StorageMessage:
        try:
            disk_path = (
                disk_attach.path
                + "/"
                + disk_attach.name
                + "."
                + disk_attach.format.value
            )
            self.logger.info(
                f"Подключение диска {disk_path} к ВМ {disk_attach.vm_name}"
            )

            vm = self.conn.lookupByName(disk_attach.vm_name)

            if disk_attach.format.value in (
                DiskFormat.ISO.value,
                DiskFormat.IMG.value,
            ):
                device_type = "cdrom"
                # Для CDROM обычно используется readonly
                if not hasattr(disk_attach, "readonly") or disk_attach.readonly is None:
                    readonly = True
                else:
                    readonly = disk_attach.readonly
            else:
                device_type = "disk"  # TODO: Костыль, доработать
                readonly = (
                    disk_attach.readonly if hasattr(disk_attach, "readonly") else False
                )

            get_vm_by_path = self._find_vm_by_disk_path(disk_path)
            if get_vm_by_path:
                self.logger.warning("Диск уже подключен")
                return StorageMessage(
                    success=False,
                    code=CommandMessagesEnum.disk_already_attached_error.name,
                )

            disk_info = self.get_disk_info(
                path=disk_attach.path,
                disk_name=disk_attach.name,
                disk_format=disk_attach.format,
            )
            if disk_info.code != CommandMessagesEnum.disk_founded.name:
                return disk_info
            disk_info = disk_info.disk_info

            bus_type = (
                disk_attach.bus_type or BusType.IDE
            )  # Для CDROM чаще используется IDE
            cache_mode = (
                disk_attach.cache_mode.value if disk_attach.cache_mode else "none"
            )
            target_dev = disk_attach.target_dev or self._find_free_disk_device(
                vm, bus_type
            )

            # Формируем XML в зависимости от типа устройства
            if device_type == "cdrom":
                disk_xml = f"""
                <disk type='file' device='cdrom'>
                    <driver name='qemu' type='raw' cache='{cache_mode}'/>
                    <source file='{disk_path}'/>
                    <target dev='{target_dev}' bus='{bus_type.value}'/>
                    <readonly/>
                </disk>
                """
            else:
                disk_xml = f"""
                <disk type='file' device='disk'>
                    <driver name='qemu' type='{disk_info.format.value}' cache='{cache_mode}'/>
                    <source file='{disk_path}'/>
                    <target dev='{target_dev}' bus='{bus_type.value}'/>
                    {"<readonly/>" if readonly else ""}
                </disk>
                """

            vm_state, _ = vm.state()

            if vm_state == libvirt.VIR_DOMAIN_RUNNING:
                vm.attachDeviceFlags(
                    disk_xml,
                    libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE
                    | libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG,
                )
            else:
                vm.attachDeviceFlags(disk_xml, libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)

            self.logger.info(
                f"Диск успешно подключен как {target_dev} (тип: {device_type})"
            )
            return StorageMessage(
                success=True,
                code=CommandMessagesEnum.disk_successfully_attached.name,
            )

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка подключения: {e}")
            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_attach_libvirt_error.name,
                note=str(e),
            )
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_attach_unexpected_error.name,
                note=str(e),
            )

    def get_storage_used(self, vm_name: str) -> int:
        used_storage = 0
        all_disks = self.get_disks_by_vm(vm_name)
        for disk_elem in all_disks:
            used_storage += disk_elem.allocation_bytes

        return used_storage

    def get_disks_by_vm(self, vm_name: str) -> list[Disk]:
        """
        Получить все диски, подключенные к указанной ВМ
        """
        all_disks = []
        try:
            vm = self.conn.lookupByName(vm_name)
            xml_desc = vm.XMLDesc()
            root = ElementTree.fromstring(xml_desc)

            for disk_element in root.findall(".//disk"):
                target = disk_element.find("target")
                if target is None:
                    continue

                target_dev = target.get("dev")
                if target_dev:
                    try:
                        disk = self.get_disk_info_by_target_dev(vm_name, target_dev)
                        disk = disk.disk_info
                        all_disks.append(disk)
                    except Exception as e:
                        self.logger.warning(
                            f"Не удалось получить диск {target_dev}: {e}"
                        )
                        continue

            self.logger.info(f"Найдено {len(all_disks)} дисков для ВМ {vm_name}")
            return all_disks

        except Exception as e:
            self.logger.exception(f"Ошибка при получении дисков ВМ {vm_name}: {e}")
            return []

    def get_disk_info_by_target_dev(
        self, vm_name: str, target_dev: str
    ) -> StorageMessage:
        """
        Получить информацию о диске по target_dev в конкретной ВМ
        """
        self.logger.info(f"Получение информации о диске {target_dev} для ВМ {vm_name}")

        try:
            vm = self.conn.lookupByName(vm_name)
            xml_desc = vm.XMLDesc()

            # Используем ElementTree для надежного парсинга XML
            root = ElementTree.fromstring(xml_desc)

            # Ищем диск с указанным target_dev
            disk_element = None
            for disk in root.findall(".//disk"):
                target = disk.find("target")
                if target is not None and target.get("dev") == target_dev:
                    disk_element = disk
                    break

            if disk_element is None:
                return StorageMessage(
                    success=False,
                    code=CommandMessagesEnum.disk_not_found_by_target_dev.name,
                )

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
            file_path_exists = Path(disk_path).exists()

            # Получаем размер файла если он существует
            capacity_bytes = None
            allocation_bytes = None
            if file_path_exists:
                capacity_bytes = os.path.getsize(disk_path)
                allocation_bytes = capacity_bytes

            # Определяем тип диска
            disk_type = DiskType.EXTERNAL_DISK

            # Извлекаем тип шины
            bus_type = None
            if target is not None:
                bus_str = target.get("bus")
                if bus_str:
                    try:
                        bus_type = BusType(bus_str)
                    except ValueError:
                        self.logger.info(f"Неизвестный тип шины: {bus_str}")

            # Извлекаем режим кэширования
            cache_mode = None
            if driver is not None:
                cache_str = driver.get("cache")
                if cache_str:
                    try:
                        cache_mode = CacheMode(cache_str)
                    except ValueError:
                        self.logger.info(f"Неизвестный режим кэширования: {cache_str}")

            # Извлекаем дополнительные параметры
            device_type = disk_element.get("device", "disk")

            # Для QCOW2 пытаемся получить дополнительные метаданные
            backing_file = None
            if disk_format == DiskFormat.QCOW2 and file_path_exists:
                try:
                    cmd = ["qemu-img", "info", "--output=json", disk_path]
                    result = self.cli.execute(cmd, timeout=5, return_proc=True)
                    if result.returncode == 0:

                        info = orjson.loads(result.stdout)
                        if "backing-file" in info and info["backing-file"]:
                            backing_file = info["backing-file"]
                except Exception as e:
                    self.logger.info(f"Не удалось получить метаданные QCOW2: {e}")

            # Создаем объект Disk
            disk = Disk(
                name=disk_name,
                path=disk_path,
                file_path_exists=file_path_exists,
                type=disk_type,
                format=disk_format,
                capacity_bytes=capacity_bytes,
                allocation_bytes=allocation_bytes,
                capacity_gb=capacity_bytes / (1024**3) if capacity_bytes else None,
                allocation_gb=(
                    allocation_bytes / (1024**3) if allocation_bytes else None
                ),
                vm_name=vm_name,
                status=DiskStatus.ATTACHED,
                bus_type=bus_type,
                target_dev=target_dev,
                cache_mode=cache_mode,
                backing_file=backing_file,
                readonly=(device_type == "cdrom"),
                created=(
                    datetime.fromtimestamp(os.path.getctime(disk_path))
                    if file_path_exists
                    else None
                ),
                modified=(
                    datetime.fromtimestamp(os.path.getmtime(disk_path))
                    if file_path_exists
                    else None
                ),
            )

            self.logger.info(f"Информация о диске {target_dev} получена: {disk_name}")
            storage_message = StorageMessage(
                success=True,
                code=CommandMessagesEnum.disk_founded_by_target_dev.name,
            )
            storage_message.disk_info = disk
            return storage_message

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка libvirt при получении диска {target_dev}: {e}")
            raise
        except Exception as e:
            self.logger.exception(
                f"Неожиданная ошибка при получении диска {target_dev}: {e}"
            )
            raise

    def detach_disk(self, detach_disk: DiskDetach) -> StorageMessage:
        try:
            self.logger.info(f"Отключение диска от ВМ {detach_disk.vm_name}")

            vm = self.conn.lookupByName(detach_disk.vm_name)
            xml_desc = vm.XMLDesc()
            root = ElementTree.fromstring(xml_desc)
            for disk_device in root.find("devices").findall("disk"):
                if disk_device.find("target").get("dev") == detach_disk.target_dev:
                    disk_xml = ElementTree.tostring(disk_device, encoding="unicode")
                    break
            else:
                raise ValueError(
                    f"Не найден диск с target_dev: {detach_disk.target_dev}"
                )
            if not disk_xml:
                self.logger.error("Диск не найден")
                return False

            vm_state, _ = vm.state()

            if vm_state == libvirt.VIR_DOMAIN_RUNNING:
                vm.detachDeviceFlags(
                    disk_xml,
                    libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE
                    | libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG,
                )
            else:
                vm.detachDeviceFlags(disk_xml, libvirt.VIR_DOMAIN_DEVICE_MODIFY_CONFIG)

            self.logger.info("Диск успешно отключен")
            return StorageMessage(code=CommandMessagesEnum.disk_successfully_detached.name, success=True)

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка отключения: {e}")
            return StorageMessage(code=CommandMessagesEnum.disk_detach_error.name, success=False)
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
            return StorageMessage(code=CommandMessagesEnum.disk_detach_error.name, success=False)

    def list_disks(self, query: DiskQuery | None = None) -> StorageMessage:
        all_disks = []
        try:
            all_disks.extend(self._get_file_disks(query))
            all_disks.extend(self._get_attached_disks(query))

            all_disks = self._remove_duplicate_disks(all_disks)
            all_disks = self._apply_filters(all_disks, query)

            return StorageMessage(success=True,
                code=CommandMessagesEnum.disk_list_founded.name,
                                  disk_info=all_disks)

        except Exception as e:
            self.logger.exception(f"Ошибка получения списка: {e}")
            return StorageMessage(success=False,
                                  code=CommandMessagesEnum.disk_list_error.name,
                                  note=str(e))

    def convert_disk_format(
        self,
        source_path: str,
        target_format: DiskFormat,
        sparse: bool = True,
        target_path: str | None = None,
    ) -> StorageMessage | bool:
        """
        В target_path нужно указывать полный путь включая сам файл диска и его расширение
        """

        try:
            if not Path(source_path).exists():
                self.logger.error("Исходный файл не существует")
                return False
            if target_path is not None:
                target_dir = Path(os.path.dirname(target_path))
                if not target_dir.exists():
                    target_dir.mkdir()
            else:
                current_disk_format = self.libvirt_config.disk_format_by_path(
                    source_path
                )
                target_path = source_path.replace(
                    f".{current_disk_format.value}", f".{target_format.value}"
                )

            sparse_flag = [] if sparse else ["-S", "0"]
            cmd = (
                ["qemu-img", "convert"]
                + sparse_flag
                + ["-O", target_format.value, source_path, target_path]
            )

            self.logger.info(
                f"Конвертация диска: {source_path} -> {target_path} ({target_format.value})"
            )
            self.logger.info(f"Выполнение команды: {' '.join(cmd)}")

            result = self.cli.execute(cmd, return_proc=True)
            if result.returncode != 0:
                self.logger.error(f"Ошибка при конвертации: {result.stderr}")
                return StorageMessage(
                    success=False,
                    code=CommandMessagesEnum.disk_convert_error.name,
                )

            self.logger.info("Конвертация успешно завершена")
            return StorageMessage(
                success=True,
                code=CommandMessagesEnum.disk_convert_successfully.name,
                target_path=target_path,
            )

        except Exception as e:
            self.logger.exception(f"Ошибка при конвертации диска: {e}")
            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_convert_error.name,
                note=str(e),
            )

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
                BusType.XEN: "xvd",
            }

            prefix = prefix_map.get(bus_type, "vd")
            used_devices = set()

            lines = xml_desc.split("\n")
            for line in lines:
                if "target dev=" in line:
                    match = re.search(r"dev=['\"]([^'\"]+)['\"]", line)
                    if match:
                        used_devices.add(match.group(1))

            # Для IDE устройств (hd) используем традиционные имена
            if bus_type == BusType.IDE:
                for letter in "abcd":
                    device = f"{prefix}{letter}"
                    if device not in used_devices:
                        return device
            else:
                for letter in "abcdefghijklmnopqrstuvwxyz":
                    device = f"{prefix}{letter}"
                    if device not in used_devices:
                        return device

            return f"{prefix}z1"

        except Exception as e:
            self.logger.error(f"Ошибка поиска устройства: {e}")
            return "vdz"

    def get_disk_info(
        self,
        disk_name: str,
        path: str | None = None,
        disk_format: DiskFormat = DiskFormat.QCOW2,
        is_pool: bool = False,
    ) -> Disk | StorageMessage:
        ha_nfs_storages = self.ha_controller.loaded_ha_nfs_storages.nfs_storages
        if ha_nfs_storages and path is None:
            ha_nfs_storage = ha_nfs_storages.pop()
            path = ha_nfs_storage.mount
        elif path is None:
            path = self.system_disk_path
        try:
            disk_path = str(Path(path) / f"{disk_name}.{disk_format.value}")
            print("БЛЯЯЯЯЯЯЯЯЯЯЯЯЯЯЯЯЯЯЯ ПАФ", disk_path)
            if is_pool:
                if disk_format.value == DiskFormat.QCOW2.value:
                    if Path(disk_path).exists():
                        disk_info = self._get_file_disk_info(disk_path)
                        if disk_info is None or isinstance(disk_info, str):
                            return StorageMessage(
                                success=False,
                                code=CommandMessagesEnum.disk_not_found.name,
                                note=disk_info,
                            )
                        return StorageMessage(
                            success=True,
                            code=CommandMessagesEnum.disk_founded.name,
                            disk_info=disk_info,
                        )
                else:
                    current_lv = self.logic_volume_manager.get_volume_by_name(
                        disk_name, self.system_volume_group_name
                    )
                    vm_name = None
                    if self._is_disk_in_use(current_lv.logic_volume_path):
                        vm_name = self._find_vm_by_disk_path(path)
                        if vm_name:
                            status = DiskStatus.ATTACHED
                        else:
                            status = DiskStatus.DETACHED
                    else:
                        status = DiskStatus.DETACHED

                    disk_info = Disk(
                        name=current_lv.logic_volume_name,
                        path=current_lv.logic_volume_path,
                        file_path_exists=True,
                        status=status,
                        type=DiskType.POOL_DISK,
                        format=DiskFormat.RAW,
                        capacity_bytes=current_lv.volume_size,
                        pool=current_lv.logic_volume_pool,
                        allocation_bytes=current_lv.volume_size
                        - current_lv.available_volume_size,
                        vm_name=vm_name,
                        readonly=False,
                    )
                    return StorageMessage(
                        success=True,
                        code=CommandMessagesEnum.disk_founded.name,
                        disk_info=disk_info,
                    )
            else:
                if Path(disk_path).exists():
                    disk_info = self._get_file_disk_info(disk_path)
                    if disk_info is None or isinstance(disk_info, str):
                        return StorageMessage(
                            success=False,
                            code=CommandMessagesEnum.disk_not_found.name,
                            note=disk_info,
                        )
                    return StorageMessage(
                        success=True,
                        code=CommandMessagesEnum.disk_founded.name,
                        disk_info=disk_info,
                    )
                return StorageMessage(
                    success=False,
                    code=CommandMessagesEnum.disk_not_found.name,
                )

            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_not_found.name,
            )

        except (libvirt.libvirtError, FileNotFoundError) as e:
            self.logger.error(f"Ошибка получения информации: {e}")
            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_not_found_libvirt_error.name,
                note=str(e),
            )
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка: {e}")
            return StorageMessage(
                success=False,
                code=CommandMessagesEnum.disk_not_found_unexpected_error.name,
                note=str(e),
            )

    @staticmethod
    def convert_to_bytes_simple(size_data: float, size_type: str) -> int:
        """
        Простая конвертация в байты (только двоичные единицы KiB, MiB, GiB, TiB)
        """
        # Приводим к верхнему регистру и удаляем пробелы
        size_type = size_type.upper().strip()

        # Определяем множитель
        if size_type == "B":
            return int(size_data)
        elif size_type == "KIB" or size_type == "K":
            return int(size_data * 1024)
        elif size_type == "MIB" or size_type == "M":
            return int(size_data * 1024**2)
        elif size_type == "GIB" or size_type == "G":
            return int(size_data * 1024**3)
        elif size_type == "TIB" or size_type == "T":
            return int(size_data * 1024**4)
        else:
            raise ValueError(f"Неизвестный тип размера: {size_type}")

    def get_qemu_disk_info(self, disk_path: str) -> QemuDisk:
        cmd = ["qemu-img", "info", "--output=json", disk_path]
        result = self.cli.execute(cmd, return_proc=True)

        if result.returncode != 0:
            raise Exception(f"Ошибка qemu-img при чтении диска: {result.stderr}")
        qemu_disk = QemuDisk(**orjson.loads(result.stdout))
        self.logger.info(
            f"Disk: '{qemu_disk.filename}', virtual-size: '{qemu_disk.virtual_size}', actual-size: '{qemu_disk.actual_size}'"
        )

        return qemu_disk

    def _get_file_disk_info(self, disk_path: str) -> Disk | str:
        try:
            file_path_exists = Path(disk_path).exists()
            disk_format = DiskFormat.UNKNOWN

            # Определяем формат по расширению
            if disk_path.endswith(".qcow2"):
                disk_format = DiskFormat.QCOW2
            elif disk_path.endswith((".raw", ".img")):
                disk_format = DiskFormat.RAW
            elif disk_path.endswith(".iso"):
                disk_format = DiskFormat.ISO
            elif disk_path.endswith(".vmdk"):
                disk_format = DiskFormat.VMDK
            elif disk_path.endswith(".vdi"):
                disk_format = DiskFormat.VDI
            elif disk_path.endswith(".vhd") or disk_path.endswith(".vhdx"):
                disk_format = DiskFormat.VHDX

            qemu_disk_info = (
                self.get_qemu_disk_info(disk_path) if file_path_exists else 0
            )
            disk_name = os.path.basename(disk_path).split(".").pop(0)
            disk_dir = os.path.dirname(disk_path)

            disk_type = DiskType.EXTERNAL_DISK
            vm_name = None

            if self._is_disk_in_use(disk_path):
                vm_name = self._find_vm_by_disk_path(disk_path)
                if vm_name:
                    status = DiskStatus.ATTACHED
                else:
                    status = DiskStatus.DETACHED
            else:
                status = DiskStatus.DETACHED

            # Определяем, является ли диск CDROM
            readonly = disk_path.lower().endswith(
                ".iso"
            )  # ISO файлы по умолчанию readonly

            disk = Disk(
                name=disk_name,
                path=disk_dir,
                file_path_exists=file_path_exists,
                type=disk_type,
                format=disk_format,
                capacity_bytes=qemu_disk_info.actual_size,
                allocation_bytes=qemu_disk_info.actual_size,
                status=status,
                vm_name=vm_name,
                readonly=readonly,
            )

            return disk

        except Exception as e:
            self.logger.exception(f"Ошибка получения файловой информации: {e}")
            return str(e)

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

    def _get_file_disks(self, query: DiskQuery | None) -> list[Disk]:
        all_disks = []
        standard_dirs = list(self.libvirt_config.search_dirs)

        if query and hasattr(query, "search_path"):
            standard_dirs.insert(0, query.search_path)

        for dir_path in standard_dirs:
            if Path(dir_path).exists():
                for file_name in os.listdir(dir_path):
                    file_path = os.path.join(dir_path, file_name)
                    if self._is_disk_file(file_path):
                        disk_info = self._get_file_disk_info(file_path)
                        if disk_info:
                            all_disks.append(disk_info)

        return all_disks

    def _is_disk_file(self, file_path: str) -> bool:
        disk_extensions = list(self.libvirt_config.disk_extensions) + [".iso", ".img"]
        return not Path(file_path).is_dir() and any(
            file_path.endswith(ext) for ext in disk_extensions
        )

    def _get_attached_disks(
        self, query: DiskQuery | None, existing_disks: list[Disk] | None = None
    ) -> list[Disk]:
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
                        disk_path = disk_block.get("source_file")
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
                                disk_path,
                                vm_name,
                                disk_block.get("target_dev"),
                                disk_block.get("bus_type"),
                                disk_block.get("driver_type"),
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

    @staticmethod
    def _extract_disk_blocks_from_vm_xml(xml_desc: str) -> list[dict]:
        disk_blocks = []
        lines = xml_desc.split("\n")
        i = 0

        while i < len(lines):
            if "<disk " in lines[i]:
                disk_block = {}
                j = i

                while j < len(lines) and "</disk>" not in lines[j]:
                    line = lines[j]

                    if "file=" in line:
                        match = re.search(r"file=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block["source_file"] = match.group(1)

                    if "target dev=" in line:
                        match = re.search(r"dev=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block["target_dev"] = match.group(1)

                    if "bus=" in line:
                        match = re.search(r"bus=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block["bus_type"] = match.group(1)

                    if "type=" in line and "driver" in line:
                        match = re.search(r"type=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block["driver_type"] = match.group(1)

                    j += 1

                if disk_block:
                    disk_blocks.append(disk_block)

                i = j + 1
            else:
                i += 1

        return disk_blocks

    def _create_disk_from_vm_attachment(
        self,
        disk_path: str,
        vm_name: str,
        target_dev: str | None,
        bus_type_str: str | None,
        driver_type: str | None,
    ) -> Disk | None:
        try:
            disk_format = DiskFormat.UNKNOWN
            if driver_type:
                try:
                    disk_format = DiskFormat(driver_type)
                except ValueError:
                    pass

            if disk_format == DiskFormat.UNKNOWN:
                disk_format = self.libvirt_config.disk_format_by_path(disk_path)

            size_bytes = (
                self.get_qemu_disk_info(disk_path).actual_size
                if Path(disk_path).exists()
                else 0
            )

            bus_type = None
            if bus_type_str:
                try:
                    bus_type = BusType(bus_type_str)
                except ValueError:
                    bus_type = None

            disk = Disk(
                name=os.path.basename(disk_path),
                path=disk_path,
                file_path_exists=Path(disk_path).exists(),
                type=DiskType.EXTERNAL_DISK,
                format=disk_format,
                capacity_bytes=size_bytes,
                allocation_bytes=size_bytes,
                vm_name=vm_name,
                status=DiskStatus.ATTACHED,
                target_dev=target_dev,
                bus_type=bus_type,
            )

            return disk
        except Exception as e:
            self.logger.exception(f"Ошибка создания диска: {e}")
            return None

    @staticmethod
    def _remove_duplicate_disks(all_disks: list[Disk]) -> list[Disk]:
        unique_disks = {}
        for disk in all_disks:
            if disk.path not in unique_disks:
                unique_disks[disk.path] = disk
            else:
                existing = unique_disks[disk.path]
                if disk.vm_name and not existing.vm_name:
                    existing.vm_name = disk.vm_name
                    existing.status = DiskStatus.ATTACHED
                    existing.type = DiskType.EXTERNAL_DISK
                if disk.pool and not existing.pool:
                    existing.pool = disk.pool
                    existing.type = DiskType.POOL_DISK

        return list(unique_disks.values())

    def _apply_filters(
        self, all_disks: list[Disk], query: DiskQuery | None
    ) -> list[Disk]:
        if not query:
            return all_disks

        filtered_disks = []
        for disk in all_disks:
            if self._filter_disk(disk, query):
                filtered_disks.append(disk)

        return filtered_disks

    @staticmethod
    def _filter_disk(disk: Disk, query: DiskQuery | None) -> bool:
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
    # print(
    #     [(key, param) for key, param in VmUpdateRequest().model_dump().items() if param]
    # )
    # """
    # Пример использования StorageManager:
    # 1. Создание диска в пуле
    # 2. Создание файлового диска
    # 3. Подключение диска к ВМ
    # 4. Получение списка дисков
    # 5. Конвертация формата диска
    # """
    #
    with StorageManager() as manager:
        print(manager.get_qemu_disk_info("/eskvisor/storages/disk-test-81278.qcow2"))
        #     # Создание диска в пуле
        #     # disk_create = DiskCreate(
        #     #     name="test_disk",
        #     #     size_gb=10,
        #     #     format=DiskFormat.QCOW2,
        #     #     pool="default"
        #     # )
        #     # disk = manager.create_disk(disk_create)
        #     # if disk:
        #     #     print(f"Диск создан: {disk.name}, размер: {disk.get_effective_size_gb()}GB")
        #
        # Получение списка всех дисков

        disks = manager.list_disks()
        for current_disk in disks:
            print(
                f"****************************************************************\n"
                f"ИМЯ ДИСКА: {current_disk.name}\n"
                f"ПУТЬ ДИСКА: {current_disk.path}\n"
                f"TARGET_DEV: {current_disk.target_dev}\n"
                f"К КАКОЙ ВМ ПОДКЛЮЧЕН ДИСК: {current_disk.vm_name}\n"
            )
        print(f"Всего дисков: {len(disks)}")
