
from xml.etree import ElementTree as ET
import ipaddress

from agent.client.cli import CLIControl
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.models.msg import NetworkMessage, CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import NetworkParameters, NetworkTypeInfo, NetworkInfo


class NetworkManager(LibvirtClient):
    """
    Управление сетевыми интерфейсами
    """

    libvirtError = None

    # Описания типов сетей
    NETWORK_TYPE_DESCRIPTIONS = {
        "nat": "NAT сеть - ВМ получают доступ в интернет через NAT",
        "route": "Routed сеть - маршрутизация без NAT",
        "bridge": "Bridge сеть - прямое подключение к физическому интерфейсу",
        "private": "Private сеть - изолированная с внутренним форвардингом",
        "vepa": "VEPA сеть - Virtual Ethernet Port Aggregator",
        "passthrough": "Passthrough сеть - прямой доступ к физическому интерфейсу",
        "isolated": "Изолированная сеть - без доступа к внешним сетям",
        "no-forward": "Сеть без форвардинга - только внутренняя коммуникация"
    }

    def __init__(self, connection_uri: str = "qemu:///session", username: str | None = None, password: str | None = None):
        super().__init__(connection_uri, username, password)
        self.cli = CLIControl()

    def list_networks(self) -> list[str]:
        """Получение списка сетей"""
        try:
            networks = self.conn.listNetworks()
            return networks
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения списка сетей: {e}")
            return []

    def create_network(self, params: NetworkParameters, request_id: str) -> NetworkMessage:
        """Создание виртуальной сети"""
        try:
            # Определяем тип сети перед созданием
            network_type_info = self._determine_network_type(params)
            self.logger.info(
                f"Создание сети '{params.name}' типа '{network_type_info.type}' "
                f"({network_type_info.description})"
            )

            # Дополнительная валидация для bridge сетей
            if network_type_info.type == "bridge" and (params.dhcp_ranges or params.dhcp_hosts):
                self.logger.warning(
                    f"Bridge сети обычно не используют DHCP. Сеть: '{params.name}'"
                )

            xml_config = self._generate_network_xml(params)
            network = self.conn.networkDefineXML(xml_config)

            if params.uuid:
                network.setUUID(params.uuid)

            if params.autostart:
                network.setAutostart(True)  # По умолчанию автозапуск включен
            else:
                network.setAutostart(False)  # По умолчанию автозапуск выключен
            network.create()  # Активируем сеть

            self.logger.info(
                f"Сеть '{params.name}' успешно создана "
                f"(тип: {network_type_info.type}, активна: True)"
            )

            created_network = self.get_network_info(params.name, request_id)
            assert created_network.message == CommandMessagesEnum.virtual_network_founded.value
            return NetworkMessage(request_id=request_id,
                                  message=CommandMessagesEnum.virtual_network_successfully_created.value,
                                  code=CommandMessagesEnum.virtual_network_successfully_created.name,
                                  net_info=created_network.net_info,
                                  success=True)

        except self.libvirtError as e:
            self.logger.error(f"Ошибка создания сети '{params.name}': {e}")
            return NetworkMessage(request_id=request_id,
                                  message=CommandMessagesEnum.virtual_network_create_error.value,
                                  code=CommandMessagesEnum.virtual_network_create_error.name,
                                  success=False,
                                  note=str(e))
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при создании сети '{params.name}': {e}")
            return NetworkMessage(request_id=request_id,
                                  message=CommandMessagesEnum.virtual_network_create_error.value,
                                  code=CommandMessagesEnum.virtual_network_create_error.name,
                                  success=False,
                                  note=str(e))

    def delete_network(self, network_name: str, request_id: str, force: bool = False) -> NetworkMessage:
        """Удаление виртуальной сети"""
        try:
            network = self.conn.networkLookupByName(network_name)

            # Получаем информацию о типе сети перед удалением
            network_type = self._get_network_type_from_xml(network.XMLDesc(0))

            if network.isActive():
                if force:
                    network.destroy()
                    self.logger.info(f"Сеть '{network_name}' (тип: {network_type}) остановлена перед удалением")
                else:
                    self.logger.error(
                        f"Сеть '{network_name}' активна. Используйте force=True для принудительного удаления"
                    )
                    return NetworkMessage(request_id=request_id,
                                          message=CommandMessagesEnum.virtual_network_delete_error.value,
                                          code=CommandMessagesEnum.virtual_network_delete_error.name,
                                          success=False,
                                          note="use force=True for force delete")

            network.undefine()
            self.logger.info(f"Сеть '{network_name}' (тип: {network_type}) успешно удалена")
            return NetworkMessage(request_id=request_id,
                                  message=CommandMessagesEnum.virtual_network_successfully_deleted.value,
                                  code=CommandMessagesEnum.virtual_network_successfully_deleted.name,
                                  success=True)

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления сети '{network_name}': {e}")
            return NetworkMessage(request_id=request_id,
                                  message=CommandMessagesEnum.virtual_network_delete_error.value,
                                  code=CommandMessagesEnum.virtual_network_delete_error.name,
                                  success=False,
                                  note=str(e))

    def edit_network(self, network_name: str, params: NetworkParameters) -> bool:
        """Редактирование виртуальной сети"""
        try:
            # Получаем текущую сеть
            network = self.conn.networkLookupByName(network_name)

            # Определяем старый и новый типы сетей
            old_type = self._get_network_type_from_xml(network.XMLDesc(0))
            new_type_info = self._determine_network_type(params)

            self.logger.info(
                f"Редактирование сети '{network_name}': "
                f"старый тип: {old_type}, новый тип: {new_type_info.type}"
            )

            # Если сеть активна, деактивируем её для редактирования
            was_active = network.isActive()
            if was_active:
                network.destroy()
                self.logger.info(f"Сеть '{network_name}' остановлена для редактирования")

            # Генерируем новую XML конфигурацию
            xml_config = self._generate_network_xml(params)

            # Определяем сеть с новой конфигурацией
            new_network = self.conn.networkDefineXML(xml_config)

            # Восстанавливаем состояние автозапуска
            autostart = network.autostart()
            new_network.setAutostart(autostart)

            # Если сеть была активна, активируем её
            if was_active:
                new_network.create()
                self.logger.info(f"Сеть '{network_name}' запущена после редактирования")

            self.logger.info(
                f"Сеть '{network_name}' успешно отредактирована "
                f"(тип изменен: {old_type} -> {new_type_info.type})"
            )
            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка редактирования сети '{network_name}': {e}")
            return False

    def get_network_info(self, network_name: str, request_id: str) -> NetworkMessage:
        """Получение информации о сети"""
        try:
            network = self.conn.networkLookupByName(network_name)
            xml_desc = network.XMLDesc(0)

            # Определяем тип сети из XML
            network_type_info = self._get_network_type_info_from_xml(xml_desc)

            info = NetworkInfo(
                name=network.name(),
                uuid=network.UUIDString(),
                bridge_name=network.bridgeName() if hasattr(network, 'bridgeName') else None,
                active=network.isActive(),
                persistent=network.isPersistent(),
                autostart=network.autostart(),
                network_type=network_type_info,
                xml=xml_desc
            )

            return NetworkMessage(request_id=request_id,
                                  message=CommandMessagesEnum.virtual_network_founded.value,
                                  code=CommandMessagesEnum.virtual_network_founded.name,
                                  success=True,
                                  net_info=info)

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения информации о сети '{network_name}': {e}")
            return NetworkMessage(request_id=request_id,
                                  message=CommandMessagesEnum.virtual_network_not_found.value,
                                  code=CommandMessagesEnum.virtual_network_not_found.name,
                                  success=False,
                                  note=str(e))

    def _generate_network_xml(self, params: NetworkParameters) -> str:
        """Генерация XML конфигурации сети"""
        # Дополнительная валидация перед генерацией XML
        self._validate_network_parameters(params)

        root = ET.Element("network")

        # Базовые параметры
        name_elem = ET.SubElement(root, "name")
        name_elem.text = params.name

        if params.uuid:
            uuid_elem = ET.SubElement(root, "uuid")
            uuid_elem.text = params.uuid

        # Мост
        if params.bridge:
            bridge_elem = ET.SubElement(root, "bridge")
            if params.bridge.name:
                bridge_elem.set("name", params.bridge.name)
            if params.bridge.stp is not None:
                bridge_elem.set("stp", params.bridge.stp)
            if params.bridge.delay is not None:
                bridge_elem.set("delay", str(params.bridge.delay))
            if params.bridge.zone is not None:
                bridge_elem.set("zone", params.bridge.zone)

        # Форвардинг
        if params.forward:
            forward_elem = ET.SubElement(root, "forward", mode=params.forward.mode)
            if params.forward.dev:
                forward_elem.set("dev", params.forward.dev)
            if params.forward.interface:
                interface_elem = ET.SubElement(forward_elem, "interface")
                interface_elem.set("dev", params.forward.interface)

        # Domain
        if params.domain_name:
            domain_elem = ET.SubElement(root, "domain")
            domain_elem.set("name", params.domain_name)

        # MTU
        if params.mtu and params.mtu != 1500:
            mtu_elem = ET.SubElement(root, "mtu", size=str(params.mtu))

        # Trust guest RX filters
        if params.trust_guest_rx_filters:
            ET.SubElement(root, "trustGuestRxFilters")

        # IP конфигурация
        if params.ipv4 and params.ipv4_address:
            ip_elem = ET.SubElement(root, "ip")
            ip_elem.set("address", str(ipaddress.ip_network(str(params.ipv4_address)).network_address))
            ip_elem.set("prefix", str(ipaddress.ip_network(str(params.ipv4_address)).prefixlen))
            ip_elem.set("family", "ipv4")

            # DHCP
            if params.dhcp_ranges or params.dhcp_hosts:
                dhcp_elem = ET.SubElement(ip_elem, "dhcp")

                # Диапазоны DHCP
                if params.dhcp_ranges:
                    for dhcp_range in params.dhcp_ranges:
                        range_elem = ET.SubElement(dhcp_elem, "range")
                        range_elem.set("start", str(dhcp_range.start))
                        range_elem.set("end", str(dhcp_range.end))

                # Статические хосты DHCP
                if params.dhcp_hosts:
                    for dhcp_host in params.dhcp_hosts:
                        host_elem = ET.SubElement(dhcp_elem, "host")
                        host_elem.set("mac", dhcp_host.mac)
                        host_elem.set("ip", str(dhcp_host.ip))
                        if dhcp_host.name:
                            host_elem.set("name", dhcp_host.name)

        # IPv6 конфигурация
        if params.ipv6 and params.ipv6_address:
            ip6_elem = ET.SubElement(root, "ip")
            ip6_elem.set("address", str(ipaddress.ip_network(str(params.ipv6_address)).network_address))
            ip6_elem.set("prefix", str(ipaddress.ip_network(str(params.ipv6_address)).prefixlen))
            ip6_elem.set("family", "ipv6")

        # Маршруты
        if params.routes:
            for route in params.routes:
                route_elem = ET.SubElement(root, "route")
                route_elem.set("address", str(route.address))
                if route.gateway:
                    route_elem.set("gateway", str(route.gateway))
                if route.metric:
                    route_elem.set("metric", str(route.metric))

        # DNS
        if params.dns:
            dns_elem = ET.SubElement(root, "dns")

            # Forwarders
            if params.dns.forwarders:
                for forwarder in params.dns.forwarders:
                    forwarder_elem = ET.SubElement(dns_elem, "forwarder")
                    forwarder_elem.set("addr", str(forwarder))
                    if params.dns.local_only:
                        forwarder_elem.set("domain", params.dns.domain or ".")

            # Hosts
            if params.dns.hosts:
                for host in params.dns.hosts:
                    host_elem = ET.SubElement(dns_elem, "host")
                    host_elem.set("ip", str(host.ip))
                    for hostname in host.hostnames:
                        hostname_elem = ET.SubElement(host_elem, "hostname")
                        hostname_elem.text = hostname

            # TXT записи
            if params.dns.txt_records:
                for txt in params.dns.txt_records:
                    txt_elem = ET.SubElement(dns_elem, "txt")
                    txt_elem.set("name", txt.name)
                    txt_elem.set("value", txt.value)

            # SRV записи
            if params.dns.srv_records:
                for srv in params.dns.srv_records:
                    srv_elem = ET.SubElement(dns_elem, "srv")
                    srv_elem.set("service", srv.service)
                    srv_elem.set("protocol", srv.protocol)
                    srv_elem.set("target", srv.target)
                    if srv.port:
                        srv_elem.set("port", str(srv.port))
                    if srv.priority:
                        srv_elem.set("priority", str(srv.priority))
                    if srv.weight:
                        srv_elem.set("weight", str(srv.weight))

        # Изолированная сеть
        if params.isolated:
            ET.SubElement(root, "isolated")

        # Преобразуем в строку
        xml_str = ET.tostring(root, encoding='unicode')

        # Добавляем XML заголовок
        xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
        return xml_header + xml_str

    def set_network_autostart(self, network_name: str, autostart: bool = True) -> bool:
        """Настройка автозапуска сети"""
        try:
            network = self.conn.networkLookupByName(network_name)
            network_type = self._get_network_type_from_xml(network.XMLDesc(0))
            network.setAutostart(autostart)
            self.logger.info(
                f"Автозапуск сети '{network_name}' (тип: {network_type}) "
                f"установлен в {autostart}"
            )
            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка установки автозапуска для сети '{network_name}': {e}")
            return False

    def start_network(self, network_name: str) -> bool:
        """Запуск сети"""
        try:
            network = self.conn.networkLookupByName(network_name)
            network_type = self._get_network_type_from_xml(network.XMLDesc(0))

            if not network.isActive():
                network.create()
                self.logger.info(f"Сеть '{network_name}' (тип: {network_type}) запущена")
                return True
            else:
                self.logger.info(f"Сеть '{network_name}' (тип: {network_type}) уже запущена")
                return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка запуска сети '{network_name}': {e}")
            return False

    def stop_network(self, network_name: str) -> bool:
        """Остановка сети"""
        try:
            network = self.conn.networkLookupByName(network_name)
            network_type = self._get_network_type_from_xml(network.XMLDesc(0))

            if network.isActive():
                network.destroy()
                self.logger.info(f"Сеть '{network_name}' (тип: {network_type}) остановлена")
                return True
            else:
                self.logger.info(f"Сеть '{network_name}' (тип: {network_type}) уже остановлена")
                return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка остановки сети '{network_name}': {e}")
            return False

    def list_all_networks(self) -> list[NetworkInfo]:
        """Получение полного списка всех сетей с информацией"""
        networks_info = []
        try:
            # Получаем все сети (флаг 0 - все сети)
            networks = self.conn.listAllNetworks(0)

            for network in networks:
                try:
                    xml_desc = network.XMLDesc(0)
                    network_type_info = self._get_network_type_info_from_xml(xml_desc)

                    info = NetworkInfo(
                        name=network.name(),
                        uuid=network.UUIDString(),
                        bridge_name=network.bridgeName() if hasattr(network, 'bridgeName') else None,
                        active=network.isActive(),
                        persistent=network.isPersistent(),
                        autostart=network.autostart(),
                        network_type=network_type_info,
                        xml=xml_desc
                    )

                    networks_info.append(info)
                except Exception as e:
                    self.logger.warning(f"Ошибка получения информации о сети {network.name()}: {e}")

            return networks_info

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения полного списка сетей: {e}")
            return []

    def _determine_network_type(self, params: NetworkParameters) -> NetworkTypeInfo:
        """Определение типа сети на основе параметров"""
        # Определяем базовые характеристики
        has_ipv4 = params.ipv4 and params.ipv4_address is not None
        has_ipv6 = params.ipv6 and params.ipv6_address is not None
        has_dhcp = bool(params.dhcp_ranges or params.dhcp_hosts)
        has_bridge = params.bridge is not None

        # Определяем основной тип сети
        if params.isolated:
            network_type = 'isolated'
        elif params.forward:
            network_type = params.forward.mode
        else:
            network_type = 'no-forward'

        # Получаем описание типа
        description = self.NETWORK_TYPE_DESCRIPTIONS.get(
            network_type,
            f"Неизвестный тип сети: {network_type}"
        )

        return NetworkTypeInfo(
            type=network_type,
            is_isolated=params.isolated or False,
            has_dhcp=has_dhcp,
            has_ipv4=has_ipv4,
            has_ipv6=has_ipv6,
            has_bridge=has_bridge,
            description=description
        )

    def _get_network_type_from_xml(self, xml_desc: str) -> str:
        """Получение типа сети из XML конфигурации"""
        try:
            root = ET.fromstring(xml_desc)

            # Проверяем на изолированную сеть
            isolated_elem = root.find('isolated')
            if isolated_elem is not None:
                return 'isolated'

            # Проверяем на наличие forward
            forward_elem = root.find('forward')
            if forward_elem is not None:
                mode = forward_elem.get('mode', 'nat')
                return mode

            # Сеть без форвардинга
            return 'no-forward'

        except ET.ParseError as e:
            self.logger.error(f"Ошибка парсинга XML при определении типа сети: {e}")
            return 'unknown'

    def _get_network_type_info_from_xml(self, xml_desc: str) -> NetworkTypeInfo:
        """Получение полной информации о типе сети из XML"""
        try:
            root = ET.fromstring(xml_desc)

            # Определяем базовые характеристики
            has_ipv4 = root.find(".//ip[@family='ipv4']") is not None
            has_ipv6 = root.find(".//ip[@family='ipv6']") is not None
            has_dhcp = root.find(".//dhcp") is not None
            has_bridge = root.find("bridge") is not None

            # Определяем основной тип
            isolated_elem = root.find('isolated')
            if isolated_elem is not None:
                network_type = 'isolated'
            else:
                forward_elem = root.find('forward')
                if forward_elem is not None:
                    network_type = forward_elem.get('mode', 'nat')
                else:
                    network_type = 'no-forward'

            # Получаем описание
            description = self.NETWORK_TYPE_DESCRIPTIONS.get(
                network_type,
                f"Неизвестный тип сети: {network_type}"
            )

            return NetworkTypeInfo(
                type=network_type,
                is_isolated=isolated_elem is not None,
                has_dhcp=has_dhcp,
                has_ipv4=has_ipv4,
                has_ipv6=has_ipv6,
                has_bridge=has_bridge,
                description=description
            )

        except ET.ParseError as e:
            self.logger.error(f"Ошибка парсинга XML: {e}")
            return NetworkTypeInfo(
                type='unknown',
                description='Ошибка определения типа сети'
            )

    def _validate_network_parameters(self, params: NetworkParameters):
        """Дополнительная валидация параметров сети"""
        # Валидация для bridge сетей
        if params.forward and params.forward.mode == 'bridge':
            if not params.forward.dev and not params.forward.interface:
                self.logger.warning(
                    f"Bridge сеть '{params.name}': рекомендуется указать dev или interface"
                )

        # Валидация для routed сетей
        if params.forward and params.forward.mode == 'route':
            if params.bridge:
                self.logger.warning(
                    f"Routed сеть '{params.name}': параметр bridge обычно не используется"
                )

        # Валидация для NAT сетей
        if params.forward and params.forward.mode == 'nat':
            if not params.ipv4_address:
                self.logger.warning(
                    f"NAT сеть '{params.name}': рекомендуется указать ipv4_address"
                )

    def get_network_summary(self) -> dict:
        """Получение сводки по всем сетям"""
        networks = self.list_all_networks()

        summary = {
            'total': len(networks),
            'active': 0,
            'inactive': 0,
            'by_type': {},
            'by_autostart': {
                'enabled': 0,
                'disabled': 0
            }
        }

        for network in networks:
            # Подсчет активных/неактивных
            if network.active:
                summary['active'] += 1
            else:
                summary['inactive'] += 1

            # Подсчет по типам
            network_type = network.network_type.type
            if network_type not in summary['by_type']:
                summary['by_type'][network_type] = 0
            summary['by_type'][network_type] += 1

            # Подсчет по автозапуску
            if network.autostart:
                summary['by_autostart']['enabled'] += 1
            else:
                summary['by_autostart']['disabled'] += 1

        return summary

    def is_network_visible(self, network_name: str) -> bool:
        """
        Проверяет, видна ли сеть в 'virsh net-list --all'
        """
        try:
            result = self.cli.virsh_net_data("--all")
            return network_name in result
        except self.libvirtError as e:
            self.logger.error(f"Ошибка проверки видимости сети '{network_name}': {e}")
            return False

    def enable_network_with_autostart(self, network_name: str, start_now: bool = True) -> bool:
        """
        Включает сеть и настраивает автозапуск.

        Args:
            network_name: Имя сети
            start_now: Запускать сеть сразу (True) или только настроить автозапуск (False)

        Returns:
            bool: True если операция успешна, False в случае ошибки
        """
        try:
            # Получаем информацию о сети
            network_info = self.get_network_info(network_name)
            if not network_info:
                self.logger.error(f"Сеть '{network_name}' не найдена")
                return False

            # Настраиваем автозапуск
            autostart_success = self.set_network_autostart(network_name, True)
            if not autostart_success:
                self.logger.error(f"Не удалось настроить автозапуск для сети '{network_name}'")
                return False

            # Запускаем сеть, если требуется
            if start_now:
                start_success = self.start_network(network_name)
                if not start_success:
                    self.logger.error(f"Не удалось запустить сеть '{network_name}'")
                    # Автозапуск все равно настроен, но возвращаем False
                    return False

                self.logger.info(
                    f"Сеть '{network_name}' запущена и настроен автозапуск "
                    f"(тип: {network_info.network_type.type})"
                )
            else:
                self.logger.info(
                    f"Для сети '{network_name}' настроен автозапуск "
                    f"(тип: {network_info.network_type.type}, "
                    f"активна: {network_info.active})"
                )

            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка включения сети '{network_name}' с автозапуском: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при включении сети '{network_name}': {e}")
            return False


