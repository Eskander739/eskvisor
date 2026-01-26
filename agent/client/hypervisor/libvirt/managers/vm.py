import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from xml.etree import ElementTree
from pathlib import Path
from typing import Any

import libvirt
from libvirt import VIR_DOMAIN_UNDEFINE_MANAGED_SAVE, VIR_DOMAIN_UNDEFINE_NVRAM

from agent.client.hypervisor.ha.controller import HAController
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.config import LibvirtConfig
from agent.client.hypervisor.libvirt.managers.network import NetworkManager
from agent.client.hypervisor.libvirt.managers.snapshot import SnapshotManager
from agent.client.hypervisor.libvirt.managers.storage import StorageManager
from agent.client.hypervisor.libvirt.models.volume.disk import (
    BusType,
    Disk,
    DiskAttach,
    DiskType,
    CacheMode,
    DiskCreate,
)
from agent.client.hypervisor.libvirt.models.enum import (
    GraphicsType,
    NetworkType,
)
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import (
    CommandMessagesEnum,
    VmError,
    VmMessage,
)
from agent.client.hypervisor.libvirt.models.vm import (
    VirtualMachine,
    VMCreateRequest,
    VmUpdateRequest,
    HostForward,
    VirtualMachinesList,
    SecureBootVM, VMStateInfo,
)
from agent.client.logger_config import DefaultLogger

QEMU_NAMESPACE = {"qemu": "http://libvirt.org/schemas/domain/qemu/1.0"}
SUPPORT_LIVE_UPGRADE_PARAMS = (
    "vcpus",
)  # параметры поддерживаемые в live обновлении конфигурации ВМ из модели VmUpdateRequest
UNSUPPORT_LIVE_UPGRADE_PARAMS = (
    "max_memory_mb",
    "current_memory_mb",
)  # параметры которые нельзя обновить на лету(в нашей системе)


