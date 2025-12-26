from agent.client import XmlTools, serialize_xml
from agent.client import XmlVCpu, XmlCpu, CpuModeEnum
from agent.client import XmlDisk, XmlDiskDeviceType, XmlDiskSourceVolume, XmlDiskSourceDir, \
    XmlDiskSourceFile, XmlDiskSourcCDRome, XmlDiskSourceBlock, XmlDiskSourceNetwork, XmlDiskSourceNetworkHost
from agent.client import PowerPCFeatures, ARMFeatures, BaseFeatures, X86Features
from agent.client.xml_confugurator.models.general import DomainVirtualizationType, StateYesNo, StateOnOff, \
    ProcessorArchitecture, MachineOS, TypeOS, NvramModel
from agent.client.xml_confugurator.models.interface import XmlInterface
from agent.client.xml_confugurator.models.loader import ConfigurationLoader, StatelessLoaderEnum, LoaderValueEnum, \
    LoaderTypeEnum, ReadOnlyLoaderEnum
from agent.client.xml_confugurator.models.memory import MemoryXml, MemoryUnitEnum, CurrentMemory
from agent.client import XmlObject, XmlOS, XmlDevices, ConfigurationOSType, BootLoadList, \
    BootLoad, BootDevEnum, BootEnableEnum
from agent.client import XmlClock, ClockOffset, Timer, TimerTickpolicy


