from enum import Enum


DIRECTORIES_FOR_SEARCH = [
    # Основные
    "/usr/bin",
    "/usr/libexec",  # RHEL/Fedora
    "/usr/lib",
    "/usr/lib64",
    # Пользовательские
    "/usr/local/bin",
    "/usr/local/libexec",
    # Опциональные
    "/opt",
    "/opt/homebrew/bin",  # macOS
    "/opt/local/bin",  # MacPorts
    # Snap/Flatpak
    "/snap/bin",
    "/var/lib/flatpak/exports/bin",
    # Nix
    "/nix/store/*/bin",
    "/run/current-system/sw/bin",
]

# Описания типов сетей
NETWORK_TYPE_DESCRIPTIONS = {
    "nat": "NAT сеть - ВМ получают доступ в интернет через NAT",
    "route": "Routed сеть - маршрутизация без NAT",
    "bridge": "Bridge сеть - прямое подключение к физическому интерфейсу",
    "private": "Private сеть - изолированная с внутренним форвардингом",
    "vepa": "VEPA сеть - Virtual Ethernet Port Aggregator",
    "passthrough": "Passthrough сеть - прямой доступ к физическому интерфейсу",
    "isolated": "Изолированная сеть - без доступа к внешним сетям",
    "no-forward": "Сеть без форвардинга - только внутренняя коммуникация",
}

QEMU_EMULATORS = {
    # === x86/x86_64 архитектуры ===
    "qemu-system-x86_64": "x86 64-bit (современные ПК/серверы)",
    "qemu-system-i386": "x86 32-bit (старые ПК)",
    "qemu-kvm": "Специальная версия для KVM (RedHat)",
    "kvm": "Упрощенный интерфейс KVM",
    "qemu-system-x86": "Общий x86 эмулятор",
    # === ARM архитектуры ===
    "qemu-system-aarch64": "ARM 64-bit (современные ARM устройства)",
    "qemu-system-arm": "ARM 32-bit (старые ARM устройства)",
    "qemu-system-aarch64_be": "ARM 64-bit big-endian",
    "qemu-system-armeb": "ARM 32-bit big-endian",
    # === RISC-V архитектуры ===
    "qemu-system-riscv64": "RISC-V 64-bit (современные RISC-V)",
    "qemu-system-riscv32": "RISC-V 32-bit",
    "qemu-system-riscv64gc": "RISC-V 64-bit с расширениями G и C",
    "qemu-system-riscv32gc": "RISC-V 32-bit с расширениями G и C",
    # === PowerPC/IBM архитектуры ===
    "qemu-system-ppc64": "PowerPC 64-bit (IBM серверы)",
    "qemu-system-ppc64le": "PowerPC 64-bit little-endian",
    "qemu-system-ppc": "PowerPC 32-bit",
    "qemu-system-ppcemb": "PowerPC embedded системы",
    # === MIPS архитектуры ===
    "qemu-system-mips64": "MIPS 64-bit (сетевые устройства)",
    "qemu-system-mips64el": "MIPS 64-bit little-endian",
    "qemu-system-mips": "MIPS 32-bit",
    "qemu-system-mipsel": "MIPS 32-bit little-endian",
    "qemu-system-mipsn32": "MIPS n32 ABI",
    "qemu-system-mipsn32el": "MIPS n32 little-endian",
    # === IBM System/390 ===
    "qemu-system-s390x": "IBM System/390 64-bit (мейнфреймы)",
    # === SPARC архитектуры ===
    "qemu-system-sparc64": "SPARC 64-bit (Sun/Oracle серверы)",
    "qemu-system-sparc": "SPARC 32-bit",
    "qemu-system-sparc32plus": "SPARC32+",
    # === Другие архитектуры ===
    "qemu-system-alpha": "DEC Alpha (устаревшие рабочие станции)",
    "qemu-system-cris": "Axis Communications CRIS",
    "qemu-system-hppa": "HP PA-RISC (HP-UX серверы)",
    "qemu-system-lm32": "LatticeMico32 (микроконтроллеры)",
    "qemu-system-m68k": "Motorola 68000 (классические Mac, Amiga)",
    "qemu-system-microblaze": "Xilinx MicroBlaze (FPGA)",
    "qemu-system-microblazeel": "MicroBlaze little-endian",
    "qemu-system-moxie": "Moxie процессоры",
    "qemu-system-nios2": "Altera Nios II (микроконтроллеры)",
    "qemu-system-or1k": "OpenRISC 1000",
    "qemu-system-rx": "Renesas RX микроконтроллеры",
    "qemu-system-sh4": "SuperH SH-4 (игровые приставки)",
    "qemu-system-sh4eb": "SuperH SH-4 big-endian",
    "qemu-system-tricore": "Infineon TriCore (автомобильные системы)",
    "qemu-system-xtensa": "Tensilica Xtensa (встроенные системы)",
    "qemu-system-xtensaeb": "Xtensa big-endian",
    # # === Специальные/утилиты ===
    # "qemu-img": "Утилита для работы с образами дисков",
    # "qemu-nbd": "Network Block Device сервер",
    # "qemu-io": "Утилита тестирования ввода-вывода",
    # "qemu-pr-helper": "Persistent reservation helper",
    # "qemu-storage-daemon": "Сервис для работы с хранилищами",
    # "qemu-ga": "QEMU Guest Agent",
    # "qemu-edid": "Генератор EDID данных для мониторов",
}


