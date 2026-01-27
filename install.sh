#!/bin/bash

# install.sh для AlmaLinux - установка зависимостей для Eskvisor

# Цвета для логгирования
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Переменные для подсчета результатов
SUCCESS_COUNT=0
ERROR_COUNT=0
SKIP_COUNT=0

# Функция логирования
log_success() {
    echo -e "${GREEN}[УСПЕХ]${NC} $1"
    ((SUCCESS_COUNT++))
}

log_error() {
    echo -e "${RED}[ОШИБКА]${NC} $1"
    ((ERROR_COUNT++))
}

log_skip() {
    echo -e "${YELLOW}[ПРОПУЩЕНО]${NC} $1"
    ((SKIP_COUNT++))
}

# Функция проверки установки пакета
is_package_installed() {
    rpm -q "$1" &> /dev/null
    return $?
}

# Функция установки пакета с проверкой
install_package() {
    local package_name=$1
    local friendly_name=${2:-$1}

    if is_package_installed "$package_name"; then
        log_skip "$friendly_name уже установлен"
        return 0
    fi

    echo "Установка $friendly_name..."
    if sudo dnf install -y "$package_name"; then
        log_success "$friendly_name установлен"
        return 0
    else
        log_error "Ошибка установки $friendly_name"
        return 1
    fi
}

# Начало скрипта
echo "========================================="
echo "Установка зависимостей для Eskvisor на AlmaLinux"
echo "========================================="

# Обновление системы
echo "Обновление системы..."
if sudo dnf update -y; then
    log_success "Система обновлена"
else
    log_error "Ошибка обновления системы"
fi

# Установка базовых утилит
install_package "nano" "Текстовый редактор Nano"
install_package "sudo" "Утилита sudo"

# Установка и настройка SSH
install_package "openssh-server" "SSH сервер"

echo "Настройка SSH сервера..."
sudo systemctl enable sshd
sudo systemctl start sshd

if sudo systemctl is-active --quiet sshd; then
    log_success "SSH сервер запущен"
else
    log_error "Ошибка запуска SSH сервера"
fi

# Настройка SSH конфигурации
echo "Настройка SSH конфигурации..."
SSH_CONFIG="/etc/ssh/sshd_config"
sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' "$SSH_CONFIG"
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' "$SSH_CONFIG"

if sudo systemctl restart sshd; then
    log_success "Конфигурация SSH применена"
else
    log_error "Ошибка применения конфигурации SSH"
fi

# Установка зависимостей для libvirt
echo "Установка зависимостей для виртуализации..."
install_package "qemu-kvm" "QEMU KVM"
install_package "qemu-img" "QEMU Image Tools"
install_package "libvirt" "Libvirt"
install_package "libvirt-client" "Libvirt клиент"
install_package "virt-install" "Virt-install"
install_package "virt-viewer" "Virt-viewer"
install_package "virt-manager" "Virt-manager"
install_package "@virtualization" "Группа виртуализации"

# Установка инструментов разработки
install_package "gcc" "Компилятор GCC"
install_package "make" "Утилита Make"
install_package "automake" "Automake"
install_package "autoconf" "Autoconf"
install_package "libtool" "Libtool"
install_package "kernel-headers" "Заголовки ядра"
install_package "kernel-devel" "Библиотеки разработки ядра"
install_package "glib2-devel" "Разработка GLib2"
install_package "libaio-devel" "Разработка libaio"
install_package "numactl-devel" "Разработка NUMA"
install_package "zstd" "Zstandard"

# Запуск и настройка libvirt
echo "Настройка Libvirt..."
sudo systemctl enable libvirtd
sudo systemctl start libvirtd

if sudo systemctl is-active --quiet libvirtd; then
    log_success "Libvirt сервис запущен"
else
    log_error "Ошибка запуска Libvirt"
fi

# Настройка сети по умолчанию
echo "Настройка сетей виртуализации..."
if sudo virsh net-autostart default; then
    log_success "Сеть default настроена на автозапуск"
else
    log_error "Ошибка настройки сети default"
fi

# Проверка доступности KVM
echo "Проверка KVM..."
if [[ -c /dev/kvm ]]; then
    log_success "KVM доступен (/dev/kvm существует)"
else
    log_error "KVM недоступен"
fi

# Проверка модулей ядра
echo "Проверка модулей ядра..."
if lsmod | grep -q kvm; then
    log_success "Модуль KVM загружен"
else
    log_error "Модуль KVM не загружен"
fi