if __name__ == "__main__":
    # Пример использования
    with NetworkManager().with_default_user() as nm:
        print("=== Сводка по сетям ===")
        # print("СЕТЬ ВИДНА ?: ", nm.is_network_visible("test-nat-network"))
        summary = nm.get_network_summary()
        print(f"Всего сетей: {summary['total']}")
        print(f"Активных: {summary['active']}, Неактивных: {summary['inactive']}")
        print("По типам:")
        for net_type, count in summary['by_type'].items():
            print(f"  - {net_type}: {count}")


        print("\n=== Подробная информация о сетях ===")
        for network in nm.list_all_networks():
            print(f"\nСеть: {network.name}")
            print(f"  Тип: {network.network_type.type}")
            print(f"  Описание: {network.network_type.description}")
            print(f"  UUID: {network.uuid}")
            print(f"  Мост: {network.bridge_name or 'Нет'}")
            print(f"  Активна: {network.active}")
            print(f"  Автозапуск: {network.autostart}")
            print(f"  IPv4: {network.network_type.has_ipv4}")
            print(f"  IPv6: {network.network_type.has_ipv6}")
            print(f"  DHCP: {network.network_type.has_dhcp}")
            # if network.name != "default":
            #     nm.delete_network(network.name, str(uuid.uuid4()), force=True)

        # # Пример создания разных типов сетей

        # simple_nat_params = NetworkParameters(
        #     name="simple-nat-network",
        #     forward=NetworkForward(mode="nat"),
        #     bridge=NetworkBridge(name="virbr-simple-nat"),
        #     ipv4=True,
        #     ipv4_address="192.168.123.0/24",
        #     # DHCP будет использовать автоматический диапазон по умолчанию
        # )

        # print("\n=== Пример создания различных типов сетей ===")
        #
        # 1. NAT сеть
        # nat_params = NetworkParameters(
        #     name="test-nat-network-2",
        #     forward=NetworkForward(mode="nat"),
        #     bridge=NetworkBridge(name="virbr-test-ntt"),
        #     ipv4_address="192.168.100.0/24",
        #     dhcp_ranges=[
        #         NetworkDHCPRange(start="192.168.100.100", end="192.168.100.200")
        #     ]
        # )
        # nm.delete_network("nat-network")

        # # 2. Изолированная сеть
        # isolated_params = NetworkParameters(
        #     name="test-isolated-network",
        #     isolated=True,
        #     bridge=NetworkBridge(name="virbr-test-isolated"),
        #     ipv4_address="192.168.101.0/24"
        # )
        #
        # # 3. Bridge сеть
        # bridge_params = NetworkParameters(
        #     name="test-bridge-network",
        #     forward=NetworkForward(mode="bridge", dev="eth0"),
        #     bridge=NetworkBridge(name="virbr-test-bridge")
        # )
        #
        # # 4. Сеть без форвардинга
        # no_forward_params = NetworkParameters(
        #     name="test-no-forward-network",
        #     bridge=NetworkBridge(name="virbr-test-noforward"),
        #     ipv4_address="192.168.102.0/24"
        # )
        #
        # # Удаляем тестовые сети если они существуют
        # for network_name in ["test-nat-network", "test-isolated-network",
        #                      "test-bridge-network", "test-no-forward-network"]:
        #     try:
        #         network = nm.conn.networkLookupByName(network_name)
        #         nm.delete_network(network_name, force=True)
        #     except:
        #         pass
        #
        # # Создаем тестовые сети
        # print("\nСоздание NAT сети...")
        # if nm.create_network(nat_params):
        #     print("NAT сеть создана")
        #
        # print("\nСоздание изолированной сети...")
        # if nm.create_network(isolated_params):
        #     print("Изолированная сеть создана")
        #
        # print("\nСоздание bridge сети...")
        # if nm.create_network(bridge_params):
        #     print("Bridge сеть создана")
        #
        # print("\nСоздание сети без форвардинга...")
        # if nm.create_network(no_forward_params):
        #     print("Сеть без форвардинга создана")
        #
        # # Выводим обновленную сводку
        # print("\n=== Обновленная сводка ===")
        # updated_summary = nm.get_network_summary()
        # for net_type, count in updated_summary['by_type'].items():
        #     print(f"{net_type}: {count}")
        #
        # # Удаляем тестовые сети
        # print("\n=== Очистка тестовых сетей ===")
        # for network_name in ["test-nat-network", "test-isolated-network",
        #                      "test-bridge-network", "test-no-forward-network"]:
        #     nm.delete_network(network_name, force=True)
        #     print(f"Сеть '{network_name}' удалена")