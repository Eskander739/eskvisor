from enum import Enum

from pydantic import BaseModel


class StatelessLoaderEnum(Enum):
    yes = "yes" # Игнорировать изменения в ПРОШИВКЕ
    no = "no" # (или не указано) - Разрешить изменения


class LoaderValueEnum(Enum):

    # x86_64
    general_uefi = "/usr/share/OVMF/OVMF_CODE.fd" # Основной UEFI (рекомендуется)
    uefi_with_secure_boot = "/usr/share/OVMF/OVMF_CODE.secboot.fd" # UEFI с Secure Boot
    bios = "/usr/share/qemu/bios.bin" # Устаревший BIOS

    # ARM (aarch64)

    arm_uefi = "/usr/share/AAVMF/AAVMF_CODE.fd"
    arm_uefi_with_secure_boot = "/usr/share/AAVMF/AAVMF_CODE.secboot.fd"

    # IBM Power
    ibm_power = "/usr/share/qemu/slof.bin"

    # IBM Z
    ibm_z = "/usr/share/qemu/s390-ccw.img"


class LoaderTypeEnum(Enum):
    """
    Тип загрузчика
    """

    rom = "rom" # ROM образ BIOS (устаревшее)
    pflash = "pflash" # PFlash память для UEFI (современное)
    none = "none" # Прямая загрузка ядра (минималистичное)


class ReadOnlyLoaderEnum(Enum):
    yes = "yes" # ROM код только для чтения
    no = "no" # Для модификации прошивки (опасно!)


class ConfigurationLoader(BaseModel):
    stateless: StatelessLoaderEnum | None = None
    value: LoaderValueEnum = LoaderValueEnum.general_uefi.value
    type: LoaderTypeEnum = LoaderTypeEnum.pflash.value
    readonly: ReadOnlyLoaderEnum = ReadOnlyLoaderEnum.yes
