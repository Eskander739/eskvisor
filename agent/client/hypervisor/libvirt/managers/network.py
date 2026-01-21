import ipaddress
import subprocess
from xml.etree import ElementTree as ET

import libvirt

from agent.client.cli import CLIControl
from agent.client.constants import NETWORK_TYPE_DESCRIPTIONS
from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.models.msg import (
    CommandMessagesEnum,
    NetworkMessage,
)
from agent.client.hypervisor.libvirt.models.network import (
    DNSTXT,
    DNSForwarder,
    DNSHost,
    NetworkInfo,
    NetworkInterfacesInfo,
    NetworkInterfacesList,
    NetworkParameters,
    NetworkTypeInfo,
    VmInfo,
    NetworkList,
)
from agent.client.logger_config import DefaultLogger


class NetworkManager(LibvirtClient):
    """
    Управление сетевыми интерфейсами
    """

    libvirtError = None

    def __init__(self):
        super().__init__()
        self.cli = CLIControl()
        self.logger = DefaultLogger("NetworkManager")

    def list_networks(self) -> list[str]:
        """Получение списка сетей"""
        try:
            networks = self.conn.listNetworks()
            return networks
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения списка сетей: {e}")
            return []

    def create_network(self, params: NetworkParameters) -> NetworkMessage:
        """Создание виртуальной сети"""
        try:
            # Определяем тип сети перед созданием
            network_type_info = self._determine_network_type(params)
            self.logger.info(
                f"Создание сети '{params.name}' типа '{network_type_info.type}' "
                f"({network_type_info.description})"
            )

            # Дополнительная валидация для bridge сетей
            if network_type_info.type == "bridge" and (
                params.dhcp_ranges or params.dhcp_hosts
            ):
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

            created_network = self.get_network_info(params.name)
            assert (
                created_network.code == CommandMessagesEnum.virtual_network_found.name
            )
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_successfully_created.name,
                net_info=created_network.net_info,
                success=True,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка создания сети '{params.name}': {e}")
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_create_error.name,
                success=False,
                note=str(e),
            )
        except Exception as e:
            self.logger.error(
                f"Неожиданная ошибка при создании сети '{params.name}': {e}"
            )
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_create_error.name,
                success=False,
                note=str(e),
            )

    def _has_vms_connected_to_network(self, network_name: str) -> bool:
        """
        Простая проверка через список всех ВМ с фильтрацией по сети
        """
        try:
            # Получаем все запущенные ВМ
            domains = self.conn.listAllDomains(libvirt.VIR_CONNECT_LIST_DOMAINS_RUNNING)

            for domain in domains:
                try:
                    # Получаем XML ВМ
                    xml_desc = domain.XMLDesc(0)

                    # Быстрая проверка строкой
                    if f"<source network='{network_name}'" in xml_desc:
                        return True

                    # Альтернативный формат (без кавычек)
                    if f"<source network={network_name}" in xml_desc:
                        return True

                except BaseException:
                    continue

            return False

        except Exception as e:
            self.logger.debug(f"Ошибка проверки ВМ в сети '{network_name}': {e}")
            return False

    def delete_network(
        self,
        network_name: str,
        force: bool = False,
        approve_admin: bool = False,
    ) -> NetworkMessage:
        """Удаление виртуальной сети"""
        try:
            network = self.conn.networkLookupByName(network_name)

            # Получаем информацию о типе сети перед удалением
            network_type = self._get_network_type_from_xml(network.XMLDesc(0))
            if self._has_vms_connected_to_network(network_name) and not approve_admin:
                self.logger.info(
                    f"Сеть '{network_name}' (тип: {network_type}) не может быть удалена с подключенными ВМ без подтверждения администратора"
                )
                return NetworkMessage(
                    code=CommandMessagesEnum.virtual_network_have_connected_vms.name,
                    success=False,
                )

            if network.isActive():
                if force:
                    network.destroy()
                    self.logger.info(
                        f"Сеть '{network_name}' (тип: {network_type}) остановлена перед удалением"
                    )
                else:
                    self.logger.error(
                        f"Сеть '{network_name}' активна. Используйте force=True для принудительного удаления"
                    )
                    return NetworkMessage(
                        code=CommandMessagesEnum.virtual_network_delete_error.name,
                        success=False,
                        note="use force=True for force delete",
                    )

            network.undefine()
            self.logger.info(
                f"Сеть '{network_name}' (тип: {network_type}) успешно удалена"
            )
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_successfully_deleted.name,
                success=True,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления сети '{network_name}': {e}")
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_delete_error.name,
                success=False,
                note=str(e),
            )

    def restart_network(self, network_name: str, force: bool = False) -> NetworkMessage:
        """Перезапуск виртуальной сети с опциональной проверкой подключенных ВМ"""
        try:
            network = self.conn.networkLookupByName(network_name)
            network_type = self._get_network_type_from_xml(network.XMLDesc(0))

            # Проверяем, есть ли подключенные ВМ (если не force)
            if not force and self._has_vms_connected_to_network(network_name):
                self.logger.warning(
                    f"Сеть '{network_name}' имеет подключенные ВМ. Используйте force=True для принудительного перезапуска"
                )
                return NetworkMessage(
                    code=CommandMessagesEnum.virtual_network_have_connected_vms.name,
                    success=False,
                    note="Network has connected VMs, use force=True to restart anyway",
                )

            # Если сеть активна, останавливаем
            was_active = network.isActive()
            if was_active:
                network.destroy()
                self.logger.info(
                    f"Сеть '{network_name}' (тип: {network_type}) остановлена для перезапуска"
                )
                import time

                time.sleep(2)  # Даем время для корректного завершения

            # Запускаем сеть
            network.create()
            self.logger.info(
                f"Сеть '{network_name}' (тип: {network_type}) запущена {'после перезапуска' if was_active else ''}"
            )

            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_successfully_started.name,
                success=True,
                note=f"Сеть '{network_name}' успешно {'перезапущена' if was_active else 'запущена'}",
            )

        except libvirt.libvirtError as e:
            self.logger.error(f"Ошибка перезапуска сети '{network_name}': {e}")
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_restart_error.name,
                success=False,
                note=str(e),
            )

    def edit_network(
        self, network_name: str, params: NetworkParameters
    ) -> NetworkMessage:
        """Редактирование виртуальной сети"""
        old_xml = None
        autostart = None
        was_active = None
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

            # Сохраняем важные параметры старой сети
            was_active = network.isActive()
            autostart = network.autostart()
            old_uuid = network.UUIDString()

            # Сохраняем старую XML для возможного восстановления
            old_xml = network.XMLDesc(0)

            # Если сеть активна, деактивируем её для редактирования
            if was_active:
                network.destroy()
                self.logger.info(
                    f"Сеть '{network_name}' остановлена для редактирования"
                )
                import time

                time.sleep(1)  # Даем время для корректного завершения

            # ⭐ ВАЖНО: УДАЛЯЕМ старую сеть перед созданием новой ⭐
            network.undefine()
            self.logger.debug(f"Старая сеть '{network_name}' удалена")

            # Генерируем новую XML конфигурацию
            # Сохраняем UUID для совместимости с существующими ВМ
            if not params.uuid:
                params.uuid = old_uuid

            xml_config = self._generate_network_xml(params)

            # Определяем сеть с новой конфигурацией
            new_network = self.conn.networkDefineXML(xml_config)

            # Восстанавливаем состояние автозапуска
            new_network.setAutostart(autostart)

            # Если сеть была активна, активируем её
            if was_active:
                new_network.create()
                self.logger.info(f"Сеть '{params.name}' запущена после редактирования")

            self.logger.info(
                f"Сеть успешно отредактирована: '{network_name}' -> '{params.name}' "
                f"(тип изменен: {old_type} -> {new_type_info.type})"
            )

            # Получаем информацию об обновленной сети
            updated_info = self.get_network_info(params.name)

            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_successfully_updated.name,
                success=True,
                net_info=updated_info.net_info if updated_info.success else None,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка редактирования сети '{network_name}': {e}")

            # Попытка восстановить оригинальную сеть в случае ошибки
            try:
                if old_xml is not None:
                    self.logger.warning(
                        f"Попытка восстановления оригинальной сети '{network_name}'"
                    )
                    self.conn.networkDefineXML(old_xml)
                    restored = self.conn.networkLookupByName(network_name)
                    restored.setAutostart(autostart if autostart is not None else True)
                    if was_active if was_active is not None else False:
                        restored.create()
            except Exception as restore_error:
                self.logger.error(f"Не удалось восстановить сеть: {restore_error}")

            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_update_error.name,
                success=False,
                note=str(e),
            )

    def get_network_info(self, network_name: str) -> NetworkMessage:
        """Получение информации о сети"""
        try:
            network = self.conn.networkLookupByName(network_name)
            xml_desc = network.XMLDesc(0)

            # Определяем тип сети из XML
            network_type_info = self._get_network_type_info_from_xml(xml_desc)

            # Парсим дополнительные настройки из XML
            parsed_settings = self._parse_network_xml_settings(xml_desc)
            info = NetworkInfo(
                name=network.name(),
                uuid=network.UUIDString(),
                bridge_name=(
                    network.bridgeName() if hasattr(network, "bridgeName") else None
                ),
                active=network.isActive(),
                persistent=network.isPersistent(),
                autostart=network.autostart(),
                network_type=network_type_info,
                xml=xml_desc,
                gateway=parsed_settings.get("gateway"),
                dns_forwarders=parsed_settings.get("dns_forwarders", []),
                dns_hosts=parsed_settings.get("dns_hosts", []),
                dns_txts=parsed_settings.get("dns_txts", []),
                ipv4_address=parsed_settings.get("ipv4_address"),
                dhcp_ranges=parsed_settings.get("dhcp_ranges", []),
            )

            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_found.name,
                success=True,
                net_info=info,
            )

        except self.libvirtError as e:
            self.logger.error(
                f"Ошибка получения информации о сети '{network_name}': {e}"
            )
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_not_found.name,
                success=False,
                note=str(e),
            )

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

        # Форвардинга
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
            ET.SubElement(root, "mtu", size=str(params.mtu))

        # Trust guest RX filters
        if params.trust_guest_rx_filters:
            ET.SubElement(root, "trustGuestRxFilters")

        # IP конфигурация
        if params.ipv4 and params.ipv4_address:
            ip_elem = ET.SubElement(root, "ip")
            ip_elem.set(
                "address",
                str(ipaddress.ip_network(str(params.ipv4_address)).network_address),
            )
            ip_elem.set(
                "prefix", str(ipaddress.ip_network(str(params.ipv4_address)).prefixlen)
            )
            ip_elem.set("family", "ipv4")
            # Gateway
            if params.gateway:
                gateway_elem = ET.SubElement(ip_elem, "gateway")
                gateway_elem.set("addr", params.gateway)

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
            ip6_elem.set(
                "address",
                str(ipaddress.ip_network(str(params.ipv6_address)).network_address),
            )
            ip6_elem.set(
                "prefix", str(ipaddress.ip_network(str(params.ipv6_address)).prefixlen)
            )
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

        # DNS конфигурация - используем новые поля dns_forwarders, dns_hosts, dns_txts
        dns_elem = None

        # Создаем элемент DNS, если есть любые DNS настройки
        if (
            params.dns_forwarders
            or params.dns_hosts
            or params.dns_txts
            or params.dns
            and (params.dns.forwarders or params.dns.hosts or params.dns.txt_records)
        ):
            dns_elem = ET.SubElement(root, "dns")

            # Обрабатываем новые DNS forwarders
            if params.dns_forwarders:
                for forwarder in params.dns_forwarders:
                    forwarder_elem = ET.SubElement(dns_elem, "forwarder")
                    forwarder_elem.set("addr", forwarder.addr)
                    if forwarder.domain:
                        forwarder_elem.set("domain", forwarder.domain)

            # Обрабатываем новые DNS hosts
            if params.dns_hosts:
                for host in params.dns_hosts:
                    host_elem = ET.SubElement(dns_elem, "host")
                    host_elem.set("ip", host.ip)
                    for hostname in host.hostnames:
                        hostname_elem = ET.SubElement(host_elem, "hostname")
                        hostname_elem.text = hostname

            # Обрабатываем новые DNS TXT записи
            if params.dns_txts:
                for txt in params.dns_txts:
                    txt_elem = ET.SubElement(dns_elem, "txt")
                    txt_elem.set("name", txt.name)
                    txt_elem.set("value", txt.value)

        # Обрабатываем старые DNS настройки (для обратной совместимости)
        if params.dns and dns_elem is not None:
            # Старые forwarders
            if params.dns.forwarders:
                for forwarder in params.dns.forwarders:
                    forwarder_elem = ET.SubElement(dns_elem, "forwarder")
                    forwarder_elem.set("addr", str(forwarder))

            # Старые hosts
            if params.dns.hosts:
                for host in params.dns.hosts:
                    host_elem = ET.SubElement(dns_elem, "host")
                    host_elem.set("ip", str(host.ip))
                    if host.hostnames:
                        for hostname in host.hostnames:
                            hostname_elem = ET.SubElement(host_elem, "hostname")
                            hostname_elem.text = hostname

            # Старые TXT записи
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

            # Domain и local_only
            if params.dns.domain:
                domain_elem = ET.SubElement(dns_elem, "domain")
                domain_elem.set("name", params.dns.domain)
                if params.dns.local_only:
                    domain_elem.set("localOnly", "yes")

        # Изолированная сеть
        if params.isolated:
            ET.SubElement(root, "isolated")

        # Преобразуем в строку
        xml_str = ET.tostring(root, encoding="unicode")

        # Добавляем XML заголовок
        xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
        return xml_header + xml_str

    def _parse_network_xml_settings(self, xml_desc: str) -> dict:
        """Парсинг дополнительных настроек из XML сети"""
        try:
            root = ET.fromstring(xml_desc)
            settings = {
                "gateway": None,
                "dns_forwarders": [],
                "dns_hosts": [],
                "dns_txts": [],
                "ipv4_address": None,
                "dhcp_ranges": [],
            }

            # Парсим gateway из элемента ip
            ip_elem = root.find(".//ip[@family='ipv4']")
            if ip_elem is not None:
                gateway_elem = ip_elem.find("gateway")
                if gateway_elem is not None:
                    settings["gateway"] = gateway_elem.get("addr")

                # Парсим IPv4 адрес
                address = ip_elem.get("address")
                prefix = ip_elem.get("prefix")
                if address and prefix:
                    settings["ipv4_address"] = f"{address}/{prefix}"

            # Парсим DHCP диапазоны
            dhcp_elem = root.find(".//dhcp")
            if dhcp_elem is not None:
                for range_elem in dhcp_elem.findall("range"):
                    start = range_elem.get("start")
                    end = range_elem.get("end")
                    if start and end:
                        settings["dhcp_ranges"].append({"start": start, "end": end})

            # Парсим DNS настройки
            dns_elem = root.find("dns")
            if dns_elem is not None:
                # Парсим forwarders
                for forwarder_elem in dns_elem.findall("forwarder"):
                    domain = forwarder_elem.get("domain")
                    addr = forwarder_elem.get("addr")
                    if addr:
                        settings["dns_forwarders"].append(
                            DNSForwarder(domain=domain, addr=addr)
                        )

                # Парсим hosts
                for host_elem in dns_elem.findall("host"):
                    ip = host_elem.get("ip")
                    hostnames = []
                    for hostname_elem in host_elem.findall("hostname"):
                        if hostname_elem.text:
                            hostnames.append(hostname_elem.text)

                    if ip and hostnames:
                        settings["dns_hosts"].append(
                            DNSHost(ip=ip, hostnames=hostnames)
                        )

                # Парсим TXT записи
                for txt_elem in dns_elem.findall("txt"):
                    name = txt_elem.get("name")
                    value = txt_elem.get("value")
                    if name and value:
                        settings["dns_txts"].append(DNSTXT(name=name, value=value))

            return settings

        except ET.ParseError as e:
            self.logger.error(f"Ошибка парсинга XML настроек сети: {e}")
            return {}

    def set_network_autostart(self, network_name: str, autostart: bool = True) -> bool:
        """Настройка автозапуска сети"""
        try:
            current_network = self.conn.networkLookupByName(network_name)
            network_type = self._get_network_type_from_xml(current_network.XMLDesc(0))
            current_network.setAutostart(autostart)
            self.logger.info(
                f"Автозапуск сети '{network_name}' (тип: {network_type}) "
                f"установлен в {autostart}"
            )
            return True

        except self.libvirtError as e:
            self.logger.error(
                f"Ошибка установки автозапуска для сети '{network_name}': {e}"
            )
            return False

    def start_network(self, network_name: str) -> NetworkMessage:
        """Запуск сети"""
        try:
            current_network = self.conn.networkLookupByName(network_name)
            network_type = self._get_network_type_from_xml(current_network.XMLDesc(0))

            if not current_network.isActive():
                current_network.create()
                self.logger.info(
                    f"Сеть '{network_name}' (тип: {network_type}) запущена"
                )
                return NetworkMessage(
                    code=CommandMessagesEnum.virtual_network_successfully_started.name,
                    success=True,
                )
            else:
                self.logger.info(
                    f"Сеть '{network_name}' (тип: {network_type}) уже запущена"
                )
                return NetworkMessage(
                    code=CommandMessagesEnum.virtual_network_already_started.name,
                    success=True,
                )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка запуска сети '{network_name}': {e}")
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_start_error.name,
                success=False,
            )

    def stop_network(self, network_name: str) -> NetworkMessage:
        """Остановка сети"""
        try:
            network = self.conn.networkLookupByName(network_name)
            network_type = self._get_network_type_from_xml(network.XMLDesc(0))

            if network.isActive():
                network.destroy()
                self.logger.info(
                    f"Сеть '{network_name}' (тип: {network_type}) остановлена"
                )
                return NetworkMessage(
                    code=CommandMessagesEnum.virtual_network_successfully_stopped.name,
                    success=True,
                )
            else:
                self.logger.info(
                    f"Сеть '{network_name}' (тип: {network_type}) уже остановлена"
                )
                return NetworkMessage(
                    code=CommandMessagesEnum.virtual_network_already_stopped.name,
                    success=True,
                )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка остановки сети '{network_name}': {e}")
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_stopping_error.name,
                success=False,
            )

    def list_all_networks(self) -> NetworkMessage:
        """Получение полного списка всех сетей с информацией"""
        networks_info = []
        try:
            # Получаем все сети (флаг 0 - все сети)
            networks = self.conn.listAllNetworks(0)

            for network in networks:
                try:
                    xml_desc = network.XMLDesc(0)
                    network_type_info = self._get_network_type_info_from_xml(xml_desc)

                    # Парсим дополнительные настройки
                    parsed_settings = self._parse_network_xml_settings(xml_desc)

                    info = NetworkInfo(
                        name=network.name(),
                        uuid=network.UUIDString(),
                        bridge_name=(
                            network.bridgeName()
                            if hasattr(network, "bridgeName")
                            else None
                        ),
                        active=network.isActive(),
                        persistent=network.isPersistent(),
                        autostart=network.autostart(),
                        network_type=network_type_info,
                        xml=xml_desc,
                        gateway=parsed_settings.get("gateway"),
                        dns_forwarders=parsed_settings.get("dns_forwarders", []),
                        dns_hosts=parsed_settings.get("dns_hosts", []),
                        dns_txts=parsed_settings.get("dns_txts", []),
                        ipv4_address=parsed_settings.get("ipv4_address"),
                        dhcp_ranges=parsed_settings.get("dhcp_ranges", []),
                    )

                    networks_info.append(info)
                except Exception as e:
                    self.logger.warning(
                        f"Ошибка получения информации о сети {network.name()}: {e}"
                    )

            return NetworkMessage(
                success=True,
                code=CommandMessagesEnum.networks_list_found.name,
                net_info=NetworkList(items=networks_info, total=len(networks_info)),
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения полного списка сетей: {e}")
            return NetworkMessage(
                success=False,
                code=CommandMessagesEnum.networks_list_not_found.name,
                net_info=NetworkList(items=[], total=0),
            )

    @staticmethod
    def _determine_network_type(params: NetworkParameters) -> NetworkTypeInfo:
        """Определение типа сети на основе параметров"""
        # Определяем базовые характеристики
        has_ipv4 = params.ipv4 and params.ipv4_address is not None
        has_ipv6 = params.ipv6 and params.ipv6_address is not None
        has_dhcp = bool(params.dhcp_ranges or params.dhcp_hosts)
        has_bridge = params.bridge is not None

        # Определяем основной тип сети
        if params.isolated:
            network_type = "isolated"
        elif params.forward:
            network_type = params.forward.mode
        else:
            network_type = "no-forward"

        # Получаем описание типа
        description = NETWORK_TYPE_DESCRIPTIONS.get(
            network_type, f"Неизвестный тип сети: {network_type}"
        )

        return NetworkTypeInfo(
            type=network_type,
            is_isolated=params.isolated or False,
            has_dhcp=has_dhcp,
            has_ipv4=has_ipv4,
            has_ipv6=has_ipv6,
            has_bridge=has_bridge,
            description=description,
        )

    def _get_network_type_from_xml(self, xml_desc: str) -> str:
        """Получение типа сети из XML конфигурации"""
        try:
            root = ET.fromstring(xml_desc)

            # Проверяем на изолированную сеть
            isolated_elem = root.find("isolated")
            if isolated_elem is not None:
                return "isolated"

            # Проверяем на наличие forward
            forward_elem = root.find("forward")
            if forward_elem is not None:
                mode = forward_elem.get("mode", "nat")
                return mode

            # Сеть без форвардинга
            return "no-forward"

        except ET.ParseError as e:
            self.logger.error(f"Ошибка парсинга XML при определении типа сети: {e}")
            return "unknown"

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
            isolated_elem = root.find("isolated")
            if isolated_elem is not None:
                network_type = "isolated"
            else:
                forward_elem = root.find("forward")
                if forward_elem is not None:
                    network_type = forward_elem.get("mode", "nat")
                else:
                    network_type = "no-forward"

            # Получаем описание
            description = NETWORK_TYPE_DESCRIPTIONS.get(
                network_type, f"Неизвестный тип сети: {network_type}"
            )

            return NetworkTypeInfo(
                type=network_type,
                is_isolated=isolated_elem is not None,
                has_dhcp=has_dhcp,
                has_ipv4=has_ipv4,
                has_ipv6=has_ipv6,
                has_bridge=has_bridge,
                description=description,
            )

        except ET.ParseError as e:
            self.logger.error(f"Ошибка парсинга XML: {e}")
            return NetworkTypeInfo(
                type="unknown", description="Ошибка определения типа сети"
            )

    def _validate_network_parameters(self, params: NetworkParameters):
        """Дополнительная валидация параметров сети"""
        # Валидация для bridge сетей
        if params.forward and params.forward.mode == "bridge":
            if not params.forward.dev and not params.forward.interface:
                self.logger.warning(
                    f"Bridge сеть '{params.name}': рекомендуется указать dev или interface"
                )

        # Валидация для routed сетей
        if params.forward and params.forward.mode == "route":
            if params.bridge:
                self.logger.warning(
                    f"Routed сеть '{params.name}': параметр bridge обычно не используется"
                )

        # Валидация для NAT сетей
        if params.forward and params.forward.mode == "nat":
            if not params.ipv4_address:
                self.logger.warning(
                    f"NAT сеть '{params.name}': рекомендуется указать ipv4_address"
                )

    def get_network_summary(self) -> dict:
        """Получение сводки по всем сетям"""
        networks = self.list_all_networks().net_info

        summary = {
            "total": networks.total,
            "active": 0,
            "inactive": 0,
            "by_type": {},
            "by_autostart": {"enabled": 0, "disabled": 0},
        }

        for network in networks.items:
            # Подсчет активных/неактивных
            if network.active:
                summary["active"] += 1
            else:
                summary["inactive"] += 1

            # Подсчет по типам
            network_type = network.network_type.type
            if network_type not in summary["by_type"]:
                summary["by_type"][network_type] = 0
            summary["by_type"][network_type] += 1

            # Подсчет по автозапуску
            if network.autostart:
                summary["by_autostart"]["enabled"] += 1
            else:
                summary["by_autostart"]["disabled"] += 1

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

    def enable_network_with_autostart(
        self, network_name: str, start_now: bool = True
    ) -> bool:
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
                self.logger.error(
                    f"Не удалось настроить автозапуск для сети '{network_name}'"
                )
                return False

            # Запускаем сеть, если требуется
            if start_now:
                start_success = self.start_network(network_name)
                if start_success.code not in (
                    CommandMessagesEnum.virtual_network_already_started.name,
                    CommandMessagesEnum.virtual_network_successfully_started.name,
                ):
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
            self.logger.error(
                f"Ошибка включения сети '{network_name}' с автозапуском: {e}"
            )
            return False
        except Exception as e:
            self.logger.error(
                f"Неожиданная ошибка при включении сети '{network_name}': {e}"
            )
            return False

    def get_vm_network_info(self, vm_name: str) -> NetworkMessage:
        """Получить полную информацию о сетевых интерфейсах ВМ в формате JSON"""

        try:
            vm = self.conn.lookupByName(vm_name)
        except libvirt.libvirtError as e:
            return NetworkMessage(
                code=CommandMessagesEnum.vm_found_error.name,
                success=False,
                note=str(e),
            )

        xml_desc = vm.XMLDesc(0)
        root = ET.fromstring(xml_desc)

        interfaces = []

        for iface in root.findall(".//devices/interface"):
            # Определяем драйвер по умолчанию на основе модели
            model = (
                iface.find("model").get("type")
                if iface.find("model") is not None
                else ""
            )

            # Значения драйвера по умолчанию для разных моделей
            default_drivers = {
                "virtio": {"name": "virtio-net-pci", "queues": "1", "iommu": "off"},
                "e1000": {"name": "e1000", "queues": "1", "iommu": "off"},
                "rtl8139": {"name": "rtl8139", "queues": "1", "iommu": "off"},
                "vmxnet3": {"name": "vmxnet3", "queues": "1", "iommu": "off"},
            }

            interface_info = {
                # Основные поля
                "interface_type": iface.get("type", ""),
                "mac_address": (
                    iface.find("mac").get("address")
                    if iface.find("mac") is not None
                    else ""
                ),
                "model": model,
                # Драйвер с подстановкой значений по умолчанию
                "driver": {},
                # Источник подключения
                "source": {},
                "host_interface": (
                    iface.find("target").get("dev")
                    if iface.find("target") is not None
                    else ""
                ),
                # Состояние связи (по умолчанию 'up')
                "link_state": {
                    "state": "up",
                    "description": "Канал активен по умолчанию",
                },
                # Boot order (если не указан, значит не используется для загрузки)
                "boot_order": None,
                "boot_order_description": (
                    "Не используется для PXE загрузки"
                    if iface.find("boot") is None
                    else "Используется для сетевой загрузки"
                ),
                # ROM (по умолчанию отключен)
                "rom_bar": {
                    "enabled": "off",
                    "description": "ROM отключен по умолчанию",
                },
                # Filter (по умолчанию нет фильтрации)
                "filter": {
                    "name": "none",
                    "description": "Фильтрация трафика не настроена",
                },
                # MTU (по умолчанию 1500)
                "mtu": {"size": "1500", "description": "Стандартный MTU по умолчанию"},
                # Коалесцирование (актуально для virtio)
                "coalescing": {
                    "enabled": "false",
                    "description": "Коалесцирование отключено по умолчанию",
                },
            }

            # Заполняем драйвер (явные настройки или значения по умолчанию)
            driver = iface.find("driver")
            if driver is not None:
                # Используем явные настройки
                interface_info["driver"] = {
                    "name": driver.get(
                        "name", default_drivers.get(model, {}).get("name", "unknown")
                    ),
                    "queues": driver.get(
                        "queues", default_drivers.get(model, {}).get("queues", "1")
                    ),
                    "iommu": driver.get(
                        "iommu", default_drivers.get(model, {}).get("iommu", "off")
                    ),
                    "txmode": driver.get("txmode", ""),
                    "rxmode": driver.get("rxmode", ""),
                    "description": "Настройки драйвера из конфигурации",
                }
            else:
                # Используем значения по умолчанию для модели
                interface_info["driver"] = {
                    "name": default_drivers.get(model, {}).get("name", "unknown"),
                    "queues": default_drivers.get(model, {}).get("queues", "1"),
                    "iommu": default_drivers.get(model, {}).get("iommu", "off"),
                    "description": f"Стандартный драйвер для модели {model}",
                }

            source = iface.find("source")
            if source is not None:
                if source.get("network"):
                    interface_info["source"] = {
                        "type": "network",
                        "name": source.get("network"),
                        "description": "Виртуальная сеть libvirt",
                        "network_uuid": self._get_network_uuid(
                            self.conn, source.get("network")
                        ),  # Можно добавить
                    }

            # Проверяем link state
            link = iface.find("link")
            if link is not None:
                interface_info["link_state"] = {
                    "state": link.get("state", "up"),
                    "description": "Явно заданное состояние канала",
                }

            # Проверяем boot
            boot = iface.find("boot")
            if boot is not None:
                interface_info["boot_order"] = boot.get("order")
                interface_info["boot_order_description"] = (
                    f"Порядок загрузки: {boot.get('order')}"
                )

            # Проверяем rom
            rom = iface.find("rom")
            if rom is not None:
                interface_info["rom_bar"] = {
                    "enabled": rom.get("bar", "on"),
                    "file": rom.get("file", ""),
                    "description": "ROM настроен явно",
                }

            # Проверяем фильтр
            filterref = iface.find("filterref")
            if filterref is not None:
                interface_info["filter"] = {
                    "name": filterref.get("filter"),
                    "parameters": {},
                    "description": "Применен сетевой фильтр",
                }
                for param in filterref.findall("parameter"):
                    interface_info["filter"]["parameters"][param.get("name")] = (
                        param.get("value")
                    )

            # Проверяем MTU
            mtu = iface.find("mtu")
            if mtu is not None:
                interface_info["mtu"] = {
                    "size": mtu.get("size"),
                    "description": "MTU задан явно",
                }

            interfaces.append(interface_info)

        # Добавляем информацию о сети
        for iface in interfaces:
            if iface["source"].get("type") == "network":
                network_name = iface["source"]["name"]
                try:
                    network = self.conn.networkLookupByName(network_name)
                    iface["source"]["network_info"] = {
                        "active": network.isActive(),
                        "persistent": network.isPersistent(),
                        "autostart": network.autostart(),
                        "bridge": network.bridgeName() if network.isActive() else None,
                        "uuid": network.UUIDString(),
                    }
                except libvirt.libvirtError:
                    iface["source"]["network_info"] = {"error": "Network not found"}

        net_info = NetworkInterfacesInfo(
            vm_info=VmInfo(
                name=vm_name,
                uuid=vm.UUIDString(),
                state="running" if vm.isActive() else "shut off",
                has_guest_agent=self._check_guest_agent(vm),
            ),
            network_interfaces=NetworkInterfacesList(
                count=len(interfaces), interfaces=interfaces
            ),
        )
        return NetworkMessage(
            code=CommandMessagesEnum.virtual_network_interfaces_found.name,
            net_info=net_info,
            success=True,
        )

    def _get_network_uuid(self, conn, network_name):
        """Получить UUID сети"""
        try:
            current_network = conn.networkLookupByName(network_name)
            return current_network.UUIDString()
        except self.libvirtError:
            return None

    def _check_guest_agent(self, vm):
        """Проверить наличие guest agent"""
        try:
            # Попробовать получить информацию через агент
            vm.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT, 0)
            return True
        except self.libvirtError:
            return False

    def detach_vm_network_interface(
        self,
        vm_name: str,
        mac_address: str,
        persistent: bool = True,
        live: bool = True,
    ) -> NetworkMessage:
        """Отключение сетевого интерфейса от виртуальной машины"""
        try:
            # Проверяем существование ВМ
            try:
                vm = self.conn.lookupByName(vm_name)
            except libvirt.libvirtError as e:
                self.logger.error(f"ВМ '{vm_name}' не найдена: {e}")
                return NetworkMessage(
                    code=CommandMessagesEnum.vm_found_error.name,
                    success=False,
                    note=f"VM not found: {e}",
                )

            # Проверяем существование интерфейса с указанным MAC
            xml_desc = vm.XMLDesc(0)
            root = ET.fromstring(xml_desc)

            interface_found = False
            for iface in root.findall(".//devices/interface"):
                mac_elem = iface.find("mac")
                if mac_elem is not None and mac_elem.get("address") == mac_address:
                    interface_found = True
                    break

            if not interface_found:
                self.logger.error(
                    f"Сетевой интерфейс с MAC '{mac_address}' не найден у ВМ '{vm_name}'"
                )
                return NetworkMessage(
                    code=CommandMessagesEnum.virtual_network_interface_not_found.name,
                    success=False,
                    note=f"Network interface with MAC {mac_address} not found",
                )

            # Строим команду virsh detach-interface
            cmd = [
                "virsh",
                "--connect",
                self.connection_uri,
                "detach-interface",
                vm_name,
                "network",
            ]

            if mac_address:
                cmd.extend(["--mac", mac_address])

            if persistent:
                cmd.append("--persistent")

            if live:
                cmd.append("--live")
            else:
                cmd.append("--config")

            # Выполняем команду
            self.logger.info(
                f"Отключение сетевого интерфейса {mac_address} от ВМ {vm_name}"
            )
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self.logger.info(
                    f"Сетевой интерфейс {mac_address} успешно отключен от ВМ {vm_name}"
                )

                # Получаем обновленную информацию о сетевых интерфейсах ВМ
                network_info = self.get_vm_network_info(vm_name)

                return NetworkMessage(
                    code=CommandMessagesEnum.virtual_network_interface_detached.name,
                    success=True,
                    net_info=network_info.net_info if network_info.success else None,
                    note="Network interface successfully detached",
                )
            else:
                error_msg = result.stderr.strip()
                self.logger.error(
                    f"Ошибка отключения интерфейса {mac_address}: {error_msg}"
                )
                return NetworkMessage(
                    code=CommandMessagesEnum.virtual_network_interface_detach_error.name,
                    success=False,
                    note=error_msg,
                )

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Ошибка выполнения команды detach-interface: {e}")
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_interface_detach_error.name,
                success=False,
                note=str(e),
            )
        except Exception as e:
            self.logger.error(
                f"Неожиданная ошибка при отключении сетевого интерфейса: {e}"
            )
            return NetworkMessage(
                code=CommandMessagesEnum.virtual_network_interface_detach_error.name,
                success=False,
                note=str(e),
            )


if __name__ == "__main__":
    # Пример использования
    with NetworkManager() as nm:
        print("=== Сводка по сетям ===")
        summary = nm.get_network_summary()
        print(f"Всего сетей: {summary['total']}")
        print(f"Активных: {summary['active']}, Неактивных: {summary['inactive']}")
        print("По типам:")
        for net_type, count in summary["by_type"].items():
            print(f"  - {net_type}: {count}")

        print("\n=== Подробная информация о сетях ===")
        for network in nm.list_all_networks().net_info.items:
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
            print(f"  GATEWAY: {network.gateway}")
            print(f"  DNS: {network.dns_forwarders}")
            print(f"  DNS_HOSTS: {network.dns_hosts}")
            print(f"  DNS_TXTS: {network.dns_txts}")
            if network.name != "default":
                nm.delete_network(network.name, force=True)
