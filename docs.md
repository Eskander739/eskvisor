# Руководство по работе с libvirt
## Содержание
* Введение
* Установка и настройка
* Основные концепции
* Работа с виртуальными машинами
* Управление сетями
* Работа с хранилищами
* Мониторинг и производительность
* Безопасность
* Примеры использования
* Устранение неполадок
* Полезные ссылки
## Введение
***libvirt*** - это инструментарий для управления виртуализацией, предоставляющий унифицированный API для работы с различными системами виртуализации, включая KVM/QEMU.
Основные компоненты
* ***libvirt-daemon*** - фоновый сервис
* ***libvirt-client*** - клиентские утилиты
* ***virt-manager*** - графический интерфейс
* ***virsh*** - это интерактивная командная утилита или CLI (Command Line Interface) для управления libvirt,

## Установка и настройка
### Установка на Debian/Ubuntu
```commandline
sudo apt update
sudo apt install qemu-kvm libvirt-daemon-system libvirt-clients \
    bridge-utils virt-manager ovmf
```
### Установка на RHEL/CentOS/Fedora
```commandline
sudo dnf install @virtualization
sudo systemctl enable --now libvirtd
```
### Добавление пользователя в группу libvirt
```commandline
sudo usermod -aG libvirt $USER
sudo usermod -aG kvm $USER

# Чтобы не приходилось каждый раз прописывать пароль для root пользователя
# После выполнения требуется перелогиниться
```
## Проверка установки
```commandline
virsh version
virt-host-validate
```
### Основные концепции
#### Домены (виртуальные машины)
Домен — это экземпляр виртуальной машины, управляемый libvirt.
### Подключения (connections)
Подключение — это сессия для взаимодействия с гипервизором:
* ***Системное подключение (qemu:///system)*** — для привилегированных ВМ
* ***Пользовательское подключение (qemu:///session)*** — для непривилегированных ВМ
### Хранилища (storage pools)
Логические контейнеры для хранения образов дисков.
### Сети (networks)
Виртуальные сети для подключения ВМ.
## Работа с виртуальными машинами
### Создание ВМ с помощью virt-install
#### Базовый пример
bash
```commandline
virt-install \
    --name ubuntu-vm \
    --ram 2048 \
    --vcpus 2 \
    --disk size=20 \
    --os-variant ubuntu22.04 \
    --network network=default \
    --graphics spice \
    --console pty,target_type=serial \
    --location /path/to/ubuntu.iso \
    --extra-args 'console=ttyS0,115200n8 serial'
```
#### Создание ВМ из cloud-образа

```commandline
virt-install \
    --name cloud-vm \
    --ram 2048 \
    --vcpus 2 \
    --import \
    --disk /var/lib/libvirt/images/cloud-image.qcow2 \
    --os-variant ubuntu22.04 \
    --network network=default \
    --graphics none \
    --console pty,target_type=serial
```
## Управление ВМ через virsh
### Просмотр списка ВМ
```commandline
# Все ВМ
virsh list --all

# Только работающие
virsh list

# Подробная информация
virsh dominfo <имя-вм>
```

### Запуск и остановка
```commandline
# Запуск
virsh start <имя-вм>

# Плавная остановка
virsh shutdown <имя-вм>

# Принудительная остановка
virsh destroy <имя-вм>

# Автозапуск
virsh autostart <имя-вм>
virsh autostart --disable <имя-вм>
```

## Консоль ВМ
```commandline
# Подключение к консоли
virsh console <имя-вм>

# Выйти из консоли: Ctrl+]
```
### Редактирование конфигурации
```commandline
# Временное редактирование
virsh edit <имя-вм>

# Дамп конфигурации в файл
virsh dumpxml <имя-вм> > vm-config.xml

# Определение ВМ из файла
virsh define vm-config.xml

# Удаление ВМ (сохраняет диски)
virsh undefine <имя-вм>
virsh undefine --remove-all-storage <имя-вм>
```
## Снимки (snapshots)
```commandline
# Создание снапшота
virsh snapshot-create-as <имя-вм> <имя-снапшота> \
    --description "Описание"

# Просмотр снапшотов
virsh snapshot-list <имя-вм>

# Восстановление
virsh snapshot-revert <имя-вм> <имя-снапшота>

# Удаление
virsh snapshot-delete <имя-вм> <имя-снапшота>
```
## Конфигурационный файл ВМ (XML)
### Пример минимальной конфигурации:
```xml
<domain type='kvm'>
  <name>example-vm</name>
  <memory unit='KiB'>2097152</memory>
  <currentMemory unit='KiB'>2097152</currentMemory>
  <vcpu placement='static'>2</vcpu>
  
  <os>
    <type arch='x86_64' machine='pc-q35-7.2'>hvm</type>
    <boot dev='hd'/>
  </os>
  
  <features>
    <acpi/>
    <apic/>
    <vmport state='off'/>
  </features>
  
  <cpu mode='host-passthrough' check='none'/>
  
  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>
  
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='/var/lib/libvirt/images/example.qcow2'/>
      <target dev='vda' bus='virtio'/>
      <address type='pci' domain='0x0000' bus='0x04' slot='0x00' function='0x0'/>
    </disk>
    
    <interface type='network'>
      <mac address='52:54:00:11:22:33'/>
      <source network='default'/>
      <model type='virtio'/>
      <address type='pci' domain='0x0000' bus='0x01' slot='0x00' function='0x0'/>
    </interface>
  </devices>
</domain>
```
## Управление сетями
### Встроенные сети
#### Сеть по умолчанию (NAT)
```commandline
# Активация
virsh net-start default
virsh net-autostart default

# Информация
virsh net-info default
```
#### Просмотр сетей
```commandline
# Список сетей
virsh net-list --all

# Детали сети
virsh net-dumpxml default
```
## Создание пользовательской сети
### Пример конфигурации сети
```xml
<network>
  <name>isolated-net</name>
  <bridge name='virbr1' stp='on' delay='0'/>
  <domain name='example.local'/>
  <ip address='192.168.100.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.100.100' end='192.168.100.200'/>
      <host mac='52:54:00:aa:bb:cc' name='vm1' ip='192.168.100.50'/>
    </dhcp>
  </ip>
</network>
```
### Создание и управление
```commandline
# Создание из файла
virsh net-define network.xml
virsh net-start isolated-net
virsh net-autostart isolated-net

# Удаление
virsh net-destroy isolated-net
virsh net-undefine isolated-net
```

### Мостовая сеть (bridge)
#### Создание моста
```commandline
# Установка утилит
sudo apt install bridge-utils

# Создание моста
sudo brctl addbr br0
sudo ip addr add 192.168.1.100/24 dev br0
sudo ip link set br0 up

# Настройка libvirt
cat > bridge-net.xml << EOF
<network>
  <name>host-bridge</name>
  <forward mode="bridge"/>
  <bridge name="br0"/>
</network>
EOF

virsh net-define bridge-net.xml
virsh net-start host-bridge
virsh net-autostart host-bridge
```
## Работа с хранилищами
### Типы хранилищ
    • dir — директория на файловой системе
    • fs — предварительно отформатированный раздел
    • netfs — сетевая файловая система (NFS)
    • logical — LVM том
    • disk — физический диск
    • iscsi — iSCSI целевое устройство
    • scsi — SCSI устройство
### Управление пулами хранилищ
#### Создание пула в директории
```commandline
# Создание XML файла
cat > pool-dir.xml << EOF
<pool type='dir'>
  <name>vm-storage</name>
  <target>
    <path>/var/lib/libvirt/vm-storage</path>
  </target>
</pool>
EOF

# Определение и запуск
virsh pool-define pool-dir.xml
virsh pool-build vm-storage
virsh pool-start vm-storage
virsh pool-autostart vm-storage
```
### Создание пула LVM
```xml
<pool type='logical'>
  <name>lvm-pool</name>
  <source>
    <device path='/dev/sdb'/>
    <name>vg_virt</name>
  </source>
  <target>
    <path>/dev/vg_virt</path>
  </target>
</pool>
```
### Команды управления пулами
```commandline
# Список пулов
virsh pool-list --all

# Информация о пуле
virsh pool-info <имя-пула>

# Просмотр томов в пуле
virsh vol-list <имя-пула>

# Создание тома
virsh vol-create-as <имя-пула> <имя-тома> 20G --format qcow2

# Удаление тома
virsh vol-delete --pool <имя-пула> <имя-тома>

# Изменение размера тома
virsh vol-resize --pool <имя-пула> <имя-тома> 30G
```

### Форматы образов дисков
```commandline
# Конвертация между форматами
qemu-img convert -f raw -O qcow2 input.img output.qcow2
qemu-img convert -f qcow2 -O qcow2 -c input.qcow2 compressed.qcow2

# Изменение размера
qemu-img resize disk.qcow2 +5G

# Информация об образе
qemu-img info disk.qcow2

# Создание образа
qemu-img create -f qcow2 disk.qcow2 20G
```
### Мониторинг и производительность
#### Мониторинг ВМ
```commandline
# Статистика домена
virsh domstats <имя-вм>

# Потребление CPU
virsh cpu-stats <имя-вм>

# Использование памяти
virsh dommemstat <имя-вм>

# Информация о блочных устройствах
virsh domblklist <имя-вм>
virsh domblkinfo <имя-вм> <устройство>

# Информация о сети
virsh domiflist <имя-вм>
virsh domifstat <имя-вм> <интерфейс>
```

### Тюнинг производительности
#### Конфигурация CPU
```xml
<cpu mode='host-passthrough' check='none'>
  <topology sockets='1' dies='1' cores='4' threads='2'/>
  <cache mode='passthrough'/>
  <feature policy='require' name='vmx'/>
</cpu>
```
#### Конфигурация памяти
```xml
<memoryBacking>
  <hugepages>
    <page size='2048' unit='KiB' nodeset='0'/>
  </hugepages>
  <nosharepages/>
  <locked/>
</memoryBacking>
```
#### Конфигурация ввода-вывода
```xml
<iothreads>4</iothreads>
<cputune>
  <vcpupin vcpu='0' cpuset='0'/>
  <vcpupin vcpu='1' cpuset='1'/>
  <emulatorpin cpuset='2-3'/>
  <iothreadpin iothread='1' cpuset='4-5'/>
</cputune>
```
## Безопасность
### Настройка SELinux
```commandline
# Проверка статуса
sestatus

# Разрешить libvirt доступ к директориям
semanage fcontext -a -t virt_image_t "/custom/path(/.*)?"
restorecon -R /custom/path
```
### AppArmor профили
```commandline
# Редактирование профилей
sudo vim /etc/apparmor.d/usr.lib.libvirt.virt-aa-helper
sudo systemctl reload apparmor
```
### Ограничения ресурсов cgroups
```xml
<resource>
  <partition>/virtualmachines</partition>
</resource>
<memtune>
  <hard_limit unit='KiB'>4194304</hard_limit>
  <soft_limit unit='KiB'>2097152</soft_limit>
</memtune>
```
## Примеры использования
### Автоматизация развертывания ВМ
#### Скрипт создания ВМ
```commandline
#!/bin/bash
VM_NAME=$1
VM_RAM=2048
VM_CPUS=2
DISK_SIZE=20
OS_VARIANT="ubuntu22.04"

virt-install \
  --name "${VM_NAME}" \
  --ram "${VM_RAM}" \
  --vcpus "${VM_CPUS}" \
  --disk size="${DISK_SIZE}" \
  --os-variant "${OS_VARIANT}" \
  --network network=default \
  --graphics spice \
  --location /iso/ubuntu-22.04.iso \
  --noautoconsole
```

## Миграция ВМ
### Live миграция
```commandline
# Миграция на другой хост
virsh migrate --live <имя-вм> qemu+ssh://user@remotehost/system
```
## Оффлайн миграция
```commandline
# Дамп конфигурации и перенос дисков
virsh dumpxml <имя-вм> > vm.xml
scp vm.xml user@remotehost:/tmp/
scp /var/lib/libvirt/images/vm-disk.qcow2 user@remotehost:/var/lib/libvirt/images/

# На целевом хосте
virsh define /tmp/vm.xml
virsh start <имя-вм>
```

## Резервное копирование
### Скрипт резервного копирования
```commandline
#!/bin/bash
BACKUP_DIR="/backup/vms"
DATE=$(date +%Y%m%d_%H%M%S)

for VM in $(virsh list --name --all); do
  echo "Backing up $VM..."
  
  # Дамп конфигурации
  virsh dumpxml "$VM" > "$BACKUP_DIR/${VM}_${DATE}.xml"
  
  # Получение списка дисков
  for DISK in $(virsh domblklist "$VM" | awk '/^[sh]d[a-z]/ {print $2}'); do
    DISK_NAME=$(basename "$DISK")
    cp "$DISK" "$BACKUP_DIR/${VM}_${DISK_NAME}_${DATE}.qcow2"
  done
done
```
## Устранение неполадок
### Журналы (logs)
```commandline
# Основной лог libvirt
sudo journalctl -u libvirtd -f

# Лог конкретной ВМ
virsh dumpxml <имя-вм> | grep log
sudo tail -f /var/log/libvirt/qemu/<имя-вм>.log
```
## Отладка подключений
```commandline
# Проверка подключения
virsh uri
virsh connect

# Подробный вывод
LIBVIRT_DEBUG=1 virsh list
```
## Распространенные проблемы
### Ошибка прав доступа
```commandline
# Проверка групп
groups $USER

# Проверка прав на сокет
ls -la /var/run/libvirt/libvirt-sock

# Решение
sudo chmod a+rx /var/lib/libvirt
```
## Ошибка сети
```commandline
# Проверка сетевого моста
ip addr show virbr0
sudo systemctl restart libvirtd
virsh net-start default
```

## Ошибка при запуске ВМ
```commandline
# Проверка KVM модулей
lsmod | grep kvm

# Перезагрузка служб
sudo systemctl restart libvirtd
```

## Восстановление после сбоя
### Список нерабочих ВМ
```commandline
virsh list --inactive

# Принудительный сброс
virsh reset <имя-вм>

# Очистка блокировок
sudo rm -f /var/lib/libvirt/qemu/lock/*.lock
sudo rm -f /var/lib/libvirt/qemu/run/*.pid
```

## Утилиты диагностики
```commandline
# Проверка системы
virt-host-validate

# Информация о хосте
virsh nodeinfo
virsh freecell
virsh capabilities

# Список всех команд virsh
virsh help
```

## Просмотреть все доступные типы машин
```commandline
virsh domcapabilities | grep -A 50 "<arch name='x86_64'>"

# Или через QEMU
/usr/bin/qemu-system-x86_64 -machine help

# Для конкретной архитектуры
virsh capabilities | xmlstarlet sel -t -v "//guest/arch[@name='x86_64']/domain/machine"
```
## Типичные ошибки и решения
### Ошибка 1: Несовместимость машины и ОС
```
Ошибка: unsupported configuration: machine type 'pc-q35-7.2' is not supported by hypervisor
```
#### Решение: Укажите более старую версию или другую машину:

```xml
<type arch='x86_64' machine='pc-i440fx-7.2'>hvm</type>
```
### Ошибка 2: Несоответствие архитектуры
```
Ошибка: invalid argument: could not find capabilities for arch=x86_64
```
#### Решение: Проверьте поддержку архитектуры:

```commandline
virsh capabilities | grep "arch"
```
### Ошибка 3: Для UEFI не указан loader
```
Ошибка: XML error: UEFI boot requested but no UEFI loader configured
```
#### Решение: Добавьте loader:

```xml
<os>
  <type arch='x86_64' machine='pc-q35-7.2'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/vm1_VARS.fd</nvram>
</os>
```
## Рекомендации по выбору
### Для современных ОС (2020+):
```xml
<os>
  <type arch='x86_64' machine='pc-q35-7.2'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <boot dev='hd'/>
</os>
```
### Для максимальной совместимости:
```xml
<os>
  <type arch='x86_64' machine='pc-i440fx-7.2'>hvm</type>
  <boot dev='hd'/>
  <boot dev='cdrom'/>
</os>
```
### Для легковесных Linux (Alpine, CoreOS):
```xml
<os>
  <type arch='x86_64'>hvm</type>
  <kernel>/boot/vmlinuz</kernel>
  <initrd>/boot/initrd</initrd>
  <cmdline>console=ttyS0</cmdline>
</os>
```
### Для Windows:
```xml
<!-- Windows 10/11 -->
<os>
  <type arch='x86_64' machine='pc-q35-7.2'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <boot dev='cdrom'/>  <!-- для установки -->
  <boot dev='hd'/>     <!-- после установки -->
</os>

<!-- Windows 7/XP -->
<os>
  <type arch='x86_64' machine='pc-i440fx-7.2'>hvm</type>
  <boot dev='cdrom'/>
  <boot dev='hd'/>
</os>
```
###  Автоматическое определение через virt-install
```commandline
# Virt-install сам определит правильный тип
virt-install \
  --os-variant ubuntu22.04 \
  --machine q35 \
  --boot uefi

# Просмотреть все варианты OS
osinfo-query os
```
### Проверка конфигурации
```commandline
# Проверить XML перед определением
virsh define --validate vm.xml

# Посмотреть текущую конфигурацию
virsh dumpxml vm-name | grep -A 5 "<os>"

# Проверить поддержку гипервизором
virsh domcapabilities | grep -B5 -A5 "pc-q35"
```

### Как найти доступные прошивки
```commandline
# Поиск OVMF (x86 UEFI)
find /usr/share -name "*OVMF*.fd" -type f

# Поиск AAVMF (ARM UEFI)
find /usr/share -name "*AAVMF*.fd" -type f

# Поиск BIOS образов
find /usr/share -name "*.bin" -type f | grep -i bios
find /usr/share/qemu -name "*.bin"

# Установка прошивок
sudo apt install ovmf             # Debian/Ubuntu
sudo dnf install edk2-ovmf        # Fedora/RHEL
sudo pacman -S edk2-ovmf          # Arch
```
### Управление NVRAM файлами
```commandline
# Просмотр существующих NVRAM файлов
ls -la /var/lib/libvirt/qemu/nvram/

# Создать копию шаблона вручную
sudo cp /usr/share/OVMF/OVMF_VARS.fd /var/lib/libvirt/qemu/nvram/myvm_VARS.fd
sudo chown libvirt-qemu:libvirt-qemu /var/lib/libvirt/qemu/nvram/myvm_VARS.fd

# Очистить NVRAM (сброс настроек UEFI)
sudo dd if=/dev/zero of=/var/lib/libvirt/qemu/nvram/myvm_VARS.fd bs=1M count=64

# Восстановить из шаблона
sudo cp /usr/share/OVMF/OVMF_VARS.fd /var/lib/libvirt/qemu/nvram/myvm_VARS.fd

# Удалить NVRAM при удалении ВМ
virsh undefine myvm --nvram
```
## Важные особенности и настройки
### 1. Размер NVRAM
```commandline
# Проверить размер NVRAM файла
ls -lh /usr/share/OVMF/OVMF_VARS.fd
# Обычно 64K-128K

# Увеличить размер (если нужно больше переменных)
sudo truncate -s 128K /var/lib/libvirt/qemu/nvram/vm_VARS.fd
```
### 2. Модель загрузки UEFI

```xml
<!-- Для графического интерфейса UEFI -->
<loader readonly='yes' type='pflash'>
  /usr/share/OVMF/OVMF_CODE.fd
</loader>

<!-- Для текстового режима (меньше ресурсов) -->
<loader readonly='yes' type='pflash'>
  /usr/share/OVMF/OVMF_CODE.ms.fd  # "minimal size"
</loader>
```
### 3. Прямая загрузка ядра (без прошивки)
```xml
<os>
  <type arch='x86_64'>hvm</type>
  
  <!-- Прямая загрузка ядра -->
  <kernel>/var/lib/libvirt/images/kernel</kernel>
  <initrd>/var/lib/libvirt/images/initrd</initrd>
  <cmdline>console=ttyS0 root=/dev/vda1</cmdline>
  
  <!-- Нет loader/nvram -->
</os>
```
### 4. Управление через virsh
```commandline
# Изменить boot order без редактирования XML
virsh dumpxml vm > vm.xml
# Отредактировать вручную

# Или через изменение параметров
virsh edit vm

# Просмотр текущих настроек
virsh dumpxml vm | xmllint --xpath "//os" -
```

4. Проблемы и решения
#### Проблема: ВМ загружается не с того устройства
### Решение:

```xml
<!-- Убедитесь, что правильный порядок -->
<boot dev='cdrom'/>    <!-- Первый -->
<boot dev='hd'/>       <!-- Второй -->
<boot dev='network' enable='no'/>  <!-- Отключен -->
```
#### Проблема: Ошибка загрузки UEFI
#### Решение:

```commandline
# Проверить наличие прошивки
sudo apt install ovmf

# Создать NVRAM файл

sudo cp /usr/share/OVMF/OVMF_VARS.fd /var/lib/libvirt/qemu/nvram/vm_VARS.fd
sudo chown libvirt-qemu:libvirt-qemu /var/lib/libvirt/qemu/nvram/vm_VARS.fd
```
#### Проблема: Secure Boot блокирует загрузку
#### Решение:

```xml
<!-- Использовать без Secure Boot -->
<loader readonly='yes' type='pflash'>
  /usr/share/OVMF/OVMF_CODE.fd  # Без .secboot
</loader>
```
## Краткий справочник
### Для обычной ВМ:
```xml
<os>
  <type arch='x86_64' machine='pc-q35-7.2'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/vm_VARS.fd</nvram>
  <boot dev='cdrom'/>
  <boot dev='hd'/>
</os>
```
### Для сервера:
```xml
<os>
  <type arch='x86_64' machine='pc-q35-7.2'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/OVMF/OVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/server_VARS.fd</nvram>
  <boot dev='network'/>
  <boot dev='hd'/>
</os>
```
### Для совместимости:
```xml
<os>
  <type arch='x86_64' machine='pc-i440fx-7.2'>hvm</type>
  <!-- Нет loader/nvram для BIOS -->
  <boot dev='cdrom'/>
  <boot dev='hd'/>
</os>
```
### Для ARM:
```xml
<os>
  <type arch='aarch64' machine='virt-7.2'>hvm</type>
  <loader readonly='yes' type='pflash'>/usr/share/AAVMF/AAVMF_CODE.fd</loader>
  <nvram>/var/lib/libvirt/qemu/nvram/arm-vm_VARS.fd</nvram>
  <boot dev='network'/>
  <boot dev='hd'/>
</os>
```

### Проверка поддержки KVM:
```commandline
# Проверить наличие аппаратной виртуализации
LC_ALL=C lscpu | grep Virtualization

# Проверить загруженные модули
lsmod | grep kvm

# Проверить через libvirt
virt-host-validate

# Проверить права
groups $USER | grep kvm
```
### Разные значения (для памяти с шарнированием):
```xml
<memory unit='MiB'>2048</memory>
<currentMemory unit='MiB'>1024</memory>
```
* ВМ запускается с 1GB
* Можно увеличить до 2GB без перезапуска (ballooning)
* Требует virsh setmem или драйвер balloon в гостевой ОС

### Ballooning драйвер:
```xml
<memory unit='MiB'>4096</memory>
<currentMemory unit='MiB'>1024</memory>
<memballoon model='virtio'>
  <stats period='10'/>
</memballoon>
```
### Управление памятью в runtime:
```commandline
# Изменить выделенную память (требует balloon драйвер)
virsh setmem minimal-vm 2G --live

# Узнать текущее использование
virsh dommemstat minimal-vm

# Установить максимальный предел
virsh setmaxmem minimal-vm 4G
```
### Управление vCPU в runtime:
```commandline
# Горячее добавление vCPU (требует настройки в XML)
virsh setvcpus minimal-vm 4 --live

# Просмотр информации
virsh vcpuinfo minimal-vm
```

## Частые проблемы и решения
### Проблема 1: Windows не устанавливается
```xml
<!-- Решение: добавить Hyper-V фичи -->
<features>
  <acpi/>
  <apic/>
  <hyperv>
    <relaxed state='on'/>
    <vapic state='on'/>
  </hyperv>
</features>
```

### Проблема 2: ВМ не выключается изнутри
```xml
<!-- Решение: проверить ACPI -->
<features>
  <acpi/>  <!-- Должен быть! -->
  <apic/>
</features>
```

### Проблема 3: 32-bit ОС не видит всю память
```xml
<!-- Решение: добавить PAE -->
<features>
  <acpi/>
  <apic/>
  <pae/>
</features>
```

### Проблема 4: Гость определяет, что это виртуальная машина
```xml
<!-- Решение: скрыть фичи -->
<features>
  <acpi/>
  <apic/>
  <kvm>
    <hidden state='on'/>
  </kvm>
  <vmport state='off'/>
</features>
```
## Как проверить текущие фичи?
### Извне ВМ:
```commandline
virsh dumpxml vm-name | xmllint --xpath "//features" -
```
### Изнутри Linux гостя:
```commandline
# Проверить ACPI
ls /sys/firmware/acpi/tables/

# Проверить APIC
dmesg | grep -i apic
cat /proc/interrupts

# Проверить PAE
grep pae /proc/cpuinfo
```

### Изнутри Windows гостя:
```cmd
msinfo32
# Смотреть в "Эмуляция системы" и "Процессор"
```

## Рекомендации по настройке
### Для большинства Linux:
```xml
<features>
  <acpi/>
  <apic/>
  <vmport state='off'/>
</features>
```

### Для Windows 10/11:
```xml
<features>
  <acpi/>
  <apic/>
  <hyperv>
    <relaxed state='on'/>
    <vapic state='on'/>
    <spinlocks state='on' retries='8191'/>
  </hyperv>
</features>
```

### Для Docker/контейнерных ВМ:
```xml
<features>
  <acpi/>
  <apic/>
  <kvm>
    <hidden state='on'/>
  </kvm>
</features>
```

### Для вложенной виртуализации:
```xml
<features>
  <acpi/>
  <apic/>
  <vmx/>  <!-- Intel -->
  <!-- или -->
  <svm/>  <!-- AMD -->
</features>
```
### Что происходит без секции features?

```xml
<!-- Если НЕТ секции features -->
<domain>
  <!-- ... -->
  <!-- NO <features> section -->
</domain>
```
#### Результат:

* Нет ACPI → нельзя выключить ВМ изнутри
* Нет APIC → многопроцессорность не работает
* Могут быть проблемы с управлением питанием

***Рекомендация***: Всегда включайте хотя бы:

```xml
<features>
  <acpi/>
  <apic/>
</features>
```
`<acpi/>` и `<apic/>` - ***обязательные фичи: ACPI для управления питанием и выключения ВМ изнутри, 
APIC для работы многопроцессорности (SMP) и обработки прерываний.***

# Закрепление vCPU за физическими ядрами
virsh vcpupin minimal-vm 0 2,3  # vCPU 0 → ядра 2,3
Краткий итог
* `<type arch='x86_64'>hvm</type>` - 99% случаев для KVM
* `machine='pc-q35-7.2'` - для современных ОС с UEFI
* `machine='pc-i440fx-7.2'` - для старых ОС или максимальной совместимости
* ***Всегда указывайте конкретную версию*** machine для воспроизводимости
* ***Для UEFI обязательно добавьте*** <loader>
* ***arch должен соответствовать*** гостевой ОС и поддерживаться гипервизором


## Полезные ссылки
* Официальная документация libvirt
* Документация QEMU
* Справочник по XML схеме libvirt
* Репозиторий libvirt на GitHub
