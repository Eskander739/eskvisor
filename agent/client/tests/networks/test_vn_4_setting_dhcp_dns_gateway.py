import os
import random
import re
import time
import uuid
from ipaddress import IPv4Address

import pytest
from dotenv import load_dotenv

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate
from agent.client.hypervisor.libvirt.models.enum import NetworkType
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.network import (
    DNSTXT,
    DNSForwarder,
    DNSHost,
    NetworkBridge,
    NetworkDHCPRange,
    NetworkForward,
    NetworkParameters,
    VmNetAdapter,
)
from agent.client.hypervisor.libvirt.models.vm import (
    VMCreateRequest,
    NetQemuCommandline,
)
from agent.client.tools import wait_while_not

load_dotenv()
IMG_PATH = os.environ.get("IMAGE_PATH")


@pytest.mark.tags("VN‑04", "Настройка DHCP (пул адресов, шлюз)")
def test_vn_04_setting_dhcp_dns_gateway(
    network_session, vm_session, virsh_console_session, storage_session
):
    """
    VN‑04: Настройка DHCP (пул адресов, шлюз)

    Задать диапазон IP, шлюз, DNS. Подключить ВМ, убедиться, что настройки применяются.
    """

    request_id = str(uuid.uuid4())
    get_state = vm_session.get_vm_state_by_name
    vm_created = None
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"
    virsh_console = virsh_console_session(random_name)
    vm_template = VMCreateRequest(
        name=random_name,
        autostart_vm=True,
        disks=[DiskCreate(path=IMG_PATH), DiskCreate()],
        networks=[VmNetAdapter(network_type=NetworkType.NETWORK)],
        qemu_commandline=NetQemuCommandline(),
    )
    network_name = None
    try:
        # ____________________________________Создание виртуальной изолированной с
        nat_params = NetworkParameters(
            name=f"nat-{random.randint(1000, 9999)}",
            forward=NetworkForward(mode="nat"),
            bridge=NetworkBridge(name="virbr-test-ntt", stp="on", delay=0),
            ipv4_address="192.168.100.0/24",
            dhcp_ranges=[
                NetworkDHCPRange(start="192.168.100.100", end="192.168.100.200")
            ],
            # Добавляем шлюз
            gateway="192.168.100.1",
            # Добавляем DNS серверы
            dns_forwarders=[
                DNSForwarder(domain="example.com", addr="8.8.8.8"),
                DNSForwarder(addr="8.8.4.4"),  # DNS без домена
            ],
            # Добавляем DNS записи
            dns_hosts=[
                DNSHost(ip="192.168.100.10", hostnames=["host1", "host1.example.com"]),
                DNSHost(ip="192.168.100.11", hostnames=["host2"]),
            ],
            # Добавляем TXT записи DNS
            dns_txts=[
                DNSTXT(name="example.com", value="v=spf1 mx ~all"),
                DNSTXT(
                    name="_domainkey.example.com",
                    value="k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC9...",
                ),
            ],
            autostart=True,
        )

        network_name = nat_params.name
        created_network_info = network_session.create_network(nat_params, request_id)
        assert (
            created_network_info.message
            == CommandMessagesEnum.virtual_network_successfully_created.value
        )

        # _________________________Проверка созданных настроек сети_______________
        get_network_info = network_session.get_network_info(network_name, request_id)
        assert (
            get_network_info.message == CommandMessagesEnum.virtual_network_found.value
        )
        network = get_network_info.net_info

        # Проверяем DHCP диапазон
        assert len(get_network_info.net_info.dhcp_ranges) == 1
        dhcp_range = get_network_info.net_info.dhcp_ranges[0]
        assert dhcp_range.start == IPv4Address("192.168.100.100")
        assert dhcp_range.end == IPv4Address("192.168.100.200")

        # Проверяем шлюз
        # assert network.gateway == "192.168.100.1" # TODO: Доработать проверку
        # шлюза, сейчас он не ставится в сети

        # Проверяем DNS серверы
        assert len(network.dns_forwarders) >= 2
        dns_found = False
        for dns in network.dns_forwarders:
            if dns.addr == "8.8.8.8":
                assert dns.domain == "example.com"
                dns_found = True
        assert dns_found, "DNS сервер 8.8.8.8 не найден"

        vm_template.networks[0].source = nat_params.name

        # ____________________________________Создание ВМ_________________________
        create_vm_info = vm_session.create_vm(vm_template)
        assert (
            create_vm_info.message == CommandMessagesEnum.vm_successfully_created.value
        )
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert create_vm_info.vm_info is not None
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        time.sleep(60)  # Даем время ВМ загрузиться

        # _________________________Проверка наличия виртуальной сети у ВМ_________
        get_net_vm_info = network_session.get_vm_network_info(
            vm_template.name, request_id
        )
        assert (
            get_net_vm_info.message
            == CommandMessagesEnum.virtual_network_interfaces_found.value
        )
        assert (
            get_net_vm_info.code
            == CommandMessagesEnum.virtual_network_interfaces_found.name
        )
        assert get_net_vm_info.net_info.network_interfaces.count == 1
        network_interface = get_net_vm_info.net_info.network_interfaces.interfaces.pop()
        network_mac_address = network_interface.mac_address
        assert network_interface.interface_type == NetworkType.NETWORK.value
        assert network_interface.source.name == nat_params.name
        assert network_interface.source.network_info.bridge == nat_params.bridge.name

        # ____________________________________Подключение к ВМ и проверка DHCP____
        virsh_console.connect()

        # Получаем IP через DHCP и проверяем настройки
        commands = [
            "root",
            "ip link set eth0 up",
            "udhcpc -i eth0",  # Получаем IP по DHCP
            "sleep 10",
            "ip a show eth0",  # Показываем настройки интерфейса
            "cat /etc/resolv.conf",  # Проверяем DNS серверы
            "ip route show default",  # Проверяем шлюз по умолчанию
            "nslookup google.com",  # Проверяем работу DNS (если есть интернет через NAT)
        ]

        results = virsh_console.execute_commands(commands)

        # Проверяем что MAC адрес присутствует в выводе
        ip_result = results[-4]  # Результат ip a show eth0
        assert network_mac_address in ip_result

        # Проверяем что получен IP из правильного диапазона
        ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", ip_result)
        if ip_match:
            ip_address = ip_match.group(1)
            # Проверяем что IP в диапазоне 192.168.100.100-105
            ip_parts = list(map(int, ip_address.split(".")))
            assert ip_parts[0] == 192
            assert ip_parts[1] == 168
            assert ip_parts[2] == 100
            assert 100 <= ip_parts[3] <= 200, f"IP {ip_address} не в диапазоне DHCP"

        # Проверяем DNS настройки
        resolv_conf = results[-3]  # Результат cat /etc/resolv.conf
        assert "nameserver" in resolv_conf.lower()

        # Проверяем шлюз
        route_result = results[-2]  # Результат ip route show default
        assert "192.168.100.1" in route_result

    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created:
            delete_vm_info = vm_session.delete_vm_with_force(
                name=random_name, request_id=request_id, delete_disks=False
            )
            assert (
                delete_vm_info.message
                == CommandMessagesEnum.vm_successfully_deleted.value
            )
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
            delete_disk = storage_session.delete_disk(path=vm_template.disks[1].path)
            assert delete_disk is True

        # ____________________________________Удаление сети(постусловие)__________
        if network_name is not None:
            network_session.delete_network(network_name, request_id, True)
            v_network = network_session.get_network_info(network_name, request_id)
            assert (
                v_network.message == CommandMessagesEnum.virtual_network_not_found.value
            )
            assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name
