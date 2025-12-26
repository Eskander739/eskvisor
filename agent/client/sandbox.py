from agent.client.hypervisor.libvirt.managers.vm_manager import VmManager
from agent.client import XmlConverter
from agent.client import XmlVCpu, XmlCpu, CpuModeEnum, CpuTopology
from agent.client import XmlDisk, XmlDiskDriver, XmlDriverNameEnum, XmlDiskDriverType, \
    XmlDiskSourceFile, XmlDiskTarget
from agent.client import AcpiFeature, X86Features, ApicFeature
from agent.client.xml_confugurator.models.general import DomainVirtualizationType, StateOnOff, NvramModel, \
    ProcessorArchitecture, MachineOS, TypeOS, EnableParam
from agent.client.xml_confugurator.models.loader import ConfigurationLoader, StatelessLoaderEnum, LoaderValueEnum, \
    LoaderTypeEnum, ReadOnlyLoaderEnum
from agent.client.xml_confugurator.models.memory import CurrentMemory, MemoryUnitEnum, MemoryXml
from agent.client import XmlDevices, XmlEmulator, XmlObject, BootLoadList, BootLoad, \
    BootDevEnum, BootEnableEnum, ConfigurationOSType, XmlOS
from agent.client import XmlOnReboot, XmlOnPowerOff, XmlOnCrash, \
    XmlOnPowerOffEnum, XmlOnRebootEnum, XmlOnCrashEnum
from agent.client import XmlClock, ClockOffset

xml_converter = XmlConverter()
# 1. Создаем минимальную конфигурацию CPU
vcpu = XmlVCpu(value=2)  # 2 виртуальных процессора
cpu = XmlCpu(
    mode=CpuModeEnum.host_model,  # Используем модель хоста
    topology=CpuTopology(sockets=1, cores=2, threads=1)  # 1 сокет, 2 ядра, 1 поток на ядро
)

# 2. Создаем простой диск
simple_disk = XmlDisk(
    driver=XmlDiskDriver(
        name=XmlDriverNameEnum.qemu,
        type=XmlDiskDriverType.qcow2
    ),
    source=XmlDiskSourceFile(file="/var/lib/libvirt/images/vm-root.qcow2"),
    target=XmlDiskTarget(dev="vda", bus="virtio"),
    readonly=EnableParam.enable  # Диск только для чтения
)

# 3. Создаем конфигурацию OS
os_config = XmlOS(
    type=ConfigurationOSType(
        arch=ProcessorArchitecture.x86_64_bit,
        machine=MachineOS.pc_q35_7_2,
        value=TypeOS.HVM
    ),
    loader=ConfigurationLoader(
        stateless=StatelessLoaderEnum.no,
        value=LoaderValueEnum.general_uefi,
        type=LoaderTypeEnum.pflash,
        readonly=ReadOnlyLoaderEnum.yes
    ),
    nvram=NvramModel(
        template="/usr/share/OVMF/OVMF_VARS.fd",
        value="/var/lib/libvirt/qemu/nvram/test-vm_VARS.fd"
    ),
    boot=BootLoadList(
        boot_loads=[
            BootLoad(
                dev=BootDevEnum.hd,
                enable=BootEnableEnum.yes
            )
        ]
    )
)

# 4. Создаем базовые фичи для x86
features = X86Features(
    acpi=AcpiFeature(state=StateOnOff.on),
    apic=ApicFeature(state=StateOnOff.on)
)

# 5. Создаем конфигурацию времени
clock = XmlClock(offset=ClockOffset.utc)

# 6. Создаем политики поведения
on_poweroff = XmlOnPowerOff(value=XmlOnPowerOffEnum.destroy)
on_reboot = XmlOnReboot(value=XmlOnRebootEnum.restart)
on_crash = XmlOnCrash(value=XmlOnCrashEnum.destroy)

# 7. Создаем устройства
devices = XmlDevices(
    emulator=XmlEmulator(),  # Используем эмулятор по умолчанию
    disk=[simple_disk]  # Добавляем наш диск
)

# 8. Создаем главную модель XmlObject
xml_object = XmlObject(
    id=1,  # ID для редактирования
    type=DomainVirtualizationType.KVM,
    name="test-vm-01",  # Имя ВМ (латинские буквы, цифры, дефисы)
    memory=MemoryXml(
        unit=MemoryUnitEnum.GiB,
        value=4  # 4 GB максимальной памяти
    ),
    current_memory=CurrentMemory(
        unit=MemoryUnitEnum.GiB,
        value=2  # 2 GB текущей памяти (должно быть ≤ максимальной)
    ),
    vcpu=vcpu,
    os=os_config,
    features=features,
    cpu=cpu,
    clock=clock,
    on_poweroff=on_poweroff,
    on_reboot=on_reboot,
    on_crash=on_crash,
    devices=devices
)

# Выводим результат для проверки
print("Создана модель XmlObject:")
print(f"ID: {xml_object.id}")
print(f"Имя: {xml_object.name}")
print(f"Тип: {xml_object.type}")
print(f"Память: {xml_object.memory.value} {xml_object.memory.unit}")
print(f"Текущая память: {xml_object.current_memory.value} {xml_object.current_memory.unit}")
print(f"vCPU: {xml_object.vcpu.value}")
print(f"Архитектура: {xml_object.os.type.arch}")
print(f"Количество дисков: {len(xml_object.devices.disk)}")
# xml_data = xml_converter.convert_object_to_xml(xml_object)
# print(xml_data)
manager = VmManager()
manager.connect()
vms = manager.list_vms()
print(f"Найдено ВМ: {len(vms)}")
node_info = manager.get_node_info()
print("Информация о хосте: ", node_info)
# print(f"Запуск ВМ: test-vm-01", manager.start_vm("test-vm-01"))
for vm in vms:
    print(f"Имя: {vm.name}, Состояние: {vm.state.name}, "
          f"Память: {vm.memory // 1024} MB, vCPUs: {vm.vcpus}, Состояние: {vm.state}")
# manager.create_vm_from_xml(xml_data)

# Для получения XML используйте XmlConverter
# from agent.client.xml_confugurator.managers.xml_converter import XmlConverter
# converter = XmlConverter()
# xml_str = converter.convert_object_to_xml(xml_object)
# print(xml_str)