import os
import pprint
import shutil
import subprocess
import json
import time
import uuid
from typing import Any
from pathlib import Path

from libvirt import VIR_DOMAIN_UNDEFINE_MANAGED_SAVE, VIR_DOMAIN_UNDEFINE_NVRAM

from agent.client.cli import CLIControl
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.config import LibvirtConfig
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.enum import DiskBus, DiskFormat, NetworkType, NetworkModel, OSType, \
    GraphicsType, ControllerType, Architecture
from agent.client.hypervisor.libvirt.models.network import VMNetwork
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.hypervisor.models.general import VMState
from agent.client.hypervisor.models.msg import VmError, CommandMessagesEnum, VmMessage
from agent.client.hypervisor.models.vm import VirtualMachine
from agent.client.hypervisor.templates.vm import simple_config, simple_config_without_net, simple_hotplug_vm_config
from agent.client.logger_config import DefaultLogger


class VmManager(LibvirtClient):
    """
    Управление виртуальными машинами с использованием virt-install
    """

    libvirtError = None

    def __init__(self, connection_uri: str = "qemu:///session", username: str | None = None, password: str | None = None):
        self.cli = CLIControl()
        self.config = LibvirtConfig()
        self.logger = DefaultLogger()
        super().__init__(connection_uri, username, password)

    def create_vm(self, config: VMCreateRequest, dry_run: bool = False) -> dict[str, Any] | VmError | VmMessage:
        """
        Создание виртуальной машины через virt-install

        Args:
            config: Конфигурация ВМ
            dry_run: Только проверить команду, не выполнять

        Returns:
            Словарь с результатом выполнения
        """
        try:
            self.logger.info(f"Запуск создания ВМ: {config.name}")

            existing_vm = self.get_vm_by_name(config.name, config.request_id)
            if existing_vm.message == CommandMessagesEnum.vm_successfully_found.value:
                return VmError(message=CommandMessagesEnum.vm_with_name_already_exists.value.format(config.name),
                               code=CommandMessagesEnum.vm_with_name_already_exists.name,
                               request_id=config.request_id)

            # Создаем директории для дисков если нужно
            for disk in config.disks:
                if disk.path is not None:
                    disk_path = Path(disk.path)
                    if not disk_path.exists() and disk_path.parent:
                        disk_path.parent.mkdir(parents=True, exist_ok=True)
                        self.logger.info(f"Создана директория: {disk_path.parent}")

            if not (config.cdrom or config.location):
                if config.disks:
                    main_disk = config.disks[0]
                    if main_disk.path is not None:
                        disk_path = Path(main_disk.path)
                        if disk_path.exists():
                            config.install_method = "import"
                    else:
                        self.logger.warning(
                            f"Диск {main_disk.path} не существует. Используем --import для создания пустой ВМ")

            command = self._build_virt_install_command(config)
            self.logger.info(f"Команда virt-install: {command}")

            if dry_run:
                return {
                    "success": True,
                    "message": "DRY RUN: команда сгенерирована успешно",
                    "command": command,
                    "vm_name": config.name
                }

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                time.sleep(2)

                vm_info = self.get_vm_by_name(config.name, config.request_id)

                if vm_info:
                    self.logger.info(f"ВМ '{config.name}' создана успешно")
                    if config.autostart:
                        self._set_autostart(config.name, True)

                    return VmMessage(request_id=config.request_id,
                                     success=True,
                                     message=CommandMessagesEnum.vm_successfully_created.value,
                                     code=CommandMessagesEnum.vm_successfully_created.name,
                                     command=command,
                                     vm_info=vm_info.vm_info,
                                     stdout=result.stdout,
                                     stderr=result.stderr)
                else:
                    self.logger.error(f"ВМ создана, но не найдена в libvirt")
                    return VmMessage(request_id=config.request_id,
                                     success=False,
                                     message=CommandMessagesEnum.vm_created_but_not_found_in_libvirt.value,
                                     code=CommandMessagesEnum.vm_created_but_not_found_in_libvirt.name,
                                     command=command,
                                     stdout=result.stdout,
                                     stderr=result.stderr)
            else:
                error_msg = result.stderr

                if "Необходимо определить метод установки" in error_msg or "install method must be specified" in error_msg.lower():
                    self.logger.warning("Обнаружена ошибка метода установки. Пробуем с флагом --import...")

                    import_command = command + " --import"
                    self.logger.info(f"Повторная попытка с командой: {import_command}")

                    import_result = subprocess.run(
                        import_command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )

                    if import_result.returncode == 0:
                        vm_info = self.get_vm_by_name(config.name, config.request_id)

                        if vm_info:
                            self.logger.info(f"ВМ '{config.name}' создана успешно с флагом --import")

                            if config.autostart:
                                self._set_autostart(config.name, True)

                            return VmMessage(request_id=config.request_id,
                                             success=True,
                                             message=CommandMessagesEnum.vm_successfully_created.value,
                                             code=CommandMessagesEnum.vm_successfully_created.name,
                                             command=import_command,
                                             vm_info=vm_info,
                                             stdout=result.stdout,
                                             stderr=result.stderr,
                                             note="Использован флаг --import для создания пустой ВМ"
                                             )
                        else:
                            return VmMessage(request_id=config.request_id,
                                             success=False,
                                             message=CommandMessagesEnum.vm_created_but_not_found_in_libvirt.value,
                                             code=CommandMessagesEnum.vm_created_but_not_found_in_libvirt.name,
                                             command=import_command,
                                             vm_info=vm_info,
                                             stdout=result.stdout,
                                             stderr=result.stderr,
                                             note="Использован флаг --import для создания пустой ВМ"
                                             )
                    else:
                        self.logger.error(f"Ошибка создания ВМ: {result.stderr}")
                        return VmMessage(request_id=config.request_id,
                                         success=False,
                                         message=CommandMessagesEnum.vm_create_error.value,
                                         code=CommandMessagesEnum.vm_create_error.name,
                                         command=import_command,
                                         stdout=result.stdout,
                                         stderr=result.stderr,
                                         note="Использован флаг --import для создания пустой ВМ"
                                         )
                else:
                    error_msg = f"Ошибка создания ВМ: {result.stderr}"
                    self.logger.error(error_msg)
                    return VmMessage(request_id=config.request_id,
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
            return VmMessage(request_id=config.request_id,
                             success=False,
                             message=CommandMessagesEnum.vm_create_subprocess_timeout_error.value,
                             code=CommandMessagesEnum.vm_create_subprocess_timeout_error.name,
                             command=command if "command" in locals() else None,
                             )
        except Exception as e:
            error_msg = f"Неожиданная ошибка при создании ВМ: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return VmMessage(request_id=config.request_id,
                             success=False,
                             message=CommandMessagesEnum.vm_create_unexpected_error.value,
                             code=CommandMessagesEnum.vm_create_unexpected_error.name,
                             command=command if "command" in locals() else None
                             )

    def _build_virt_install_command(self, config: VMCreateRequest) -> str:
        """
        Построение команды virt-install из конфигурации

        Args:
            config: Конфигурация ВМ

        Returns:
            Строка команды для выполнения
        """
        cmd_parts = ["virt-install"]

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

        cmd_parts.extend(["--vcpus", str(config.vcpus)])

        if config.max_vcpus and config.max_vcpus != config.vcpus:
            cmd_parts.extend(["--vcpus", f"{config.vcpus},maxvcpus={config.max_vcpus}"])

        cmd_parts.extend(["--arch", config.architecture.value])

        if config.os_variant:
            cmd_parts.extend(["--os-variant", config.os_variant])

        if config.cpu_model:
            cmd_parts.extend(["--cpu", config.cpu_model])

        if config.cpu_features:
            features_str = ",".join(config.cpu_features)
            cmd_parts.extend(["--features", features_str])

        for i, disk in enumerate(config.disks):
            disk_cmd = f"--disk "

            disk_params = []

            if disk.path:
                disk_path = Path(disk.path)
                if disk_path.exists():
                    disk_params.append(f"path={disk.path}")
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

            if disk.bus:
                disk_params.append(f"bus={disk.bus.value}")

            if disk.cache:
                disk_params.append(f"cache={disk.cache}")

            if disk.readonly:
                disk_params.append("readonly=on")

            if disk.shareable:
                disk_params.append("shareable=on")

            if disk.serial:
                disk_params.append(f"serial={disk.serial}")

            if disk.boot_order:
                disk_params.append(f"bootindex={disk.boot_order}")

            disk_cmd += ",".join(disk_params)
            cmd_parts.append(disk_cmd)

        for i, net in enumerate(config.networks):
            net_cmd = f"--network "

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

            if net.boot_order:
                net_params.append(f"bootindex={net.boot_order}")

            net_cmd += ",".join(net_params)
            cmd_parts.append(net_cmd)

        for controller in config.controllers:
            controller_cmd = f"--controller "

            controller_params = []
            controller_params.append(f"type={controller.controller_type.value}")

            if controller.index is not None:
                controller_params.append(f"index={controller.index}")

            if controller.model:
                controller_params.append(f"model={controller.model}")

            # if controller.ports:
            #     controller_params.append(f"ports={controller.ports}")

            controller_cmd += ",".join(controller_params)
            cmd_parts.append(controller_cmd)

        if config.graphics == GraphicsType.NONE:
            cmd_parts.append("--graphics none")
        else:
            graphics_cmd = f"--graphics {config.graphics.value}"

            graphics_params = []
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
            boot_params = []

            for i, device in enumerate(config.boot_devices):
                boot_params.append(device)

            boot_params.append("menu=on")

            boot_cmd += ",".join(boot_params)
            cmd_parts.append(boot_cmd)

        if config.autostart:
            cmd_parts.append("--autostart")

        if config.cdrom:
            cmd_parts.extend(["--cdrom", config.cdrom])
        elif config.location:
            cmd_parts.extend(["--location", config.location])

        elif hasattr(config, 'install_method') and config.install_method:
            if config.install_method == "import":
                cmd_parts.append("--import")
            elif config.install_method == "pxe":
                cmd_parts.append("--pxe")
            elif config.install_method == "boot":
                pass

        if config.extra_args:
            cmd_parts.extend(["--extra-args", f"'{config.extra_args}'"])

        for current_disk in config.disks:
            if current_disk.path is not None:
                cmd_parts.append("--wait -1")
                break

        cmd_parts.append("--noautoconsole")

        return " ".join(cmd_parts)

    def create_vm_from_xml(self, xml_config: str, autostart: bool = False) -> bool:
        """
        Создание ВМ из XML конфигурации (устаревший метод)

        Args:
            xml_config: XML конфигурация ВМ
            autostart: автостарт при загрузке хоста
        """
        self.logger.logger.warning("Метод create_vm_from_xml устарел. Используйте create_vm()")

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
            self.logger.error(f"Ошибка установки автостарта для ВМ '{vm_name}', \nerr: {e}")
            return False

    def create_vm_from_template(self, template_name: str, vm_name: str, **overrides) -> dict[str, Any]:
        """
        Создание ВМ из шаблона

        Args:
            template_name: Имя шаблона (из предустановленных или путь к файлу)
            vm_name: Имя новой ВМ
            **overrides: Переопределения параметров

        Returns:
            Результат создания
        """
        templates = {
            "ubuntu-server": VMCreateRequest(
                name=vm_name,
                os_variant="ubuntu22.04",
                memory_mb=2048,
                vcpus=2,
                disks=[
                    VMDisk(
                        path=f"/var/lib/libvirt/images/{vm_name}.qcow2",
                        size_gb=20,
                        bus=DiskBus.VIRTIO,
                        format=DiskFormat.QCOW2
                    )
                ],
                networks=[
                    VMNetwork(
                        network_type=NetworkType.NETWORK,
                        source="default",
                        model=NetworkModel.VIRTIO
                    )
                ]
            ),
            "centos-server": VMCreateRequest(
                name=vm_name,
                os_variant="centos8",
                memory_mb=2048,
                vcpus=2,
                disks=[
                    VMDisk(
                        path=f"/var/lib/libvirt/images/{vm_name}.qcow2",
                        size_gb=20,
                        bus=DiskBus.VIRTIO,
                        format=DiskFormat.QCOW2
                    )
                ],
                networks=[
                    VMNetwork(
                        network_type=NetworkType.NETWORK,
                        source="default",
                        model=NetworkModel.VIRTIO
                    )
                ]
            ),
            "windows-10": VMCreateRequest(
                name=vm_name,
                os_type=OSType.WINDOWS,
                os_variant="win10",
                memory_mb=4096,
                vcpus=4,
                disks=[
                    VMDisk(
                        path=f"/var/lib/libvirt/images/{vm_name}.qcow2",
                        size_gb=50,
                        bus=DiskBus.SATA,
                        format=DiskFormat.QCOW2
                    )
                ],
                networks=[
                    VMNetwork(
                        network_type=NetworkType.NETWORK,
                        source="default",
                        model=NetworkModel.E1000
                    )
                ],
                video_model="qxl"
            ),
            "debian-minimal": VMCreateRequest(
                name=vm_name,
                os_variant="debian10",
                memory_mb=1024,
                vcpus=1,
                disks=[
                    VMDisk(
                        path=f"/var/lib/libvirt/images/{vm_name}.qcow2",
                        size_gb=10,
                        bus=DiskBus.VIRTIO,
                        format=DiskFormat.QCOW2
                    )
                ],
                networks=[
                    VMNetwork(
                        network_type=NetworkType.NETWORK,
                        source="default",
                        model=NetworkModel.VIRTIO
                    )
                ],
                graphics=GraphicsType.NONE,
                extra_args="console=ttyS0"
            ),
        }

        if template_name in templates:
            config = templates[template_name]
            config.name = vm_name  # Обновляем имя
        else:
            try:
                template_path = Path(template_name)
                if template_path.exists():
                    with open(template_path, 'r') as f:
                        template_data = json.load(f)
                    config = VMCreateRequest(**template_data)
                    config.name = vm_name
                else:
                    return {
                        "success": False,
                        "error": f"Шаблон '{template_name}' не найден"
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Ошибка загрузки шаблона: {str(e)}"
                }

        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return self.create_vm(config)

    def edit_vm(self, vm_name: str, **changes) -> bool:
        """
        Редактирование существующей ВМ

        Args:
            vm_name: Имя ВМ для редактирования
            **changes: Изменяемые параметры

        Returns:
            Успех операции
        """
        try:
            domain = self.conn.lookupByName(vm_name)
            xml_config = domain.XMLDesc(0)

            self.logger.logger.warning("Метод edit_vm требует реализации парсера XML")

            if 'new_name' in changes:
                new_name = changes.pop('new_name')
                pass

            return False

        except self.libvirtError as e:
            self.logger.error(f"Ошибка редактирования ВМ '{vm_name}', \nerr: {e}")
            return False

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
                    vms.append(self._get_vm_info(domain))
            else:
                domains = self.conn.listAllDomains(0)
                print("domains: ", domains)
                for domain in domains:
                    vms.append(self._get_vm_info(domain))

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения списка ВМ, \nerr: {e}")

        return vms

    def _get_vm_info(self, domain, display_logs: bool = True) -> VirtualMachine:
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
                memory=info[1],
                max_memory=info[2],
                cpu_time=info[4]
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
            return self._get_vm_info(virtual_machine, display_logs).state.value
        except self.libvirtError:
            if display_logs:
                self.logger.info(f"ВМ {name} не найдена")
            return False

    def get_vm_by_name(self, name: str, request_id: str) -> VmMessage:
        """Получение ВМ по имени"""
        try:
            virtual_machine = self.conn.lookupByName(name)
            self.logger.info(f"Поиск ВМ {name}")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_successfully_found.value,
                             code=CommandMessagesEnum.vm_successfully_found.name,
                             vm_info=self._get_vm_info(virtual_machine),
                             success=True)
        except self.libvirtError as e:
            self.logger.info(f"ВМ {name} не найдена")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_found_error.value,
                             code=CommandMessagesEnum.vm_found_error.name,
                             success=False,
                             note=str(e))

    def start_vm(self, name: str, request_id: str) -> VmMessage:
        """Запуск виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.create() == 0:
                self.logger.info(f"ВМ {name} запущена")
                return VmMessage(request_id=request_id,
                                 message=CommandMessagesEnum.vm_successfully_started.value,
                                 code=CommandMessagesEnum.vm_successfully_started.name,
                                 success=True)
            self.logger.info(f"ВМ {name} не запустилась")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_start_error.value,
                             code=CommandMessagesEnum.vm_start_error.name,
                             success=False)
        except self.libvirtError as e:
            self.logger.error(f"Ошибка запуска ВМ {name}, \nerr: {e}")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_start_error.value,
                             code=CommandMessagesEnum.vm_start_error.name,
                             success=False,
                             note=str(e))

    def shutdown_vm(self, name: str, request_id: str, force: bool = False) -> VmMessage:
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
                return VmMessage(request_id=request_id,
                                 message=CommandMessagesEnum.vm_successfully_shutdowned.value,
                                 code=CommandMessagesEnum.vm_successfully_shutdowned.name,
                                 success=True)
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_shutdown_error.value,
                             code=CommandMessagesEnum.vm_shutdown_error.name,
                             success=False)

        except self.libvirtError as e:
            self.logger.error(f"Ошибка выключения ВМ {name}, \nerr: {e}")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_shutdown_error.value,
                             code=CommandMessagesEnum.vm_shutdown_error.name,
                             success=False,
                             note=str(e))

    def reboot_vm(self, name: str, request_id: str) -> VmMessage:
        """Перезагрузка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.reboot(0) == 0:
                self.logger.info(f"ВМ {name} перезагружается")
                return VmMessage(request_id=request_id,
                                 message=CommandMessagesEnum.vm_successfully_restarted.value,
                                 code=CommandMessagesEnum.vm_successfully_restarted.name,
                                 success=True)
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_restart_error.value,
                             code=CommandMessagesEnum.vm_restart_error.name,
                             success=False)
        except self.libvirtError as e:
            self.logger.error(f"Ошибка перезагрузки ВМ {name}, \nerr: {e}")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_restart_error.value,
                             code=CommandMessagesEnum.vm_restart_error.name,
                             success=False,
                             note=str(e))

    def suspend_vm(self, name: str, request_id: str) -> VmMessage:
        """Приостановка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.suspend() == 0:
                self.logger.info(f"ВМ {name} приостановлена")
                return VmMessage(request_id=request_id,
                                 message=CommandMessagesEnum.vm_successfully_stopped.value,
                                 code=CommandMessagesEnum.vm_successfully_stopped.name,
                                 success=True)
            self.logger.info(f"ВМ {name} не приостановлена")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_stop_error.value,
                             code=CommandMessagesEnum.vm_stop_error.name,
                             success=False)
        except self.libvirtError as e:
            self.logger.error(f"Ошибка приостановки ВМ {name}, \nerr: {e}")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_stop_error.value,
                             code=CommandMessagesEnum.vm_stop_error.name,
                             success=False,
                             note=str(e))

    def resume_vm(self, name: str, request_id: str) -> VmMessage:
        """Возобновление работы виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.resume() == 0:
                self.logger.info(f"ВМ {name} возобновлена")
                return VmMessage(request_id=request_id,
                                 message=CommandMessagesEnum.vm_successfully_resumed.value,
                                 code=CommandMessagesEnum.vm_successfully_resumed.name,
                                 success=True)
            self.logger.info(f"ВМ {name} не возобновлена")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_resume_error.value,
                             code=CommandMessagesEnum.vm_resume_error.name,
                             success=False)
        except self.libvirtError as e:
            self.logger.error(f"Ошибка возобновления ВМ {name}")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_resume_error.value,
                             code=CommandMessagesEnum.vm_resume_error.name,
                             success=False,
                             note=str(e))

    def delete_vm(self, name: str, request_id: str, delete_disks: bool = False, delete_nvram: bool = True) -> VmMessage:
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
                    VIR_DOMAIN_UNDEFINE_MANAGED_SAVE |
                    VIR_DOMAIN_UNDEFINE_NVRAM
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
                    self.logger.error(f"Не удалось удалить файл NVRAM {nvram_path}, \nerr: {e}")

            for disk_path in disks_to_delete:
                if os.path.exists(disk_path):
                    try:
                        os.remove(disk_path)
                        self.logger.info(f"Диск удален: {disk_path}")
                    except OSError as e:
                        self.logger.error(f"Не удалось удалить диск {disk_path}, \nerr: {e}")

            self.logger.info(f"ВМ {name} удалена")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_successfully_deleted.value,
                             code=CommandMessagesEnum.vm_successfully_deleted.name,
                             success=True)

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления ВМ {name}, \nerr: {e}")

            if "nvram" in str(e).lower():
                return self._delete_vm_with_nvram_fallback(name, request_id, delete_disks)

            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_delete_error.value,
                             code=CommandMessagesEnum.vm_delete_error.name,
                             success=False,
                             note=str(e))

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
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_config)

            for disk in root.findall('.//disk'):
                source = disk.find('source')
                if source is not None:
                    file_attr = source.get('file')
                    if file_attr:
                        disk_paths.append(file_attr)

                    dev_attr = source.get('dev')
                    if dev_attr:
                        disk_paths.append(dev_attr)

                    volume_attr = source.get('volume')
                    if volume_attr:
                        pool_attr = source.get('pool')
                        if pool_attr:
                            pass
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении путей к дискам: {e}")

        return disk_paths

    def _delete_vm_with_nvram_fallback(self, name: str, request_id: str, delete_disks: bool = False) -> VmMessage:
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
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True
            )

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

                return VmMessage(request_id=request_id,
                                 message=CommandMessagesEnum.vm_successfully_deleted.value,
                                 code=CommandMessagesEnum.vm_successfully_deleted.name,
                                 success=True)
            else:
                command = f"virsh undefine --remove-all-storage {name}"
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    self.logger.info(f"ВМ {name} удалена через virsh undefine --remove-all-storage")
                    return VmMessage(request_id=request_id,
                                     message=CommandMessagesEnum.vm_successfully_deleted.value,
                                     code=CommandMessagesEnum.vm_successfully_deleted.name,
                                     success=True)
                else:
                    self.logger.error(f"Не удалось удалить ВМ {name} даже через virsh: {result.stderr}")
                    return VmMessage(request_id=request_id,
                                     message=CommandMessagesEnum.vm_delete_error.value,
                                     code=CommandMessagesEnum.vm_delete_error.name,
                                     success=False)

        except Exception as e:
            self.logger.error(f"Ошибка в альтернативном методе удаления ВМ {name}, \nerr: {e}")
            return VmMessage(request_id=request_id,
                             message=CommandMessagesEnum.vm_delete_error.value,
                             code=CommandMessagesEnum.vm_delete_error.name,
                             success=False,
                             note=str(e))

    def get_vm_xml(self, name: str) -> str | None:
        """Получение XML конфигурации ВМ"""
        try:
            domain = self.conn.lookupByName(name)
            return domain.XMLDesc(0)
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения XML для ВМ {name}, \nerr: {e}")
            return None

    def delete_vm_with_force(self, name: str, request_id: str):
        """
        Вспомогательная функция для принудительного удаления ВМ
        Используйте эту функцию если обычное удаление не работает

        Args:
            name: Имя ВМ
            request_id: id запроса
        """

        methods = [
            lambda: self.delete_vm(name, delete_nvram=True, request_id=request_id),
            lambda: self.delete_vm(name, delete_nvram=False, request_id=request_id),
            lambda: self._delete_vm_with_nvram_fallback(name, request_id)
        ]

        for i, method in enumerate(methods, 1):
            print(f"Попытка {i} удаления ВМ {name}...")
            if method():
                print(f"ВМ {name} успешно удалена")
                return VmMessage(request_id=request_id,
                                 message=CommandMessagesEnum.vm_successfully_deleted.value,
                                 code=CommandMessagesEnum.vm_successfully_deleted.name,
                                 success=True)

        print(f"Не удалось удалить ВМ {name}")
        return VmMessage(request_id=request_id,
                         message=CommandMessagesEnum.vm_delete_error.value,
                         code=CommandMessagesEnum.vm_delete_error.name,
                         success=False)

    def _extract_nvram_path(self, xml_config: str) -> str | None:
        """
        Извлечение пути к файлу NVRAM из XML конфигурации

        Args:
            xml_config: XML конфигурация ВМ

        Returns:
            Путь к файлу NVRAM или None если не используется
        """
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_config)
            os_element = root.find('.//os')

            if os_element is not None:
                nvram_element = os_element.find('nvram')
                if nvram_element is not None:
                    return nvram_element.text

            loader_element = root.find('.//loader[@type="pflash"]')
            if loader_element is not None:
                parent = loader_element.getparent()
                if parent is not None:
                    nvram_element = parent.find('nvram')
                    if nvram_element is not None:
                        return nvram_element.text

            return None
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге XML для поиска NVRAM: {e}")
            return None

    def clone_vm(self, source_name: str, new_name: str, new_uuid: bool = True) -> dict[str, Any]:
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
                if source_elem is not None and 'file' in source_elem.attrib:
                    old_path = source_elem.get('file')
                    if old_path:
                        dir_name = os.path.dirname(old_path)
                        base_name = os.path.basename(old_path)
                        new_path = os.path.join(dir_name, f"{new_name}_{base_name}")

                        shutil.copy2(old_path, new_path)

                        source_elem.set('file', new_path)

            rough_string = ET.tostring(root, 'utf-8')
            new_xml = minidom.parseString(rough_string).toprettyxml(indent="  ")

            new_domain = self.conn.defineXML(new_xml)

            return {
                "success": True,
                "message": f"ВМ '{source_name}' клонирована в '{new_name}'",
                "xml": new_xml,
                "domain_name": new_domain.name()
            }

        except Exception as e:
            error_msg = f"Ошибка клонирования ВМ: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }


if __name__ == "__main__":
    # Пример создания ВМ с использованием нового API


    # Инициализация менеджера
    with VmManager().with_default_user() as vm_manager:
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
            vm_manager.delete_vm_with_force(vm.name, str(uuid.uuid4()))
            print(f"  - {vm.name}: {vm.state}, {vm.memory} KB RAM, {vm.vcpus} vCPUs")