class CpuModelIntel(Enum):
    """Модели CPU Intel x86_64"""

    WESTMERE = "Westmere"
    SANDYBRIDGE = "SandyBridge"
    IVYBRIDGE = "IvyBridge"
    HASWELL = "Haswell"
    BROADWELL = "Broadwell"
    SKYLAKE_CLIENT = "Skylake-Client"
    SKYLAKE_SERVER = "Skylake-Server"
    CASCADELAKE_SERVER = "Cascadelake-Server"
    ICELAKE_CLIENT = "Icelake-Client"
    ICELAKE_SERVER = "Icelake-Server"
    COOPERLAKE = "Cooperlake"
    TIGERLAKE = "Tigerlake"
    SAPPHIRERAPIDS = "SapphireRapids"
    NEHALEM = "Nehalem"
    PENRYN = "Penryn"
    CONROE = "Conroe"
    CORE2DUO = "core2duo"
    QEMU64 = "qemu64"
    QEMU32 = "qemu32"
    HOST = "host"


class CpuModelAMD(Enum):
    """Модели CPU AMD x86_64"""

    OPTERON_G1 = "Opteron_G1"
    OPTERON_G2 = "Opteron_G2"
    OPTERON_G3 = "Opteron_G3"
    OPTERON_G4 = "Opteron_G4"
    OPTERON_G5 = "Opteron_G5"
    EPYC = "EPYC"
    EPYC_ROME = "EPYC-Rome"
    EPYC_MILAN = "EPYC-Milan"
    EPYC_GENOA = "EPYC-Genoa"
    PHENOM = "phenom"
    ATHLON = "athlon"
    K8 = "k8"
    K8_SSE3 = "k8-sse3"
    K10 = "k10"


class CpuModelARM(Enum):
    """Модели CPU ARM aarch64"""

    CORTEX_A7 = "cortex-a7"
    CORTEX_A8 = "cortex-a8"
    CORTEX_A9 = "cortex-a9"
    CORTEX_A15 = "cortex-a15"
    CORTEX_A35 = "cortex-a35"
    CORTEX_A53 = "cortex-a53"
    CORTEX_A55 = "cortex-a55"
    CORTEX_A57 = "cortex-a57"
    CORTEX_A72 = "cortex-a72"
    CORTEX_A73 = "cortex-a73"
    CORTEX_A76 = "cortex-a76"
    NEOVERSE_N1 = "neoverse-n1"
    A64FX = "a64fx"
    MAX = "max"


class CpuModelPowerPC(Enum):
    """Модели CPU PowerPC"""

    POWER8 = "POWER8"
    POWER9 = "POWER9"
    POWER10 = "POWER10"


class CpuModelS390X(Enum):
    """Модели CPU IBM System Z"""

    Z13 = "z13"
    Z14 = "z14"
    Z15 = "z15"
    Z16 = "z16"


class CpuModelRiscV(Enum):
    """Модели CPU RISC-V"""

    RV64 = "rv64"


class CpuModelMIPS(Enum):
    """Модели CPU MIPS"""

    MIPS64R6_GENERIC = "mips64r6-generic"


