import os
import shutil
import subprocess
import tempfile
import time
import uuid
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from pathlib import Path

import libvirt
from libvirt import VIR_DOMAIN_UNDEFINE_MANAGED_SAVE, VIR_DOMAIN_UNDEFINE_NVRAM

from agent.client.cli import CLIControl
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.config import LibvirtConfig
from agent.client.hypervisor.libvirt.managers.storage_manager import StorageManager
from agent.client.hypervisor.libvirt.models.volume.disk import (
    BusType,
    Disk,
    DiskAttach,
    DiskCreate,
)
from agent.client.hypervisor.libvirt.models.volume.disk import (
    DiskFormat as StorageDiskFormat,
)
from agent.client.hypervisor.libvirt.models.enum import (
    DiskFormat,
    DiskType,
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
)
from agent.client.logger_config import DefaultLogger


class VmManager(LibvirtClient):
    """
    Управление виртуальными машинами с использованием virt-install
    """

    libvirtError = None

    def __init__(self):
        self.cli = CLIControl()
        self.config = LibvirtConfig()
        self.logger = DefaultLogger("VmManager")
        super().__init__()
        self.storage_manager = StorageManager()
        self.storage_manager.connect()

    def create_vm(
        self, config: VMCreateRequest, dry_run: bool = False
    ) -> dict | VmError | VmMessage:
        """
        Создание виртуальной машины через virt-install


        U.P.D - Порядок загрузки дисков происходит в соответствии с их порядком в переданном списке

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
                            request_id=config.request_id,
                            success=False,
                            message=f"ISO файл не найден: {config.cdrom}",
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
                            request_id=config.request_id,
                            success=False,
                            message="Нельзя одновременно указывать cdrom и location",
                            code="CDROM_AND_LOCATION_CONFLICT",
                        )

            existing_vm = self.get_vm_by_name(config.name, config.request_id)
            if existing_vm.message == CommandMessagesEnum.vm_successfully_found.value:
                return VmError(
                    message=CommandMessagesEnum.vm_with_name_already_exists.value.format(
                        config.name
                    ),
                    code=CommandMessagesEnum.vm_with_name_already_exists.name,
                    request_id=config.request_id,
                )

            # Создаем диски через StorageManager
            try:
                for i, disk in enumerate(config.disks):
                    # Если диск существует, проверяем его
                    if disk.path and os.path.exists(disk.path):
                        self.logger.info(
                            f"Диск {disk.path} уже существует, используем существующий"
                        )
                        disk.format = self.config.disk_format_by_path(disk.path)
                        continue

                    # Создаем новый диск через StorageManager
                    disk_name = f"{config.name}-disk-{i + 1}"
                    if disk.path:
                        disk_name = Path(disk.path).stem

                    # Определяем формат для StorageManager
                    storage_format = StorageDiskFormat.QCOW2
                    if disk.format == DiskFormat.RAW:
                        storage_format = StorageDiskFormat.RAW
                    elif disk.format == DiskFormat.QCOW2:
                        storage_format = StorageDiskFormat.QCOW2

                    # Создаем диск
                    disk_create = DiskCreate(
                        name=disk_name,
                        size_gb=disk.size_gb or 1,
                        disk_type=disk.disk_type,
                        bus_type=disk.bus_type,
                        description=disk.description,
                        pool=disk.pool,
                        format=storage_format,
                        path=disk.path or None,
                        sparse=True,
                    )

                    self.logger.info(
                        f"Создание диска через StorageManager: {disk_create.name}"
                    )
                    result = self.storage_manager.create_disk(
                        disk_create, config.request_id
                    )

                    if hasattr(result, "disk_info") and result.disk_info:
                        # Обновляем путь диска в конфигурации
                        disk.path = result.disk_info.path
                        all_disks.append(result.disk_info.path)
                        self.logger.info(f"Диск создан: {result.disk_info.path}")
                    else:
                        self.logger.error(f"Ошибка создания диска: {result}")
                        # Откатываем созданные диски
                        for created_disk_path in all_disks:
                            try:
                                self.storage_manager.delete_disk(path=created_disk_path)
                            except Exception as e:
                                self.logger.error(
                                    f"Ошибка при откате диска {created_disk_path}: {e}"
                                )
                        return VmMessage(
                            request_id=config.request_id,
                            success=False,
                            message=f"Ошибка создания диска: {result.message if hasattr(result, 'message') else 'Unknown error'}",
                            code="DISK_CREATION_FAILED",
                        )
            except Exception as e:
                self.logger.exception(f"Ошибка при создании дисков: {e}")
                # Откатываем созданные диски
                for created_disk_path in all_disks:
                    try:
                        self.storage_manager.delete_disk(path=created_disk_path)
                    except Exception as e:
                        self.logger.error(
                            f"Ошибка при откате диска {created_disk_path}: {e}"
                        )
                return VmMessage(
                    request_id=config.request_id,
                    success=False,
                    message=f"Ошибка при создании дисков: {str(e)}",
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

                vm_info = self.get_vm_by_name(config.name, config.request_id)

                if vm_info:
                    self.logger.info(f"ВМ '{config.name}' создана успешно")
                    if config.autostart:
                        self._set_autostart(config.name, True)

                    return VmMessage(
                        request_id=config.request_id,
                        success=True,
                        message=CommandMessagesEnum.vm_successfully_created.value,
                        code=CommandMessagesEnum.vm_successfully_created.name,
                        command=command,
                        vm_info=vm_info.vm_info,
                        stdout=result.stdout,
                        stderr=result.stderr,
                    )
                else:
                    self.logger.error("ВМ создана, но не найдена в libvirt")
                    return VmMessage(
                        request_id=config.request_id,
                        success=False,
                        message=CommandMessagesEnum.vm_created_but_not_found_in_libvirt.value,
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
                        vm_info = self.get_vm_by_name(config.name, config.request_id)

                        if vm_info:
                            self.logger.info(
                                f"ВМ '{config.name}' создана успешно с флагом --import"
                            )

                            if config.autostart:
                                self._set_autostart(config.name, True)

                            return VmMessage(
                                request_id=config.request_id,
                                success=True,
                                message=CommandMessagesEnum.vm_successfully_created.value,
                                code=CommandMessagesEnum.vm_successfully_created.name,
                                command=import_command,
                                vm_info=vm_info.vm_info,
                                stdout=result.stdout,
                                stderr=result.stderr,
                                note="Использован флаг --import для создания пустой ВМ",
                            )
                        else:
                            return VmMessage(
                                request_id=config.request_id,
                                success=False,
                                message=CommandMessagesEnum.vm_created_but_not_found_in_libvirt.value,
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
                            request_id=config.request_id,
                            success=False,
                            message=CommandMessagesEnum.vm_create_error.value,
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
                        request_id=config.request_id,
                        success=False,
                        message=CommandMessagesEnum.vm_create_error.value,
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
                    self.storage_manager.delete_disk(path=created_disk_path)
                except Exception as e:
                    self.logger.error(
                        f"Ошибка при откате диска {created_disk_path}: {e}"
                    )
            return VmMessage(
                request_id=config.request_id,
                success=False,
                message=CommandMessagesEnum.vm_create_subprocess_timeout_error.value,
                code=CommandMessagesEnum.vm_create_subprocess_timeout_error.name,
                command=command if "command" in locals() else None,
            )
        except Exception as e:
            error_msg = f"Неожиданная ошибка при создании ВМ: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            # Откатываем созданные диски при исключении
            for created_disk_path in all_disks:
                try:
                    self.storage_manager.delete_disk(path=created_disk_path)
                except Exception as e:
                    self.logger.error(
                        f"Ошибка при откате диска {created_disk_path}: {e}"
                    )
            return VmMessage(
                request_id=config.request_id,
                success=False,
                message=CommandMessagesEnum.vm_create_unexpected_error.value,
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

        cmd_parts.extend(["--memory", str(config.memory_mb)])

        if config.current_memory_mb and config.current_memory_mb != config.memory_mb:
            cmd_parts.extend(["--current-memory", str(config.current_memory_mb)])

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

            if disk.path:
                disk_path = Path(disk.path)
                if disk_path.exists():
                    if disk.disk_type.value == DiskType.CDROM.value:
                        disk_params.append(f"--cdrom {disk.path}")
                    else:
                        print("БЛЯЯЯЯ МЫ ТУТ")
                        disk_params.append(f"path={disk.path}")
                        disk_params.append(f"format={disk.format.value}")
                else:
                    if disk.size_gb:
                        disk_params.append(f"size={disk.size_gb}")
                    if disk.format:
                        print("БЛЯЯЯЯ МЫ ТУТ 222222222222")
                        disk_params.append(f"format={disk.format.value}")
                    disk_params.append(f"path={disk.path}")
            else:
                if disk.size_gb:
                    disk_params.append(f"size={disk.size_gb}")
                if disk.format:
                    print("БЛЯЯЯЯ МЫ ТУТ 3333333333333333")
                    disk_params.append(f"format={disk.format.value}")
            if disk.bus_type:
                disk_params.append(f"bus={disk.bus_type.value}")

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

        cmd_parts.extend(["--video", config.video_model])

        if config.console_type:
            cmd_parts.extend(["--console", f"{config.console_type}"])

        if config.boot_devices:
            boot_cmd = "--boot "

            for i, device in enumerate(config.boot_devices):
                boot_params.append(device)

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

        cmd_parts.append(
            '--qemu-commandline="-netdev user,id=net0,ipv4=on,ipv6=off,dns=8.8.8.8,hostfwd=tcp::2222-:22"'
        )

        return " ".join(cmd_parts)

    def attach_iso_to_vm(
        self, vm_name: str, iso_path: str, bus_type: str = "ide", target_dev: str = None
    ) -> VmMessage:
        """
        Подключить ISO образ к существующей ВМ

        Args:
            vm_name: Имя ВМ
            iso_path: Путь к ISO файлу
            bus_type: Тип шины (ide, sata, scsi)
            target_dev: Целевое устройство (hdX, sdX и т.д.)

        Returns:
            Результат операции
        """
        request_id = str(uuid.uuid4())

        try:
            # Проверяем существование ВМ
            vm_info = self.get_vm_by_name(vm_name, request_id)
            if not vm_info.success:
                return vm_info

            # Проверяем существование ISO файла
            if not os.path.exists(iso_path):
                return VmMessage(
                    request_id=request_id,
                    success=False,
                    message=f"ISO файл не найден: {iso_path}",
                    code="ISO_FILE_NOT_FOUND",
                )

            # Преобразуем строковый bus_type в enum
            bus_type_enum = BusType.IDE
            if bus_type.lower() == "sata":
                bus_type_enum = BusType.SATA
            elif bus_type.lower() == "scsi":
                bus_type_enum = BusType.SCSI
            elif bus_type.lower() == "virtio":
                bus_type_enum = BusType.VIRTIO

            disk_attach = DiskAttach(
                vm_name=vm_name,
                path=iso_path,
                target_dev=target_dev or self._get_free_cdrom_device(vm_name),
                bus_type=bus_type_enum,
                cache_mode="none",
            )

            # Подключаем диск через StorageManager
            result = self.storage_manager.attach_disk(disk_attach, request_id)

            if hasattr(result, "success") and result.success:
                return VmMessage(
                    request_id=request_id,
                    success=True,
                    message=f"ISO успешно подключен к ВМ {vm_name}",
                    code="ISO_ATTACH_SUCCESS",
                )
            else:
                return VmMessage(
                    request_id=request_id,
                    success=False,
                    message=f"Ошибка подключения ISO: {result.message if hasattr(result, 'message') else 'Unknown error'}",
                    code="ISO_ATTACH_FAILED",
                )

        except Exception as e:
            self.logger.exception(f"Ошибка при подключении ISO к ВМ: {e}")
            return VmMessage(
                request_id=request_id,
                success=False,
                message=f"Ошибка при подключении ISO: {str(e)}",
                code="ISO_ATTACH_EXCEPTION",
            )

    def _get_free_cdrom_device(self, vm_name: str) -> str:
        """
        Получить свободное устройство CDROM для ВМ

        Args:
            vm_name: Имя ВМ

        Returns:
            Имя свободного устройства (hdc, hdd и т.д.)
        """
        try:
            vm = self.conn.lookupByName(vm_name)
            xml_desc = vm.XMLDesc()

            # Ищем используемые CDROM устройства
            used_devices = set()
            root = ET.fromstring(xml_desc)

            for disk in root.findall(".//disk"):
                if disk.get("device") == "cdrom":
                    target = disk.find("target")
                    if target is not None:
                        used_devices.add(target.get("dev"))

            # Для IDE устройств (hdX)
            for letter in ["c", "d", "e", "f", "g", "h"]:
                device = f"hd{letter}"
                if device not in used_devices:
                    return device

            # Если все заняты, используем следующий доступный
            return "hdi"

        except Exception as e:
            self.logger.error(f"Ошибка при поиске свободного CDROM устройства: {e}")
            return "hdc"

    def detach_iso_from_vm(self, vm_name: str, target_dev: str) -> VmMessage:
        """
        Отключить ISO образ от ВМ

        Args:
            vm_name: Имя ВМ
            target_dev: Целевое устройство для отключения

        Returns:
            Результат операции
        """
        request_id = str(uuid.uuid4())

        try:
            from agent.client.hypervisor.libvirt.models.volume.disk import DiskDetach

            disk_detach = DiskDetach(vm_name=vm_name, target_dev=target_dev)

            # Отключаем диск через StorageManager
            result = self.storage_manager.detach_disk(disk_detach)

            if result:
                return VmMessage(
                    request_id=request_id,
                    success=True,
                    message=f"ISO успешно отключен от ВМ {vm_name}",
                    code="ISO_DETACH_SUCCESS",
                )
            else:
                return VmMessage(
                    request_id=request_id,
                    success=False,
                    message="Ошибка отключения ISO",
                    code="ISO_DETACH_FAILED",
                )

        except Exception as e:
            self.logger.exception(f"Ошибка при отключении ISO от ВМ: {e}")
            return VmMessage(
                request_id=request_id,
                success=False,
                message=f"Ошибка при отключении ISO: {str(e)}",
                code="ISO_DETACH_EXCEPTION",
            )

    def list_vm_disks(self, vm_name: str) -> list[Disk]:
        """
        Получить список всех дисков ВМ (включая ISO)

        Args:
            vm_name: Имя ВМ

        Returns:
            Список дисков ВМ
        """
        request_id = str(uuid.uuid4())

        try:
            # Используем StorageManager для получения дисков ВМ
            disks = self.storage_manager.get_disks_by_vm(vm_name, request_id)
            return disks

        except Exception as e:
            self.logger.exception(f"Ошибка при получении дисков ВМ: {e}")
            return []

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

    def _set_autostart(self, vm_name: str, enabled: bool) -> bool:
        """
        Включение/выключение автостарта ВМ

        Args:
            vm_name: Имя ВМ
            enabled: Включить автостарт

        Returns:
            Успех операции
        """
        try:
            domain = self.conn.lookupByName(vm_name)
            domain.setAutostart(1 if enabled else 0)
            self.logger.info(f"Автостарт для ВМ '{vm_name}' установлен в {enabled}")
            return True
        except self.libvirtError as e:
            self.logger.error(
                f"Ошибка установки автостарта для ВМ '{vm_name}', \nerr: {e}"
            )
            return False

    # _______________________________________________Редактирование ВМ________

    def edit_vm(
        self, vm_name: str, vm_update: VmUpdateRequest, request_id: str
    ) -> VmMessage:
        try:
            self.logger.info(f"Редактирование свойств ВМ {vm_name}")

            # Получаем домен
            vm = self.conn.lookupByName(vm_name)
            state, _ = vm.state()
            is_running = state == libvirt.VIR_DOMAIN_RUNNING

            self.logger.info(
                f"Состояние ВМ: {'запущена' if is_running else 'остановлена'}"
            )

            # Получаем текущую XML конфигурацию
            xml_desc = vm.XMLDesc(0)
            self.logger.debug(f"Текущий XML: {xml_desc[:500]}...")

            # Парсим XML
            root = ET.fromstring(xml_desc)
            modified = False

            # Изменение vCPU
            if vm_update.vcpus is not None:
                self.logger.info(f"Изменение vCPU на {vm_update.vcpus}")

                # Находим или создаем элемент vcpu
                vcpu_elem = root.find("vcpu")
                if vcpu_elem is None:
                    vcpu_elem = ET.SubElement(root, "vcpu")

                # Устанавливаем значение
                vcpu_elem.text = str(vm_update.vcpus)
                vcpu_elem.set("current", str(vm_update.vcpus))

                # Обновляем элемент cpu для топологии
                cpu_elem = root.find("cpu")
                if cpu_elem is not None:
                    # Обновляем топологию CPU
                    topology = cpu_elem.find("topology")
                    if topology is None:
                        topology = ET.SubElement(cpu_elem, "topology")

                    # Устанавливаем простую топологию: sockets = vcpus, cores = 1, threads
                    # = 1
                    topology.set("sockets", str(vm_update.vcpus))
                    topology.set("cores", "1")
                    topology.set("threads", "1")

                modified = True

            # Изменение памяти
            if vm_update.memory_mb is not None:
                self.logger.info(f"Изменение памяти на {vm_update.memory_mb} MB")

                # Преобразуем MB в KB (libvirt работает с KB)
                memory_kb = vm_update.memory_mb * 1024

                # Находим или создаем элемент memory
                memory_elem = root.find("memory")
                if memory_elem is None:
                    memory_elem = ET.SubElement(root, "memory")

                # Устанавливаем значение
                memory_elem.text = str(memory_kb)
                memory_elem.set("unit", "KiB")

                # Обновляем currentMemory если есть
                current_elem = root.find("currentMemory")
                if current_elem is None:
                    current_elem = ET.SubElement(root, "currentMemory")

                current_elem.text = str(memory_kb)
                current_elem.set("unit", "KiB")

                modified = True

            # Изменение max vCPU
            if vm_update.max_vcpus is not None:
                self.logger.info(f"Изменение max vCPU на {vm_update.max_vcpus}")

                vcpu_elem = root.find("vcpu")
                if vcpu_elem is None:
                    vcpu_elem = ET.SubElement(root, "vcpu")

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
                new_xml = ET.tostring(root, encoding="unicode", method="xml")
                self.logger.debug(f"Новый XML: {new_xml[:500]}...")

                # Сохраняем во временный файл
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".xml", delete=False
                ) as tmp_file:
                    tmp_file.write(new_xml)
                    tmp_file_path = tmp_file.name

                try:
                    if not is_running:
                        self.conn.defineXML(new_xml)
                        self.logger.info("Конфигурация ВМ обновлена (остановлена)")
                    else:
                        try:
                            # Пытаемся обновить с флагом --live
                            cmd = ["virsh", "define", tmp_file_path]
                            result = subprocess.run(
                                cmd, capture_output=True, text=True, timeout=30
                            )

                            if result.returncode != 0:
                                self.logger.warning(
                                    f"Не удалось обновить на лету: {result.stderr}"
                                )
                                # Возможно, потребуется перезагрузка
                        except Exception as e:
                            self.logger.warning(f"Ошибка при обновлении на лету: {e}")

                    self.logger.info(f"Конфигурация ВМ {vm_name} обновлена")

                finally:
                    # Удаляем временный файл
                    if os.path.exists(tmp_file_path):
                        os.unlink(tmp_file_path)

                # Если ВМ запущена и мы изменили vCPU или память, применяем изменения на
                # лету
                if is_running:
                    try:
                        if vm_update.vcpus is not None:
                            # Пытаемся изменить vCPU на лету
                            flags = libvirt.VIR_DOMAIN_VCPU_LIVE
                            vm.setVcpusFlags(vm_update.vcpus, flags)
                            self.logger.info(
                                f"vCPU изменено на лету на {vm_update.vcpus}"
                            )

                        if vm_update.memory_mb is not None:
                            # Пытаемся изменить память на лету
                            memory_kb = vm_update.memory_mb * 1024
                            flags = libvirt.VIR_DOMAIN_MEM_LIVE
                            vm.setMemoryFlags(memory_kb, flags)
                            self.logger.info(
                                f"Память изменена на лету на {vm_update.memory_mb} MB"
                            )
                    except Exception as e:
                        self.logger.warning(
                            f"Не удалось применить изменения на лету: {e}"
                        )
                        self.logger.info(
                            "Для полного применения изменений может потребоваться перезагрузка ВМ"
                        )

            else:
                self.logger.info("Нет изменений для применения")

            # Перечитываем домен после изменений
            vm = self.conn.lookupByName(vm_name)

            # Проверяем, что изменения применились
            if vm_update.vcpus is not None:
                # Получаем обновленную информацию
                new_xml = vm.XMLDesc(0)
                new_root = ET.fromstring(new_xml)
                new_vcpu_elem = new_root.find("vcpu")

                if new_vcpu_elem is not None:
                    actual_vcpus = new_vcpu_elem.text
                    self.logger.info(
                        f"Фактическое количество vCPU после изменения: {actual_vcpus}"
                    )

                    if actual_vcpus != str(vm_update.vcpus):
                        self.logger.warning(
                            f"vCPU не изменилось: ожидалось {vm_update.vcpus}, получено {actual_vcpus}"
                        )

            self.logger.info(f"ВМ {vm_name} успешно обновлена")
            return VmMessage(
                request_id=request_id,
                success=True,
                message=CommandMessagesEnum.vm_edit_success.value,
                code=CommandMessagesEnum.vm_edit_success.name,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка при редактировании ВМ {vm_name}: {e}")
            return VmMessage(
                request_id=request_id,
                success=False,
                message=CommandMessagesEnum.vm_edit_error.value,
                code=CommandMessagesEnum.vm_edit_error.name,
                note=str(e),
            )
        except Exception as e:
            self.logger.exception(f"Неожиданная ошибка при редактировании ВМ: {e}")
            return VmMessage(
                request_id=request_id,
                success=False,
                message=CommandMessagesEnum.vm_edit_unexpected_error.value,
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
            vm = self.conn.lookupByName(vm_name)
            current_xml = vm.XMLDesc()
            root = ET.fromstring(current_xml)

            self._modify_xml(root, vm_update)
            new_xml = ET.tostring(root, encoding="unicode")

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

    def _modify_xml(self, root: ET.Element, vm_update: VmUpdateRequest):
        devices_elem = root.find("./devices")
        if devices_elem is None:
            devices_elem = ET.SubElement(root, "devices")

        if vm_update.cpu_model is not None or vm_update.cpu_features is not None:
            cpu_elem = root.find("./cpu")
            if cpu_elem is None:
                cpu_elem = ET.SubElement(root, "cpu")
                cpu_elem.set("mode", "custom")
                cpu_elem.set("match", "exact")

            if vm_update.cpu_model is not None:
                model_elem = cpu_elem.find("./model")
                if model_elem is None:
                    model_elem = ET.SubElement(cpu_elem, "model")
                    model_elem.set("fallback", "allow")
                model_elem.text = vm_update.cpu_model

            if vm_update.cpu_features is not None:
                for feature in cpu_elem.findall("./feature"):
                    cpu_elem.remove(feature)
                for feature_name in vm_update.cpu_features:
                    feature_elem = ET.SubElement(cpu_elem, "feature")
                    feature_elem.set("policy", "require")
                    feature_elem.set("name", feature_name)

        if vm_update.graphics is not None:
            for graphics in devices_elem.findall("./graphics"):
                devices_elem.remove(graphics)

            graphics_elem = ET.SubElement(devices_elem, "graphics")
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

            video_elem = ET.SubElement(devices_elem, "video")
            model_elem = ET.SubElement(video_elem, "model")
            model_elem.set("type", vm_update.video_model)

        if vm_update.machine_type is not None:
            os_elem = root.find("./os")
            if os_elem is not None:
                type_elem = os_elem.find("./type")
                if type_elem is None:
                    type_elem = ET.SubElement(os_elem, "type")
                    type_elem.set("arch", "x86_64")
                    type_elem.text = "hvm"
                type_elem.set("machine", vm_update.machine_type)

        if vm_update.os_variant is not None:
            os_elem = root.find("./os")
            if os_elem is not None:
                variant_elem = os_elem.find("./variant")
                if variant_elem is None:
                    variant_elem = ET.SubElement(os_elem, "variant")
                variant_elem.text = vm_update.os_variant

        if vm_update.boot_devices is not None:
            os_elem = root.find("./os")
            if os_elem is None:
                os_elem = ET.SubElement(root, "os")
                type_elem = ET.SubElement(os_elem, "type")
                type_elem.set("arch", "x86_64")
                type_elem.text = "hvm"

            for boot in os_elem.findall("./boot"):
                os_elem.remove(boot)

            for device in vm_update.boot_devices:
                boot_elem = ET.SubElement(os_elem, "boot")
                boot_elem.set("dev", device)

        if vm_update.features is not None:
            features_elem = root.find("./features")
            if features_elem is None:
                features_elem = ET.SubElement(root, "features")

            for feature in features_elem:
                features_elem.remove(feature)

            for feature_name, feature_value in vm_update.features.items():
                feature_elem = ET.SubElement(features_elem, feature_name)
                feature_elem.set("state", feature_value)

        if vm_update.memballoon_model is not None:
            for memballoon in devices_elem.findall("./memballoon"):
                devices_elem.remove(memballoon)

            memballoon_elem = ET.SubElement(devices_elem, "memballoon")
            memballoon_elem.set("model", vm_update.memballoon_model)

        if vm_update.hyperv_features is not None:
            features_elem = root.find("./features")
            if features_elem is None:
                features_elem = ET.SubElement(root, "features")

            hyperv_elem = features_elem.find("./hyperv")
            if hyperv_elem is not None:
                features_elem.remove(hyperv_elem)

            hyperv_elem = ET.SubElement(features_elem, "hyperv")

            for feature_name, feature_value in vm_update.hyperv_features.items():
                if feature_name == "relaxed":
                    relaxed_elem = ET.SubElement(hyperv_elem, "relaxed")
                    relaxed_elem.set("state", feature_value)
                elif feature_name == "vapic":
                    vapic_elem = ET.SubElement(hyperv_elem, "vapic")
                    vapic_elem.set("state", feature_value)
                elif feature_name == "spinlocks":
                    spinlocks_elem = ET.SubElement(hyperv_elem, "spinlocks")
                    spinlocks_elem.set("state", feature_value)

        if vm_update.qemu_agent is not None:
            for channel in devices_elem.findall("./channel"):
                target = channel.find("./target")
                if target is not None and target.get("type") == "virtio":
                    devices_elem.remove(channel)

            if vm_update.qemu_agent:
                channel_elem = ET.SubElement(devices_elem, "channel")
                channel_elem.set("type", "unix")
                source_elem = ET.SubElement(channel_elem, "source")
                source_elem.set("mode", "bind")
                target_elem = ET.SubElement(channel_elem, "target")
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

    def list_vms(self, only_active: bool = False) -> list[VirtualMachine]:
        """
        Получение списка виртуальных машин

        Args:
            only_active: только активные ВМ

        Returns:
            Список информации о ВМ
        """
        if not self.conn:
            raise ConnectionError("Сначала подключитесь к гипервизору")

        vms = []
        try:
            if only_active:
                domain_ids = self.conn.listDomainsID()
                for domain_id in domain_ids:
                    domain = self.conn.lookupByID(domain_id)
                    vms.append(self.get_vm_info(domain))
            else:
                domains = self.conn.listAllDomains(0)
                print("domains: ", domains)
                for domain in domains:
                    vms.append(self.get_vm_info(domain))

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения списка ВМ, \nerr: {e}")

        return vms

    def get_vm_info(self, domain, display_logs: bool = True) -> VirtualMachine | None:
        """Получение информации о виртуальной машине"""
        try:
            info = domain.info()
            state = VMState(info[0])
            if display_logs:
                self.logger.info(f"ВМ {domain} найдена")
            return VirtualMachine(
                name=domain.name(),
                state=state,
                id=domain.ID() if domain.ID() != -1 else -1,
                uuid=domain.UUIDString(),
                vcpus=info[3],
                memory=info[2],
                max_memory=info[1],
                cpu_time=info[4],
            )
        except self.libvirtError as e:
            if display_logs:
                self.logger.error(f"Ошибка получения информации о ВМ, \nerr: {e}")
            raise

    def get_vm_state_by_name(self, name: str, display_logs: bool = False) -> int | bool:
        """Получение состояния ВМ по имени"""
        try:
            virtual_machine = self.conn.lookupByName(name)
            if display_logs:
                self.logger.info(f"Поиск ВМ {name}")
            return self.get_vm_info(virtual_machine, display_logs).state.value
        except self.libvirtError:
            if display_logs:
                self.logger.info(f"ВМ {name} не найдена")
            return False

    def get_vm_by_name(self, name: str, request_id: str) -> VmMessage:
        """Получение ВМ по имени"""
        try:
            virtual_machine = self.conn.lookupByName(name)
            self.logger.info(f"Поиск ВМ {name}")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_successfully_found.value,
                code=CommandMessagesEnum.vm_successfully_found.name,
                vm_info=self.get_vm_info(virtual_machine),
                success=True,
            )
        except self.libvirtError as e:
            self.logger.info(f"ВМ {name} не найдена")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_found_error.value,
                code=CommandMessagesEnum.vm_found_error.name,
                success=False,
                note=str(e),
            )

    def start_vm(self, name: str, request_id: str) -> VmMessage:
        """Запуск виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.create() == 0:
                self.logger.info(f"ВМ {name} запущена")
                return VmMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.vm_successfully_started.value,
                    code=CommandMessagesEnum.vm_successfully_started.name,
                    success=True,
                )
            self.logger.info(f"ВМ {name} не запустилась")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_start_error.value,
                code=CommandMessagesEnum.vm_start_error.name,
                success=False,
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка запуска ВМ {name}, \nerr: {e}")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_start_error.value,
                code=CommandMessagesEnum.vm_start_error.name,
                success=False,
                note=str(e),
            )

    def shutoff_vm(self, name: str, request_id: str, force: bool = False) -> VmMessage:
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
                    request_id=request_id,
                    message=CommandMessagesEnum.vm_successfully_shutdowned.value,
                    code=CommandMessagesEnum.vm_successfully_shutdowned.name,
                    success=True,
                )
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_shutdown_error.value,
                code=CommandMessagesEnum.vm_shutdown_error.name,
                success=False,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка выключения ВМ {name}, \nerr: {e}")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_shutdown_error.value,
                code=CommandMessagesEnum.vm_shutdown_error.name,
                success=False,
                note=str(e),
            )

    def reboot_vm(
        self, name: str, request_id: str, hard_reset: bool = False
    ) -> VmMessage:
        """Перезагрузка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if hard_reset:
                domain.reset()
                self.logger.info(f"Выполнена жесткая перезагрузка для ВМ {name}")
                return VmMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.vm_successfully_restarted.value,
                    code=CommandMessagesEnum.vm_successfully_restarted.name,
                    success=True,
                )
            if domain.reboot(0) == 0:
                self.logger.info(f"ВМ {name} перезагружается")
                return VmMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.vm_successfully_restarted.value,
                    code=CommandMessagesEnum.vm_successfully_restarted.name,
                    success=True,
                )
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_restart_error.value,
                code=CommandMessagesEnum.vm_restart_error.name,
                success=False,
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка перезагрузки ВМ {name}, \nerr: {e}")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_restart_error.value,
                code=CommandMessagesEnum.vm_restart_error.name,
                success=False,
                note=str(e),
            )

    def suspend_vm(self, name: str, request_id: str) -> VmMessage:
        """Приостановка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.suspend() == 0:
                self.logger.info(f"ВМ {name} приостановлена")
                return VmMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.vm_successfully_stopped.value,
                    code=CommandMessagesEnum.vm_successfully_stopped.name,
                    success=True,
                )
            self.logger.info(f"ВМ {name} не приостановлена")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_stop_error.value,
                code=CommandMessagesEnum.vm_stop_error.name,
                success=False,
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка приостановки ВМ {name}, \nerr: {e}")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_stop_error.value,
                code=CommandMessagesEnum.vm_stop_error.name,
                success=False,
                note=str(e),
            )

    def resume_vm(self, name: str, request_id: str) -> VmMessage:
        """Возобновление работы виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.resume() == 0:
                self.logger.info(f"ВМ {name} возобновлена")
                return VmMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.vm_successfully_resumed.value,
                    code=CommandMessagesEnum.vm_successfully_resumed.name,
                    success=True,
                )
            self.logger.info(f"ВМ {name} не возобновлена")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_resume_error.value,
                code=CommandMessagesEnum.vm_resume_error.name,
                success=False,
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка возобновления ВМ {name}")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_resume_error.value,
                code=CommandMessagesEnum.vm_resume_error.name,
                success=False,
                note=str(e),
            )

    def delete_vm(
        self,
        name: str,
        request_id: str,
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
                            self.storage_manager.delete_disk(path=disk_path)
                            self.logger.info(
                                f"Диск удален через StorageManager: {disk_path}"
                            )
                    except OSError as e:
                        self.logger.error(
                            f"Не удалось удалить диск {disk_path}, \nerr: {e}"
                        )

            self.logger.info(f"ВМ {name} удалена")
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_successfully_deleted.value,
                code=CommandMessagesEnum.vm_successfully_deleted.name,
                success=True,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления ВМ {name}, \nerr: {e}")

            if "nvram" in str(e).lower():
                return self._delete_vm_with_nvram_fallback(
                    name, request_id, delete_disks
                )

            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_delete_error.value,
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
            root = ET.fromstring(xml_config)

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

    def _delete_vm_with_nvram_fallback(
        self, name: str, request_id: str, delete_disks: bool = False
    ) -> VmMessage:
        """
        Альтернативный метод удаления ВМ с NVRAM

        Args:
            name: Имя ВМ
            delete_disks: Удалять ли диски

        Returns:
            Успех операции
        """
        try:
            command = f"virsh undefine --nvram {name}"
            result = subprocess.run(command, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                self.logger.info(f"ВМ {name} удалена через virsh undefine --nvram")

                nvram_pattern = f"/var/lib/libvirt/qemu/nvram/{name}_*"
                import glob

                nvram_files = glob.glob(nvram_pattern)
                for nvram_file in nvram_files:
                    try:
                        os.remove(nvram_file)
                        self.logger.info(f"Удален файл NVRAM: {nvram_file}")
                    except OSError:
                        pass

                return VmMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.vm_successfully_deleted.value,
                    code=CommandMessagesEnum.vm_successfully_deleted.name,
                    success=True,
                )
            else:
                command = f"virsh undefine --remove-all-storage {name}"
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True
                )

                if result.returncode == 0:
                    self.logger.info(
                        f"ВМ {name} удалена через virsh undefine --remove-all-storage"
                    )
                    return VmMessage(
                        request_id=request_id,
                        message=CommandMessagesEnum.vm_successfully_deleted.value,
                        code=CommandMessagesEnum.vm_successfully_deleted.name,
                        success=True,
                    )
                else:
                    self.logger.error(
                        f"Не удалось удалить ВМ {name} даже через virsh: {result.stderr}"
                    )
                    return VmMessage(
                        request_id=request_id,
                        message=CommandMessagesEnum.vm_delete_error.value,
                        code=CommandMessagesEnum.vm_delete_error.name,
                        success=False,
                    )

        except Exception as e:
            self.logger.error(
                f"Ошибка в альтернативном методе удаления ВМ {name}, \nerr: {e}"
            )
            return VmMessage(
                request_id=request_id,
                message=CommandMessagesEnum.vm_delete_error.value,
                code=CommandMessagesEnum.vm_delete_error.name,
                success=False,
                note=str(e),
            )

    def get_vm_xml(self, name: str) -> str | None:
        """Получение XML конфигурации ВМ"""
        try:
            domain = self.conn.lookupByName(name)
            return domain.XMLDesc(0)
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения XML для ВМ {name}, \nerr: {e}")
            return None

    def delete_vm_with_force(
        self, name: str, request_id: str, delete_disks: bool = True
    ):
        """
        Вспомогательная функция для принудительного удаления ВМ
        Используйте эту функцию если обычное удаление не работает

        Args:
            name: Имя ВМ
            request_id: id запроса
            delete_disks: удалять ли диски ВМ
        """

        methods = [
            lambda: self.delete_vm(
                name,
                delete_disks=delete_disks,
                delete_nvram=True,
                request_id=request_id,
            ),
            lambda: self.delete_vm(
                name,
                delete_disks=delete_disks,
                delete_nvram=False,
                request_id=request_id,
            ),
            lambda: self._delete_vm_with_nvram_fallback(
                name, request_id, delete_disks=delete_disks
            ),
        ]

        for i, method in enumerate(methods, 1):
            print(f"Попытка {i} удаления ВМ {name}...")
            result = method()
            if result.success:
                print(f"ВМ {name} успешно удалена")
                return VmMessage(
                    request_id=request_id,
                    message=CommandMessagesEnum.vm_successfully_deleted.value,
                    code=CommandMessagesEnum.vm_successfully_deleted.name,
                    success=True,
                )

        print(f"Не удалось удалить ВМ {name}")
        return VmMessage(
            request_id=request_id,
            message=CommandMessagesEnum.vm_delete_error.value,
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
            root = ET.fromstring(xml_config)
            os_element = root.find(".//os")

            if os_element is not None:
                nvram_element = os_element.find("nvram")
                if nvram_element is not None:
                    return nvram_element.text

            loader_element = root.find('.//loader[@type="pflash"]')
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

    @staticmethod
    def _generate_uuid():
        return str(uuid.uuid4())

    def clone_vm(self, source_name: str, new_name: str, new_uuid: bool = True) -> dict:
        """
        Клонирование существующей ВМ

        Args:
            source_name: Имя исходной ВМ
            new_name: Имя новой ВМ
            new_uuid: Генерировать новый UUID

        Returns:
            Результат клонирования
        """
        try:
            source_domain = self.conn.lookupByName(source_name)
            xml_config = source_domain.XMLDesc(0)

            root = ET.fromstring(xml_config)

            name_elem = root.find("name")
            if name_elem is not None:
                name_elem.text = new_name

            if new_uuid:
                uuid_elem = root.find("uuid")
                if uuid_elem is not None:
                    uuid_elem.text = self._generate_uuid()

            for disk in root.findall(".//disk"):
                source_elem = disk.find("source")
                if source_elem is not None and "file" in source_elem.attrib:
                    old_path = source_elem.get("file")
                    if old_path:
                        dir_name = os.path.dirname(old_path)
                        base_name = os.path.basename(old_path)
                        new_path = os.path.join(dir_name, f"{new_name}_{base_name}")

                        # Используем StorageManager для клонирования диска
                        if old_path.lower().endswith(".iso"):
                            # Для ISO файлов просто копируем
                            shutil.copy2(old_path, new_path)
                        else:
                            # Для обычных дисков используем StorageManager
                            self.storage_manager.clone_disk(
                                old_path, new_path, new_name
                            )

                        source_elem.set("file", new_path)

            rough_string = ET.tostring(root, "utf-8")
            new_xml = minidom.parseString(rough_string).toprettyxml(indent="  ")

            new_domain = self.conn.defineXML(new_xml)

            return {
                "success": True,
                "message": f"ВМ '{source_name}' клонирована в '{new_name}'",
                "xml": new_xml,
                "domain_name": new_domain.name(),
            }

        except Exception as e:
            error_msg = f"Ошибка клонирования ВМ: {str(e)}"
            self.logger.error(error_msg)
            return {"success": False, "error": error_msg}


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
        vms = vm_manager.list_vms()
        print(f"Найдено ВМ: {len(vms)}")

        for vm in vms:
            # vm_manager.delete_vm_with_force(vm.name, str(uuid.uuid4()))
            print(
                f"  - {vm.name}: {vm.state}, {vm.memory} KB RAM, {vm.vcpus} vCPUs, UUID: {vm.uuid}"
            )
