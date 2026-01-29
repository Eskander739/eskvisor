import random

import pytest

from agent.client.hypervisor.libvirt.models.enum import NetworkType
from agent.client.hypervisor.libvirt.models.network import NetworkParameters, NetworkForward, NetworkBridge, \
    NetworkDHCPRange, VmNetAdapter
from agent.client.hypervisor.libvirt.models.volume.disk import DiskCreate, DiskType
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
from agent.client.hypervisor.libvirt.models.vm import VirtualMachine, VMCreateRequest, NetQemuCommandline
from agent.client.tools import wait_while_not

IMG_PATH = "/home/eska/AlmaLinux-10.1-x86_64-minimal.iso"


@pytest.mark.tags("VM‑01", "Создание ВМ с присоединением диска а не созданием нового")
@pytest.mark.skip("Для внутреннего тестирования, не для общего запуска")
def test_vm_01_create_vm_with_attach_disk(vm_session, network_session):
    """
    VM‑01: Создание ВМ с образом AlmaLinux и отдельной сетью

    Указать имя, ресурсы (CPU, RAM, диск), сеть. Проверить, что ВМ появляется в списке в состоянии «Выключена».
    """
    vm_created = None
    random_name = f"alma-linux-eskvisor"

    def kb_to_mb(kb):
        return kb / 1024

    get_state = vm_session.get_vm_state_by_name
    vm_template = VMCreateRequest(
        name=random_name,
        autostart_vm=True,
        disks=[
            DiskCreate(path=IMG_PATH, disk_type=DiskType.CDROM),
            DiskCreate(size_gb=6),
        ],
        vcpus=2,
        memory_mb=2048,
        networks=[VmNetAdapter(network_type=NetworkType.NETWORK)],
        qemu_commandline=[NetQemuCommandline()])
    try:
        # ____________________________________Создание NAT сети________________
        nat_params = NetworkParameters(
            name=f"nat-{random.randint(1000, 9999)}",
            forward=NetworkForward(mode="nat"),
            bridge=NetworkBridge(name="alma-nat-net", stp="on", delay=0),
            ipv4_address="192.168.100.0/24",
            dhcp_ranges=[
                NetworkDHCPRange(start="192.168.100.100", end="192.168.100.200")
            ],
            autostart=True,
        )

        network_name = nat_params.name
        created_network_info = network_session.create_network(nat_params)
        assert (
            created_network_info.code
            == CommandMessagesEnum.virtual_network_successfully_created.name
        )
        vm_template.networks[0].source = nat_params.name

        # ____________________________________Создание ВМ_________________________
        create_vm_info = vm_session.create_vm(vm_template)
        assert create_vm_info.code == CommandMessagesEnum.vm_successfully_created.name
        vm_created = True
        assert create_vm_info.vm_info is not None
        vm_info: VirtualMachine = create_vm_info.vm_info
        assert wait_while_not(lambda: get_state(random_name) == VMState.RUNNING.value)
        assert vm_info.vcpus == vm_template.vcpus
        assert vm_info.name == vm_template.name
        assert kb_to_mb(vm_info.memory) == vm_template.memory_mb
    finally:
        # ____________________________________Удаление ВМ(постусловие)____________
        if vm_created is not None:
            pass
            # delete_vm_info = vm_session.delete_vm_with_force(name=random_name)
            # assert (
            #         delete_vm_info.code
            #         == CommandMessagesEnum.vm_successfully_deleted.name
            # )
            # assert delete_vm_info.success is True
