import os
import subprocess
import json
from typing import Any
from pathlib import Path

from libvirt import VIR_DOMAIN_UNDEFINE_MANAGED_SAVE, VIR_DOMAIN_UNDEFINE_NVRAM

from agent.client.cli import CLIControl
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.config import LibvirtConfig
from agent.client.hypervisor.libvirt.models.controller import VMController
from agent.client.hypervisor.libvirt.models.disk import VMDisk
from agent.client.hypervisor.libvirt.models.enum import DiskBus, DiskFormat, NetworkType, NetworkModel, OSType, \
    GraphicsType, ControllerType, Architecture
from agent.client.hypervisor.libvirt.models.network import VMNetwork
from agent.client.hypervisor.libvirt.models.vm import VMCreateRequest
from agent.client.hypervisor.models.general import VMState
from agent.client.hypervisor.models.vm import VirtualMachine
from agent.client.hypervisor.templates.vm import simple_config, simple_config_without_net
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

    def create_vm(self, config: VMCreateRequest, dry_run: bool = False) -> dict[str, Any]:
        """
        Создание виртуальной машины через virt-install

        Args:
            config: Конфигурация ВМ
            dry_run: Только проверить команду, не выполнять

        Returns:
            Словарь с результатом выполнения
        """
        try:
            # Логируем начало создания
            # self.logger.info(config.name, config)

            # Проверяем, существует ли ВМ с таким именем
            existing_vm = self.get_vm_by_name(config.name)
            if existing_vm:
                return {
                    "success": False,
                    "error": f"ВМ с именем '{config.name}' уже существует",
                    "command": None
                }

            # Создаем директории для дисков если нужно
            for disk in config.disks:
                disk_path = Path(disk.path)
                if not disk_path.exists() and disk_path.parent:
                    disk_path.parent.mkdir(parents=True, exist_ok=True)
                    self.logger.info(f"Создана директория: {disk_path.parent}")

            # Проверяем, указан ли источник установки
            # Если нет, добавляем флаг --import для существующего образа
            if not (config.cdrom or config.location):
                # Проверяем, существует ли основной диск
                if config.disks:
                    main_disk = config.disks[0]
                    disk_path = Path(main_disk.path)
                    if disk_path.exists():
                        # Если диск существует, используем --import
                        config.install_method = "import"
                    else:
                        # Если диск не существует, нужен источник установки
                        # Создаем пустой диск и используем --import для создания пустой ВМ
                        # или можно установить значение по умолчанию
                        self.logger.warning(
                            f"Диск {main_disk.path} не существует. Используем --import для создания пустой ВМ")

            # Строим команду virt-install с дополнительной проверкой
            command = self._build_virt_install_command(config)
            self.logger.info(f"Команда virt-install: {command}")

            if dry_run:
                return {
                    "success": True,
                    "message": "DRY RUN: команда сгенерирована успешно",
                    "command": command,
                    "vm_name": config.name
                }

            # Выполняем команду
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 минут таймаут
            )

            if result.returncode == 0:
                # Ждем немного, чтобы ВМ появилась в libvirt
                import time
                time.sleep(2)

                # Получаем информацию о созданной ВМ
                vm_info = self.get_vm_by_name(config.name)

                if vm_info:
                    self.logger.info(f"ВМ '{config.name}' создана успешно")

                    # Устанавливаем автостарт если нужно
                    if config.autostart:
                        self._set_autostart(config.name, True)

                    return {
                        "success": True,
                        "message": f"ВМ '{config.name}' создана успешно",
                        "command": command,
                        "vm_info": vm_info.dict() if hasattr(vm_info, 'dict') else str(vm_info),
                        "stdout": result.stdout,
                        "stderr": result.stderr
                    }
                else:
                    self.logger.error(f"ВМ создана, но не найдена в libvirt")
                    return {
                        "success": False,
                        "error": "ВМ создана, но не найдена в libvirt",
                        "command": command,
                        "stdout": result.stdout,
                        "stderr": result.stderr
                    }
            else:
                # Анализируем ошибку и пытаемся исправить
                error_msg = result.stderr

                # Если ошибка связана с отсутствием метода установки
                if "Необходимо определить метод установки" in error_msg or "install method must be specified" in error_msg.lower():
                    self.logger.warning("Обнаружена ошибка метода установки. Пробуем с флагом --import...")

                    # Добавляем флаг --import и пробуем снова
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
                        vm_info = self.get_vm_by_name(config.name)

                        if vm_info:
                            self.logger.info(f"ВМ '{config.name}' создана успешно с флагом --import")

                            if config.autostart:
                                self._set_autostart(config.name, True)

                            return {
                                "success": True,
                                "message": f"ВМ '{config.name}' создана успешно с флагом --import",
                                "command": import_command,
                                "vm_info": vm_info.dict() if hasattr(vm_info, 'dict') else str(vm_info),
                                "stdout": import_result.stdout,
                                "stderr": import_result.stderr,
                                "note": "Использован флаг --import для создания пустой ВМ"
                            }
                        else:
                            return {
                                "success": False,
                                "error": "ВМ создана с --import, но не найдена в libvirt",
                                "command": import_command,
                                "stdout": import_result.stdout,
                                "stderr": import_result.stderr
                            }
                    else:
                        error_msg = f"Ошибка создания ВМ с --import: {import_result.stderr}"
                        self.logger.error(error_msg)
                        return {
                            "success": False,
                            "error": error_msg,
                            "command": import_command,
                            "stdout": import_result.stdout,
                            "stderr": import_result.stderr
                        }
                else:
                    error_msg = f"Ошибка создания ВМ: {result.stderr}"
                    self.logger.error(error_msg)
                    return {
                        "success": False,
                        "error": error_msg,
                        "command": command,
                        "stdout": result.stdout,
                        "stderr": result.stderr
                    }

        except subprocess.TimeoutExpired:
            error_msg = f"Таймаут при создании ВМ '{config.name}'"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "command": command if 'command' in locals() else None
            }
        except Exception as e:
            error_msg = f"Неожиданная ошибка при создании ВМ: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "command": command if 'command' in locals() else None
            }

    def _build_virt_install_command(self, config: VMCreateRequest) -> str:
        """
        Построение команды virt-install из конфигурации

        Args:
            config: Конфигурация ВМ

        Returns:
            Строка команды для выполнения
        """
        cmd_parts = ["virt-install"]

        # Основные параметры
        cmd_parts.extend(["--name", config.name])

        if config.description:
            cmd_parts.extend(["--description", f"'{config.description}'"])

        cmd_parts.extend(["--memory", str(config.memory_mb)])

        if config.current_memory_mb and config.current_memory_mb != config.memory_mb:
            cmd_parts.extend(["--current-memory", str(config.current_memory_mb)])

        cmd_parts.extend(["--vcpus", str(config.vcpus)])

        if config.max_vcpus and config.max_vcpus != config.vcpus:
            cmd_parts.extend(["--vcpus", f"{config.vcpus},maxvcpus={config.max_vcpus}"])

        # Архитектура и эмулятор
        cmd_parts.extend(["--arch", config.architecture.value])

        # Тип ОС и вариант
        if config.os_variant:
            cmd_parts.extend(["--os-variant", config.os_variant])

        # CPU модель и фичи
        if config.cpu_model:
            cmd_parts.extend(["--cpu", config.cpu_model])

        if config.cpu_features:
            features_str = ",".join(config.cpu_features)
            cmd_parts.extend(["--features", features_str])

        # Диски
        for i, disk in enumerate(config.disks):
            disk_cmd = f"--disk "

            # Собираем параметры диска
            disk_params = []

            if disk.path:
                # Проверяем, существует ли диск
                disk_path = Path(disk.path)
                if disk_path.exists():
                    # Существующий диск
                    disk_params.append(f"path={disk.path}")
                else:
                    # Новый диск
                    if disk.size_gb:
                        disk_params.append(f"size={disk.size_gb}")
                    if disk.format:
                        disk_params.append(f"format={disk.format.value}")
                    disk_params.append(f"path={disk.path}")

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

        # Сети
        for i, net in enumerate(config.networks):
            net_cmd = f"--network "

            # Собираем параметры сети
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

        # Контроллеры
        for controller in config.controllers:
            controller_cmd = f"--controller "

            # Собираем параметры контроллера
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

        # Графика
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

        # Видео
        cmd_parts.extend(["--video", config.video_model])

        # Консоль
        if config.console_type:
            cmd_parts.extend(["--console", f"{config.console_type}"])

        # Устройства загрузки
        if config.boot_devices:
            boot_cmd = "--boot "
            boot_params = []

            for i, device in enumerate(config.boot_devices):
                boot_params.append(device)

            # Добавляем menu=on для отображения меню загрузки
            boot_params.append("menu=on")

            boot_cmd += ",".join(boot_params)
            cmd_parts.append(boot_cmd)

        # Автостарт
        if config.autostart:
            cmd_parts.append("--autostart")

        # CD-ROM для установки
        if config.cdrom:
            cmd_parts.extend(["--cdrom", config.cdrom])
        elif config.location:
            cmd_parts.extend(["--location", config.location])

        # Если нет источника установки, но есть атрибут install_method
        elif hasattr(config, 'install_method') and config.install_method:
            if config.install_method == "import":
                cmd_parts.append("--import")
            elif config.install_method == "pxe":
                cmd_parts.append("--pxe")
            elif config.install_method == "boot":
                # Уже обрабатывается в boot_devices
                pass

        # Дополнительные аргументы
        if config.extra_args:
            cmd_parts.extend(["--extra-args", f"'{config.extra_args}'"])

        # Флаг --wait -1 для фонового выполнения
        cmd_parts.append("--wait -1")

        # Флаг --noautoconsole
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
        # Предустановленные шаблоны
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

        # Получаем шаблон
        if template_name in templates:
            config = templates[template_name]
            config.name = vm_name  # Обновляем имя
        else:
            # Пытаемся загрузить шаблон из файла
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

        # Применяем переопределения
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        # Создаем ВМ
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
            # Получаем текущую конфигурацию
            domain = self.conn.lookupByName(vm_name)
            xml_config = domain.XMLDesc(0)

            # Здесь должна быть логика парсинга XML и применения изменений
            # Это упрощенная версия - в реальности нужен парсер XML

            self.logger.logger.warning("Метод edit_vm требует реализации парсера XML")

            # Временное решение - пересоздание ВМ
            if 'new_name' in changes:
                new_name = changes.pop('new_name')
                # Создаем копию ВМ с новым именем
                # Это упрощенный подход, в реальности нужно клонировать ВМ
                pass

            return False

        except self.libvirtError as e:
            self.logger.error(f"Ошибка редактирования ВМ '{vm_name}', \nerr: {e}")
            return False

    # Остальные методы остаются без изменений
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

    def _get_vm_info(self, domain) -> VirtualMachine:
        """Получение информации о виртуальной машине"""
        try:
            info = domain.info()
            state = VMState(info[0])

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
            self.logger.error(f"Ошибка получения информации о ВМ, \nerr: {e}")
            raise

    def get_vm_by_name(self, name: str) -> VirtualMachine | None:
        """Получение ВМ по имени"""
        try:
            virtual_machine = self.conn.lookupByName(name)
            return self._get_vm_info(virtual_machine)
        except self.libvirtError:
            return None

    def start_vm(self, name: str) -> bool:
        """Запуск виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.create() == 0:
                self.logger.info(f"ВМ {name} запущена")
                return True
            return False
        except self.libvirtError as e:
            self.logger.error(f"Ошибка запуска ВМ {name}, \nerr: {e}")
            return False

    def shutdown_vm(self, name: str, force: bool = False) -> bool:
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
                return True
            return False

        except self.libvirtError as e:
            self.logger.error(f"Ошибка выключения ВМ {name}, \nerr: {e}")
            return False

    def reboot_vm(self, name: str) -> bool:
        """Перезагрузка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.reboot(0) == 0:
                self.logger.info(f"ВМ {name} перезагружается")
                return True
            return False
        except self.libvirtError as e:
            self.logger.error(f"Ошибка перезагрузки ВМ {name}, \nerr: {e}")
            return False

    def suspend_vm(self, name: str) -> bool:
        """Приостановка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.suspend() == 0:
                self.logger.info(f"ВМ {name} приостановлена")
                return True
            return False
        except self.libvirtError as e:
            self.logger.error(f"Ошибка приостановки ВМ {name}, \nerr: {e}")
            return False

    def resume_vm(self, name: str) -> bool:
        """Возобновление работы виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.resume() == 0:
                self.logger.info(f"ВМ {name} возобновлена")
                return True
            return False
        except self.libvirtError as e:
            self.logger.error(f"Ошибка возобновления ВМ {name}")
            return False

    def delete_vm(self, name: str, delete_disks: bool = False, delete_nvram: bool = True) -> bool:
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
            # Получаем домен
            domain = self.conn.lookupByName(name)

            # Получаем XML конфигурацию перед удалением
            xml_config = domain.XMLDesc(0)

            # Извлекаем путь к NVRAM файлу
            nvram_path = None
            if delete_nvram:
                nvram_path = self._extract_nvram_path(xml_config)

            # Получаем информацию о дисках
            disks_to_delete = []
            if delete_disks:
                disks_to_delete = self._extract_disk_paths(xml_config)

            # Если ВМ запущена, выключаем её
            if domain.isActive():
                self.logger.info(f"ВМ {name} запущена, выключаем...")
                domain.destroy()

            # Удаляем конфигурацию домена
            # Используем флаги для корректного удаления с NVRAM
            try:
                # Пытаемся удалить с флагом --managed-save
                domain.undefineFlags(
                    VIR_DOMAIN_UNDEFINE_MANAGED_SAVE |
                    VIR_DOMAIN_UNDEFINE_NVRAM
                )
                self.logger.info(f"Конфигурация ВМ {name} удалена с флагами")
            except self.libvirtError as e:
                # Если не сработало, пробуем стандартный способ
                self.logger.warning(f"Стандартное удаление не сработало: {e}")
                domain.undefine()

            # Удаляем файл NVRAM если он существует
            if nvram_path and os.path.exists(nvram_path):
                try:
                    os.remove(nvram_path)
                    self.logger.info(f"Файл NVRAM удален: {nvram_path}")
                except OSError as e:
                    self.logger.error(f"Не удалось удалить файл NVRAM {nvram_path}, \nerr: {e}")

            # Удаляем диски если нужно
            for disk_path in disks_to_delete:
                if os.path.exists(disk_path):
                    try:
                        os.remove(disk_path)
                        self.logger.info(f"Диск удален: {disk_path}")
                    except OSError as e:
                        self.logger.error(f"Не удалось удалить диск {disk_path}, \nerr: {e}")

            self.logger.info(f"ВМ {name} удалена")
            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления ВМ {name}, \nerr: {e}")

            # Если ошибка связана с NVRAM, пробуем альтернативный способ
            if "nvram" in str(e).lower():
                return self._delete_vm_with_nvram_fallback(name, delete_disks)

            return False

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

            # Ищем все элементы disk
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
                            # Формируем путь к тому в пуле
                            # В реальности нужно использовать libvirt API для получения пути
                            pass
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении путей к дискам: {e}")

        return disk_paths

    def _delete_vm_with_nvram_fallback(self, name: str, delete_disks: bool = False) -> bool:
        """
        Альтернативный метод удаления ВМ с NVRAM

        Args:
            name: Имя ВМ
            delete_disks: Удалять ли диски

        Returns:
            Успех операции
        """
        try:
            # Используем virsh команду для удаления
            command = f"virsh undefine --nvram {name}"
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                self.logger.info(f"ВМ {name} удалена через virsh undefine --nvram")

                # Дополнительно удаляем вручную если остались следы
                nvram_pattern = f"/var/lib/libvirt/qemu/nvram/{name}_*"
                import glob
                nvram_files = glob.glob(nvram_pattern)
                for nvram_file in nvram_files:
                    try:
                        os.remove(nvram_file)
                        self.logger.info(f"Удален файл NVRAM: {nvram_file}")
                    except OSError:
                        pass

                return True
            else:
                # Пробуем удалить без NVRAM
                command = f"virsh undefine --remove-all-storage {name}"
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    self.logger.info(f"ВМ {name} удалена через virsh undefine --remove-all-storage")
                    return True
                else:
                    self.logger.error(f"Не удалось удалить ВМ {name} даже через virsh: {result.stderr}")
                    return False

        except Exception as e:
            self.logger.error(f"Ошибка в альтернативном методе удаления ВМ {name}, \nerr: {e}")
            return False

    def get_vm_xml(self, name: str) -> str | None:
        """Получение XML конфигурации ВМ"""
        try:
            domain = self.conn.lookupByName(name)
            return domain.XMLDesc(0)
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения XML для ВМ {name}, \nerr: {e}")
            return None

    def delete_vm_with_force(self, name: str):
        """
        Вспомогательная функция для принудительного удаления ВМ
        Используйте эту функцию если обычное удаление не работает

        Args:
            name: Имя ВМ
        """

        # Пробуем разные методы удаления
        methods = [
            lambda: self.delete_vm(name, delete_nvram=True),
            lambda: self.delete_vm(name, delete_nvram=False),
            lambda: self._delete_vm_with_nvram_fallback(name)
        ]

        for i, method in enumerate(methods, 1):
            print(f"Попытка {i} удаления ВМ {name}...")
            if method():
                print(f"ВМ {name} успешно удалена")
                return True

        print(f"Не удалось удалить ВМ {name}")
        return False

    def _extract_nvram_path(self, xml_config: str) -> str | None:
        """
        Извлечение пути к файлу NVRAM из XML конфигурации

        Args:
            xml_config: XML конфигурация ВМ

        Returns:
            Путь к файлу NVRAM или None если не используется
        """
        try:
            # Парсим XML для поиска nvram
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_config)
            os_element = root.find('.//os')

            if os_element is not None:
                nvram_element = os_element.find('nvram')
                if nvram_element is not None:
                    return nvram_element.text

            # Проверяем loader/nvram в другом формате
            loader_element = root.find('.//loader[@type="pflash"]')
            if loader_element is not None:
                # Ищем nvram в родительском элементе
                parent = loader_element.getparent()
                if parent is not None:
                    nvram_element = parent.find('nvram')
                    if nvram_element is not None:
                        return nvram_element.text

            return None
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге XML для поиска NVRAM: {e}")
            return None


# ========== EXAMPLE USAGE ==========

if __name__ == "__main__":
    # Пример создания ВМ с использованием нового API


    # Инициализация менеджера
    with VmManager().with_default_user() as vm_manager:
        # print(vm_manager.delete_vm("test-vm-03"))
        # Пример создания ВМ /var/lib/libvirt/images/disk-859480.qcow2
        # result = vm_manager.create_vm(simple_config_without_net)
        # print(json.dumps(result, indent=2, ensure_ascii=False))
        #
        # # Пример использования шаблона
        # template_result = vm_manager.create_vm_from_template(
        #     "ubuntu-server",
        #     "new-ubuntu-vm",
        #     memory_mb=4096,
        #     vcpus=4
        # )
        # print(json.dumps(template_result, indent=2, ensure_ascii=False))

        # Получение списка ВМ
        # vm_manager.shutdown_vm("test-vm-01", force=True)
        # vm_manager.delete_vm_with_force("test-vm-01")
        vms = vm_manager.list_vms()
        print(f"Найдено ВМ: {len(vms)}")

        for vm in vms:
            print(f"  - {vm.name}: {vm.state}, {vm.memory} KB RAM, {vm.vcpus} vCPUs")