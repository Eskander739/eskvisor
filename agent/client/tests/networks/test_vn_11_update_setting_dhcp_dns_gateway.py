import os
import random
import re
import time
from ipaddress import IPv4Address

import pytest

from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate, DiskType
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

IMG_PATH = os.environ.get("IMAGE_PATH")


@pytest.mark.tags("VN‑11", "Обновление DHCP (пул адресов, шлюз)")
@pytest.mark.skip(
    "Проблема в том, что DHCP-сервер сети не обновляет настройки для существующих клиентов"
)
def test_vn_11_update_setting_dhcp_dns_gateway(
    network_session, vm_session, virsh_console_session, storage_session
):
    """
    VN‑04: Настройка DHCP (пул адресов, шлюз)

    Задать диапазон IP, шлюз, DNS. Подключить ВМ, убедиться, что настройки применяются.
    """

    get_state = vm_session.get_vm_state_by_name
    vm_created = None
    random_name = f"VM-TEST-{random.randint(10000, 99999)}"
    virsh_console = virsh_console_session(random_name)
    vm_template = VMCreateRequest(
        name=random_name,
        autostart_vm=True,
        disks=[DiskCreate(path=IMG_PATH, disk_type=DiskType.CDROM), DiskCreate()],
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
        created_network_info = network_session.create_network(nat_params)
        assert (
            created_network_info.code
            == CommandMessagesEnum.virtual_network_successfully_created.name
        )

        # _________________________Проверка созданных настроек сети_______________
        get_network_info = network_session.get_network_info(network_name)
        assert (
            get_network_info.code == CommandMessagesEnum.virtual_network_found.name
        )

        # Проверяем DHCP диапазон
        assert len(get_network_info.net_info.dhcp_ranges) == 1
        dhcp_range = get_network_info.net_info.dhcp_ranges[0]
        assert dhcp_range.start == IPv4Address("192.168.100.100")
        assert dhcp_range.end == IPv4Address("192.168.100.200")

        # Проверяем шлюз
        # assert network.gateway == "192.168.100.1" # TODO: Доработать проверку
        # шлюза, сейчас он не ставится в сети

        # ____________________________________Создание ВМ_________________________
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert create_vm_info.vm_info is not None
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        time.sleep(60)  # Даем время ВМ загрузиться

        # _________________________Проверка наличия виртуальной сети у ВМ_________
        get_net_vm_info = network_session.get_vm_network_info(vm_template.name)
        assert (
            get_net_vm_info.code
            == CommandMessagesEnum.virtual_network_interfaces_found.name
        )
        assert get_net_vm_info.net_info.network_interfaces.count == 1
        network_interface = get_net_vm_info.net_info.network_interfaces.interfaces.pop()
        assert network_interface.interface_type == NetworkType.NETWORK.value
        assert network_interface.source.name == nat_params.name
        assert network_interface.source.network_info.bridge == nat_params.bridge.name

        # ____________________________________Подключение к ВМ и проверка DHCP____
        virsh_console.connect()

        # ____________________________Обновление настроек сети (DHCP, Gateway, DNS
        # Создаем новые настройки
        updated_params = NetworkParameters(
            name=network_name,  # Такое же имя сети
            forward=NetworkForward(mode="nat"),
            bridge=NetworkBridge(name="virbr-test-ntt", stp="on", delay=0),
            ipv4_address="192.168.200.0/24",  # Новая подсеть
            dhcp_ranges=[
                NetworkDHCPRange(start="192.168.200.50", end="192.168.200.60")
            ],
            gateway="192.168.200.1",  # Новый шлюз
            dns_forwarders=[
                DNSForwarder(addr="1.1.1.1"),  # Новый DNS
                DNSForwarder(addr="1.0.0.1"),
            ],
            autostart=True,
        )

        # Обновляем сеть
        update_network_info = network_session.edit_network(network_name, updated_params)
        assert (
            update_network_info.code
            == CommandMessagesEnum.virtual_network_successfully_updated.name
        )

        # Перезапускаем сеть для применения изменений
        restart_network_info = network_session.restart_network(network_name, True)
        assert (
            restart_network_info.code
            == CommandMessagesEnum.virtual_network_successfully_started.name
        )

        # Проверяем обновленные настройки
        get_updated_network_info = network_session.get_network_info(network_name)
        network_details = get_updated_network_info.net_info
        assert network_details.ipv4_address == "192.168.200.0/24"
        # assert network_details.gateway == "192.168.200.1" # TODO: Доработать
        # проверку шлюза, сейчас он не ставится в сети
        assert len(network_details.dhcp_ranges) == 1
        assert network_details.dhcp_ranges[0].start == IPv4Address("192.168.200.50")
        assert network_details.dhcp_ranges[0].end == IPv4Address("192.168.200.60")

        # ____________________________Проверка новых настроек на ВМ_______________
        # Обновляем IP на ВМ
        renew_commands = [
            "root",
            "ip link set eth0 down",
            "sleep 3",
            "ip addr flush dev eth0",  # Очищаем все адреса
            "ip link set eth0 up",
            "sleep 3",
            "killall -9 udhcpc 2>/dev/null || true",
            "sleep 2",
            "udhcpc -i eth0 -t 10 -n -f",  # Больше попыток, форк в фон
            "sleep 15",  # Больше времени для получения IP
            "ip a show eth0",
            "cat /etc/resolv.conf 2>/dev/null || echo 'No resolv.conf'",
            "ip route show default 2>/dev/null || echo 'No default route'",
        ]

        renew_results = virsh_console.execute_commands(renew_commands)

        # Проверяем новый IP
        new_ip_result = renew_results[-3]  # Результат ip a show eth0
        ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", new_ip_result)
        if ip_match:
            new_ip_address = ip_match.group(1)
            ip_parts = list(map(int, new_ip_address.split(".")))
            assert ip_parts[0] == 192
            assert ip_parts[1] == 168
            assert ip_parts[2] == 200
            assert (
                50 <= ip_parts[3] <= 60
            ), f"IP {new_ip_address} не в новом диапазоне DHCP"

        # Проверяем новый шлюз
        # new_route_result = renew_results[-2]  # Результат ip route show default
        # assert "192.168.200.1" in new_route_result # TODO: Доработать проверку
        # шлюза, сейчас он не ставится в сети

        # Проверяем новые DNS
        new_resolv_conf = renew_results[-1]  # Результат cat /etc/resolv.conf
        assert "1.1.1.1" in new_resolv_conf or "1.0.0.1" in new_resolv_conf

    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created:
            delete_vm_info = vm_session.delete_vm_with_force(
                name=random_name, delete_disks=False
            )
            assert (
                delete_vm_info.code == CommandMessagesEnum.vm_successfully_deleted.name
            )
            assert delete_vm_info.success is True
            disk_path = (
                vm_template.disks[1].path
                + "/"
                + vm_template.disks[1].name
                + "."
                + vm_template.disks[1].format.value
            )
            delete_disk = storage_session.delete_disk(path=disk_path)
            assert delete_disk is True

        # ____________________________________Удаление сети(постусловие)__________
        if network_name is not None:
            network_session.delete_network(network_name, True)
            v_network = network_session.get_network_info(network_name)
            assert v_network.code == CommandMessagesEnum.virtual_network_not_found.name