class XmlConverter(XmlTools):


    @staticmethod
    def convert_timer_to_xml(timer: Timer) -> str:
        """

        Пример:
        <clock offset='utc'>
          <!-- Таймеры для лучшей синхронизации -->
          <timer name='rtc' tickpolicy='catchup' track='wall'/>
          <timer name='pit' tickpolicy='delay'/>
          <timer name='hpet' present='no'/>  <!-- HPET может замедлять ВМ -->
          <timer name='kvmclock' present='yes'/>  <!-- Для Linux гостей -->
          <timer name='hypervclock' present='yes'/>  <!-- Для Windows гостей -->
        </clock>
        """
        if not isinstance(timer, Timer):
            raise ValueError(f"Некорректный тип модели: {timer}")
        xml = f"<timer name='{timer.name}' "
        if timer.tickpolicy is not None:
            tickpolicy = f"tickpolicy='{timer.tickpolicy.value}' "
            xml += tickpolicy

        if timer.present is not None:
            present = f"present='{timer.present.value}' "
            xml += present

        if timer.track is not None:
            track = f"track='{timer.track}' "
            xml += track
        xml = xml + "/>"

        return xml

    @serialize_xml
    def convert_clock_to_xml(self, clock: XmlClock) -> str:
        additional_attr = False
        if not isinstance(clock, XmlClock):
            raise ValueError(f"Некорректный тип модели: {clock}")
        xml = f"  <clock offset='{clock.offset.value}' "
        if clock.offset.value == ClockOffset.timezone.value and clock.timezone is None:
            raise ValueError("Нельзя указывать offset='timezone' без атрибута timezone")
        elif clock.offset.value != ClockOffset.timezone.value:
            clock.timezone = None

        if clock.offset.value in (ClockOffset.timezone.value, ClockOffset.variable.value) and clock.adjustment is not None:
            raise ValueError("Нельзя указывать adjustment если offset != timezone или variable")
        elif clock.offset.value not in (ClockOffset.timezone.value, ClockOffset.variable.value):
            clock.adjustment = None

        if clock.offset.value == ClockOffset.timezone.value and clock.timezone is not None:
            timezone = f"timezone='{clock.timezone.value}' "
            xml += timezone

        if clock.offset.value in (ClockOffset.timezone.value, ClockOffset.variable.value) and clock.adjustment is not None:
            adjustment = f"adjustment='{clock.adjustment}' "
            xml += adjustment

        if additional_attr:
            xml += ">"

        if clock.timer:
            additional_attr = True
            timer_list_xml = [self.convert_timer_to_xml(timer) for timer in clock.timer]

            for timer in timer_list_xml:
                xml += f"\n{timer}"

        if additional_attr:
            xml += "\n  </clock>"
        else:
            xml += "/>"
        return xml

    @serialize_xml
    def convert_vcpu_to_xml(self, vcpu: XmlVCpu) -> str:
        if not isinstance(vcpu, XmlVCpu):
            raise ValueError(f"Некорректный тип модели: {vcpu}")

        xml = f"<vcpu "

        if vcpu.value <= 0:
            raise ValueError("Число ядер не может быть меньше 1")

        if vcpu.placement is None and vcpu.cpuset is not None:
            raise ValueError("Нельзя установить cpuset без placement")
        if vcpu.current is not None:
            if vcpu.current > vcpu.value:
                raise ValueError(f"Current '{vcpu.current}' не может быть больше указанного значения vcpu: '{vcpu.value}'")
            current = f"current='{vcpu.current}' "
            xml += current
        if vcpu.cpuset is not None:
            if not self.validate_cpuset(vcpu.cpuset):
                raise ValueError("Невалидный cpuset")

            # Проверка логики: размер cpuset должен соответствовать количеству vCPU
            # 1. Разбираем cpuset для подсчета доступных физических ядер
            available_cores = self._count_cores_in_cpuset(vcpu.cpuset)

            # 2. Определяем количество vCPU, которые будут использовать этот cpuset
            active_vcpus = vcpu.current if vcpu.current is not None else vcpu.value

            # 3. Проверяем логическое соответствие
            # Если active_vcpus > available_cores, это ошибка - не хватит ядер
            if active_vcpus > available_cores:
                raise ValueError(
                    f"Количество vCPU ({active_vcpus}) превышает количество доступных "
                    f"физических ядер в cpuset ({available_cores})"
                )

            # Если active_vcpus значительно меньше available_cores - предупреждение (не ошибка)
            if active_vcpus * 2 < available_cores:
                print(f"Предупреждение: cpuset содержит {available_cores} ядер, "
                      f"но используется только {active_vcpus} vCPU. "
                      f"Это может быть неоптимально.")
            cpuset = f"cpuset='{vcpu.cpuset}' "
            xml += cpuset

        if vcpu.placement is not None:
            placement = f"placement='{vcpu.placement.value}' "
            xml += placement

        xml += f">{vcpu.value}"
        xml += "<"
        xml += f"/vcpu>"

        return xml

    @staticmethod
    def convert_memory_and_current_memory_to_xml(memory: MemoryXml | CurrentMemory) -> str:
        xml = ""

        if isinstance(memory, MemoryXml):
            xml += "<memory "
        elif isinstance(memory, CurrentMemory):
            xml += "<currentMemory "
        else:
            raise ValueError(f"Некорректный тип модели: {memory}")

        xml += f"unit='{memory.unit.value}' "
        xml += f">{memory.value}"

        if isinstance(memory, MemoryXml):
            xml += "</memory>"
        elif isinstance(memory, CurrentMemory):
            xml += "</currentMemory>"

        return xml

    @staticmethod
    @serialize_xml
    def convert_disk_to_xml(disk: XmlDisk) -> str:
        xml = f"\n    <disk type='{disk.type.value}' device='{disk.device.value}'>"

        if not isinstance(disk, XmlDisk):
            raise ValueError(f"Некорректный тип модели: {disk}")

        if disk.driver is not None:
            driver = disk.driver
            xml_driver = f"      <driver name='{driver.name.value}' type='{driver.type.value}' "

            if driver.cache is not None:
                xml_driver += f"cache='{driver.cache.value}' "
            if driver.io is not None:
                xml_driver += f"io='{driver.io.value}' "
            if driver.discard is not None:
                xml_driver += f"discard='{driver.discard.value}' "

            if driver.error_policy is not None:
                xml_driver += f"error_policy='{driver.error_policy.value}' "

            if driver.rerror_policy is not None:
                xml_driver += f"rerror_policy='{driver.rerror_policy.value}' "

            if driver.ioeventfd is not None:
                xml_driver += f"ioeventfd='{driver.ioeventfd.value}' "
            if driver.event_idx is not None:
                xml_driver += f"event_idx='{driver.event_idx.value}' "

            # TODO: Доизучить возможные логические противоречия в driver

            xml_driver += "/>"
            xml += f"\n{xml_driver}"

        source = disk.source
        xml_source = ""

        if isinstance(source, XmlDiskSourceFile):
            xml_source += f"      <source file='{source.file}'/>"

        elif isinstance(source, XmlDiskSourcCDRome):
            if source.file is not None:
                xml_source += f"      <source file='{source.file}'/>"
            else:
                xml_source += f"      <source/>"
        elif isinstance(source, XmlDiskSourceBlock):
            xml_source += f"      <source dev='{source.dev}'/>"

        elif isinstance(source, XmlDiskSourceNetwork):
            xml_source += f"      <source protocol='{source.protocol}' name='{source.name}'>"
            if isinstance(source.host, XmlDiskSourceNetworkHost):
                xml_source += f"\n    <host name='{source.host.name}' port='{source.host.port}'/>"
            elif isinstance(source.host, list):
                for current_host in source.host:
                    xml_source += f"\n    <host name='{current_host.name}' port='{current_host.port}'/>"

            xml_source += "      </source>"

        elif isinstance(source, XmlDiskSourceDir):
            xml_source += f"      <source dir='{source.dir}'/>"
        elif isinstance(source, XmlDiskSourceVolume):
            xml_source += f"      <source pool='{source.pool}' volume='{source.volume}'/>"
        else:
            raise ValueError(f"Некорректный тип модели: {source}")

        xml_target = f"      <target dev='{disk.target.dev.value}' bus='{disk.target.bus.value}' "

        if disk.target.removable is not None:
            xml_target += f"removable='{disk.target.removable.value}' "

        if disk.target.tray is not None:
            if disk.device.value != XmlDiskDeviceType.cdrom.value:
                raise ValueError(f"Нельзя установить tray для device='{disk.device.value}'")
            xml_target += f"tray='{disk.target.tray.value}' "

        xml += f"\n{xml_source}"
        xml_target += "/>"
        xml += f"\n{xml_target}"

        disk_address = disk.address

        if disk_address is not None:
            xml_address = (f"      <address type='{disk_address.type}' "
                           f"domain='{disk_address.domain}' "
                           f"bus='{disk_address.bus}' "
                           f"slot='{disk_address.slot}' "
                           f"function='{disk_address.function}'/>")
            xml += f"\n{xml_address}"

        if disk.boot is not None:
            xml += f"\n      <boot order='{disk.boot.order}'/>"


        if disk.readonly is not None:
            xml += "\n      <readonly/>"

        if disk.geometry is not None:
            xml += (f"\n      <geometry cyls='{disk.geometry.cyls}' "
                    f"heads='{disk.geometry.heads}' "
                    f"secs='{disk.geometry.secs}' "
                    f"trans='{disk.geometry.trans}'/>")

        if disk.blockio is not None:
            blockio_params = [disk.blockio.total_bytes_sec,
                              disk.blockio.read_bytes_sec,
                              disk.blockio.write_bytes_sec,
                              disk.blockio.total_iops_sec,
                              disk.blockio.read_iops_sec,
                              disk.blockio.write_iops_sec,
                              ]
            have_blockio_params = len([True for blockio_param in blockio_params if blockio_param is not None]) >= 1

            if have_blockio_params:
                xml_blockio = (f"\n      <blockio logical_block_size='{disk.blockio.logical_block_size}' "
                               f"physical_block_size='{disk.blockio.physical_block_size}'>")
                if disk.blockio.total_bytes_sec:
                    xml_blockio += f"\n      <total_bytes_sec>{disk.blockio.total_bytes_sec}</total_bytes_sec>"

                if disk.blockio.read_bytes_sec:
                    xml_blockio += f"\n      <read_bytes_sec>{disk.blockio.read_bytes_sec}</read_bytes_sec>"

                if disk.blockio.write_bytes_sec:
                    xml_blockio += f"\n      <write_bytes_sec>{disk.blockio.write_bytes_sec}</write_bytes_sec>"

                if disk.blockio.total_iops_sec:
                    xml_blockio += f"\n      <total_iops_sec>{disk.blockio.total_iops_sec}</total_iops_sec>"
                if disk.blockio.read_iops_sec:
                    xml_blockio += f"\n      <read_iops_sec>{disk.blockio.read_iops_sec}</read_iops_sec>"
                if disk.blockio.write_iops_sec:
                    xml_blockio += f"\n      <write_iops_sec>{disk.blockio.write_iops_sec}</write_iops_sec>"
                xml_blockio += f"\n      </blockio>"
            else:
                xml_blockio = (f"\n      <blockio logical_block_size='{disk.blockio.logical_block_size}' "
                               f"physical_block_size='{disk.blockio.physical_block_size}'/>")


            xml += f"\n{xml_blockio}"

        if disk.serial is not None:
            xml_serial = f"      <serial>{disk.serial.value}</serial>"
            xml += f"\n{xml_serial}"

        if disk.alias is not None:
            xml += f"\n      <alias name='{disk.alias.name}'/>"

        if disk.iotune is not None:
            xml_iotune = "      <iotune>"
            if disk.blockio.total_bytes_sec:
                xml_iotune += f"\n      <total_bytes_sec>{disk.iotune.total_bytes_sec}</total_bytes_sec>"

            if disk.blockio.read_bytes_sec:
                xml_iotune += f"\n      <read_bytes_sec>{disk.iotune.read_bytes_sec}</read_bytes_sec>"

            if disk.blockio.write_bytes_sec:
                xml_iotune += f"\n      <write_bytes_sec>{disk.iotune.write_bytes_sec}</write_bytes_sec>"

            if disk.blockio.total_iops_sec:
                xml_iotune += f"\n      <total_iops_sec>{disk.iotune.total_iops_sec}</total_iops_sec>"
            if disk.blockio.read_iops_sec:
                xml_iotune += f"\n      <read_iops_sec>{disk.iotune.read_iops_sec}</read_iops_sec>"
            if disk.blockio.write_iops_sec:
                xml_iotune += f"\n      <write_iops_sec>{disk.iotune.write_iops_sec}</write_iops_sec>"
            if disk.iotune.size_iops_sec:
                xml_iotune += f"\n      <size_iops_sec>{disk.iotune.size_iops_sec}</size_iops_sec>"
            xml_iotune += f"\n      </iotune>"
            xml += f"\n{xml_iotune}"


        xml += "\n    </disk>"

        return xml

    def convert_interface_to_xml(self, interface: XmlInterface):
        raise NotImplementedError

    def convert_devices_to_xml(self, devices: XmlDevices) -> str:
        if not isinstance(devices, XmlDevices):
            raise ValueError(f"Некорректный тип модели: {devices}")

        xml_devices = "  <devices>"
        xml_devices += f"\n    <emulator>{devices.emulator.value}</emulator>"
        for current_device in devices.disk:
            converted_xml = self.convert_disk_to_xml(current_device)
            xml_devices += f"    {converted_xml}"
            # elif isinstance(current_device, XmlInterface):
            #     converted_xml = self.convert_interface_to_xml(current_device)
            #     xml_devices += f"\n{converted_xml}"

        xml_devices += "\n  </devices>"
        return xml_devices


    @staticmethod
    def convert_os_to_xml(obj_os: XmlOS) -> str:
        if not isinstance(obj_os, XmlOS):
            raise ValueError(f"Некорректный тип модели: {obj_os}")

        xml = "<os>"
        xml += f"\n    <type arch='{obj_os.type.arch.value}' machine='{obj_os.type.machine.value}'>{obj_os.type.value.value}</type>"

        if obj_os.loader is not None:
            xml_loader = f"    <loader "

            if obj_os.loader.readonly is not None:
                xml_loader += f"readonly='{obj_os.loader.readonly.value}' "
            if obj_os.loader.type is not None:
                xml_loader += f"type='{obj_os.loader.type.value}' "
            if obj_os.loader.stateless is not None:
                xml_loader += f"stateless='{obj_os.loader.stateless.value}' "
            xml_loader += f" >{obj_os.loader.value.value}</loader>"

            xml += f"\n{xml_loader}"

        if obj_os.nvram is not None:
            if obj_os.loader is not None:
                if obj_os.loader.stateless is not None:
                    if obj_os.loader.stateless.value == StatelessLoaderEnum.yes.value:
                        raise ValueError("Использование шаблонов NVRAM не допускается, если загрузчик не имеет состояния.")
            xml_nvram = "    <nvram "
            if obj_os.nvram.template is not None:
                xml_nvram += f"template='{obj_os.nvram.template}'"
            xml_nvram += f">{obj_os.nvram.value}</nvram>"
            xml += f"\n{xml_nvram}"

        if obj_os.boot is not None:
            xml_boot_list = ""
            for current_boot in obj_os.boot.boot_loads:
                xml_current_boot = f"<boot dev='{current_boot.dev.value}' "

                if current_boot.enable is not None:
                    xml_current_boot += f"enable='{current_boot.enable.value}' "
                if current_boot.loadparm is not None:
                    xml_current_boot += f"loadparm='{current_boot.loadparm.value}' "

                xml_current_boot += f"/>"

                xml_boot_list += f"    {xml_current_boot}"

            xml += f"\n{xml_boot_list}"

        xml += "\n  </os>"
        return xml

    @staticmethod
    def convert_cpu_to_xml(cpu: XmlCpu) -> str:
        additional_attr = False
        if not isinstance(cpu, XmlCpu):
            raise ValueError(f"Некорректный тип модели: {XmlCpu}")

        xml_cpu = "<cpu "

        if cpu.mode is not None:
            xml_cpu += f"mode='{cpu.mode.value}' "

        if cpu.check is not None:
            xml_cpu += f"check='{cpu.check.value}' "

        if cpu.match is not None:
            xml_cpu += f"match='{cpu.match.value}' "

        if cpu.model is not None or cpu.topology is not None or cpu.features is not None:
            additional_attr = True
        if additional_attr:
            xml_cpu += ">"
        else:
            xml_cpu += "/>"

        if cpu.mode is not None and cpu.mode.value == CpuModeEnum.custom.value and cpu.model is None:
            raise ValueError("Если mode='custom' то внутри cpu должна присутствовать разметка model")

        if cpu.model is not None:
            xml_model = "<model "

            if cpu.model.fallback is not None:
                xml_model += f"fallback='{cpu.model.fallback.value}' "
            if cpu.model.vendor_id is not None:
                xml_model += f"vendor_id='{cpu.model.vendor_id}' "

            xml_model += f">{cpu.model.value.value}\n</model>"

            xml_cpu += f"\n{xml_model}"
        if cpu.topology is not None:
            xml_topology = "    <topology "

            if cpu.topology.sockets is not None:
                xml_topology += f"sockets='{cpu.topology.sockets}' "
            if cpu.topology.cores is not None:
                xml_topology += f"cores='{cpu.topology.cores}' "
            if cpu.topology.threads is not None:
                xml_topology += f"threads='{cpu.topology.threads}' "

            xml_topology += "/>"

            xml_cpu += f"\n{xml_topology}"

        if cpu.features is not None:
            for current_feature in cpu.features:
                xml_current_feature = f"<feature policy='{current_feature.policy.value}' name='{current_feature.name}'/>"
                xml_cpu += f"\n{xml_current_feature}"

        if additional_attr:
            xml_cpu += "\n  </cpu>"

        return xml_cpu

    def convert_features_to_xml(self, xml_features: PowerPCFeatures | ARMFeatures | X86Features):
        if not isinstance(xml_features, (PowerPCFeatures, ARMFeatures, X86Features)):
            raise ValueError(f"Некорректный тип модели: {type(xml_features)}")

        # Определяем архитектуру
        if isinstance(xml_features, X86Features):
            return self._convert_x86_features_to_xml(xml_features)
        elif isinstance(xml_features, ARMFeatures):
            return self._convert_arm_features_to_xml(xml_features)
        elif isinstance(xml_features, PowerPCFeatures):
            return self._convert_powerpc_features_to_xml(xml_features)
        else:
            raise ValueError(f"Неизвестный тип модели: {type(xml_features)}")

    @staticmethod
    def _convert_base_features_to_xml(xml_features: BaseFeatures) -> str:
        """Конвертирует базовые фичи, общие для всех архитектур"""
        xml = ""

        if xml_features.acpi is not None:
            xml_acpi = "    <acpi"
            if xml_features.acpi.state is not None:
                xml_acpi += f" state='{xml_features.acpi.state.value}'"
            xml_acpi += "/>"
            xml += f"\n{xml_acpi}"

        if xml_features.apic is not None:
            xml_apic = "    <apic"
            if xml_features.apic.state is not None:
                xml_apic += f" state='{xml_features.apic.state.value}'"
            if xml_features.apic.eoi is not None:
                xml_apic += f" eoi='{xml_features.apic.eoi.value}'"
            xml_apic += "/>"
            xml += f"\n{xml_apic}"

        if xml_features.hap is not None:
            xml_hap = "    <hap"
            if xml_features.hap.state is not None:
                xml_hap += f" state='{xml_features.hap.state.value}'"
            xml_hap += "/>"
            xml += f"\n{xml_hap}"

        if xml_features.smm is not None:
            xml_smm = "    <smm"
            if xml_features.smm.state is not None:
                xml_smm += f" state='{xml_features.smm.state.value}'"
            xml_smm += "/>"
            xml += f"\n{xml_smm}"

        if xml_features.pmu is not None:
            xml_pmu = "    <pmu"
            if xml_features.pmu.state is not None:
                xml_pmu += f" state='{xml_features.pmu.state.value}'"
            if xml_features.pmu.version is not None:
                xml_pmu += f" version='{xml_features.pmu.version.value}'"
            xml_pmu += "/>"
            xml += f"\n{xml_pmu}"

        if xml_features.mmu is not None:
            xml_mmu = "    <mmu"
            if xml_features.mmu.state is not None:
                xml_mmu += f" state='{xml_features.mmu.state.value}'"
            xml_mmu += "/>"
            xml += f"\n{xml_mmu}"

        if xml_features.htm is not None:
            xml_htm = "    <htm"
            if xml_features.htm.state is not None:
                xml_htm += f" state='{xml_features.htm.state.value}'"
            xml_htm += ">"
            if xml_features.htm.suspensible is not None:
                xml_suspensible = "    <suspensible"
                if xml_features.htm.suspensible.state is not None:
                    xml_suspensible += f" state='{xml_features.htm.suspensible.state.value}'"
                xml_suspensible += "/>"
                xml_htm += f"\n{xml_suspensible}"
            xml_htm += "\n  </htm>"
            xml += f"\n{xml_htm}"

        if xml_features.vmcoreinfo is not None:
            xml_vmcoreinfo = "    <vmcoreinfo"
            if xml_features.vmcoreinfo.state is not None:
                xml_vmcoreinfo += f" state='{xml_features.vmcoreinfo.state.value}'"
            xml_vmcoreinfo += "/>"
            xml += f"\n{xml_vmcoreinfo}"

        if xml_features.pvspinlock is not None:
            xml_pvspinlock = "    <pvspinlock"
            if xml_features.pvspinlock.state is not None:
                xml_pvspinlock += f" state='{xml_features.pvspinlock.state.value}'"
            xml_pvspinlock += "/>"
            xml += f"\n{xml_pvspinlock}"

        if xml_features.capabilities is not None:
            xml_capabilities = "    <capabilities>"
            if xml_features.capabilities.sbbc is not None:
                xml_sbbc = "      <sbbc"
                if xml_features.capabilities.sbbc.state is not None:
                    xml_sbbc += f" state='{xml_features.capabilities.sbbc.state.value}'"
                xml_sbbc += "/>"
                xml_capabilities += f"\n{xml_sbbc}"
            if xml_features.capabilities.ibs is not None:
                xml_ibs = "      <ibs"
                if xml_features.capabilities.ibs.state is not None:
                    xml_ibs += f" state='{xml_features.capabilities.ibs.state.value}'"
                xml_ibs += "/>"
                xml_capabilities += f"\n{xml_ibs}"
            xml_capabilities += "\n  </capabilities>"
            xml += f"\n{xml_capabilities}"

        if xml_features.hyperv is not None:
            xml_hyperv = "    <hyperv>"
            if xml_features.hyperv.relaxed is not None:
                xml_relaxed = "      <relaxed"
                if xml_features.hyperv.relaxed.state is not None:
                    xml_relaxed += f" state='{xml_features.hyperv.relaxed.state.value}'"
                xml_relaxed += "/>"
                xml_hyperv += f"\n{xml_relaxed}"
            if xml_features.hyperv.vapic is not None:
                xml_vapic = "      <vapic"
                if xml_features.hyperv.vapic.state is not None:
                    xml_vapic += f" state='{xml_features.hyperv.vapic.state.value}'"
                xml_vapic += "/>"
                xml_hyperv += f"\n{xml_vapic}"
            if xml_features.hyperv.spinlocks is not None:
                xml_spinlocks = "      <spinlocks"
                if xml_features.hyperv.spinlocks.state is not None:
                    xml_spinlocks += f" state='{xml_features.hyperv.spinlocks.state.value}'"
                if xml_features.hyperv.spinlocks.retries is not None:
                    xml_spinlocks += f" retries='{xml_features.hyperv.spinlocks.retries}'"
                xml_spinlocks += "/>"
                xml_hyperv += f"\n{xml_spinlocks}"
            xml_hyperv += "\n    </hyperv>"
            xml += f"\n{xml_hyperv}"

        if xml_features.kvm is not None:
            xml_kvm = "    <kvm>"
            if xml_features.kvm.hidden is not None:
                xml_hidden = "      <hidden"
                if xml_features.kvm.hidden.state is not None:
                    xml_hidden += f" state='{xml_features.kvm.hidden.state.value}'"
                xml_hidden += "/>"
                xml_kvm += f"\n{xml_hidden}"
            if xml_features.kvm.hint_dedicated is not None:
                xml_hint_dedicated = "      <hint-dedicated"
                if xml_features.kvm.hint_dedicated.state is not None:
                    xml_hint_dedicated += f" state='{xml_features.kvm.hint_dedicated.state.value}'"
                xml_hint_dedicated += "/>"
                xml_kvm += f"\n{xml_hint_dedicated}"
            xml_kvm += "\n    </kvm>"
            xml += f"\n{xml_kvm}"

        return xml

    def _convert_x86_features_to_xml(self, xml_features: X86Features) -> str:
        """Конвертирует специфичные x86 фичи"""
        xml = "<features>"

        # Базовые фичи
        xml += self._convert_base_features_to_xml(xml_features)

        # x86 специфичные фичи
        if xml_features.pae is not None:
            xml_pae = "    <pae"
            if xml_features.pae.state is not None:
                xml_pae += f" state='{xml_features.pae.state.value}'"
            xml_pae += "/>"
            xml += f"\n{xml_pae}"

        if xml_features.nonpae is not None:
            xml_nonpae = "    <nonpae"
            if xml_features.nonpae.state is not None:
                xml_nonpae += f" state='{xml_features.nonpae.state.value}'"
            xml_nonpae += "/>"
            xml += f"\n{xml_nonpae}"

        if xml_features.ioapic is not None:
            xml_ioapic = "    <ioapic"
            if xml_features.ioapic.driver is not None:
                xml_ioapic += f" driver='{xml_features.ioapic.driver.value}'"
            xml_ioapic += "/>"
            xml += f"\n{xml_ioapic}"

        if xml_features.vmport is not None:
            xml_vmport = "    <vmport"
            if xml_features.vmport.state is not None:
                xml_vmport += f" state='{xml_features.vmport.state.value}'"
            if xml_features.vmport.mode is not None:
                xml_vmport += f" mode='{xml_features.vmport.mode.value}'"
            xml_vmport += "/>"
            xml += f"\n{xml_vmport}"

        # Проверка на конфликт vmx/svm
        if xml_features.vmx is not None and xml_features.svm is not None:
            if xml_features.vmx.state == StateOnOff.on and xml_features.svm.state == StateOnOff.on:
                raise ValueError("vmx (Intel) и svm (AMD) одновременно включены - недопустимая конфигурация")

        if xml_features.vmx is not None:
            xml_vmx = "    <vmx"
            if xml_features.vmx.state is not None:
                xml_vmx += f" state='{xml_features.vmx.state.value}'"
            xml_vmx += "/>"
            xml += f"\n{xml_vmx}"

        if xml_features.svm is not None:
            xml_svm = "    <svm"
            if xml_features.svm.state is not None:
                xml_svm += f" state='{xml_features.svm.state.value}'"
            xml_svm += "/>"
            xml += f"\n{xml_svm}"

        if xml_features.msrs is not None:
            xml_msrs = "    <msrs"
            if xml_features.msrs.unknown is not None:
                xml_msrs += f" unknown='{xml_features.msrs.unknown.value}'"
            xml_msrs += "/>"
            xml += f"\n{xml_msrs}"

        if xml_features.viridian is not None:
            xml_viridian = "    <viridian"
            if xml_features.viridian.state is not None:
                xml_viridian += f" state='{xml_features.viridian.state.value}'"
            xml_viridian += "/>"
            xml += f"\n{xml_viridian}"

        if xml_features.pv_eoi is not None:
            xml_pv_eoi = "    <pv_eoi"
            if xml_features.pv_eoi.state is not None:
                xml_pv_eoi += f" state='{xml_features.pv_eoi.state.value}'"
            xml_pv_eoi += "/>"
            xml += f"\n{xml_pv_eoi}"

        if xml_features.pv_unhalt is not None:
            xml_pv_unhalt = "    <pv_unhalt"
            if xml_features.pv_unhalt.state is not None:
                xml_pv_unhalt += f" state='{xml_features.pv_unhalt.state.value}'"
            xml_pv_unhalt += "/>"
            xml += f"\n{xml_pv_unhalt}"

        if xml_features.xen is not None:
            xml_xen = "    <xen>"
            if xml_features.xen.e820_host is not None:
                xml_e820_host = "    <e820_host"
                if xml_features.xen.e820_host.state is not None:
                    xml_e820_host += f" state='{xml_features.xen.e820_host.state.value}'"
                xml_e820_host += "/>"
                xml_xen += f"\n{xml_e820_host}"
            xml_xen += "\n  </xen>"
            xml += f"\n{xml_xen}"

        if xml_features.privnet is not None:
            xml_privnet = "    <privnet"
            if xml_features.privnet.state is not None:
                xml_privnet += f" state='{xml_features.privnet.state.value}'"
            xml_privnet += "/>"
            xml += f"\n{xml_privnet}"

        xml += "\n  </features>"
        return xml

    def _convert_arm_features_to_xml(self, xml_features: ARMFeatures) -> str:
        """Конвертирует специфичные ARM фичи"""
        xml = "  <features>"

        # Базовые фичи
        xml += self._convert_base_features_to_xml(xml_features)

        # ARM специфичные фичи
        if xml_features.gic is not None:
            xml_gic = "    <gic"
            if xml_features.gic.version is not None:
                xml_gic += f" version='{xml_features.gic.version.value}'"
            xml_gic += "/>"
            xml += f"\n{xml_gic}"

        if xml_features.aa64pfetch is not None:
            xml_aa64pfetch = "    <aa64pfetch"
            if xml_features.aa64pfetch.state is not None:
                xml_aa64pfetch += f" state='{xml_features.aa64pfetch.state.value}'"
            xml_aa64pfetch += "/>"
            xml += f"\n{xml_aa64pfetch}"

        if xml_features.sve is not None:
            xml_sve = "    <sve>"
            if xml_features.sve.vl is not None:
                xml_vl = "    <vl"
                if xml_features.sve.vl.length is not None:
                    xml_vl += f" length='{xml_features.sve.vl.length}'"
                xml_vl += "/>"
                xml_sve += f"\n{xml_vl}"
            xml_sve += "\n  </sve>"
            xml += f"\n{xml_sve}"

        xml += "\n  </features>"
        return xml

    def _convert_powerpc_features_to_xml(self, xml_features: PowerPCFeatures) -> str:
        """Конвертирует специфичные PowerPC фичи"""
        xml = "  <features>"

        # Базовые фичи
        xml += self._convert_base_features_to_xml(xml_features)

        # PowerPC специфичные фичи
        if xml_features.hpt is not None:
            xml_hpt = "  <hpt"
            if xml_features.hpt.resizing is not None:
                xml_hpt += f" resizing='{xml_features.hpt.resizing.value}'"
            if xml_features.hpt.maxpagesize is not None:
                xml_hpt += f" maxpagesize='{xml_features.hpt.maxpagesize.value}'"
            xml_hpt += "/>"
            xml += f"\n{xml_hpt}"

        xml += "\n  </features>"
        return xml

    @serialize_xml
    def convert_object_to_xml(self, xml_object: XmlObject):
        """
        Синтаксис:
        Оба тега имеют обязательный атрибут unit.

        Значения — целые числа.
        Формально XML валиден.

        Проблема:
        <currentMemory> (текущая память при запуске) обычно меньше или равна <memory> (максимальной памяти).

        В твоём примере:
        memory = 2048 MiB ≈ 2 GiB
        currentMemory = 1024 GiB ≈ 1024 GiB


        Libvirt поведение:
        Может вызвать ошибку при создании ВМ или просто проигнорировать currentMemory, установив его равным memory.
        """
        if not isinstance(xml_object, XmlObject):
            raise ValueError(f"Некорректный тип модели: {XmlObject}")

        xml = f"<domain type='{xml_object.type.value}'>"
        xml += f"\n  <name>{xml_object.name}</name>"
        xml += f"\n  {self.convert_memory_and_current_memory_to_xml(xml_object.memory)}"
        xml += f"\n  {self.convert_memory_and_current_memory_to_xml(xml_object.current_memory)}"
        xml += f"\n  {self.convert_vcpu_to_xml(xml_object.vcpu)}"
        xml += f"\n  {self.convert_os_to_xml(xml_object.os)}"
        xml += f"\n  {self.convert_features_to_xml(xml_object.features)}"
        xml += f"\n  {self.convert_cpu_to_xml(xml_object.cpu)}"
        xml += f"\n{self.convert_clock_to_xml(xml_object.clock)}"

        if xml_object.on_poweroff is not None:
            xml += f"\n  <on_poweroff>\n    <action>{xml_object.on_poweroff.value.value}</action>\n  </on_poweroff>"

        if xml_object.on_reboot is not None:
            xml += f"\n  <on_reboot>\n    <action>{xml_object.on_reboot.value.value}</action>\n  </on_reboot>"

        if xml_object.on_crash is not None:
            xml += f"\n  <on_crash>\n    <action>{xml_object.on_crash.value.value}</action>\n  </on_crash>"

        xml += f"\n{self.convert_devices_to_xml(xml_object.devices)}"

        xml += "\n</domain>"
        return xml



