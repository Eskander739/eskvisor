from xml.etree import ElementTree


class XmlClient:

    @staticmethod
    def xml_string_from_object(element_tree_object: ElementTree.Element) -> str:
        xml_string = ElementTree.tostring(element_tree_object).decode("utf-8")
        return xml_string

    @staticmethod
    def xml_object_from_string(xml_string: str) -> ElementTree.Element:
        return ElementTree.fromstring(xml_string)

    @staticmethod
    def set_element_in_parent(
        parent_object: ElementTree.Element,
        child_object: ElementTree.Element,
        position: int = None,
    ) -> None:
        """
        Вставляет дочерний элемент в родительский

        Args:
            parent_object: Родительский ElementTree объект
            child_object: Дочерний ElementTree объект для вставки
            position: Позиция для вставки (если None - добавляем в конец)
        """
        if position is not None and 0 <= position < len(parent_object):
            parent_object.insert(position, child_object)
        else:
            parent_object.append(child_object)

    def children(self, xml_desc: str | ElementTree.Element, is_string: bool = False) -> list[ElementTree.Element] | list[str]:
        if isinstance(xml_desc, str):
            xml_element = self.xml_object_from_string(xml_desc)
        else:
            xml_element = xml_desc

        children = xml_element.findall("./")
        if is_string:
            return [self.xml_string_from_object(child) for child in children]
        return children