# Для проекта с LVM/виртуализацией используйте:
LVM_SAFE_FORBIDDEN = [
    "/",  # строго запрещено
    "\x00",  # строго запрещено
    " ",  # пробелы сложны в управлении
    "\t",  # табуляция
    "\n",  # newline
    "\r",  # carriage return
    "*",  # wildcard
    "?",  # wildcard
    "[",
    "]",  # могут конфликтовать с glob
    "{",
    "}",  # могут конфликтовать с expansion
    "|",  # pipe
    "&",  # background
    ";",  # command separator
    "`",  # backtick
    "$",  # dollar
    "#",  # hash
    "!",  # exclamation
    "~",  # tilde
    ">",
    "<",  # redirection
    "(",
    ")",  # parentheses
]
INVALID_LINUX_CHAR = [
    # 1. АБСОЛЮТНО ЗАПРЕЩЕННЫЕ СИМВОЛЫ:
    # Нулевой байт (символ конца строки в C)
    "\0",  # NULL character
    # Слэш (разделитель путей)
    "/",  # Path separator
    # 2. СИМВОЛЫ, КОТОРЫЕ ТРЕБУЮТ ЭКРАНИРОВАНИЯ (работают в кавычках):
    # Пробельные символы (не запрещены, но проблематичны)
    " ",  # Space
    "\t",  # Tab
    "\n",  # Newline
    "\r",  # Carriage return
    # 3. СИМВОЛЫ, ИСПОЛЬЗУЕМЫЕ SHELL (проблематичны без кавычек):
    # Метасимволы shell
    "|",  # Pipe
    "&",  # Ampersand
    ";",  # Semicolon
    "(",  # Open parenthesis
    ")",  # Close parenthesis
    "<",  # Less than (input redirection)
    ">",  # Greater than (output redirection)
    "`",  # Backtick (command substitution)
    # 4. СИМВОЛЫ ДЛЯ ПОДСТАНОВКИ И РАСШИРЕНИЯ:
    "*",  # Asterisk (wildcard)
    "?",  # Question mark (wildcard)
    "[",  # Open bracket (character class)
    "]",  # Close bracket (character class)
    "{",  # Open brace (brace expansion)
    "}",  # Close brace (brace expansion)
    "~",  # Tilde (home directory expansion)
    # 5. СИМВОЛЫ ДЛЯ ПЕРЕМЕННЫХ И КОМАНД:
    "$",  # Dollar sign (variable expansion)
    "!",  # Exclamation mark (history expansion)
    "#",  # Hash (comment)
    # 6. КАВЫЧКИ И ЭКРАНИРОВАНИЕ:
    '"',  # Double quote
    "'",  # Single quote
    "\\",  # Backslash (escape character)
    # 7. РЕДКИЕ ПРОБЛЕМНЫЕ СЛУЧАИ:
    # Двоеточие (в некоторых файловых системах или контекстах)
    ":",  # Colon (problematic in some filesystems)
    # Непечатаемые управляющие символы ASCII (0x01-0x1F)
    "\x01",  # SOH (Start of Heading)
    "\x02",  # STX (Start of Text)
    "\x03",  # ETX (End of Text) - также Ctrl+C
    "\x04",  # EOT (End of Transmission) - также Ctrl+D
    "\x05",  # ENQ (Enquiry)
    "\x06",  # ACK (Acknowledge)
    "\x07",  # BEL (Bell) - звуковой сигнал
    "\x08",  # BS (Backspace)
    "\x0b",  # VT (Vertical Tab)
    "\x0c",  # FF (Form Feed)
    "\x0e",  # SO (Shift Out)
    "\x0f",  # SI (Shift In)
    "\x10",  # DLE (Data Link Escape)
    "\x11",  # DC1 (Device Control 1)
    "\x12",  # DC2 (Device Control 2)
    "\x13",  # DC3 (Device Control 3)
    "\x14",  # DC4 (Device Control 4)
    "\x15",  # NAK (Negative Acknowledge)
    "\x16",  # SYN (Synchronous Idle)
    "\x17",  # ETB (End of Transmission Block)
    "\x18",  # CAN (Cancel)
    "\x19",  # EM (End of Medium)
    "\x1a",  # SUB (Substitute) - также Ctrl+Z
    "\x1b",  # ESC (Escape)
    "\x1c",  # FS (File Separator)
    "\x1d",  # GS (Group Separator)
    "\x1e",  # RS (Record Separator)
    "\x1f",  # US (Unit Separator)
    # DELETE character
    "\x7f",  # DEL (Delete)
]