# Загрузка модуля tun
echo "Проверка модуля tun..."
if sudo modprobe tun; then
    log_success "Модуль tun загружен"
else
    log_error "Ошибка загрузки модуля tun"
fi

# Добавление tun в автозагрузку
if ! grep -q "^tun" /etc/modules-load.d/tun.conf 2>/dev/null; then
    echo "tun" | sudo tee /etc/modules-load.d/tun.conf > /dev/null
    log_success "Модуль tun добавлен в автозагрузку"
else
    log_skip "Модуль tun уже в автозагрузке"
fi

# Установка Python и зависимостей
echo "Установка Python и зависимостей..."
install_package "python3" "Python 3"
install_package "python3-pip" "Pip для Python 3"
install_package "python3-devel" "Разработка Python 3"
install_package "python3-virtualenv" "Virtualenv для Python 3"

# Дополнительные зависимости для Python
install_package "gobject-introspection-devel" "Разработка GObject Introspection"
install_package "cairo-devel" "Разработка Cairo"
install_package "pango-devel" "Разработка Pango"
install_package "gdk-pixbuf2-devel" "Разработка GDK-Pixbuf"

# Создание виртуального окружения
echo "Создание виртуального окружения..."
if [[ ! -d "eskvisor" ]]; then
    python3 -m venv eskvisor
    if [[ $? -eq 0 ]]; then
        log_success "Виртуальное окружение создано"
    else
        log_error "Ошибка создания виртуального окружения"
    fi
else
    log_skip "Виртуальное окружение уже существует"
fi

# Активация виртуального окружения и установка Python пакетов
echo "Установка Python пакетов..."
if [[ -f "eskvisor/bin/activate" ]]; then
    source eskvisor/bin/activate

    # Обновление pip
    pip install --upgrade pip
    if [[ $? -eq 0 ]]; then
        log_success "Pip обновлен"
    else
        log_error "Ошибка обновления pip"
    fi

    # Установка PyGObject
    pip install PyGObject
    if [[ $? -eq 0 ]]; then
        log_success "PyGObject установлен"
    else
        log_error "Ошибка установки PyGObject"
    fi

    # Установка зависимостей из requirements.txt если файл существует
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt
        if [[ $? -eq 0 ]]; then
            log_success "Зависимости из requirements.txt установлены"
        else
            log_error "Ошибка установки зависимостей из requirements.txt"
        fi
    else
        log_skip "Файл requirements.txt не найден"
    fi

    deactivate
else
    log_error "Не удалось активировать виртуальное окружение"
fi

# Настройка cgroup v2 (если необходимо)
echo "Проверка cgroup..."
if mount | grep -q "cgroup2"; then
    log_success "Cgroup v2 уже настроен"
else
    echo "Настройка cgroup v2..."
    if sudo mount -t cgroup2 none /sys/fs/cgroup; then
        echo "+cpu +memory" | sudo tee /sys/fs/cgroup/cgroup.subtree_control > /dev/null
        log_success "Cgroup v2 настроен"
    else
        log_error "Ошибка настройки cgroup v2"
    fi
fi

# Финальный вывод результатов
echo ""
echo "========================================="
echo "УСТАНОВКА ЗАВЕРШЕНА"
echo "========================================="
echo -e "${GREEN}Успешно выполнено: $SUCCESS_COUNT${NC}"
echo -e "${RED}Ошибок: $ERROR_COUNT${NC}"
echo -e "${YELLOW}Пропущено: $SKIP_COUNT${NC}"
echo ""

if [[ $ERROR_COUNT -eq 0 ]]; then
    echo -e "${GREEN}Все зависимости успешно установлены!${NC}"
    echo ""
    echo "Следующие шаги:"
    echo "1. Проверьте настройки SSH: sudo nano /etc/ssh/sshd_config"
    echo "2. Настройте пароль root: sudo passwd root"
    echo "3. Получите IP адрес: ip a"
    echo "4. Подключитесь по SSH: ssh root@ваш_ip"
    echo "5. Проверьте виртуализацию: sudo virt-host-validate"
else
    echo -e "${YELLOW}Были ошибки при установке. Проверьте лог выше.${NC}"
fi

echo ""
echo "Проверка основных служб:"
sudo systemctl is-active sshd &> /dev/null && echo -e "SSH: ${GREEN}активен${NC}" || echo -e "SSH: ${RED}не активен${NC}"
sudo systemctl is-active libvirtd &> /dev/null && echo -e "Libvirt: ${GREEN}активен${NC}" || echo -e "Libvirt: ${RED}не активен${NC}"

exit $ERROR_COUNT