if __name__ == "__main__":
    root = ElementTree.fromstring("""<domain type='kvm' id='1'>
  <name>alma-linux-eskvisor</name>
  <uuid>8dd078fc-321c-4057-946a-3c088f177d89</uuid>
  <memory unit='KiB'>2097152</memory>
  <currentMemory unit='KiB'>2097152</currentMemory>
  <vcpu placement='static' current='2'>4</vcpu>
  <resource>
    <partition>/machine</partition>
  </resource>
  <os>
    <type arch='x86_64' machine='pc-q35-9.0'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='custom' match='exact' check='full'>
    <model fallback='forbid'>Skylake-Client-IBRS</model>
    <vendor>Intel</vendor>
    <feature policy='require' name='vmx'/>
    <feature policy='require' name='hypervisor'/>
    <feature policy='require' name='ss'/>
    <feature policy='require' name='tsc_adjust'/>
    <feature policy='require' name='clflushopt'/>
    <feature policy='require' name='clwb'/>
    <feature policy='require' name='sha-ni'/>
    <feature policy='require' name='umip'/>
    <feature policy='require' name='pku'/>
    <feature policy='require' name='waitpkg'/>
    <feature policy='require' name='gfni'/>
    <feature policy='require' name='vaes'/>
    <feature policy='require' name='vpclmulqdq'/>
    <feature policy='require' name='rdpid'/>
    <feature policy='require' name='movdiri'/>
    <feature policy='require' name='movdir64b'/>
    <feature policy='require' name='fsrm'/>
    <feature policy='require' name='md-clear'/>
    <feature policy='require' name='serialize'/>
    <feature policy='require' name='stibp'/>
    <feature policy='require' name='flush-l1d'/>
    <feature policy='require' name='arch-capabilities'/>
    <feature policy='require' name='ssbd'/>
    <feature policy='require' name='avx-vnni'/>
    <feature policy='require' name='fsrs'/>
    <feature policy='require' name='xsaves'/>
    <feature policy='require' name='pdpe1gb'/>
    <feature policy='require' name='ibpb'/>
    <feature policy='require' name='ibrs'/>
    <feature policy='require' name='amd-stibp'/>
    <feature policy='require' name='amd-ssbd'/>
    <feature policy='require' name='rdctl-no'/>
    <feature policy='require' name='ibrs-all'/>
    <feature policy='require' name='skip-l1dfl-vmentry'/>
    <feature policy='require' name='mds-no'/>
    <feature policy='require' name='pschange-mc-no'/>
    <feature policy='require' name='sbdr-ssdp-no'/>
    <feature policy='require' name='fbsdp-no'/>
    <feature policy='require' name='psdp-no'/>
    <feature policy='require' name='gds-no'/>
    <feature policy='require' name='vmx-ins-outs'/>
    <feature policy='require' name='vmx-true-ctls'/>
    <feature policy='require' name='vmx-store-lma'/>
    <feature policy='require' name='vmx-activity-hlt'/>
    <feature policy='require' name='vmx-activity-wait-sipi'/>
    <feature policy='require' name='vmx-vmwrite-vmexit-fields'/>
    <feature policy='require' name='vmx-apicv-xapic'/>
    <feature policy='require' name='vmx-ept'/>
    <feature policy='require' name='vmx-desc-exit'/>
    <feature policy='require' name='vmx-rdtscp-exit'/>
    <feature policy='require' name='vmx-apicv-x2apic'/>
    <feature policy='require' name='vmx-vpid'/>
    <feature policy='require' name='vmx-wbinvd-exit'/>
    <feature policy='require' name='vmx-unrestricted-guest'/>
    <feature policy='require' name='vmx-apicv-register'/>
    <feature policy='require' name='vmx-apicv-vid'/>
    <feature policy='require' name='vmx-rdrand-exit'/>
    <feature policy='require' name='vmx-invpcid-exit'/>
    <feature policy='require' name='vmx-vmfunc'/>
    <feature policy='require' name='vmx-shadow-vmcs'/>
    <feature policy='require' name='vmx-rdseed-exit'/>
    <feature policy='require' name='vmx-pml'/>
    <feature policy='require' name='vmx-xsaves'/>
    <feature policy='require' name='vmx-tsc-scaling'/>
    <feature policy='require' name='vmx-enable-user-wait-pause'/>
    <feature policy='require' name='vmx-ept-execonly'/>
    <feature policy='require' name='vmx-page-walk-4'/>
    <feature policy='require' name='vmx-ept-2mb'/>
    <feature policy='require' name='vmx-ept-1gb'/>
    <feature policy='require' name='vmx-invept'/>
    <feature policy='require' name='vmx-eptad'/>
    <feature policy='require' name='vmx-invept-single-context'/>
    <feature policy='require' name='vmx-invept-all-context'/>
    <feature policy='require' name='vmx-invvpid'/>
    <feature policy='require' name='vmx-invvpid-single-addr'/>
    <feature policy='require' name='vmx-invvpid-all-context'/>
    <feature policy='require' name='vmx-intr-exit'/>
    <feature policy='require' name='vmx-nmi-exit'/>
    <feature policy='require' name='vmx-vnmi'/>
    <feature policy='require' name='vmx-preemption-timer'/>
    <feature policy='require' name='vmx-posted-intr'/>
    <feature policy='require' name='vmx-vintr-pending'/>
    <feature policy='require' name='vmx-tsc-offset'/>
    <feature policy='require' name='vmx-hlt-exit'/>
    <feature policy='require' name='vmx-invlpg-exit'/>
    <feature policy='require' name='vmx-mwait-exit'/>
    <feature policy='require' name='vmx-rdpmc-exit'/>
    <feature policy='require' name='vmx-rdtsc-exit'/>
    <feature policy='require' name='vmx-cr3-load-noexit'/>
    <feature policy='require' name='vmx-cr3-store-noexit'/>
    <feature policy='require' name='vmx-cr8-load-exit'/>
    <feature policy='require' name='vmx-cr8-store-exit'/>
    <feature policy='require' name='vmx-flexpriority'/>
    <feature policy='require' name='vmx-vnmi-pending'/>
    <feature policy='require' name='vmx-movdr-exit'/>
    <feature policy='require' name='vmx-io-exit'/>
    <feature policy='require' name='vmx-io-bitmap'/>
    <feature policy='require' name='vmx-mtf'/>
    <feature policy='require' name='vmx-msr-bitmap'/>
    <feature policy='require' name='vmx-monitor-exit'/>
    <feature policy='require' name='vmx-pause-exit'/>
    <feature policy='require' name='vmx-secondary-ctls'/>
    <feature policy='require' name='vmx-exit-nosave-debugctl'/>
    <feature policy='require' name='vmx-exit-load-perf-global-ctrl'/>
    <feature policy='require' name='vmx-exit-ack-intr'/>
    <feature policy='require' name='vmx-exit-save-pat'/>
    <feature policy='require' name='vmx-exit-load-pat'/>
    <feature policy='require' name='vmx-exit-save-efer'/>
    <feature policy='require' name='vmx-exit-load-efer'/>
    <feature policy='require' name='vmx-exit-save-preemption-timer'/>
    <feature policy='require' name='vmx-entry-noload-debugctl'/>
    <feature policy='require' name='vmx-entry-ia32e-mode'/>
    <feature policy='require' name='vmx-entry-load-perf-global-ctrl'/>
    <feature policy='require' name='vmx-entry-load-pat'/>
    <feature policy='require' name='vmx-entry-load-efer'/>
    <feature policy='require' name='vmx-eptp-switching'/>
    <feature policy='disable' name='hle'/>
    <feature policy='disable' name='rtm'/>
    <feature policy='disable' name='mpx'/>
  </cpu>
  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <pm>
    <suspend-to-mem enabled='no'/>
    <suspend-to-disk enabled='no'/>
  </pm>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='/eskvisor/storages/disk-351487.qcow2' index='2'/>
      <backingStore/>
      <target dev='sda' bus='sata'/>
      <alias name='sata0-0-0'/>
      <address type='drive' controller='0' bus='0' target='0' unit='0'/>
    </disk>
    <disk type='file' device='cdrom'>
      <driver name='qemu'/>
      <target dev='sdb' bus='sata'/>
      <readonly/>
      <alias name='sata0-0-1'/>
      <address type='drive' controller='0' bus='0' target='0' unit='1'/>
    </disk>
    <controller type='usb' index='0' model='ich9-ehci1'>
      <alias name='usb'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x1d' function='0x7'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci1'>
      <alias name='usb'/>
      <master startport='0'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x1d' function='0x0' multifunction='on'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci2'>
      <alias name='usb'/>
      <master startport='2'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x1d' function='0x1'/>
    </controller>
    <controller type='usb' index='0' model='ich9-uhci3'>
      <alias name='usb'/>
      <master startport='4'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x1d' function='0x2'/>
    </controller>
    <controller type='pci' index='0' model='pcie-root'>
      <alias name='pcie.0'/>
    </controller>
    <controller type='pci' index='1' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='1' port='0x10'/>
      <alias name='pci.1'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x0' multifunction='on'/>
    </controller>
    <controller type='pci' index='2' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='2' port='0x11'/>
      <alias name='pci.2'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x1'/>
    </controller>
    <controller type='pci' index='3' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='3' port='0x12'/>
      <alias name='pci.3'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x2'/>
    </controller>
    <controller type='pci' index='4' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='4' port='0x13'/>
      <alias name='pci.4'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x3'/>
    </controller>
    <controller type='pci' index='5' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='5' port='0x14'/>
      <alias name='pci.5'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x4'/>
    </controller>
    <controller type='pci' index='6' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='6' port='0x15'/>
      <alias name='pci.6'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x5'/>
    </controller>
    <controller type='pci' index='7' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='7' port='0x16'/>
      <alias name='pci.7'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x6'/>
    </controller>
    <controller type='pci' index='8' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='8' port='0x17'/>
      <alias name='pci.8'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x02' function='0x7'/>
    </controller>
    <controller type='pci' index='9' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='9' port='0x18'/>
      <alias name='pci.9'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x0' multifunction='on'/>
    </controller>
    <controller type='pci' index='10' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='10' port='0x19'/>
      <alias name='pci.10'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x1'/>
    </controller>
    <controller type='pci' index='11' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='11' port='0x1a'/>
      <alias name='pci.11'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x2'/>
    </controller>
    <controller type='pci' index='12' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='12' port='0x1b'/>
      <alias name='pci.12'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x3'/>
    </controller>
    <controller type='pci' index='13' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='13' port='0x1c'/>
      <alias name='pci.13'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x4'/>
    </controller>
    <controller type='pci' index='14' model='pcie-root-port'>
      <model name='pcie-root-port'/>
      <target chassis='14' port='0x1d'/>
      <alias name='pci.14'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x5'/>
    </controller>
    <controller type='sata' index='0'>
      <alias name='ide'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x1f' function='0x2'/>
    </controller>
    <interface type='network'>
      <mac address='52:54:00:f4:52:f0'/>
      <source network='nat-7792' portid='2e880c40-982e-4ae0-b70f-393e196bd52b' bridge='alma-nat-net'/>
      <target dev='vnet0'/>
      <model type='virtio'/>
      <alias name='net0'/>
      <address type='pci' domain='0x0000' bus='0x01' slot='0x00' function='0x0'/>
    </interface>
    <serial type='pty'>
      <source path='/dev/pts/1'/>
      <target type='isa-serial' port='0'>
        <model name='isa-serial'/>
      </target>
      <alias name='serial0'/>
    </serial>
    <console type='pty' tty='/dev/pts/1'>
      <source path='/dev/pts/1'/>
      <target type='serial' port='0'/>
      <alias name='serial0'/>
    </console>
    <input type='tablet' bus='usb'>
      <alias name='input0'/>
      <address type='usb' bus='0' port='1'/>
    </input>
    <input type='mouse' bus='ps2'>
      <alias name='input1'/>
    </input>
    <input type='keyboard' bus='ps2'>
      <alias name='input2'/>
    </input>
    <graphics type='vnc' port='5900' autoport='yes' listen='0.0.0.0'>
      <listen type='address' address='0.0.0.0'/>
    </graphics>
    <audio id='1' type='none'/>
    <video>
      <model type='qxl' ram='65536' vram='65536' vgamem='16384' heads='1' primary='yes'/>
      <alias name='video0'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x01' function='0x0'/>
    </video>
    <watchdog model='itco' action='reset'>
      <alias name='watchdog0'/>
    </watchdog>
    <memballoon model='virtio'>
      <alias name='balloon0'/>
      <address type='pci' domain='0x0000' bus='0x02' slot='0x00' function='0x0'/>
    </memballoon>
  </devices>
  <seclabel type='dynamic' model='selinux' relabel='yes'>
    <label>system_u:system_r:svirt_t:s0:c62,c911</label>
    <imagelabel>system_u:object_r:svirt_image_t:s0:c62,c911</imagelabel>
  </seclabel>
  <seclabel type='dynamic' model='dac' relabel='yes'>
    <label>+107:+107</label>
    <imagelabel>+107:+107</imagelabel>
  </seclabel>
</domain>""")
    xml_client = XmlClient()

    # Проверяем наличие UEFI
    os_elem = root.find(".//os")
    if os_elem is not None:
        print(xml_client.children(os_elem))