class VmManager(LibvirtClient):
    """
    Управление виртуальными машинами
    """

    libvirtError = None

    def __init__(self):
        self.ha_controller = HAController()
        self.config = LibvirtConfig()
        self.logger = DefaultLogger("VmManager")
        super().__init__()
        self.snapshot = None
        self.storage_manager = None
        self.network_manager = None

    def __enter__(self):
        self.conn = self.connect()
        self.snapshot = SnapshotManager()
        self.storage_manager = StorageManager()
        self.network_manager = NetworkManager()
        self.snapshot.conn = self.conn
        self.storage_manager.conn = self.conn
        self.network_manager.conn = self.conn

        return self

    def restart_vms_in_live_host(self):
        """
        Что будет с виртуальными машинами и их дисками в ресурс пулах ?
        (помечаем для пользователя, что хранилища ресурс пулов не доступны в режиме HA, но доступно ограничение ресурсов)

        Какую команду backend будет отправлять целевому хосту для перезапуска всех ВМ на новом хосте ?

        # 1. Проверить доступность дисков(mount -o remount /nfs/storage)
        # 2. Очистить возможные блокировки(virsh pool-refresh nfs_pool)
        # 3. Зарегистрировать ВМ(через define)
        # 4. Проверить целостность диска (опционально)(qemu-img check /nfs/vms/vm1/disk.qcow2)
        # 5. Запустить

        Если сломанный хост восстановится и попытается перезапустить у себя все ВМ, какой сценарий у него должен сработать?


        Реализовать после первого пилотного клиента
        """
        raise NotImplementedError

    def create_vm(
        self, config: VMCreateRequest, dry_run: bool = False
    ) -> dict | VmError | VmMessage:
        """
        Создание виртуальной машины через virt-install


        Дополнительно - Порядок загрузки дисков происходит в соответствии с их порядком в переданном списке

        Args:
            config: Конфигурация ВМ
            dry_run: Только проверить команду, не выполнять

        Returns:
            Словарь с результатом выполнения
        """
        all_disks = []
        command = ""

        try:
            self.logger.info(f"Запуск создания ВМ: {config.name}")

            # Проверка несовместимых параметров для ISO
            for current_disk in config.disks:
                if current_disk.disk_type == DiskType.CDROM.value:
                    # Проверяем существование ISO файла
                    if not os.path.exists(config.cdrom):
                        return VmMessage(
                            success=False,
                            code="ISO_FILE_NOT_FOUND",
                        )

                    # Проверяем, что файл действительно ISO
                    if not current_disk.path.lower().endswith(".iso"):
                        self.logger.warning(
                            f"Файл {config.cdrom} не имеет расширения .iso"
                        )

                    # Если указан ISO, проверяем совместимость с другими параметрами
                    if config.install_method == "location":
                        return VmMessage(
                            success=False,
                            code="CDROM_AND_LOCATION_CONFLICT",
                        )

            existing_vm = self.get_vm_by_name(config.name)
            if existing_vm.code == CommandMessagesEnum.vm_successfully_found.name:
                return VmError(
                    code=CommandMessagesEnum.vm_with_name_already_exists.name,
                )

            # Создаем диски через StorageManager
            try:
                for i, disk in enumerate(config.disks):
                    # Если диск существует, проверяем его
                    disk_path = f"{disk.path}/{disk.name}.{disk.format.value}"
                    if disk.path and os.path.exists(disk_path):
                        self.logger.info(
                            f"Диск {disk_path} уже существует, используем существующий"
                        )
                        continue

                    self.logger.info(
                        f"Создание диска через StorageManager: {disk.name}"
                    )
                    if isinstance(disk, DiskCreate):
                        result = self.storage_manager.create_disk(disk)

                        if hasattr(result, "disk_info") and result.disk_info:
                            # Обновляем путь диска в конфигурации
                            all_disks.append(disk_path)
                            self.logger.info(f"Диск создан: {result.disk_info.path}")
                        else:
                            self.logger.error(f"Ошибка создания диска: {result}")
                            # Откатываем созданные диски
                            for created_disk_path in all_disks:
                                try:
                                    self.storage_manager.delete_disk(
                                        disk_path=created_disk_path
                                    )
                                except Exception as e:
                                    self.logger.error(
                                        f"Ошибка при откате диска {created_disk_path}: {e}"
                                    )
                            return VmMessage(
                                success=False,
                                code="DISK_CREATION_FAILED",
                            )

            except Exception as global_e:
                self.logger.exception(f"Ошибка при создании дисков: {global_e}")
                # Откатываем созданные диски
                for created_disk_path in all_disks:
                    try:
                        self.storage_manager.delete_disk(disk_path=created_disk_path)
                    except Exception as e:
                        self.logger.error(
                            f"Ошибка при откате диска {created_disk_path}: {e}"
                        )
                return VmMessage(
                    success=False,
                    code="DISK_CREATION_EXCEPTION",
                )
            command = self._build_virt_install_command(config)
            self.logger.info(f"Команда virt-install: {command}")

            if dry_run:
                return {
                    "success": True,
                    "message": "DRY RUN: команда сгенерирована успешно",
                    "command": command,
                    "vm_name": config.name,
                }

            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=600
            )

            if result.returncode == 0:
                time.sleep(2)

                vm_info = self.get_vm_by_name(config.name)

                if vm_info:
                    self.logger.info(f"ВМ '{config.name}' создана успешно")
                    if config.autostart:
                        self._set_autostart(config.name, True)
                    self.ha_controller.sync_nfs_vm_configs()
                    return VmMessage(
                        success=True,
                        code=CommandMessagesEnum.vm_successfully_created.name,
                        command=command,
                        vm_info=vm_info.vm_info,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
                else:
                    self.logger.error("ВМ создана, но не найдена в libvirt")
                    return VmMessage(
                        success=False,
                        code=CommandMessagesEnum.vm_created_but_not_found_in_libvirt.name,
                        command=command,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
            else:
                error_msg = result.stderr

                if (
                    "Необходимо определить метод установки" in error_msg
                    or "install method must be specified" in error_msg.lower()
                ):
                    self.logger.warning(
                        "Обнаружена ошибка метода установки. Пробуем с флагом --import..."
                    )

                    import_command = command + " --import"
                    self.logger.info(f"Повторная попытка с командой: {import_command}")

                    import_result = subprocess.run(
                        import_command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )

                    if import_result.returncode == 0:
                        vm_info = self.get_vm_by_name(config.name)

                        if vm_info:
                            self.logger.info(
                                f"ВМ '{config.name}' создана успешно с флагом --import"
                            )

                            if config.autostart:
                                self._set_autostart(config.name, True)

                            self.ha_controller.sync_nfs_vm_configs()
                            return VmMessage(
                                success=True,
                                code=CommandMessagesEnum.vm_successfully_created.name,
                                command=import_command,
                                vm_info=vm_info.vm_info,
                                stdout=result.stdout,
                                stderr=result.stderr,
                                note="Использован флаг --import для создания пустой ВМ",
                            )
                        else:
                            return VmMessage(
                                success=False,
                                code=CommandMessagesEnum.vm_created_but_not_found_in_libvirt.name,
                                command=import_command,
                                vm_info=vm_info.vm_info,
                                stdout=result.stdout,
                                stderr=result.stderr,
                                note="Использован флаг --import для создания пустой ВМ",
                            )
                    else:
                        self.logger.error(f"Ошибка создания ВМ: {result.stderr}")
                        return VmMessage(
                            success=False,
                            code=CommandMessagesEnum.vm_create_error.name,
                            command=import_command,
                            stdout=result.stdout,
                            stderr=result.stderr,
                            note="Использован флаг --import для создания пустой ВМ",
                        )
                else:
                    error_msg = f"Ошибка создания ВМ: {result.stderr}"
                    self.logger.error(error_msg)
                    return VmMessage(
                        success=False,
                        code=CommandMessagesEnum.vm_create_error.name,
                        command=command,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )

        except subprocess.TimeoutExpired:
            error_msg = f"Таймаут при создании ВМ '{config.name}'"
            self.logger.error(error_msg)
            for created_disk_path in all_disks:
                try:
                    self.storage_manager.delete_disk(disk_path=created_disk_path)
                except Exception as e:
                    self.logger.error(
                        f"Ошибка при откате диска {created_disk_path}: {e}"
                    )
            return VmMessage(
                success=False,
                code=CommandMessagesEnum.vm_create_subprocess_timeout_error.name,
                command=command if "command" in locals() else None,
            )
        except Exception as e:
            error_msg = f"Неожиданная ошибка при создании ВМ: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            # Откатываем созданные диски при исключении
            for created_disk_path in all_disks:
                try:
                    self.storage_manager.delete_disk(disk_path=created_disk_path)
                except Exception as e:
                    self.logger.error(
                        f"Ошибка при откате диска {created_disk_path}: {e}"
                    )
            return VmMessage(
                success=False,
                code=CommandMessagesEnum.vm_create_unexpected_error.name,
                command=command if "command" in locals() else None,
            )

    def _build_virt_install_command(self, config: VMCreateRequest) -> str:
        """
        Построение команды virt-install из конфигурации

        Args:
            config: Конфигурация ВМ

        Returns:
            Строка команды для выполнения
        """
        cmd_parts = ["virt-install --connect qemu:///system"]
        boot_cmd = ""
        controller_params = []
        graphics_params = []
        boot_params = []

        cmd_parts.extend(["--name", config.name])

        if config.description:
            cmd_parts.extend(["--description", f"'{config.description}'"])

        if not config.autostart_vm:
            cmd_parts.extend(["--noreboot"])

        if config.machine_type:
            cmd_parts.extend(["--machine", f"{config.machine_type.value}"])

        cmd_parts.extend(
            [
                f"--memory {config.memory_mb},{f'maxmemory={config.max_memory_mb}' if config.max_memory_mb and config.max_memory_mb != config.memory_mb else ''}"
            ]
        )

        if config.max_vcpus and config.max_vcpus != config.vcpus:
            cmd_parts.extend(["--vcpus", f"{config.vcpus},maxvcpus={config.max_vcpus}"])
        else:
            cmd_parts.extend(["--vcpus", str(config.vcpus)])

        cmd_parts.extend(["--arch", config.architecture.value])

        if config.os_variant:
            cmd_parts.extend(["--os-variant", config.os_variant])

        if config.cpu_model:
            cmd_parts.extend(["--cpu", config.cpu_model])

        if config.cpu_features:
            features_str = ",".join(config.cpu_features)
            cmd_parts.extend(["--features", features_str])

        for i, disk in enumerate(config.disks):
            disk_cmd = "--disk "

            disk_params = []
            if disk.path or disk.name and disk.format:
                if disk.path is None:
                    disk.path = self.storage_manager.system_disk_path
                disk_path = (
                    Path(disk.path)
                    if disk.disk_type.value == DiskType.CDROM.value
                    else Path(f"{disk.path}/{disk.name}.{disk.format.value}")
                )
                if disk_path.exists():
                    if disk.disk_type.value == DiskType.CDROM.value:
                        disk_params.append(f"--cdrom {disk.path}")
                    else:
                        disk_params.append(f"path={str(disk_path)}")
                        disk_params.append(f"format={disk.format.value}")
                else:
                    if disk.size_gb:
                        disk_params.append(f"size={disk.size_gb}")
                    if disk.format:
                        disk_params.append(f"format={disk.format.value}")
                    disk_params.append(f"path={disk.path}")
            else:
                if disk.size_gb:
                    disk_params.append(f"size={disk.size_gb}")
                if disk.format:
                    disk_params.append(f"format={disk.format.value}")
            if disk.bus_type:
                disk_params.append(f"bus={disk.bus_type.value}")

            if isinstance(disk, DiskCreate):
                if disk.cache and disk.disk_type.value != DiskType.CDROM.value:
                    disk_params.append(f"cache={disk.cache}")

                if disk.readonly:
                    disk_params.append("readonly=on")

                if disk.shareable:
                    disk_params.append("shareable=on")

                if disk.serial:
                    disk_params.append(f"serial={disk.serial}")

            if disk.disk_type.value == DiskType.CDROM.value:
                disk_cmd = disk_cmd.replace("--disk", "")
            disk_cmd += ",".join(disk_params)
            cmd_parts.append(disk_cmd)

        for i, net in enumerate(config.networks):
            net_cmd = "--network "

            net_params = []

            if net.network_type == NetworkType.BRIDGE:
                net_params.append(f"bridge={net.source}")
            elif net.network_type == NetworkType.NETWORK:
                net_params.append(f"network={net.source}")
            elif net.network_type == NetworkType.USER:
                net_params.append("user")
            elif net.network_type == NetworkType.DIRECT:
                net_params.append(f"direct={net.source}")

            if net.model:
                net_params.append(f"model={net.model.value}")

            if net.mac_address:
                net_params.append(f"mac={net.mac_address}")

            net_cmd += ",".join(net_params)
            cmd_parts.append(net_cmd)

        for controller in config.controllers:
            controller_cmd = "--controller "

            controller_params.append(f"type={controller.controller_type.value}")

            if controller.index is not None:
                controller_params.append(f"index={controller.index}")

            if controller.model:
                controller_params.append(f"model={controller.model}")

            controller_cmd += ",".join(controller_params)
            cmd_parts.append(controller_cmd)

        if config.graphics == GraphicsType.NONE:
            cmd_parts.append("--graphics none")
        else:
            graphics_cmd = f"--graphics {config.graphics.value}"

            if config.graphics_port:
                graphics_params.append(f"port={config.graphics_port}")

            if config.graphics_listen:
                graphics_params.append(f"listen={config.graphics_listen}")

            if graphics_params:
                graphics_cmd += "," + ",".join(graphics_params)

            cmd_parts.append(graphics_cmd)

        cmd_parts.extend(["--video", config.video_model.value])

        if config.console_type:
            cmd_parts.extend(["--console", f"{config.console_type}"])

        if config.boot_devices:
            boot_cmd = "--boot "

            for i, device in enumerate(config.boot_devices):
                boot_params.append(device)

        if config.boot_uefi:
            if not config.boot_devices:
                boot_cmd = "--boot "
            uefi_param = "uefi"

            if config.secure_boot:
                if config.secure_boot_loader:
                    uefi_param += f",loader={config.secure_boot_loader}"
                else:
                    # TODO: Проверить базовые загрузчики для разных OS
                    uefi_param += ",loader=/usr/share/edk2/ovmf/OVMF_CODE.secboot.fd"
                uefi_param += ",loader_secure=on"
            else:
                uefi_param += ",loader_secure=off"

            boot_params.append(uefi_param)

        if boot_cmd:
            boot_params.append("menu=on")
            boot_cmd += ",".join(boot_params)
            cmd_parts.append(boot_cmd)

        if config.autostart:
            cmd_parts.append("--autostart")

        elif hasattr(config, "install_method") and config.install_method:
            if config.install_method == "import":
                for current_disk in config.disks:
                    if current_disk.disk_type.value == DiskType.CDROM.value:
                        break
                else:
                    cmd_parts.append("--import")
            elif config.install_method == "pxe":
                cmd_parts.append("--pxe")
            elif config.install_method == "boot":
                pass

        if config.extra_args:
            cmd_parts.extend(["--extra-args", f"'{config.extra_args}'"])

        if config.noautoconsole:
            cmd_parts.append("--noautoconsole")

        if config.qemu_commandline:
            net_info = self.get_all_hostfwd_and_net_ids()
            all_net_ids = {current_net_info[0] for current_net_info in net_info}
            all_ip_and_port = {
                (current_net_info[1].host_ip, current_net_info[1].host_port)
                for current_net_info in net_info
            }

            if config.qemu_commandline.net_id in all_net_ids:
                config.qemu_commandline.net_id = self.generate_new_net_id

            if (
                config.qemu_commandline.hostfwd.host_ip,
                config.qemu_commandline.hostfwd.host_port,
            ) in all_ip_and_port:
                config.qemu_commandline.net_id = self.generate_new_net_id

            cmd_parts.append(config.qemu_commandline.qemu_commandline_string)

        return " ".join(cmd_parts)

    def get_vm_secure_boot_status(self, vm_name: str) -> SecureBootVM:
        """
        Проверяет, включен ли Secure Boot у конкретной ВМ

        Args:
            vm_name: Имя виртуальной машины

        Returns:
            Словарь с информацией о Secure Boot ВМ
        """
        try:
            domain = self.conn.lookupByName(vm_name)
            xml_desc = domain.XMLDesc(0)

            result = SecureBootVM(vm_name=vm_name)

            root = ElementTree.fromstring(xml_desc)
            print(xml_desc)

            # Проверяем наличие UEFI
            os_elem = root.find(".//os")
            if os_elem is not None:
                # Проверяем наличие firmware
                firmware_elem = os_elem.find("firmware")
                if firmware_elem is not None and firmware_elem.get("efi") == "yes":
                    result.has_uefi = True

                # Проверяем наличие loader
                loader_elem = os_elem.find("loader")
                if loader_elem is not None:
                    loader_type = loader_elem.get("type", "")
                    loader_path = loader_elem.text
                    result.loader_type = loader_type
                    result.secure_boot_loader = loader_path

                    # Проверяем, является ли загрузчик Secure Boot
                    if loader_path and (
                        "secboot" in loader_path.lower()
                        or "secure" in loader_path.lower()
                    ):
                        result.has_secure_boot = True

                    # Проверяем атрибуты secure
                    if loader_elem.get("secure") == "yes":
                        result.has_secure_boot = True

            qemu_commandline = root.find("qemu:commandline", QEMU_NAMESPACE)
            if qemu_commandline is not None:
                for arg in qemu_commandline.findall("qemu:arg", QEMU_NAMESPACE):
                    value = arg.get("value", "")
                    if "secureboot=on" in value or "loader_secure=yes" in value:
                        result.has_secure_boot = True

            # Проверяем наличие nvram
            nvram_elem = os_elem.find("nvram") if os_elem is not None else None
            if nvram_elem is not None:
                result.has_uefi = True

            return result

        except libvirt.libvirtError as e:
            self.logger.error(f"ВМ {vm_name} не найдена: {e}")
            return SecureBootVM(vm_name=vm_name, errors=[f"ВМ не найдена: '{str(e)}'"])
        except Exception as e:
            self.logger.error(f"Ошибка проверки Secure Boot для ВМ {vm_name}: {e}")
            return SecureBootVM(vm_name=vm_name, errors=[str(e)])

    def migrate_vm(
        self,
        vm_name: str,
        dest_uri: str,
        live: bool = True,
        undefine_source: bool = False,
        copy_storage: bool = False,
    ) -> VmMessage:
        """
        Миграция виртуальной машины на другой хост

        Args:
            vm_name: Имя ВМ для миграции
            dest_uri: URI целевого гипервизора (например: qemu+tcp://dest-host/system)
            live: Живая миграция (без остановки ВМ)
            undefine_source: Удалить конфигурацию с исходного хоста после миграции
            copy_storage: Копировать диски на целевой хост

        Returns:
            Результат операции
        """
        try:
            self.logger.info(f"Начало миграции ВМ '{vm_name}' на {dest_uri}")

            # Проверяем существование ВМ
            vm_info = self.get_vm_by_name(vm_name)
            if not vm_info.success:
                return vm_info

            # Получаем домен ВМ
            domain = self.conn.lookupByName(vm_name)

            # Проверяем состояние ВМ
            state, _ = domain.state()

            if state != libvirt.VIR_DOMAIN_RUNNING and live:
                return VmMessage(
                    success=False,
                    code=CommandMessagesEnum.for_live_migration_vm_need_to_running.name,
                )

            # Флаги миграции
            flags = 0
            if live:
                flags |= libvirt.VIR_MIGRATE_LIVE
                flags |= libvirt.VIR_MIGRATE_PEER2PEER
                flags |= libvirt.VIR_MIGRATE_TUNNELLED  # Для безопасности

            if undefine_source:
                flags |= libvirt.VIR_MIGRATE_UNDEFINE_SOURCE

            if copy_storage:
                flags |= libvirt.VIR_MIGRATE_NON_SHARED_DISK
                flags |= libvirt.VIR_MIGRATE_NON_SHARED_INC

            # Дополнительные параметры для миграции
            migrate_params = {
                "uri": dest_uri,
                "bandwidth": 0,  # 0 = неограниченная полоса
                "timeout": 300,  # 5 минут
            }

            # Выполняем миграцию
            self.logger.info(f"Выполнение миграции с флагами: {flags}")
            try:
                migrated_domain = domain.migrateToURI3(
                    dest_uri, params=migrate_params, flags=flags
                )

                if migrated_domain:
                    self.logger.info(f"ВМ '{vm_name}' успешно мигрирована")
                    self.ha_controller.delete_vm_from_nfs_config(vm_name)
                    return VmMessage(
                        success=True,
                        code=CommandMessagesEnum.migration_successfully_completed.name,
                        note=f"Live migration: {live} for {dest_uri}",
                    )
                else:
                    return VmMessage(
                        success=False,
                        code=CommandMessagesEnum.migration_completed_but_did_not_return_domain.name,
                    )

            except libvirt.libvirtError as e:
                self.logger.error(f"Ошибка миграции: {e}")

                # Пробуем альтернативный метод через virsh
                return self._migrate_via_virsh(
                    vm_name, dest_uri, live, undefine_source, copy_storage
                )

        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка при миграции: {e}")
            return VmMessage(
                success=False,
                code=CommandMessagesEnum.migration_error.name,
                note=str(e),
            )

    def _migrate_via_virsh(
        self,
        vm_name: str,
        dest_uri: str,
        live: bool = True,
        undefine_source: bool = False,
        copy_storage: bool = False,
    ) -> VmMessage:
        """
        Альтернативная миграция через virsh команду
        """
        try:
            cmd_parts = ["virsh", "migrate"]

            if live:
                cmd_parts.append("--live")

            if undefine_source:
                cmd_parts.append("--undefinesource")

            if copy_storage:
                cmd_parts.append("--copy-storage-all")
                cmd_parts.append("--persistent")

            cmd_parts.extend([vm_name, dest_uri])

            self.logger.info(f"Выполнение virsh команды: {' '.join(cmd_parts)}")

            result = subprocess.run(
                cmd_parts, capture_output=True, text=True, timeout=600
            )

            if result.returncode == 0:
                self.ha_controller.delete_vm_from_nfs_config(vm_name)
                return VmMessage(
                    success=True,
                    code=CommandMessagesEnum.migration_successfully_completed_with_virsh.name,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
            else:
                return VmMessage(
                    success=False,
                    code=CommandMessagesEnum.migration_error.name,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return VmMessage(
                success=False,
                code=CommandMessagesEnum.migration_timeout_error_with_virsh.value,
            )
        except Exception as e:
            return VmMessage(
                success=False,
                code=CommandMessagesEnum.migration_virsh_error.name,
                note=str(e),
            )

    def _migrate_storage_via_virsh(
        self,
        vm_name: str,
        dest_uri: str,
        dest_pool: str,
        xml_path: str,
        live: bool,
        sparse_copy: bool,
        bandwidth_limit: int,
    ) -> VmMessage:
        """
        Альтернативная миграция с дисками через virsh команду
        """
        try:
            cmd_parts = ["virsh", "migrate"]

            if live:
                cmd_parts.append("--live")

            if sparse_copy:
                cmd_parts.append("--compressed")

            if bandwidth_limit > 0:
                cmd_parts.extend(["--bandwidth", str(bandwidth_limit)])

            cmd_parts.extend(
                [
                    "--copy-storage-all",
                    "--persistent",
                    "--undefinesource",
                    "--xml",
                    xml_path,
                    vm_name,
                    dest_uri,
                ]
            )

            self.logger.info(f"Выполнение virsh команды: {' '.join(cmd_parts)}")

            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 минут для миграции с дисками
            )

            if result.returncode == 0:
                return VmMessage(
                    success=True,
                    code=CommandMessagesEnum.migration_with_disks_successfully_completed_with_virsh.name,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    note=f"Пул: {dest_pool}",
                )
            else:
                # Пробуем упрощенный вариант без --copy-storage-all
                self.logger.warning("Пробуем миграцию без copy-storage-all...")

                simple_cmd = ["virsh", "migrate"]
                if live:
                    simple_cmd.append("--live")

                simple_cmd.extend(["--persistent", vm_name, dest_uri])

                simple_result = subprocess.run(
                    simple_cmd, capture_output=True, text=True, timeout=600
                )

                if simple_result.returncode == 0:
                    return VmMessage(
                        success=True,
                        code=CommandMessagesEnum.migration_without_disks_successfully_completed_with_virsh.name,
                        note="Диски не скопированы, требуется общее хранилище",
                    )
                else:
                    return VmMessage(
                        success=False,
                        code=CommandMessagesEnum.migration_virsh_error.name,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )

        except subprocess.TimeoutExpired:
            return VmMessage(
                success=False,
                code=CommandMessagesEnum.migration_timeout_error_with_virsh.name,
            )
        except Exception as e:
            return VmMessage(
                success=False,
                code=CommandMessagesEnum.migration_virsh_error.name,
                note=str(e),
            )

    def check_migration_compatibility(self, vm_name: str, dest_uri: str) -> dict:
        """
        Проверка совместимости для миграции

        Returns:
            Словарь с результатами проверки
        """
        compatibility = {
            "cpu_compatible": False,
            "storage_accessible": False,
            "network_accessible": False,
            "libvirt_version_compatible": False,
            "errors": [],
        }

        try:
            # Получаем информацию о ВМ
            domain = self.conn.lookupByName(vm_name)
            xml_desc = domain.XMLDesc()

            # Проверяем совместимость CPU
            root = ElementTree.fromstring(xml_desc)
            cpu_elem = root.find(".//cpu")
            if cpu_elem is not None:
                cpu_mode = cpu_elem.get("mode", "host-model")
                if cpu_mode == "host-passthrough":
                    compatibility["errors"].append(
                        "CPU mode 'host-passthrough' не поддерживает миграцию"
                    )

            # Проверяем доступность NFS хранилищ
            ha_storages = self.ha_controller.loaded_ha_nfs_storages
            for storage in ha_storages.nfs_storages:
                if not self.ha_controller.check_nfs_availability(storage.source):
                    compatibility["errors"].append(
                        f"NFS хранилище {storage.source} недоступно"
                    )

            # Проверяем доступность целевого хоста
            try:
                # Пытаемся подключиться к целевому хосту
                test_cmd = ["virsh", "-c", dest_uri, "list", "--all"]
                result = subprocess.run(
                    test_cmd, capture_output=True, text=True, timeout=10
                )

                if result.returncode == 0:
                    compatibility["libvirt_version_compatible"] = True
                else:
                    compatibility["errors"].append(
                        f"Не удалось подключиться к целевому хосту: {result.stderr}"
                    )

            except Exception as e:
                compatibility["errors"].append(
                    f"Ошибка подключения к целевому хосту: {str(e)}"
                )

            # Проверяем общую совместимость
            if len(compatibility["errors"]) == 0:
                compatibility["cpu_compatible"] = True
                compatibility["storage_accessible"] = True
                compatibility["network_accessible"] = True

            return compatibility

        except Exception as e:
            self.logger.error(f"Ошибка проверки совместимости: {e}")
            compatibility["errors"].append(str(e))
            return compatibility

    def create_vm_from_xml(self, xml_config: str, autostart: bool = False) -> bool:
        """
        Создание ВМ из XML конфигурации (устаревший метод)

        Args:
            xml_config: XML конфигурация ВМ
            autostart: автостарт при загрузке хоста
        """
        self.logger.logger.warning(
            "Метод create_vm_from_xml устарел. Используйте create_vm()"
        )

        try:
            domain = self.conn.defineXML(xml_config)
            if domain is None:
                self.logger.error("Не удалось создать ВМ из XML")
                return False

            if autostart:
                domain.setAutostart(1)

            self.logger.info(f"ВМ {domain.name()} создана из XML")
            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка создания ВМ из XML, \nerr: {e}")
            return False

    def _set_autostart(self, vm_name: str | libvirt.virDomain, enabled: bool) -> bool:
        """
        Включение/выключение автостарта ВМ

        Args:
            vm_name: Имя ВМ
            enabled: Включить автостарт

        Returns:
            Успех операции
        """
        try:
            if isinstance(vm_name, str):
                domain = self.conn.lookupByName(vm_name)
            else:
                domain = vm_name
            domain.setAutostart(1 if enabled else 0)
            self.logger.info(f"Автостарт для ВМ '{vm_name}' установлен в {enabled}")
            return True
        except self.libvirtError as e:
            self.logger.error(
                f"Ошибка установки автостарта для ВМ '{vm_name}', \nerr: {e}"
            )
            return False

    # _______________________________________________Редактирование ВМ________

    def edit_vm(self, vm_name: str, vm_update: VmUpdateRequest) -> VmMessage:
        try:
            self.logger.info(f"Редактирование свойств ВМ {vm_name}")

            # Получаем домен
            current_vm = self.conn.lookupByName(vm_name)
            state, _ = current_vm.state()
            is_running = state == libvirt.VIR_DOMAIN_RUNNING

            self.logger.info(
                f"Состояние ВМ: {'запущена' if is_running else 'остановлена'}"
            )

            # Получаем текущую XML конфигурацию
            xml_desc = current_vm.XMLDesc(0)
            self.logger.debug(f"Текущий XML: {xml_desc[:500]}...")

            # Парсим XML
            root = ElementTree.fromstring(xml_desc)
            modified = False

            # Изменение vCPU
            if vm_update.vcpus is not None:
                self.logger.info(f"Изменение vCPU на {vm_update.vcpus}")

                # Находим или создаем элемент vcpu
                vcpu_elem = root.find("vcpu")
                if vcpu_elem is None:
                    vcpu_elem = ElementTree.SubElement(root, "vcpu")

                # Устанавливаем значение
                vcpu_elem.text = str(vm_update.vcpus)
                vcpu_elem.set("current", str(vm_update.vcpus))

                # Обновляем элемент cpu для топологии
                cpu_elem = root.find("cpu")
                if cpu_elem is not None:
                    # Обновляем топологию CPU
                    topology: Any = cpu_elem.find("topology")
                    if topology is None:
                        topology = ElementTree.SubElement(cpu_elem, "topology")

                    # Устанавливаем простую топологию: sockets = vcpus, cores = 1, threads
                    # = 1
                    topology.set("sockets", str(vm_update.vcpus))
                    topology.set("cores", "1")
                    topology.set("threads", "1")

                modified = True

            # Изменение описания
            if vm_update.description is not None:
                self.logger.info(f"Изменение описания на '{vm_update.description}'")

                # Находим или создаем элемент description
                description_elem = root.find("description")
                if description_elem is None:
                    # Создаем элемент description если его нет
                    description_elem = ElementTree.SubElement(root, "description")

                # Устанавливаем текст описания
                description_elem.text = str(vm_update.description)

                modified = True

            if vm_update.autostart is not None:
                self._set_autostart(current_vm, vm_update.autostart)
            # Изменение модели CPU (требует остановки ВМ)
            if vm_update.cpu_model is not None:  # Заглушка, не протестировано
                try:
                    cpu_config = vm_update.cpu_model

                    # Валидация входных данных
                    if not isinstance(cpu_config, dict):
                        raise ValueError("cpu_model должен быть словарем")

                    # Проверяем обязательные поля для разных режимов
                    mode = cpu_config.get("mode", "host-passthrough")
                    valid_modes = [
                        "host-passthrough",
                        "host-model",
                        "custom",
                        "maximum",
                    ]

                    if mode not in valid_modes:
                        raise ValueError(
                            f"Недопустимый режим CPU: {mode}. Допустимо: {valid_modes}"
                        )

                    # Для custom режима обязательна модель
                    if mode == "custom" and "model" not in cpu_config:
                        raise ValueError(
                            "Для custom режима CPU требуется параметр 'model'"
                        )

                    # Проверяем, что ВМ остановлена
                    current_dom = self.conn.lookupByName(vm_name)
                    if current_dom.isActive():
                        return VmMessage(
                            success=False,
                            code=CommandMessagesEnum.can_not_change_cpu_model_on_running_vm.name,
                        )

                    self.logger.info(f"Изменение модели CPU на режим '{mode}'")

                    # Находим или создаем элемент cpu
                    cpu_elem = root.find("cpu")
                    if cpu_elem is None:
                        # Вставляем после элемента memory
                        memory_elem = root.find("memory")
                        if memory_elem is not None:
                            index = list(root).index(memory_elem) + 1
                            cpu_elem = ElementTree.Element("cpu")
                            root.insert(index, cpu_elem)
                        else:
                            cpu_elem = ElementTree.SubElement(root, "cpu")
                    else:
                        # Очищаем старую конфигурацию
                        for child in list(cpu_elem):
                            cpu_elem.remove(child)

                    # Устанавливаем атрибуты
                    cpu_elem.set("mode", mode)

                    if "match" in cpu_config:
                        match = str(cpu_config["match"])
                        cpu_elem.set("match", match)

                    if "check" in cpu_config:
                        check = str(cpu_config["check"])
                        cpu_elem.set("check", check)

                    # Добавляем модель для custom/host-model
                    if mode in ["custom", "host-model"] and "model" in cpu_config:
                        cpu_model = str(cpu_config["model"])
                        model_elem = ElementTree.SubElement(cpu_elem, "model")
                        model_elem.text = cpu_model
                        model_elem.set("fallback", cpu_config.get("fallback", "allow"))

                    # Добавляем топологию
                    if "topology" in cpu_config:
                        topology: Any = cpu_config["topology"]
                        topology_elem = ElementTree.SubElement(cpu_elem, "topology")

                        # Валидация топологии
                        sockets = int(topology.get("sockets", 1))
                        cores = int(topology.get("cores", 1))
                        threads = int(topology.get("threads", 1))

                        if sockets * cores * threads <= 0:
                            raise ValueError("Некорректная топология CPU")

                        topology_elem.set("sockets", str(sockets))
                        topology_elem.set("cores", str(cores))
                        topology_elem.set("threads", str(threads))

                    # Добавляем features
                    if "features" in cpu_config:
                        features: Any = cpu_config["features"]
                        for feature_name, feature_policy in features.items():
                            if feature_policy not in [
                                "require",
                                "optional",
                                "disable",
                                "forbid",
                            ]:
                                self.logger.warning(
                                    f"Некорректная политика фичи '{feature_name}': {feature_policy}"
                                )
                                continue

                            feature_elem = ElementTree.SubElement(cpu_elem, "feature")
                            feature_elem.set("policy", feature_policy)
                            feature_elem.set("name", feature_name)

                    modified = True
                    self.logger.info(
                        f"Конфигурация CPU успешно обновлена: режим={mode}"
                    )

                except ValueError as e:
                    self.logger.error(f"Ошибка валидации CPU конфигурации: {e}")
                    raise
                except Exception as e:
                    self.logger.error(f"Ошибка обновления CPU конфигурации: {e}")
                    raise

            # Изменение памяти
            if vm_update.max_memory_mb is not None:
                self.logger.info(f"Изменение памяти на {vm_update.max_memory_mb} MB")

                # Преобразуем MB в KB (libvirt работает с KB)
                memory_kb = vm_update.max_memory_mb * 1024

                # Находим или создаем элемент memory
                memory_elem = root.find("memory")
                if memory_elem is None:
                    memory_elem = ElementTree.SubElement(root, "memory")

                # Устанавливаем значение
                memory_elem.text = str(memory_kb)
                memory_elem.set("unit", "KiB")

                # Обновляем currentMemory если есть
                current_elem = root.find("currentMemory")
                if current_elem is None:
                    current_elem = ElementTree.SubElement(root, "currentMemory")

                current_elem.text = str(memory_kb)
                current_elem.set("unit", "KiB")

                modified = True

            # Изменение max vCPU
            if vm_update.max_vcpus is not None:
                self.logger.info(f"Изменение max vCPU на {vm_update.max_vcpus}")

                vcpu_elem = root.find("vcpu")
                if vcpu_elem is None:
                    vcpu_elem = ElementTree.SubElement(root, "vcpu")

                # Для max_vcpus используем placement="static"
                vcpu_elem.set("placement", "static")
                if vm_update.vcpus is not None:
                    vcpu_elem.text = str(vm_update.max_vcpus)
                    vcpu_elem.set("current", str(vm_update.vcpus))
                else:
                    # Если vcpus не указано, получаем текущее значение
                    current_vcpus = vcpu_elem.get("current") or vcpu_elem.text or "1"
                    vcpu_elem.text = str(vm_update.max_vcpus)
                    vcpu_elem.set("current", current_vcpus)

                modified = True

            # Если были изменения, сохраняем новую конфигурацию
            if modified:
                # Конвертируем XML обратно в строку
                new_xml = ElementTree.tostring(root, encoding="unicode", method="xml")
                self.logger.info(f"Новый XML: {new_xml[:500]}...")

                if not is_running:
                    self.conn.defineXML(new_xml)
                    self.logger.info("Конфигурация ВМ обновлена (остановлена)")
                else:
                    if vm_update.change_live_config:
                        vm_update_model = vm_update.model_dump()
                        vm_update_model.pop("change_live_config")
                        params = [
                            (key, param)
                            for key, param in vm_update_model.items()
                            if param
                        ]
                        for key, _ in params:
                            if key not in SUPPORT_LIVE_UPGRADE_PARAMS:
                                return VmMessage(
                                    success=False,
                                    code=CommandMessagesEnum.vm_edit_error_unsupport_update_this_params_on_live_mode.name,
                                )
                        if vm_update.vcpus is not None:
                            try:
                                current_vm.setVcpusFlags(
                                    vm_update.vcpus, libvirt.VIR_DOMAIN_AFFECT_LIVE
                                )
                                self.logger.info("vCPU изменены на лету")
                            except libvirt.libvirtError as e:
                                self.logger.error(f"Ошибка: {e}")
                    else:
                        shutoff_result = self.shutoff_vm(vm_name, True)
                        if (
                            shutoff_result.code
                            != CommandMessagesEnum.vm_successfully_shutdowned.name
                        ):
                            return VmMessage(
                                success=False,
                                code=CommandMessagesEnum.vm_edit_error_in_shutoff_process.name,
                            )
                        self.conn.defineXML(new_xml)
                        self.start_vm(vm_name)
                        self.logger.info(f"ВМ {vm_name} успешно обновлена")
                        self.ha_controller.sync_nfs_vm_configs()
                        return VmMessage(
                            success=True,
                            code=CommandMessagesEnum.vm_edit_success.name,
                        )

                self.logger.info(f"Конфигурация ВМ {vm_name} обновлена")
            else:
                self.logger.info("Нет изменений для применения")

            self.logger.info(f"ВМ {vm_name} успешно обновлена")
            self.ha_controller.sync_nfs_vm_configs()
            return VmMessage(
                success=True,
                code=CommandMessagesEnum.vm_edit_success.name,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка при редактировании ВМ {vm_name}: {e}")
            return VmMessage(
                success=False,
                code=CommandMessagesEnum.vm_edit_error.name,
                note=str(e),
            )
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка при редактировании ВМ: {e}")
            return VmMessage(
                success=False,
                code=CommandMessagesEnum.vm_edit_unexpected_error.name,
                note=str(e),
            )

    def _apply_virsh_commands(
        self, vm_name: str, changes: list[str], is_running: bool
    ) -> bool:
        try:
            # Команды, которые можно передать через virsh edit
            edit_params = [
                "--description",
                "--rename",
                "--autostart",
                "--disable-autostart",
            ]
            edit_changes = [
                ch for ch in changes if any(param in ch for param in edit_params)
            ]

            if edit_changes:
                cmd = ["virsh", "edit", vm_name] + edit_changes
                if is_running:
                    cmd.append("--live")

                self.logger.debug(f"Выполнение команды edit: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                if result.returncode != 0:
                    self.logger.error(
                        f"Ошибка при применении изменений через edit: {result.stderr}"
                    )
                    return False

            # Отдельные команды для параметров, не поддерживаемых edit
            separate_commands = []

            for i in range(0, len(changes), 2):
                param = changes[i]
                value = changes[i + 1] if i + 1 < len(changes) else ""

                if param == "--memory":
                    cmd = ["virsh", "setmem", vm_name, value, "--config"]
                    separate_commands.append(cmd)
                    if is_running:
                        separate_commands.append(
                            ["virsh", "setmem", vm_name, value, "--live"]
                        )

                elif param == "--current-memory" and is_running:
                    separate_commands.append(
                        ["virsh", "setmem", vm_name, value, "--live"]
                    )

                elif param == "--vcpus":
                    cmd = ["virsh", "setvcpus", vm_name, value, "--config"]
                    separate_commands.append(cmd)
                    if is_running:
                        separate_commands.append(
                            ["virsh", "setvcpus", vm_name, value, "--live"]
                        )

                elif "maxvcpus=" in value:
                    max_vcpus = value.split("maxvcpus=")[1].split(",")[0]
                    separate_commands.append(
                        [
                            "virsh",
                            "setvcpus",
                            vm_name,
                            max_vcpus,
                            "--maximum",
                            "--config",
                        ]
                    )

            # Выполняем отдельные команды
            for cmd in separate_commands:
                if not self._execute_virsh_command(cmd):
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Ошибка при применении команд virsh: {e}")
            return False

    def _apply_xml_changes(
        self, vm_name: str, vm_update: VmUpdateRequest, is_running: bool
    ) -> bool:
        try:
            current_vm = self.conn.lookupByName(vm_name)
            current_xml = current_vm.XMLDesc()
            root = ElementTree.fromstring(current_xml)

            self._modify_xml(root, vm_update)
            new_xml = ElementTree.tostring(root, encoding="unicode")

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".xml", delete=False
            ) as tmp:
                tmp.write(new_xml)
                tmp_path = tmp.name

            try:
                cmd = ["virsh", "define", tmp_path]
                if is_running:
                    cmd.append("--live")

                self.logger.debug(f"Выполнение команды: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                if result.returncode != 0:
                    self.logger.error(f"Ошибка при обновлении XML: {result.stderr}")
                    return False

                self.logger.info(f"XML конфигурация ВМ {vm_name} успешно обновлена")
                return True

            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except Exception as e:
            self.logger.exception(f"Ошибка при модификации XML: {e}")
            return False

    @staticmethod
    def _modify_xml(root: ElementTree.Element, vm_update: VmUpdateRequest):
        devices_elem = root.find("./devices")
        if devices_elem is None:
            devices_elem = ElementTree.SubElement(root, "devices")

        if vm_update.cpu_model is not None or vm_update.cpu_features is not None:
            cpu_elem = root.find("./cpu")
            if cpu_elem is None:
                cpu_elem = ElementTree.SubElement(root, "cpu")
                cpu_elem.set("mode", "custom")
                cpu_elem.set("match", "exact")

            if vm_update.cpu_model is not None:
                model_elem = cpu_elem.find("./model")
                if model_elem is None:
                    model_elem = ElementTree.SubElement(cpu_elem, "model")
                    model_elem.set("fallback", "allow")
                model_elem.text = vm_update.cpu_model

            if vm_update.cpu_features is not None:
                for feature in cpu_elem.findall("./feature"):
                    cpu_elem.remove(feature)
                for feature_name in vm_update.cpu_features:
                    feature_elem = ElementTree.SubElement(cpu_elem, "feature")
                    feature_elem.set("policy", "require")
                    feature_elem.set("name", feature_name)

        if vm_update.graphics is not None:
            for graphics in devices_elem.findall("./graphics"):
                devices_elem.remove(graphics)

            graphics_elem = ElementTree.SubElement(devices_elem, "graphics")
            graphics_type = vm_update.graphics.get("type", "vnc")
            graphics_elem.set("type", graphics_type)

            if graphics_type == "vnc":
                graphics_elem.set("autoport", "yes")
                if "port" in vm_update.graphics:
                    graphics_elem.set("port", str(vm_update.graphics.get("port")))
                    graphics_elem.set("autoport", "no")
                if "listen" in vm_update.graphics:
                    graphics_elem.set("listen", vm_update.graphics.get("listen"))
            elif graphics_type == "spice":
                graphics_elem.set("autoport", "yes")

        if vm_update.video_model is not None:
            for video in devices_elem.findall("./video"):
                devices_elem.remove(video)

            video_elem = ElementTree.SubElement(devices_elem, "video")
            model_elem = ElementTree.SubElement(video_elem, "model")
            model_elem.set("type", vm_update.video_model.value)

        if vm_update.machine_type is not None:
            os_elem = root.find("./os")
            if os_elem is not None:
                type_elem = os_elem.find("./type")
                if type_elem is None:
                    type_elem = ElementTree.SubElement(os_elem, "type")
                    type_elem.set("arch", "x86_64")
                    type_elem.text = "hvm"
                type_elem.set("machine", vm_update.machine_type)

        if vm_update.os_variant is not None:
            os_elem = root.find("./os")
            if os_elem is not None:
                variant_elem = os_elem.find("./variant")
                if variant_elem is None:
                    variant_elem = ElementTree.SubElement(os_elem, "variant")
                variant_elem.text = vm_update.os_variant

        if vm_update.boot_devices is not None:
            os_elem = root.find("./os")
            if os_elem is None:
                os_elem = ElementTree.SubElement(root, "os")
                type_elem = ElementTree.SubElement(os_elem, "type")
                type_elem.set("arch", "x86_64")
                type_elem.text = "hvm"

            for boot in os_elem.findall("./boot"):
                os_elem.remove(boot)

            for device in vm_update.boot_devices:
                boot_elem = ElementTree.SubElement(os_elem, "boot")
                boot_elem.set("dev", device)

        if vm_update.features is not None:
            features_elem = root.find("./features")
            if features_elem is None:
                features_elem = ElementTree.SubElement(root, "features")

            for feature in features_elem:
                features_elem.remove(feature)

            for feature_name, feature_value in vm_update.features.items():
                feature_elem = ElementTree.SubElement(features_elem, feature_name)
                feature_elem.set("state", feature_value)

        if vm_update.memballoon_model is not None:
            for memballoon in devices_elem.findall("./memballoon"):
                devices_elem.remove(memballoon)

            memballoon_elem = ElementTree.SubElement(devices_elem, "memballoon")
            memballoon_elem.set("model", vm_update.memballoon_model)

        if vm_update.hyperv_features is not None:
            features_elem = root.find("./features")
            if features_elem is None:
                features_elem = ElementTree.SubElement(root, "features")

            hyperv_elem = features_elem.find("./hyperv")
            if hyperv_elem is not None:
                features_elem.remove(hyperv_elem)

            hyperv_elem = ElementTree.SubElement(features_elem, "hyperv")

            for feature_name, feature_value in vm_update.hyperv_features.items():
                if feature_name == "relaxed":
                    relaxed_elem = ElementTree.SubElement(hyperv_elem, "relaxed")
                    relaxed_elem.set("state", feature_value)
                elif feature_name == "vapic":
                    vapic_elem = ElementTree.SubElement(hyperv_elem, "vapic")
                    vapic_elem.set("state", feature_value)
                elif feature_name == "spinlocks":
                    spinlocks_elem = ElementTree.SubElement(hyperv_elem, "spinlocks")
                    spinlocks_elem.set("state", feature_value)

        if vm_update.qemu_agent is not None:
            for channel in devices_elem.findall("./channel"):
                target = channel.find("./target")
                if target is not None and target.get("type") == "virtio":
                    devices_elem.remove(channel)

            if vm_update.qemu_agent:
                channel_elem = ElementTree.SubElement(devices_elem, "channel")
                channel_elem.set("type", "unix")
                source_elem = ElementTree.SubElement(channel_elem, "source")
                source_elem.set("mode", "bind")
                target_elem = ElementTree.SubElement(channel_elem, "target")
                target_elem.set("type", "virtio")
                target_elem.set("name", "org.qemu.guest_agent.0")

    def _execute_virsh_command(self, cmd: list[str]) -> bool:
        try:
            self.logger.debug(f"Выполнение команды: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                self.logger.error(f"Ошибка: {result.stderr}")
                return False

            return True

        except subprocess.TimeoutExpired:
            self.logger.error("Таймаут при выполнении команды")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка: {e}")
            return False

    # _______________________________________________Редактирование ВМ________

    def list_vms(self, only_active: bool = False) -> VmMessage:
        """
        Получение списка виртуальных машин

        Args:
            only_active: только активные ВМ

        Returns:
            Список информации о ВМ
        """
        if not self.conn:
            raise ConnectionError("Сначала подключитесь к гипервизору")

        virtual_machines = []
        try:
            if only_active:
                domain_ids = self.conn.listDomainsID()
                for domain_id in domain_ids:
                    domain = self.conn.lookupByID(domain_id)
                    virtual_machines.append(self.get_vm_info(domain))
            else:
                domains = self.conn.listAllDomains(0)
                for domain in domains:
                    virtual_machines.append(self.get_vm_info(domain))

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения списка ВМ, \nerr: {e}")

        if virtual_machines:
            return VmMessage(
                success=True,
                code=CommandMessagesEnum.vm_list_found.name,
                vm_info=VirtualMachinesList(
                    items=virtual_machines, total=len(virtual_machines)
                ),
            )
        return VmMessage(
            success=False,
            code=CommandMessagesEnum.vm_list_not_found.name,
            vm_info=VirtualMachinesList(
                items=virtual_machines, total=len(virtual_machines)
            ),
        )

    @staticmethod
    def parse_hostfwd_regex(hostfwd_str: str) -> dict:
        """Парсит строку hostfwd с помощью regex"""

        patterns = (
            # Стандартный формат: hostfwd=tcp::2222-:22
            r"hostfwd=(?P<protocol>tcp|udp)::(?P<host_port>\d+)-(?::(?P<host_ip>[^:]+):)?:(?P<guest_port>\d+)",
            # С указанием IP хоста: hostfwd=tcp:192.168.1.1:2222-:22
            r"hostfwd=(?P<protocol>tcp|udp):(?P<host_ip>[^:]+):(?P<host_port>\d+)-:(?P<guest_port>\d+)",
            # Без протокола (редко): hostfwd=:2222-:22
            r"hostfwd=:(?P<host_port>\d+)-:(?P<guest_port>\d+)",
        )

        for pattern in patterns:
            match = re.match(pattern, hostfwd_str)
            if match:
                result = match.groupdict()
                # Преобразуем порты в int
                if "host_port" in result:
                    result["host_port"] = int(result["host_port"])
                if "guest_port" in result:
                    result["guest_port"] = int(result["guest_port"])
                return result

        return {}

    @property
    def generate_new_net_id(self):
        return f"net{random.randint(100_000_000, 999_999_999)}"

    def get_all_hostfwd_and_net_ids(
        self,
    ) -> list[tuple[str, HostForward] | tuple[None, None]]:
        hostfwd_and_net_ids_list = []

        all_domains = self.conn.listAllDomains(
            libvirt.VIR_CONNECT_LIST_DOMAINS_ACTIVE
            | libvirt.VIR_CONNECT_LIST_DOMAINS_INACTIVE
        )

        for current_domain in all_domains:
            hostfwd_and_net_id = self.get_hostfwd_and_net_id(current_domain)
            if hostfwd_and_net_id[0] is not None or hostfwd_and_net_id[1] is not None:
                hostfwd_and_net_ids_list.append(
                    self.get_hostfwd_and_net_id(current_domain)
                )

        return hostfwd_and_net_ids_list

    def get_hostfwd_and_net_id(
        self, vm_name: str | libvirt.virDomain
    ) -> tuple[str, HostForward] | tuple[None, None]:
        if isinstance(vm_name, libvirt.virDomain):
            domain = vm_name
        elif isinstance(vm_name, str):
            domain = self.conn.lookupByName(vm_name)
        else:
            raise ValueError(f"Некорректный тип данных: '{type(vm_name)}'")
        root = ElementTree.fromstring(domain.XMLDesc())

        qemu_commandline = root.find("qemu:commandline", QEMU_NAMESPACE)
        if not qemu_commandline:
            return None, None

        qemu_args = qemu_commandline.findall("qemu:arg", QEMU_NAMESPACE)
        if not qemu_args:
            return None, None

        qemu_params = qemu_args.pop().get("value").split(",")
        current_net_id = None
        hostfwd = None

        for qemu_param in qemu_params:
            if "id=" in qemu_param:
                current_net_id = qemu_param.split("=").pop()
                break
        for qemu_param in qemu_params:
            if "hostfwd" in qemu_param:
                hostfwd = HostForward(**self.parse_hostfwd_regex(qemu_param))
                break

        return current_net_id, hostfwd

    def get_vm_info(self, domain, display_logs: bool = True) -> VirtualMachine | None:
        """Получение информации о виртуальной машине"""
        try:
            info = domain.info()
            state = VMState(info[0])
            if display_logs:
                self.logger.info(f"ВМ {domain.name()} найдена : '{info}'")
            current_net_id, hostfwd = self.get_hostfwd_and_net_id(domain.name())
            root = ElementTree.fromstring(domain.XMLDesc(0))
            description = (
                root.find("description").text
                if root.find("description") is not None
                else None
            )

            return VirtualMachine(
                name=domain.name(),
                description=description,
                state=state,
                id=domain.ID() if domain.ID() != -1 else -1,
                net_id=current_net_id,
                uuid=domain.UUIDString(),
                hostfwd=hostfwd,
                vcpus=info[3],
                memory=info[2],
                max_memory=info[1],
                cpu_time=info[4],
            )
        except self.libvirtError as e:
            if display_logs:
                self.logger.error(f"Ошибка получения информации о ВМ, \nerr: {e}")
            raise

    def get_vm_state_with_msg(self, name: str, display_logs: bool = False):
        try:
            result = self.get_vm_state_by_name(name, display_logs)
            return VmMessage(code=CommandMessagesEnum.vm_state_info.name,
                             vm_info=VMStateInfo(vm_name=name, state=VMState(result)),
                             success=True)
        except Exception as e:
            return VmMessage(code=CommandMessagesEnum.vm_state_info_error.name,
                             success=False,
                             note=str(e))

    def get_vm_state_by_name(self, name: str, display_logs: bool = False) -> int | bool:
        """Получение состояния ВМ по имени"""
        try:
            domain = self.conn.lookupByName(name)
            if display_logs:
                self.logger.info(f"Поиск ВМ {name}")
            info = domain.info()
            state = VMState(info[0])
            return state.value
        except self.libvirtError:
            if display_logs:
                self.logger.info(f"ВМ {name} не найдена")
            return False

    def get_vm_by_name(self, name: str) -> VmMessage:
        """Получение ВМ по имени"""
        try:
            domain = self.conn.lookupByName(name)
            self.logger.info(f"Поиск ВМ {name}")
            return VmMessage(
                code=CommandMessagesEnum.vm_successfully_found.name,
                vm_info=self.get_vm_info(domain),
                success=True,
            )
        except self.libvirtError as e:
            self.logger.info(f"ВМ {name} не найдена")
            return VmMessage(
                code=CommandMessagesEnum.vm_found_error.name,
                success=False,
                note=str(e),
            )

    def start_vm(self, name: str) -> VmMessage:
        """Запуск виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.create() == 0:
                self.logger.info(f"ВМ {name} запущена")
                return VmMessage(
                    code=CommandMessagesEnum.vm_successfully_started.name,
                    success=True,
                )
            self.logger.info(f"ВМ {name} не запустилась")
            return VmMessage(
                code=CommandMessagesEnum.vm_start_error.name,
                success=False,
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка запуска ВМ {name}, \nerr: {e}")
            return VmMessage(
                code=CommandMessagesEnum.vm_start_error.name,
                success=False,
                note=str(e),
            )

    def shutoff_vm(self, name: str, force: bool = False) -> VmMessage:
        """
        Выключение виртуальной машины

        Args:
            name: имя ВМ
            force: принудительное выключение
        """
        try:
            domain = self.conn.lookupByName(name)

            if force:
                result = domain.destroy()
            else:
                result = domain.shutdown()

            if result == 0:
                action = "принудительно выключена" if force else "выключена"
                self.logger.info(f"ВМ {name} {action}")
                return VmMessage(
                    code=CommandMessagesEnum.vm_successfully_shutdowned.name,
                    success=True,
                )
            return VmMessage(
                code=CommandMessagesEnum.vm_shutdown_error.name,
                success=False,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка выключения ВМ {name}, \nerr: {e}")
            return VmMessage(
                code=CommandMessagesEnum.vm_shutdown_error.name,
                success=False,
                note=str(e),
            )

    def reboot_vm(self, name: str, hard_reset: bool = False) -> VmMessage:
        """Перезагрузка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if hard_reset:
                domain.reset()
                self.logger.info(f"Выполнена жесткая перезагрузка для ВМ {name}")
                return VmMessage(
                    code=CommandMessagesEnum.vm_successfully_restarted.name,
                    success=True,
                )
            if domain.reboot(0) == 0:
                self.logger.info(f"ВМ {name} перезагружается")
                return VmMessage(
                    code=CommandMessagesEnum.vm_successfully_restarted.name,
                    success=True,
                )
            return VmMessage(
                code=CommandMessagesEnum.vm_restart_error.name,
                success=False,
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка перезагрузки ВМ {name}, \nerr: {e}")
            return VmMessage(
                code=CommandMessagesEnum.vm_restart_error.name,
                success=False,
                note=str(e),
            )

    def suspend_vm(self, name: str) -> VmMessage:
        """Приостановка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.suspend() == 0:
                self.logger.info(f"ВМ {name} приостановлена")
                return VmMessage(
                    code=CommandMessagesEnum.vm_successfully_stopped.name,
                    success=True,
                )
            self.logger.info(f"ВМ {name} не приостановлена")
            return VmMessage(
                code=CommandMessagesEnum.vm_stop_error.name,
                success=False,
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка приостановки ВМ {name}, \nerr: {e}")
            return VmMessage(
                code=CommandMessagesEnum.vm_stop_error.name,
                success=False,
                note=str(e),
            )

    def resume_vm(self, name: str) -> VmMessage:
        """Возобновление работы виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.resume() == 0:
                self.logger.info(f"ВМ {name} возобновлена")
                return VmMessage(
                    code=CommandMessagesEnum.vm_successfully_resumed.name,
                    success=True,
                )
            self.logger.info(f"ВМ {name} не возобновлена")
            return VmMessage(
                code=CommandMessagesEnum.vm_resume_error.name,
                success=False,
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка возобновления ВМ {name}")
            return VmMessage(
                code=CommandMessagesEnum.vm_resume_error.name,
                success=False,
                note=str(e),
            )

    def delete_vm(
        self,
        name: str,
        delete_disks: bool = False,
        delete_nvram: bool = True,
    ) -> VmMessage:
        """
        Удаление виртуальной машины с поддержкой UEFI NVRAM

        Args:
            name: Имя ВМ
            delete_disks: Удалять ли диски ВМ
            delete_nvram: Удалять ли файл NVRAM (для UEFI ВМ)

        Returns:
            Успех операции
        """
        try:
            domain = self.conn.lookupByName(name)

            xml_config = domain.XMLDesc(0)

            nvram_path = None
            if delete_nvram:
                nvram_path = self._extract_nvram_path(xml_config)

            disks_to_delete = []
            self.snapshot.delete_all_snapshots_by_vm_name(name)
            if delete_disks:
                disks_to_delete = self._extract_disk_paths(xml_config)

            if domain.isActive():
                self.logger.info(f"ВМ {name} запущена, выключаем...")
                domain.destroy()

            try:
                domain.undefineFlags(
                    VIR_DOMAIN_UNDEFINE_MANAGED_SAVE | VIR_DOMAIN_UNDEFINE_NVRAM
                )
                self.logger.info(f"Конфигурация ВМ {name} удалена с флагами")
            except self.libvirtError as e:
                self.logger.warning(f"Стандартное удаление не сработало: {e}")
                domain.undefine()

            if nvram_path and os.path.exists(nvram_path):
                try:
                    os.remove(nvram_path)
                    self.logger.info(f"Файл NVRAM удален: {nvram_path}")
                except OSError as e:
                    self.logger.error(
                        f"Не удалось удалить файл NVRAM {nvram_path}, \nerr: {e}"
                    )

            for disk_path in disks_to_delete:
                if os.path.exists(disk_path):
                    try:
                        # Используем StorageManager для удаления дисков
                        if disk_path.lower().endswith(".iso"):
                            # Для ISO файлов просто удаляем файл
                            os.remove(disk_path)
                            self.logger.info(f"ISO файл удален: {disk_path}")
                        else:
                            # Для обычных дисков используем StorageManager
                            self.storage_manager.delete_disk(disk_path=disk_path)
                            self.logger.info(
                                f"Диск удален через StorageManager: {disk_path}"
                            )
                    except OSError as e:
                        self.logger.error(
                            f"Не удалось удалить диск {disk_path}, \nerr: {e}"
                        )

            self.logger.info(f"ВМ {name} удалена")
            self.ha_controller.delete_vm_from_nfs_config(name)
            return VmMessage(
                code=CommandMessagesEnum.vm_successfully_deleted.name,
                success=True,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления ВМ {name}, \nerr: {e}")

            return VmMessage(
                code=CommandMessagesEnum.vm_delete_error.name,
                success=False,
                note=str(e),
            )

    def _extract_disk_paths(self, xml_config: str) -> list[str]:
        """
        Извлечение путей к дискам из XML конфигурации

        Args:
            xml_config: XML конфигурация ВМ

        Returns:
            Список путей к дискам
        """
        disk_paths = []
        try:
            root = ElementTree.fromstring(xml_config)

            for disk in root.findall(".//disk"):
                source = disk.find("source")
                if source is not None:
                    file_attr = source.get("file")
                    if file_attr:
                        disk_paths.append(file_attr)

                    dev_attr = source.get("dev")
                    if dev_attr:
                        disk_paths.append(dev_attr)

                    volume_attr = source.get("volume")
                    if volume_attr:
                        pool_attr = source.get("pool")
                        if pool_attr:
                            pass
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении путей к дискам: {e}")

        return disk_paths

    def delete_vm_with_force(self, name: str, delete_disks: bool = True):
        """
        Вспомогательная функция для принудительного удаления ВМ,
        используйте эту функцию если обычное удаление не работает

        Args:
            name: Имя ВМ
            delete_disks: удалять ли диски ВМ
        """

        methods = [
            lambda: self.delete_vm(
                name,
                delete_disks=delete_disks,
                delete_nvram=True,
            ),
            lambda: self.delete_vm(
                name,
                delete_disks=delete_disks,
                delete_nvram=False,
            ),
        ]

        for i, method in enumerate(methods, 1):
            self.logger.info(f"Попытка {i} удаления ВМ {name}...")
            result = method()
            if result.success:
                self.logger.info(f"ВМ {name} успешно удалена")
                return VmMessage(
                    code=CommandMessagesEnum.vm_successfully_deleted.name,
                    success=True,
                )

        self.logger.info(f"Не удалось удалить ВМ {name}")
        return VmMessage(
            code=CommandMessagesEnum.vm_delete_error.name,
            success=False,
        )

    def _extract_nvram_path(self, xml_config: str) -> str | None:
        """
        Извлечение пути к файлу NVRAM из XML конфигурации

        Args:
            xml_config: XML конфигурация ВМ

        Returns:
            Путь к файлу NVRAM или None если не используется
        """
        try:
            root = ElementTree.fromstring(xml_config)
            os_element = root.find(".//os")

            if os_element is not None:
                nvram_element = os_element.find("nvram")
                if nvram_element is not None:
                    return nvram_element.text

            loader_element: Any = root.find('.//loader[@type="pflash"]')
            if loader_element is not None:
                parent = loader_element.getparent()
                if parent is not None:
                    nvram_element = parent.find("nvram")
                    if nvram_element is not None:
                        return nvram_element.text

            return None
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге XML для поиска NVRAM: {e}")
            return None

    def clone_vm(
        self, source_name: str, new_name: str, new_uuid: bool = True
    ) -> VmMessage:
        try:
            source_domain = self.conn.lookupByName(source_name)
            xml_config = source_domain.XMLDesc(0)
            root = ElementTree.fromstring(xml_config)

            # Обновляем имя ВМ
            name_elem = root.find("name")
            if name_elem is not None:
                name_elem.text = new_name

            # Генерируем новый UUID
            if new_uuid:
                uuid_elem = root.find("uuid")
                if uuid_elem is not None:
                    uuid_elem.text = str(uuid.uuid4())

            # Клонируем NVRAM файл для UEFI ВМ
            nvram_elem = root.find(".//os/nvram")
            if nvram_elem is not None and nvram_elem.text:
                old_nvram_path = nvram_elem.text
                if Path(old_nvram_path).exists():
                    # Создаем новый путь для NVRAM
                    nvram_dir = os.path.dirname(old_nvram_path)

                    # Создаем новое имя NVRAM файла
                    new_nvram_name = f"{new_name}_VARS.fd"
                    new_nvram_path = os.path.join(nvram_dir, new_nvram_name)

                    # Копируем NVRAM файл
                    try:
                        shutil.copy2(old_nvram_path, new_nvram_path)
                        nvram_elem.text = new_nvram_path
                        self.logger.info(
                            f"NVRAM файл скопирован: {old_nvram_path} -> {new_nvram_path}"
                        )
                    except Exception as e:
                        self.logger.warning(f"Не удалось скопировать NVRAM файл: {e}")
                        # Создаем пустой NVRAM файл
                        open(new_nvram_path, "wb").close()
                        os.chmod(new_nvram_path, 0o600)
                        nvram_elem.text = new_nvram_path

            # Также проверяем loader element
            loader_elem = root.find(".//os/loader")
            if loader_elem is not None:
                # Обновляем nvram путь в loader элементе, если есть
                if nvram_elem is None and loader_elem.get("type") == "pflash":
                    # Создаем новый nvram элемент
                    os_elem = root.find(".//os")
                    if os_elem is not None:
                        new_nvram_elem = ElementTree.SubElement(os_elem, "nvram")
                        new_nvram_path = (
                            f"/var/lib/libvirt/qemu/nvram/{new_name}_VARS.fd"
                        )
                        new_nvram_elem.text = new_nvram_path

                        # Создаем пустой файл NVRAM
                        try:
                            open(new_nvram_path, "wb").close()
                            os.chmod(new_nvram_path, 0o600)
                        except Exception as e:
                            self.logger.warning(f"Не удалось создать NVRAM файл: {e}")

            # Клонируем диски (существующий код)
            for disk in root.findall(".//disk"):
                source_elem = disk.find("source")
                if source_elem is not None and "file" in source_elem.attrib:
                    old_path = source_elem.get("file")
                    if old_path:
                        dir_name = os.path.dirname(old_path)
                        base_name = os.path.basename(old_path)
                        new_path = os.path.join(dir_name, f"{new_name}_{base_name}")

                        if old_path.lower().endswith(".iso"):
                            shutil.copy2(old_path, new_path)
                        else:
                            disk_format = self.config.disk_format_by_path(new_path)
                            disk_name = base_name.replace(f".{disk_format.value}", "")
                            path = old_path.replace(f"/{base_name}", "")
                            new_path = str(
                                Path(path) / f"{new_name}.{disk_format.value}"
                            )
                            clone_disk_info = self.storage_manager.clone_disk(
                                disk_name, path, disk_format, new_name
                            )
                            if clone_disk_info.code == CommandMessagesEnum.disk_clone_error.name:
                                return clone_disk_info
                        source_elem.set("file", new_path)

            # Применяем изменения
            new_xml = ElementTree.tostring(root, encoding="unicode")
            self.conn.defineXML(new_xml)

            # Синхронизируем с NFS
            self.ha_controller.sync_nfs_vm_configs()

            return VmMessage(
                code=CommandMessagesEnum.vm_successfully_cloned.name,
                success=True,
            )

        except Exception as e:
            self.logger.error(str(e))
            return VmMessage(
                code=CommandMessagesEnum.vm_clone_error.name,
                success=False,
            )


if __name__ == "__main__":
    # Пример создания ВМ с использованием нового API

    # Инициализация менеджера
    with VmManager() as vm_manager:
        # print(vm_manager.delete_vm("test-vm-03"))
        # Пример создания ВМ /var/lib/libvirt/images/disk-859480.qcow2
        # result = vm_manager.create_vm(simple_hotplug_vm_config)
        # pprint.pprint(result.model_dump(), indent=2, width=100, sort_dicts=False)
        #
        # # Пример использования шаблона
        # template_result = vm_manager.create_vm_from_template(
        #     "ubuntu-server",
        #     "new-ubuntu-vm",
        #     memory_mb=4096,install_method
        #     vcpus=4
        # )
        # print(json.dumps(template_result, indent=2, ensure_ascii=False))

        # Получение списка ВМ
        # vm_manager.start_vm("test-vm-03")
        # vm_manager.shutdown_vm("test-hotplug-vm-2", force=True)
        # vm_manager.start_vm("TEST-VM_66323")
        # vm_manager.delete_vm_with_force("test-hotplug-vm-2")
        vms = vm_manager.list_vms().vm_info
        print(f"Найдено ВМ: {len(vms.items)}")
        # vm_manager.delete_vm_with_force("VM-TEST-20873")
        for vm in vms.items:
            # vm_manager.start_vm(vm.name)
            # vm_manager.shutoff_vm(vm.name, True)
            # if vm.state.value == VMState.SHUTOFF.value:
            if vm.name != "VM-TEST-11049":
                vm_manager.delete_vm_with_force(vm.name)
            print(
                f"  - {vm.name}: {vm.state}, {vm.memory} KB RAM, {vm.vcpus} vCPUs, UUID: {vm.uuid}, NET_ID: {vm.net_id}, HOST_FORWARD: {vm.hostfwd}"
            )
