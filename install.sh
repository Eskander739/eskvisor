#!/bin/bash

# install.sh для AlmaLinux - установка зависимостей для Eskvisor

# Лог файл
LOG_FILE="/var/log/eskvisor_install.log"
exec > >(tee -a "$LOG_FILE") 2>&1

# Цвета для логгирования
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Переменные для подсчета результатов
SUCCESS_COUNT=0
ERROR_COUNT=0
SKIP_COUNT=0

# Порт бэкэнда агента (из main.py)
AGENT_PORT=8000
# Порт для nginx (HTTP)
NGINX_HTTP_PORT=80
# Порт Redis
REDIS_PORT=6379

# Функция логирования
log_success() {
    local message="$1"
    echo -e "${GREEN}[УСПЕХ]${NC} $message"
    ((SUCCESS_COUNT++))
}

log_error() {
    local message="$1"
    echo -e "${RED}[ОШИБКА]${NC} $message"
    ((ERROR_COUNT++))
}

log_skip() {
    local message="$1"
    echo -e "${YELLOW}[ПРОПУЩЕНО]${NC} $message"
    ((SKIP_COUNT++))
}

# Функция проверки установки пакета
is_package_installed() {
    rpm -q "$1" &>/dev/null
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

# Функция установки Redis
install_redis() {
    echo "========================================="
    echo "Установка Redis"
    echo "========================================="

    # Проверка, установлен ли уже Redis
    if command -v redis-server &> /dev/null; then
        log_skip "Redis уже установлен"
        redis_version=$(redis-server --version | awk '{print $3}' | cut -d'=' -f2)
        echo "Версия Redis: $redis_version"
        return 0
    fi

    # Установка репозитория Remi для Redis
    echo "Установка репозитория Remi..."
    if sudo dnf install -y https://rpms.remirepo.net/enterprise/remi-release-10.rpm; then
        log_success "Репозиторий Remi установлен"
    else
        log_error "Ошибка установки репозитория Remi"
        return 1
    fi

    # Просмотр доступных модулей Redis
    echo "Доступные модули Redis:"
    sudo dnf module list redis 2>/dev/null | grep -E "redis|Name|Stream" || echo "Информация о модулях недоступна"

    # Включение модуля Redis (версия 7.2)
    echo "Включение модуля Redis:remi-7.2..."
    if sudo dnf module enable -y redis:remi-7.2; then
        log_success "Модуль Redis:remi-7.2 включен"
    else
        # Попробуем другую версию
        echo "Попытка включения модуля Redis:remi..."
        if sudo dnf module enable -y redis:remi; then
            log_success "Модуль Redis:remi включен"
        else
            log_error "Не удалось включить модуль Redis"
            return 1
        fi
    fi

    # Установка Redis
    echo "Установка Redis сервера..."
    if sudo dnf install -y redis; then
        log_success "Redis установлен"

        # Получение версии Redis
        redis_version=$(redis-server --version 2>/dev/null | awk '{print $3}' | cut -d'=' -f2 || echo "неизвестно")
        echo "Установлена версия Redis: $redis_version"
    else
        log_error "Ошибка установки Redis"
        return 1
    fi

    # Настройка Redis
    echo "Настройка Redis..."

    # Резервное копирование конфигурации
    if [[ -f /etc/redis.conf ]]; then
        sudo cp /etc/redis.conf /etc/redis.conf.backup_$(date +%Y%m%d_%H%M%S)
        log_success "Резервная копия конфигурации Redis создана"
    fi

    # Настройка базовых параметров
    REDIS_CONF="/etc/redis.conf"
    if [[ -f "$REDIS_CONF" ]]; then
        # Разрешаем доступ со всех интерфейсов (для внутренней сети)
        sudo sed -i 's/^bind 127.0.0.1 -::1/#bind 127.0.0.1 -::1\nbind 0.0.0.0/' "$REDIS_CONF"

        # Отключаем защищенный режим для локальной сети
        sudo sed -i 's/^protected-mode yes/protected-mode no/' "$REDIS_CONF"

        # Разрешаем фоновое сохранение
        sudo sed -i 's/^save 900 1/#save 900 1/' "$REDIS_CONF"
        sudo sed -i 's/^save 300 10/#save 300 10/' "$REDIS_CONF"
        sudo sed -i 's/^save 60 10000/#save 60 10000/' "$REDIS_CONF"

        # Включаем AOF (Append Only File) для лучшей надежности
        echo "appendonly yes" | sudo tee -a "$REDIS_CONF" > /dev/null

        # Настраиваем максимальное использование памяти (1GB)
        echo "maxmemory 1gb" | sudo tee -a "$REDIS_CONF" > /dev/null
        echo "maxmemory-policy allkeys-lru" | sudo tee -a "$REDIS_CONF" > /dev/null

        log_success "Конфигурация Redis обновлена"
    else
        log_error "Конфигурационный файл Redis не найден: $REDIS_CONF"
    fi

    # Создание системного юнита (если не существует)
    if [[ ! -f "/usr/lib/systemd/system/redis.service" ]]; then
        echo "Создание systemd юнита для Redis..."
        cat << EOF | sudo tee /etc/systemd/system/redis.service > /dev/null
[Unit]
Description=Redis persistent key-value database
After=network.target

[Service]
ExecStart=/usr/bin/redis-server /etc/redis.conf --supervised systemd
ExecStop=/usr/bin/redis-cli shutdown
Type=notify
User=redis
Group=redis
RuntimeDirectory=redis
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
EOF
        log_success "Systemd юнит для Redis создан"
    fi

    # Создание пользователя redis (если не существует)
    if ! id -u redis &>/dev/null; then
        sudo useradd -r -s /bin/false redis
        log_success "Пользователь redis создан"
    fi

    # Создание директорий и настройка прав
    sudo mkdir -p /var/lib/redis /var/log/redis
    sudo chown -R redis:redis /var/lib/redis /var/log/redis
    sudo chmod 750 /var/lib/redis

    # Перезагрузка демона systemd
    sudo systemctl daemon-reload

    # Включение и запуск Redis
    echo "Запуск службы Redis..."
    if sudo systemctl enable redis; then
        log_success "Redis добавлен в автозапуск"
    else
        log_error "Ошибка добавления Redis в автозапуск"
    fi

    if sudo systemctl start redis; then
        log_success "Redis успешно запущен"
    else
        log_error "Ошибка запуска Redis"
        sudo systemctl status redis --no-pager
        return 1
    fi

    # Проверка статуса Redis
    if sudo systemctl is-active --quiet redis; then
        log_success "Служба Redis активна"
    else
        log_error "Служба Redis не активна"
        return 1
    fi

    # Проверка работы Redis
    echo "Проверка работы Redis..."
    if redis-cli -h 127.0.0.1 ping | grep -q "PONG"; then
        log_success "Redis работает корректно"
    else
        # Подождать и попробовать снова
        sleep 2
        if redis-cli -h 127.0.0.1 ping | grep -q "PONG"; then
            log_success "Redis работает корректно"
        else
            log_error "Redis не отвечает на запросы"
            return 1
        fi
    fi

    # Настройка firewalld для Redis порта
    echo "Настройка firewalld для порта Redis (${REDIS_PORT})..."
    if command -v firewall-cmd &> /dev/null; then
        if sudo firewall-cmd --state &> /dev/null; then
            if sudo firewall-cmd --permanent --add-port=${REDIS_PORT}/tcp; then
                sudo firewall-cmd --reload
                log_success "Порт Redis ${REDIS_PORT} открыт в firewalld"
            else
                log_error "Ошибка открытия порта Redis в firewalld"
            fi
        else
            log_skip "Firewalld не запущен, пропускаем настройку портов"
        fi
    else
        log_skip "Firewalld не установлен, пропускаем настройку портов"
    fi

    # Настройка SELinux для Redis (если включен)
    if command -v sestatus &> /dev/null && sestatus | grep -q "enabled"; then
        echo "Настройка SELinux для Redis..."
        # Разрешаем Redis доступ к сети
        sudo setsebool -P redis_can_network 1
        # Разрешаем Redis доступ к порту
        sudo semanage port -a -t redis_port_t -p tcp ${REDIS_PORT} 2>/dev/null || \
            echo "Порт Redis уже настроен в SELinux или ошибка"
        log_success "SELinux настроен для Redis"
    fi

    # Проверка подключения извне
    echo "Тестирование подключения к Redis:"
    echo -n "  Локальное подключение: "
    if redis-cli ping | grep -q "PONG"; then
        echo -e "${GREEN}успех${NC}"
    else
        echo -e "${RED}ошибка${NC}"
    fi

    echo -n "  Подключение по сети: "
    if redis-cli -h 0.0.0.0 ping | grep -q "PONG"; then
        echo -e "${GREEN}успех${NC}"
    else
        echo -e "${YELLOW}требуется настройка${NC}"
    fi

    # Вывод информации о Redis
    echo ""
    echo "Информация о Redis:"
    echo "  Версия: $(redis-server --version 2>/dev/null | awk '{print $3}' | cut -d'=' -f2 || echo 'неизвестно')"
    echo "  Порт: ${REDIS_PORT}"
    echo "  Конфигурационный файл: /etc/redis.conf"
    echo "  Данные: /var/lib/redis"
    echo "  Логи: /var/log/redis"
    echo "  Systemd сервис: redis.service"

    return 0
}

# Функция настройки сервиса
setup_service() {
    local service_file="/opt/eskvisor/agent/client/service/eskvisor.service"
    local target_dir="/etc/systemd/system"

    echo "Настройка сервиса Eskvisor..."

    # Проверка существования файла сервиса
    if [[ ! -f "$service_file" ]]; then
        log_error "Файл сервиса не найден: $service_file"
        return 1
    fi

    # Копирование файла сервиса
    if sudo cp "$service_file" "$target_dir/"; then
        log_success "Файл сервиса скопирован в $target_dir/"
    else
        log_error "Ошибка копирования файла сервиса"
        return 1
    fi

    # Перезагрузка демона systemd
    if sudo systemctl daemon-reload; then
        log_success "Демон systemd перезагружен"
    else
        log_error "Ошибка перезагрузки демона systemd"
        return 1
    fi

    # Включение автозапуска сервиса
    if sudo systemctl enable eskvisor.service; then
        log_success "Сервис eskvisor добавлен в автозапуск"
    else
        log_error "Ошибка добавления сервиса в автозапуск"
        return 1
    fi

    # Запуск сервиса
    if sudo systemctl start eskvisor.service; then
        log_success "Сервис eskvisor запущен"
    else
        log_error "Ошибка запуска сервиса eskvisor"
        return 1
    fi

    return 0
}

# Функция запуска setup.sh для pycgroup
run_pycgroup_setup() {
    local setup_script="/opt/eskvisor/agent/client/pycgroup/state/setup.sh"

    echo "Запуск скрипта настройки pycgroup..."

    # Проверка существования скрипта
    if [[ ! -f "$setup_script" ]]; then
        log_error "Скрипт setup.sh не найден: $setup_script"
        return 1
    fi

    # Проверка прав на выполнение
    if [[ ! -x "$setup_script" ]]; then
        echo "Установка прав на выполнение для скрипта..."
        if chmod +x "$setup_script"; then
            log_success "Права на выполнение установлены"
        else
            log_error "Ошибка установки прав на выполнение"
            return 1
        fi
    fi

    # Запуск скрипта
    echo "Выполнение $setup_script..."
    if sudo "$setup_script"; then
        log_success "Скрипт setup.sh успешно выполнен"
        return 0
    else
        log_error "Ошибка выполнения скрипта setup.sh"
        return 1
    fi
}

# Функция установки и настройки nginx
setup_nginx() {
    echo "Установка и настройка Nginx..."

    # Установка nginx
    install_package "nginx" "Nginx"
    log_success "Права на директорию /run/nginx исправлены"

    # Проверка установки
    if ! command -v nginx &> /dev/null; then
        log_error "Nginx не установлен"
        return 1
    fi

    # Определяем путь к конфигурационному файлу агента
    local agent_nginx_conf="/opt/eskvisor/agent/nginx.conf"
    local nginx_main_conf="/etc/nginx/nginx.conf"

    # Используем готовую конфигурацию из агента
    if [[ -f "$agent_nginx_conf" ]]; then
        echo "Использование готовой конфигурации nginx из агента..."

        # Проверяем синтаксис перед копированием
        if sudo nginx -t -c "$agent_nginx_conf" 2>/dev/null; then
            log_success "Конфигурация агента прошла проверку синтаксиса"
        else
            log_error "Конфигурация агента содержит ошибки"
            sudo nginx -t -c "$agent_nginx_conf"
            return 1
        fi

        # Создаем резервную копию текущей конфигурации nginx
        local backup_file="/etc/nginx/nginx.conf.backup_$(date +%Y%m%d_%H%M%S)"
        if sudo cp "$nginx_main_conf" "$backup_file"; then
            log_success "Создана резервная копия конфигурации nginx: $backup_file"
        else
            log_error "Ошибка создания резервной копии конфигурации nginx"
            return 1
        fi

        # Копируем конфигурацию
        if sudo cp "$agent_nginx_conf" "$nginx_main_conf"; then
            log_success "Конфигурация nginx скопирована из агента"
        else
            log_error "Ошибка копирования конфигурации nginx"
            return 1
        fi
    else
        log_error "Конфигурация nginx от агента не найдена: $agent_nginx_conf"
        return 1
    fi

    # Удаляем все конфигурации из conf.d, чтобы избежать конфликтов
    echo "Очистка конфигураций в /etc/nginx/conf.d/..."
    sudo rm -f /etc/nginx/conf.d/*.conf

    # Тестирование конфигурации nginx
    echo "Проверка конфигурации nginx..."
    if sudo nginx -t; then
        log_success "Конфигурация nginx валидна"
    else
        log_error "Ошибка в конфигурации nginx"
        return 1
    fi

    # Настройка firewalld для HTTP порта
    echo "Настройка firewalld для порта ${NGINX_HTTP_PORT}..."
    if command -v firewall-cmd &> /dev/null; then
        if sudo firewall-cmd --state &> /dev/null; then
            if sudo firewall-cmd --permanent --add-service=http; then
                sudo firewall-cmd --reload
                log_success "Порт ${NGINX_HTTP_PORT} открыт в firewalld"
            else
                log_error "Ошибка открытия порта ${NGINX_HTTP_PORT} в firewalld"
            fi
        else
            log_skip "Firewalld не запущен, пропускаем настройку портов"
        fi
    else
        log_skip "Firewalld не установлен, пропускаем настройку портов"
    fi

    # Создание системного юнита для управления nginx (если не существует)
    if [[ ! -f "/etc/systemd/system/nginx.service" ]]; then
        echo "Создание systemd юнита для nginx..."
        cat << EOF | sudo tee /etc/systemd/system/nginx.service > /dev/null
[Unit]
Description=The nginx HTTP and reverse proxy server
After=network.target remote-fs.target nss-lookup.target

[Service]
Type=forking
PIDFile=/run/nginx.pid
ExecStartPre=/usr/sbin/nginx -t
ExecStart=/usr/sbin/nginx
ExecReload=/usr/sbin/nginx -s reload
ExecStop=/bin/kill -s QUIT \$MAINPID
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
        log_success "Systemd юнит для nginx создан"
    fi

    # Перезагрузка демона systemd
    sudo systemctl daemon-reload

    # Исправление прав для директории /run
    echo "Исправление прав для директории /run/..."
    sudo mkdir -p /run/nginx
    sudo chown -R nginx:nginx /run/nginx
    sudo chmod 755 /run/nginx

    # Запуск и включение nginx
    echo "Запуск службы nginx..."
    if sudo systemctl enable nginx; then
        log_success "Nginx добавлен в автозапуск"
    else
        log_error "Ошибка добавления nginx в автозапуск"
        return 1
    fi

    if sudo systemctl start nginx; then
        log_success "Nginx успешно запущен"
    else
        log_error "Ошибка запуска nginx"
        sudo systemctl status nginx --no-pager
        return 1
    fi

    # Проверка статуса nginx
    if sudo systemctl is-active --quiet nginx; then
        log_success "Служба nginx активна"
    else
        log_error "Служба nginx не активна"
        return 1
    fi

    return 0
}

# Функция настройки SELinux для nginx (если SELinux включен)
setup_selinux_for_nginx() {
    echo "Настройка SELinux для Nginx..."

    echo "Проверка и отключение фаервола..."
    if systemctl list-unit-files | grep -q firewalld.service; then
        echo "Служба firewalld обнаружена, отключаем..."

        # Проверяем, запущена ли служба
        if systemctl is-active --quiet firewalld; then
            echo "Останавливаем firewalld..."
            sudo systemctl stop firewalld
        fi

        # Проверяем, включена ли автозагрузка
        if systemctl is-enabled --quiet firewalld 2>/dev/null; then
            echo "Отключаем автозапуск firewalld..."
            sudo systemctl disable firewalld
        else
            echo "Служба firewalld уже отключена."
        fi

        echo "firewalld успешно отключен."
    else
        echo "Служба firewalld не установлена в системе."
    fi

    # Проверяем, включен ли SELinux
    if command -v sestatus &> /dev/null; then
        local selinux_status=$(sestatus | grep "SELinux status" | awk '{print $3}')
        local selinux_mode=$(sestatus | grep "Current mode" | awk '{print $3}')

        if [[ "$selinux_status" == "enabled" ]]; then
            log_success "SELinux включен (режим: $selinux_mode)"

            # Устанавливаем необходимые политики для nginx
            echo "Установка политик SELinux для nginx..."

            # Разрешаем nginx проксировать сетевые соединения
            if sudo setsebool -P httpd_can_network_connect 1; then
                log_success "Политика httpd_can_network_connect установлена"
            else
                log_error "Ошибка установки политики SELinux"
            fi

            # Разрешаем nginx работать как обратный прокси
            if sudo setsebool -P httpd_can_network_relay 1; then
                log_success "Политика httpd_can_network_relay установлена"
            else
                log_error "Ошибка установки политики SELinux"
            fi

            # Разрешаем nginx доступ к портам
            if sudo semanage port -a -t http_port_t -p tcp ${NGINX_HTTP_PORT} 2>/dev/null; then
                log_success "Порт ${NGINX_HTTP_PORT} добавлен в политику SELinux"
            else
                log_skip "Порт ${NGINX_HTTP_PORT} уже разрешен в SELinux или ошибка"
            fi

            # Разрешаем доступ к директории eskvisor
            if sudo semanage fcontext -a -t httpd_sys_content_t "/opt/eskvisor(/.*)?" 2>/dev/null; then
                sudo restorecon -Rv /opt/eskvisor
                log_success "Политика доступа к /opt/eskvisor установлена"
            else
                log_skip "Политика доступа уже установлена или ошибка"
            fi

            # Установите правильный контекст SELinux
            sudo chcon -R -t bin_t /eskvisor/eskvisor_venv/bin/
            sudo chcon -R -t bin_t /eskvisor/eskvisor_venv/bin/python

            # Устанавливаем правильный контекст для всей директории nginx
            sudo semanage fcontext -a -t httpd_config_t "/etc/nginx(/.*)?"
            sudo restorecon -Rv /etc/nginx/

            # Для /run/nginx.pid
            sudo semanage fcontext -a -t httpd_var_run_t "/run/nginx.pid"
            sudo touch /run/nginx.pid
            sudo restorecon -v /run/nginx.pid
            sudo chown nginx:nginx /run/nginx.pid


            # Разрешаем доступ к сокетам
            if sudo setsebool -P httpd_use_nfs 1; then
                log_success "Политика httpd_use_nfs установлена"
            else
                log_skip "Ошибка установки политики httpd_use_nfs"
            fi
        else
            log_skip "SELinux отключен, пропускаем настройку"
        fi
    else
        log_skip "SELinux не установлен, пропускаем настройку"
    fi

    return 0
}

# Начало скрипта
echo "========================================="
echo "Установка зависимостей для Eskvisor на AlmaLinux"
echo "========================================="

echo "Логирование установки в файл: $LOG_FILE"

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

echo "Установка файла конфигурации"
sudo mkdir -p /etc/eskvisor
sudo mv /opt/eskvisor/agent/.env /etc/eskvisor/agent.env
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

# Установка Redis
if install_redis; then
    log_success "Redis установлен и настроен"
else
    log_error "Ошибка установки Redis"
fi

# Настройка сервиса eskvisor
if setup_service; then
    log_success "Сервис eskvisor настроен"
else
    log_error "Ошибка настройки сервиса eskvisor"
fi

# Запуск скрипта настройки pycgroup
if run_pycgroup_setup; then
    log_success "Настройка pycgroup завершена"
else
    log_error "Ошибка настройки pycgroup"
fi

# Установка зависимостей для libvirt
echo "Установка зависимостей для виртуализации..."
install_package "qemu-kvm" "QEMU KVM"
install_package "qemu-img" "QEMU Image Tools"
install_package "libvirt" "Libvirt"
install_package "libxml2-devel" "Системная зависимость"
install_package "libxslt-devel" "Системная зависимость"
install_package "zlib-devel" "Системная зависимость"
install_package "libvirt-client" "Libvirt клиент"
install_package "libvirt-devel" "Libvirt библиотека"
install_package "virt-install" "Virt-install"
install_package "virt-viewer" "Virt-viewer"
install_package "virt-manager" "Virt-manager"

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
    echo "tun" | sudo tee /etc/modules-load.d/tun.conf >/dev/null
    log_success "Модуль tun добавлен в автозагрузку"
else
    log_skip "Модуль tun уже в автозагрузке"
fi

# Установка Python и зависимостей
echo "Установка Python и зависимостей..."
install_package "python3" "Python 3"
install_package "python3-pip" "Pip для Python 3"
install_package "python3-devel" "Разработка Python 3"

# Установка virtualenv через pip
echo "Установка virtualenv для Python 3..."
if python3 -m pip install virtualenv; then
    log_success "Virtualenv установлен через pip"
else
    log_error "Ошибка установки virtualenv через pip"
fi

# Установка системных зависимостей для PyGObject
install_package "cairo-devel" "Разработка Cairo"
install_package "cairo-gobject-devel" "Разработка Cairo GObject"
install_package "gobject-introspection-devel" "Разработка GObject Introspection"
install_package "libffi-devel" "Разработка libffi"

# Дополнительные зависимости для Python
install_package "pango-devel" "Разработка Pango"
install_package "gdk-pixbuf2-devel" "Разработка GDK-Pixbuf"

# Установка дополнительных пакетов для сетевой безопасности
install_package "firewalld" "FirewallD"
install_package "policycoreutils-python-utils" "Утилиты SELinux"

# Создание виртуального окружения
echo "Создание виртуального окружения..."
if [[ ! -d "/eskvisor/eskvisor_venv" ]]; then
    python3 -m venv /eskvisor/eskvisor_venv
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
if [[ -f "/eskvisor/eskvisor_venv/bin/activate" ]]; then
    source /eskvisor/eskvisor_venv/bin/activate

    # Обновление pip
    pip install --upgrade pip
    if [[ $? -eq 0 ]]; then
        log_success "Pip обновлен"
    else
        log_error "Ошибка обновления pip"
    fi

    # Установка PyGObject с флагом для избежания проблем сборки
    echo "Установка PyGObject..."
    if pip install PyGObject --no-build-isolation; then
        log_success "PyGObject установлен"
    else
        log_error "Ошибка установки PyGObject"
        echo "Попытка альтернативной установки PyGObject..."
        if pip install pygobject; then
            log_success "PyGObject установлен альтернативным методом"
        else
            log_error "Ошибка альтернативной установки PyGObject"
        fi
    fi

    # Установка зависимостей из requirements.txt если файл существует
    if [[ -f "/opt/eskvisor/requirements.txt" ]]; then
        while read -r package; do
            [[ -z "$package" ]] || [[ "$package" =~ ^# ]] && continue
            python3 -m pip install "$package" || echo "Ошибка: $package"
        done </opt/eskvisor/requirements.txt
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

# Установка и настройка nginx
if setup_nginx; then
    log_success "Nginx установлен и настроен"
else
    log_error "Ошибка установки и настройки nginx"
fi

# Настройка SELinux для nginx
if setup_selinux_for_nginx; then
    log_success "SELinux настроен для работы с nginx"
else
    log_error "Ошибка настройки SELinux для nginx"
fi

# Настройка cgroup v2 (если необходимо)
echo "Проверка cgroup..."
if mount | grep -q "cgroup2"; then
    log_success "Cgroup v2 уже настроен"
else
    echo "Настройка cgroup v2..."
    if sudo mount -t cgroup2 none /sys/fs/cgroup; then
        echo " cpu  memory" | sudo tee /sys/fs/cgroup/cgroup.subtree_control >/dev/null
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
    echo "6. Проверьте статус сервиса eskvisor: sudo systemctl status eskvisor"
    echo "7. Проверьте работу Redis: redis-cli ping"
    echo "8. Проверьте работу nginx: curl http://localhost/health"
    echo "9. Проверьте конфигурацию nginx: sudo nginx -t"
    echo "10. Проверьте логи nginx: sudo tail -f /var/log/nginx/eskvisor-access.log"
    echo "11. Проверьте логи Redis: sudo tail -f /var/log/redis/redis.log"
else
    echo -e "${YELLOW}Были ошибки при установке. Проверьте лог выше.${NC}"
fi

echo ""
echo "Проверка основных служб:"
sudo systemctl is-active sshd &>/dev/null && echo -e "SSH: ${GREEN}активен${NC}" || echo -e "SSH: ${RED}не активен${NC}"
sudo systemctl is-active libvirtd &>/dev/null && echo -e "Libvirt: ${GREEN}активен${NC}" || echo -e "Libvirt: ${RED}не активен${NC}"
sudo systemctl is-active redis &>/dev/null && echo -e "Redis: ${GREEN}активен${NC}" || echo -e "Redis: ${RED}не активен${NC}"
sudo systemctl is-active eskvisor &>/dev/null && echo -e "Eskvisor: ${GREEN}активен${NC}" || echo -e "Eskvisor: ${RED}не активен${NC}"
sudo systemctl is-active nginx &>/dev/null && echo -e "Nginx: ${GREEN}активен${NC}" || echo -e "Nginx: ${RED}не активен${NC}"

echo ""
echo "Расположение Eskvisor: /opt/eskvisor"
echo "Расположение конфигурации: /etc/eskvisor/agent.env"
echo "Расположение сервиса: /etc/systemd/system/eskvisor.service"
echo "Расположение Redis: /etc/redis.conf"
echo "Расположение конфигурации nginx: /etc/nginx/nginx.conf"
echo "Порт бэкэнда агента: ${AGENT_PORT}"
echo "Порт nginx (HTTP): ${NGINX_HTTP_PORT}"
echo "Порт Redis: ${REDIS_PORT}"
echo ""
echo "Лог установки сохранен в: $LOG_FILE"
echo ""
echo "Для проверки работы:"
echo "  - Redis: redis-cli ping"
echo "  - Eskvisor: curl http://ваш_сервер/health"
echo "  - Nginx: curl http://localhost:8080/nginx-health"

# Создание скрипта для проверки конфигурации
cat << EOF | sudo tee /usr/local/bin/check-eskvisor-config.sh > /dev/null
#!/bin/bash

echo "=== Проверка конфигурации Eskvisor ==="
echo ""

# Проверка служб
echo "1. Проверка служб:"
services=("sshd" "libvirtd" "redis" "eskvisor" "nginx")
for service in "\${services[@]}"; do
    if systemctl is-active --quiet "\$service"; then
        echo -e "  \$service: \033[0;32mактивен\033[0m"
    else
        echo -e "  \$service: \033[0;31mне активен\033[0m"
    fi
done

echo ""
echo "2. Проверка портов:"
echo -n "  Порт ${AGENT_PORT} (агент): "
if ss -tuln | grep -q ":${AGENT_PORT} "; then
    echo -e "\033[0;32mоткрыт\033[0m"
else
    echo -e "\033[0;31mзакрыт\033[0m"
fi

echo -n "  Порт ${REDIS_PORT} (redis): "
if ss -tuln | grep -q ":${REDIS_PORT} "; then
    echo -e "\033[0;32mоткрыт\033[0m"
else
    echo -e "\033[0;31mзакрыт\033[0m"
fi

echo -n "  Порт ${NGINX_HTTP_PORT} (nginx): "
if ss -tuln | grep -q ":${NGINX_HTTP_PORT} "; then
    echo -e "\033[0;32mоткрыт\033[0m"
else
    echo -e "\033[0;31mзакрыт\033[0m"
fi

echo ""
echo "3. Проверка работы Redis:"
echo -n "  Подключение к Redis: "
if redis-cli ping | grep -q "PONG"; then
    echo -e "\033[0;32mуспех\033[0m"
    echo -n "  Версия Redis: "
    redis_version=\$(redis-server --version 2>/dev/null | awk '{print \$3}' | cut -d'=' -f2 || echo "неизвестно")
    echo "\$redis_version"
else
    echo -e "\033[0;31mошибка\033[0m"
fi

echo ""
echo "4. Проверка nginx конфигурации:"
if nginx -t 2>/dev/null; then
    echo -e "  Конфигурация nginx: \033[0;32mвалидна\033[0m"
else
    echo -e "  Конфигурация nginx: \033[0;31mошибка\033[0m"
fi

echo ""
echo "5. Быстрый тест доступа:"
echo -n "  HTTP запрос к /health: "
if curl -s -f http://localhost/health > /dev/null; then
    echo -e "\033[0;32mуспех\033[0m"
else
    echo -e "\033[0;31mошибка\033[0m"
fi

echo -n "  Health check nginx: "
if curl -s -f http://localhost:8080/nginx-health > /dev/null; then
    echo -e "\033[0;32mуспех\033[0m"
else
    echo -e "\033[0;31mошибка\033[0m"
fi

echo ""
echo "6. Проверка конфигурационных файлов:"
if [[ -f "/opt/eskvisor/agent/nginx.conf" ]]; then
    echo -e "  Конфигурация агента: \033[0;32mобнаружена\033[0m"
else
    echo -e "  Конфигурация агента: \033[0;33mне обнаружена (используется стандартная)\033[0m"
fi

if [[ -f "/etc/redis.conf" ]]; then
    echo -e "  Конфигурация Redis: \033[0;32mобнаружена\033[0m"
else
    echo -e "  Конфигурация Redis: \033[0;33mне обнаружена\033[0m"
fi

echo ""
echo "=== Проверка завершена ==="
EOF

sudo chmod +x /usr/local/bin/check-eskvisor-config.sh
log_success "Создан скрипт проверки конфигурации: /usr/local/bin/check-eskvisor-config.sh"

exit $ERROR_COUNT