# Пример использования:
if __name__ == "__main__":
    # Создаем тестовую модель

    xml_manager = XmlConverter()
    # Создаем простую конфигурацию
    vm_config = XmlObject(
        name="test-vm",
        type=DomainVirtualizationType.KVM,
        memory=MemoryXml(unit=MemoryUnitEnum.MiB, value=2048),
        current_memory=CurrentMemory(unit=MemoryUnitEnum.MiB, value=1024),
        vcpu=XmlVCpu(value=2),
        clock=XmlClock(
            offset=ClockOffset.timezone,
            timer=[
                Timer(name="rtc", tickpolicy=TimerTickpolicy.catchup, track="wall"),
                Timer(name="pit", tickpolicy=TimerTickpolicy.delay),
                Timer(name="hpet", present=StateYesNo.no),
            ]
        )
    )
    os_config = XmlOS(
        type=ConfigurationOSType(
            arch=ProcessorArchitecture.x86_64_bit,
            machine=MachineOS.pc_q35_7_2,
            value=TypeOS.HVM
        ),
        loader=ConfigurationLoader(
            stateless=StatelessLoaderEnum.yes,
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
    print(xml_manager.convert_os_to_xml(os_config))
    # print(vm_config)
    # print(xml_manager.convert_timer_to_xml(Timer(name="rtc", tickpolicy=TimerTickpolicy.catchup, track="wall")))
    # print(xml_manager.convert_timer_to_xml(Timer(name="hpet", present=State.on)))
    # print(xml_manager.convert_clock_to_xml(XmlClock(
    #         offset=ClockOffset.timezone,
    #         timer=[
    #             Timer(name="rtc", tickpolicy=TimerTickpolicy.catchup, track="wall"),
    #             Timer(name="pit", tickpolicy=TimerTickpolicy.delay),
    #             Timer(name="hpet", present=StateYesNo.no),
    #         ]
    #     )))

    # print(xml_manager.convert_vcpu_to_xml(VCpu(value=2, placement=VCpuPlacement.static, current=1, cpuset="40-80,^40,60")))
    # print(xml_manager.convert_memory_and_current_memory_to_xml(MemoryXml(unit=MemoryUnitEnum.MiB, value=2048)))
    # print(xml_manager.convert_memory_and_current_memory_to_xml(CurrentMemory(unit=MemoryUnitEnum.GiB, value=1024)))

    # print(xml_manager.convert_disk_to_xml(XmlDisk(driver=XmlDiskDriver(cache=XmlDiskDriverCache.writeback,
    #                                                                    error_policy=XmlDiskDriverErrorPolicy.report,
    #                                                                    rerror_policy=XmlDiskDriverReadErrorPolicy.report,
    #                                                                    ioeventfd=StateOnOff.off,
    #                                                                    event_idx=StateOnOff.on),
    #                                               readonly=EnableParam,
    #                                               shareable=EnableParam,
    #                                               serial=XmlDiskSerial(value="2U5GYH43FSIEDJ"),
    #                                               boot=XmlDiskBoot(order="1"),
    #                                               alias=XmlDiskAlias(name="test_alias"),
    #                                               geometry=XmlDiskGeometry(cyls=16383, heads=16, secs=63, trans="lba"),
    #                                               blockio=XmlDiskBlockIo(logical_block_size=512, physical_block_size=4096),
    #                                               iotune=XmlDiskIoTune(),
    #                                               address=XmlDiskAddress(type="pci", domain="0x0000", bus="0x00", slot="0x06", function="0x0"),
    #                                               )))

    # print(xml_manager.convert_cpu_to_xml(XmlCpu(mode=CpuModeEnum.custom,
    #                                             model=XmlCpuModel(
    #                                                 fallback=XmlCpuModelFallbackEnum.forbid,
    #                                                 vendor_id="GenuineIntel",
    #                                             value=CpuModelIntel.CORE2DUO),
    #                                             topology=CpuTopology(),
    #                                             features=[XmlCpuFeature(policy=XmlCpuFeaturePolicyEnum.disable, name="vmx"),
    #                                                       XmlCpuFeature(policy=XmlCpuFeaturePolicyEnum.optional, name="hle")],
    #                                             check=XmlCpuCheckEnum.partial,
    #                                             match=XmlCpuMatchEnum.strict)))

    # 4. ARM производительный
    # arm_performance = ARMFeatures(
    #     acpi=AcpiFeature(state=StateOnOff.on),
    #     apic=ApicFeature(state=StateOnOff.on),
    #     gic=GicFeature(version=GicFeatureVersionEnum.three),
    #     sve=SveFeature(vl=SveFeatureVLParam(length=512)),
    #     aa64pfetch=Aa64pFetchFeature(state=StateOnOff.on),
    #     pmu=PmuFeature(state=StateOnOff.on, version=PmuFeatureVersionEnum.four),
    #     hap=HapFeature(state=StateOnOff.on),
    #     mmu=MmuFeature(state=StateOnOff.on)
    # )
    #
    # # 5. ARM для контейнеров/легких ВМ
    # arm_lightweight = ARMFeatures(
    #     acpi=AcpiFeature(state=StateOnOff.off),  # минимум фич
    #     gic=GicFeature(version=GicFeatureVersionEnum.two)
    # )
    #
    # # 6. ARM с Hyper-V эмуляцией (для Windows ARM)
    # arm_hyperv = ARMFeatures(
    #     acpi=AcpiFeature(state=StateOnOff.on),
    #     gic=GicFeature(version=GicFeatureVersionEnum.three),
    #     hyperv=HyperVFeature(
    #         relaxed=RelaxedParamForHyperVFeature(state=StateOnOff.on)
    #     ),
    #     pmu=PmuFeature(state=StateOnOff.on)
    # )

    # ======================
    # POWERPC ARCHITECTURE
    # ======================

    # 1. Базовый PowerPC профиль
    # powerpc_basic = PowerPCFeatures(
    #     acpi=AcpiFeature(state=StateOnOff.on),
    #     hpt=HptFeature(
    #         resizing=HptFeatureResizing.optional,
    #         maxpagesize=HptFeatureMaxPageSizeEnum.kb_64
    #     )
    # )
    #
    # # 2. PowerPC с HPT resizing
    # powerpc_hpt = PowerPCFeatures(
    #     acpi=AcpiFeature(state=StateOnOff.on),
    #     hpt=HptFeature(
    #         resizing=HptFeatureResizing.required,
    #         maxpagesize=HptFeatureMaxPageSizeEnum.mb_16
    #     ),
    #     mmu=MmuFeature(state=StateOnOff.on)
    # )
    #
    # # 3. PowerPC с Hardware Transactional Memory
    # powerpc_htm = PowerPCFeatures(
    #     acpi=AcpiFeature(state=StateOnOff.on),
    #     hpt=HptFeature(
    #         resizing=HptFeatureResizing.optional,
    #         maxpagesize=HptFeatureMaxPageSizeEnum.kb_64
    #     ),
    #     htm=HtmFeature(
    #         state=StateOnOff.on,
    #         suspensible=SuspensibleParamForHtmFeature(state=StateOnOff.on)
    #     ),
    #     capabilities=CapabilitiesFeature(
    #         sbbc=SbbcParamForHtmFeature(state=StateOnOff.on)
    #     )
    # )
    #
    # # 4. PowerPC производительный
    # powerpc_performance = PowerPCFeatures(
    #     acpi=AcpiFeature(state=StateOnOff.on),
    #     hpt=HptFeature(
    #         resizing=HptFeatureResizing.optional,
    #         maxpagesize=HptFeatureMaxPageSizeEnum.mb_16
    #     ),
    #     hap=HapFeature(state=StateOnOff.on),
    #     mmu=MmuFeature(state=StateOnOff.on),
    #     pmu=PmuFeature(state=StateOnOff.on)
    # )
    # x86_config = X86Features(
    #     acpi=AcpiFeature(state=StateOnOff.on),
    #     apic=ApicFeature(state=StateOnOff.on),
    #     vmx=VmxFeature(state=StateOnOff.on),  # Intel
    #     ioapic=IoApicFeature(driver=IoApic.kvm),
    #     pmu=PmuFeature(state=StateOnOff.on),
    #     hyperv=HyperVFeature(
    #         relaxed=RelaxedParamForHyperVFeature(state=StateOnOff.on)
    #     )
    # )
    # ======================
    # СПЕЦИАЛЬНЫЕ КЕЙСЫ
    # ======================

    # Смешанные кейсы через универсальный XmlFeatures (не рекомендуется, но возможно)

    # print(xml_manager.convert_features_to_xml(arm_performance))
    # print(xml_manager.convert_features_to_xml(powerpc_htm))
    # print(xml_manager.convert_features_to_xml(x86_config))

    # Конвертируем модель в XML
    # xml_str = XmlManager.model_to_xml(vm_config, "domain")
    # print("Generated XML:")
    # print(xml_str)
    #
    # # Или используем утилиту для создания полного домена
    # domain_xml = XmlUtils.create_domain_xml(vm_config)
    # print("\nFull Domain XML:")
    # print(domain_xml)
    #
    # # Пример парсинга XML обратно в модель
    # try:
    #     parsed_model = XmlManager.xml_to_model(xml_str, XmlObject)
    #     print("\nParsed model name:", parsed_model.name)
    # except Exception as e:
    #     print(f"Error parsing XML: {e}")