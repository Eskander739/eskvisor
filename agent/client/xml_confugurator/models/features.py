from enum import Enum

from pydantic import BaseModel

from agent.client.xml_confugurator.models.general import StateOnOff, IoApic



class HiddenParamForKVMFeature(BaseModel):
    state: StateOnOff | None = None


class HintDedicatedParamForKVMFeature(BaseModel):
    state: StateOnOff | None = None

class RelaxedParamForHyperVFeature(BaseModel):
    state: StateOnOff | None = None


class VapicParamForHyperVFeature(BaseModel):
    state: StateOnOff | None = None


class SpinLocksParamForHyperVFeature(BaseModel):
    state: StateOnOff | None = None
    retries: int | None = None


class HyperVFeature(BaseModel):
    relaxed: RelaxedParamForHyperVFeature | None = None # разметка
    vapic: VapicParamForHyperVFeature | None = None # разметка
    spinlocks: SpinLocksParamForHyperVFeature | None = None # разметка


class KVMVFeature(BaseModel):
    hidden: HiddenParamForKVMFeature | None = None # разметка
    hint_dedicated: HintDedicatedParamForKVMFeature | None = None # разметка

class E820HostParamXenFeature(BaseModel):
    state: StateOnOff | None = None


class XenFeature(BaseModel):
    e820_host: E820HostParamXenFeature | None = None # разметка


class ApicFeature(BaseModel):
    eoi: StateOnOff | None = None
    state: StateOnOff | None = None


class AcpiFeature(BaseModel):
    state: StateOnOff | None = None


class PaeFeature(BaseModel):
    state: StateOnOff | None = None

class NonPaeFeature(BaseModel):
    state: StateOnOff | None = None

class HapFeature(BaseModel):
    state: StateOnOff | None = None

class ViridianFeature(BaseModel):
    state: StateOnOff | None = None


class PrivnetFeature(BaseModel):
    state: StateOnOff | None = None


class SmmFeature(BaseModel):
    state: StateOnOff | None = None

class VmCoreInfoFeature(BaseModel):
    state: StateOnOff | None = None


class IoApicFeature(BaseModel):
    driver: IoApic | None = None

class PmuFeatureVersionEnum(Enum):
    three = "3"
    four = "4"

class PmuFeature(BaseModel):
    state: StateOnOff | None = None
    version: PmuFeatureVersionEnum | None = None # ARM только


class HptFeatureMaxPageSizeEnum(Enum):
    kb_16 = "16kB"
    kb_64 = "64kB"
    mb_16 = "16MB"


class HptFeatureResizing(Enum):
    required = "required"
    optional = "optional"


class HptFeature(BaseModel):
    resizing: HptFeatureResizing = HptFeatureResizing.optional
    maxpagesize: HptFeatureMaxPageSizeEnum | None = None


class VmPortFeatureModeEnum(Enum):
    auto = "auto"
    hypervisor = "hypervisor"
    emulate = "emulate"


class VmPortFeature(BaseModel):
    state: StateOnOff | None = None
    mode: VmPortFeatureModeEnum | None = None


class PvsPinLockFeature(BaseModel):
    state: StateOnOff | None = None

class MsrsFeatureUnknownEnum(Enum):
    ignore = "ignore"
    fault = "fault"



class MsrsFeature(BaseModel):
    unknown: MsrsFeatureUnknownEnum | None = None


class GicFeatureVersionEnum(Enum):
    two = "2"
    three = "3"

class GicFeature(BaseModel):
    version: GicFeatureVersionEnum = GicFeatureVersionEnum.two


class Aa64pFetchFeature(BaseModel):
    state: StateOnOff | None = None


class SveFeatureVLParam(BaseModel):
    length: int | None = None


class SveFeature(BaseModel):
    vl: SveFeatureVLParam | None = None


class SuspensibleParamForHtmFeature(BaseModel):
    state: StateOnOff | None = None


class HtmFeature(BaseModel):
    state: StateOnOff | None = None
    suspensible: SuspensibleParamForHtmFeature | None = None # разметка


class SbbcParamForHtmFeature(BaseModel):
    state: StateOnOff | None = None

class IbsParamForHtmFeature(BaseModel):
    state: StateOnOff | None = None

class CapabilitiesFeature(BaseModel):
    sbbc: SbbcParamForHtmFeature | None = None # разметка
    ibs: IbsParamForHtmFeature | None = None # разметка


class VmxFeature(BaseModel):
    state: StateOnOff | None = None


class SvmFeature(BaseModel):
    state: StateOnOff | None = None


class PvEOIFeature(BaseModel):
    state: StateOnOff | None = None


class PvUnhaltFeature(BaseModel):
    state: StateOnOff | None = None


class MmuFeature(BaseModel):
    state: StateOnOff | None = None


class BaseFeatures(BaseModel):
    """
    Базовые фичи, доступные на всех архитектурах
    """
    acpi: AcpiFeature | None = None
    apic: ApicFeature | None = None
    hap: HapFeature | None = None
    smm: SmmFeature | None = None
    pmu: PmuFeature | None = None
    mmu: MmuFeature | None = None
    htm: HtmFeature | None = None
    vmcoreinfo: VmCoreInfoFeature | None = None
    pvspinlock: PvsPinLockFeature | None = None
    capabilities: CapabilitiesFeature | None = None
    hyperv: HyperVFeature | None = None
    kvm: KVMVFeature | None = None


class X86Features(BaseFeatures):
    """
    Фичи специфичные для x86/x64 архитектуры
    """
    # x86 только
    pae: PaeFeature | None = None
    nonpae: NonPaeFeature | None = None
    ioapic: IoApicFeature | None = None
    vmport: VmPortFeature | None = None
    vmx: VmxFeature | None = None
    svm: SvmFeature | None = None
    msrs: MsrsFeature | None = None

    # Устаревшие/специфичные x86
    viridian: ViridianFeature | None = None
    pv_eoi: PvEOIFeature | None = None
    pv_unhalt: PvUnhaltFeature | None = None

    # Xen в основном на x86 (хотя есть ARM порт)
    xen: XenFeature | None = None

    # Устаревшие Xen фичи
    privnet: PrivnetFeature | None = None


class ARMFeatures(BaseFeatures):
    """
    Фичи специфичные для ARM архитектуры
    """
    # ARM только
    gic: GicFeature | None = None
    aa64pfetch: Aa64pFetchFeature | None = None
    sve: SveFeature | None = None


class PowerPCFeatures(BaseFeatures):
    """
    Фичи специфичные для PowerPC/IBM POWER архитектуры
    """
    # PowerPC только
    hpt: HptFeature | None = None

