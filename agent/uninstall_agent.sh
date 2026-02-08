#!/bin/bash

# uninstall_agent.sh для AlmaLinux - полное удаление Eskvisor Agent

# Лог файл
LOG_FILE="/var/log/eskvisor_uninstall.log"
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

# Функция проверки работы сервиса
is_service_active() {
    local service_name="$1"
    sudo systemctl is-active --quiet "$service_name" 2>/dev/null
    return $?
}

# Функция остановки и отключения сервиса
stop_disable_service() {
    local service_name="$1"
    local friendly_name="$2"

    echo "Обработка службы $friendly_name..."

    # Проверка существования сервиса
    if [[ ! -f "/etc/systemd/system/$service_name" ]] &&
       [[ ! -f "/usr/lib/systemd/system/$service_name" ]]; then
        log_skip "$friendly_name не установлен"
        return 0
    fi

    # Остановка сервиса
    if is_service_active "$service_name"; then
        echo "  Остановка $friendly_name..."
        if sudo systemctl stop "$service_name"; then
            log_success "$friendly_name остановлен"
        else
            log_error "Ошибка остановки $friendly_name"
        fi
    else
        log_skip "$friendly_name не запущен"
    fi

    # Отключение автозапуска
    if sudo systemctl disable "$service_name" 2>/dev/null; then
        log_success "$friendly_name отключен из автозапуска"
    else
        log_skip "$friendly_name не был в автозапуске"
    fi

    # Удаление файла сервиса
    local service_files=(
        "/etc/systemd/system/$service_name"
        "/usr/lib/systemd/system/$service_name"
        "/etc/systemd/system/$service_name.d"
        "/usr/lib/systemd/system/$service_name.d"
    )

    for service_file in "${service_files[@]}"; do
        if [[ -f "$service_file" ]] || [[ -d "$service_file" ]]; then
            if sudo rm -rf "$service_file"; then
                log_success "Файл сервиса $service_file удален"
            else
                log_error "Ошибка удаления файла сервиса $service_file"
            fi
        fi
    done

    return 0
}

# Функция удаления процесса по имени
kill_process_by_name() {
    local process_name="$1"
    local friendly_name="$2"

    echo "Поиск процессов $friendly_name..."

    # Поиск PIDs процессов
    local pids=$(pgrep -f "$process_name" 2>/dev/null)

    if [[ -n "$pids" ]]; then
        echo "  Найдены процессы с PID: $pids"

        # Остановка процессов
        for pid in $pids; do
            echo "  Остановка процесса $pid..."
            if sudo kill -TERM "$pid" 2>/dev/null; then
                sleep 1
                # Принудительная остановка если не остановился
                if ps -p "$pid" > /dev/null 2>&1; then
                    sudo kill -KILL "$pid" 2>/dev/null
                    log_success "Процесс $pid принудительно остановлен"
                else
                    log_success "Процесс $pid остановлен"
                fi
            else
                log_error "Ошибка остановки процесса $pid"
            fi
        done
    else
        log_skip "Процессы $friendly_name не найдены"
    fi

    return 0
}

# Функция удаления директории
remove_directory() {
    local dir_path="$1"
    local friendly_name="$2"

    if [[ -d "$dir_path" ]]; then
        echo "Удаление $friendly_name..."
        if sudo rm -rf "$dir_path"; then
            log_success "$friendly_name удален"
        else
            log_error "Ошибка удаления $friendly_name"
        fi
    else
        log_skip "$friendly_name не существует"
    fi
}

# Функция удаления файла
remove_file() {
    local file_path="$1"
    local friendly_name="$2"

    if [[ -f "$file_path" ]]; then
        echo "Удаление $friendly_name..."
        if sudo rm -f "$file_path"; then
            log_success "$friendly_name удален"
        else
            log_error "Ошибка удаления $friendly_name"
        fi
    else
        log_skip "$friendly_name не существует"
    fi
}

# Функция очистки конфигураций nginx
cleanup_nginx_config() {
    echo "Очистка конфигураций nginx..."

    # Проверка установлен ли nginx
    if ! command -v nginx &> /dev/null; then
        log_skip "Nginx не установлен"
        return 0
    fi

    # Восстановление оригинальной конфигурации nginx если есть backup
    local nginx_conf="/etc/nginx/nginx.conf"
    local nginx_backups=($(ls -t /etc/nginx/nginx.conf.backup_* 2>/dev/null))

    if [[ ${#nginx_backups[@]} -gt 0 ]]; then
        local latest_backup="${nginx_backups[0]}"
        echo "  Восстановление конфигурации nginx из резервной копии..."

        if sudo cp "$latest_backup" "$nginx_conf"; then
            log_success "Конфигурация nginx восстановлена из $latest_backup"

            # Удаление остальных backup файлов
            for backup in "${nginx_backups[@]}"; do
                sudo rm -f "$backup"
            done
        else
            log_error "Ошибка восстановления конфигурации nginx"
        fi
    else
        # Удаление настроек eskvisor из конфигурации nginx
        echo "  Удаление настроек eskvisor из конфигурации nginx..."

        if [[ -f "$nginx_conf" ]]; then
            # Создание временного файла без упоминаний eskvisor
            sudo grep -v "eskvisor" "$nginx_conf" > "/tmp/nginx.conf.tmp" 2>/dev/null

            if [[ $? -eq 0 ]] && [[ -s "/tmp/nginx.conf.tmp" ]]; then
                sudo cp "/tmp/nginx.conf.tmp" "$nginx_conf"
                sudo rm -f "/tmp/nginx.conf.tmp"
                log_success "Настройки eskvisor удалены из конфигурации nginx"
            else
                # Если фильтрация не удалась, удаляем весь файл (будет восстановлен из пакета при необходимости)
                sudo rm -f "$nginx_conf"
                log_success "Конфигурационный файл nginx удален"
            fi
        fi
    fi

    # Удаление логов nginx eskvisor
    echo "  Очистка логов nginx..."
    sudo rm -f /var/log/nginx/eskvisor-*.log 2>/dev/null
    sudo rm -f /var/log/nginx/access-eskvisor.log 2>/dev/null
    sudo rm -f /var/log/nginx/error-eskvisor.log 2>/dev/null

    # Перезагрузка nginx если он запущен
    if is_service_active "nginx"; then
        echo "  Перезагрузка nginx..."
        if sudo nginx -t 2>/dev/null && sudo systemctl reload nginx; then
            log_success "Nginx перезагружен"
        else
            log_error "Ошибка перезагрузки nginx"
        fi
    fi

    return 0
}

# Функция очистки конфигураций Redis
cleanup_redis_config() {
    echo "Очистка конфигураций Redis..."

    # Проверка установлен ли redis
    if ! command -v redis-server &> /dev/null; then
        log_skip "Redis не установлен"
        return 0
    fi

    # Восстановление оригинальной конфигурации redis если есть backup
    local redis_conf="/etc/redis.conf"
    local redis_backups=($(ls -t /etc/redis.conf.backup_* 2>/dev/null))

    if [[ ${#redis_backups[@]} -gt 0 ]]; then
        local latest_backup="${redis_backups[0]}"
        echo "  Восстановление конфигурации Redis из резервной копии..."

        if sudo cp "$latest_backup" "$redis_conf"; then
            log_success "Конфигурация Redis восстановлена из $latest_backup"

            # Удаление остальных backup файлов
            for backup in "${redis_backups[@]}"; do
                sudo rm -f "$backup"
            done
        else
            log_error "Ошибка восстановления конфигурации Redis"
        fi
    fi

    # Очистка данных Redis
    echo "  Очистка данных Redis..."
    sudo rm -rf /var/lib/redis/* 2>/dev/null
    sudo rm -rf /var/log/redis/* 2>/dev/null

    # Перезагрузка redis если он запущен
    if is_service_active "redis"; then
        echo "  Перезагрузка redis..."
        if sudo systemctl restart redis; then
            log_success "Redis перезагружен"
        else
            log_error "Ошибка перезагрузки redis"
        fi
    fi

    return 0
}

# Функция удаления зависимостей (опционально)
remove_dependencies() {
    local remove_deps="$1"

    if [[ "$remove_deps" != "true" ]]; then
        log_skip "Удаление зависимостей пропущено (используйте --remove-deps для удаления)"
        return 0
    fi

    echo "Удаление установленных зависимостей..."

    # Список пакетов для удаления
    local packages_to_remove=(
        "python3-pip"
        "python3-devel"
        "virtualenv"
        "nginx"
        "redis"
        "qemu-kvm"
        "qemu-img"
        "libvirt"
        "libvirt-client"
        "libvirt-devel"
        "virt-install"
        "virt-viewer"
        "virt-manager"
        "firewalld"
        "gcc"
        "make"
        "automake"
        "autoconf"
        "libtool"
        "kernel-devel"
        "glib2-devel"
        "libaio-devel"
        "numactl-devel"
        "zstd"
        "cairo-devel"
        "cairo-gobject-devel"
        "gobject-introspection-devel"
        "libffi-devel"
        "pango-devel"
        "gdk-pixbuf2-devel"
    )

    for package in "${packages_to_remove[@]}"; do
        if rpm -q "$package" &>/dev/null; then
            echo "  Удаление $package..."
            if sudo dnf remove -y "$package" 2>/dev/null; then
                log_success "$package удален"
            else
                log_error "Ошибка удаления $package"
            fi
        else
            log_skip "$package не установлен"
        fi
    done

    # Очистка кеша dnf
    sudo dnf clean all

    return 0
}

# Функция проверки подтверждения
confirm_uninstall() {
    if [[ "$FORCE" != "true" ]]; then
        echo "========================================="
        echo "ПРЕДУПРЕЖДЕНИЕ: УДАЛЕНИЕ ESKVISOR AGENT"
        echo "========================================="
        echo "Будут выполнены следующие действия:"
        echo "1. Остановка всех служб eskvisor"
        echo "2. Удаление файлов агента из /opt/eskvisor"
        echo "3. Удаление конфигураций из /etc/eskvisor"
        echo "4. Удаление systemd сервисов"
        echo "5. Очистка логов"
        echo ""

        if [[ "$REMOVE_DEPS" == "true" ]]; then
            echo "⚠️  БУДУТ УДАЛЕНЫ ВСЕ ЗАВИСИМОСТИ (nginx, redis, libvirt и др.)"
        fi

        read -p "Вы уверены что хотите продолжить? (yes/NO): " confirmation

        if [[ "$confirmation" != "yes" ]]; then
            echo "Удаление отменено."
            exit 0
        fi
    fi
}

# Основная функция удаления
main_uninstall() {
    echo "========================================="
    echo "ПОЛНОЕ УДАЛЕНИЕ ESKVISOR AGENT"
    echo "========================================="

    # Подтверждение
    confirm_uninstall

    echo "Логирование удаления в файл: $LOG_FILE"
    echo ""

    # 1. Остановка всех служб eskvisor
    echo "=== ОСТАНОВКА СЛУЖБ ESKVISOR ==="

    stop_disable_service "eskvisor.service" "Основной сервис eskvisor"
    stop_disable_service "eskvisor-task-manager.service" "Диспетчер задач eskvisor"

    echo ""

    # 2. Убийство оставшихся процессов
    echo "=== ОСТАНОВКА ПРОЦЕССОВ ==="

    kill_process_by_name "eskvisor" "Процессы eskvisor"
    kill_process_by_name "agent.py" "Процессы агента"
    kill_process_by_name "task_manager" "Диспетчер задач"
    kill_process_by_name "pycgroup" "Pycgroup процессы"

    echo ""

    # 3. Удаление systemd юнитов
    echo "=== УДАЛЕНИЕ SYSTEMD СЕРВИСОВ ==="

    # Перезагрузка демона systemd
    echo "Перезагрузка демона systemd..."
    sudo systemctl daemon-reload 2>/dev/null
    log_success "Демон systemd перезагружен"

    echo ""

    # 4. Удаление файлов и директорий агента
    echo "=== УДАЛЕНИЕ ФАЙЛОВ АГЕНТА ==="

    remove_directory "/opt/eskvisor" "Директория агента eskvisor"
    remove_directory "/etc/eskvisor" "Конфигурации eskvisor"
    remove_directory "/eskvisor" "Виртуальное окружение eskvisor"

    # Удаление отдельных файлов конфигурации
    remove_file "/etc/systemd/system/eskvisor.service" "Сервис eskvisor"
    remove_file "/etc/systemd/system/eskvisor-task-manager.service" "Сервис диспетчера задач"

    # Удаление логов агента
    echo "Очистка логов агента..."
    sudo rm -f /var/log/eskvisor*.log 2>/dev/null
    sudo rm -rf /var/log/eskvisor 2>/dev/null
    log_success "Логи агента очищены"

    echo ""

    # 5. Очистка конфигураций nginx
    echo "=== ОЧИСТКА NGINX ==="
    cleanup_nginx_config

    echo ""

    # 6. Очистка конфигураций Redis
    echo "=== ОЧИСТКА REDIS ==="
    cleanup_redis_config

    echo ""

    # 7. Удаление скрипта проверки конфигурации
    echo "=== УДАЛЕНИЕ ВСПОМОГАТЕЛЬНЫХ СКРИПТОВ ==="

    remove_file "/usr/local/bin/check-eskvisor-config.sh" "Скрипт проверки конфигурации"

    echo ""

    # 8. Удаление зависимостей (если указано)
    echo "=== УДАЛЕНИЕ ЗАВИСИМОСТЕЙ ==="
    remove_dependencies "$REMOVE_DEPS"

    echo ""

    # 9. Очистка временных файлов
    echo "=== ОЧИСТКА ВРЕМЕННЫХ ФАЙЛОВ ==="

    sudo rm -rf /tmp/eskvisor* 2>/dev/null
    sudo rm -rf /tmp/agent_*.tar.gz 2>/dev/null
    log_success "Временные файлы очищены"

    echo ""

    # Финальный вывод результатов
    echo "========================================="
    echo "УДАЛЕНИЕ ЗАВЕРШЕНО"
    echo "========================================="
    echo -e "${GREEN}Успешно выполнено: $SUCCESS_COUNT${NC}"
    echo -e "${RED}Ошибок: $ERROR_COUNT${NC}"
    echo -e "${YELLOW}Пропущено: $SKIP_COUNT${NC}"
    echo ""

    if [[ $ERROR_COUNT -eq 0 ]]; then
        echo -e "${GREEN}Eskvisor Agent полностью удален с системы!${NC}"
        echo ""
        echo "Рекомендуется выполнить следующие действия:"
        echo "1. Перезагрузить систему: sudo reboot"
        echo "2. Проверить отсутствие процессов eskvisor: ps aux | grep -i eskvisor"
        echo "3. Проверить отсутствие сервисов: systemctl list-units | grep -i eskvisor"
        echo "4. Проверить отсутствие файлов: ls -la /opt/ | grep -i eskvisor"
    else
        echo -e "${YELLOW}Были ошибки при удалении. Проверьте лог выше.${NC}"
        echo "Некоторые файлы могли не быть удалены. Проверьте вручную:"
        echo "  - /opt/eskvisor"
        echo "  - /etc/eskvisor"
        echo "  - /etc/systemd/system/eskvisor*.service"
    fi

    echo ""
    echo "Проверка удаления:"
    if [[ -d "/opt/eskvisor" ]]; then
        echo -e "Директория /opt/eskvisor: ${RED}НЕ УДАЛЕНА${NC}"
    else
        echo -e "Директория /opt/eskvisor: ${GREEN}УДАЛЕНА${NC}"
    fi

    if systemctl list-units | grep -q "eskvisor"; then
        echo -e "Systemd сервисы eskvisor: ${RED}НАЙДЕНЫ${NC}"
    else
        echo -e "Systemd сервисы eskvisor: ${GREEN}НЕ НАЙДЕНЫ${NC}"
    fi

    if ps aux | grep -q "[e]skvisor"; then
        echo -e "Процессы eskvisor: ${RED}ЗАПУЩЕНЫ${NC}"
    else
        echo -e "Процессы eskvisor: ${GREEN}НЕ ЗАПУЩЕНЫ${NC}"
    fi

    echo ""
    echo "Лог удаления сохранен в: $LOG_FILE"

    return $ERROR_COUNT
}

# Парсинг аргументов
FORCE="false"
REMOVE_DEPS="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        --force|-f)
            FORCE="true"
            shift
            ;;
        --remove-deps|-r)
            REMOVE_DEPS="true"
            shift
            ;;
        --help|-h)
            echo "Использование: $0 [ОПЦИИ]"
            echo ""
            echo "Опции:"
            echo "  -f, --force           Пропустить подтверждение удаления"
            echo "  -r, --remove-deps     Удалить все зависимости (nginx, redis, libvirt и др.)"
            echo "  -h, --help            Показать эту справку"
            echo ""
            echo "Примеры:"
            echo "  $0                    Удалить агент с подтверждением"
            echo "  $0 --force            Принудительное удаление без подтверждения"
            echo "  $0 --remove-deps      Удалить агент и все зависимости"
            exit 0
            ;;
        *)
            echo "Неизвестный аргумент: $1"
            echo "Используйте $0 --help для справки"
            exit 1
            ;;
    esac
done

# Запуск удаления
main_uninstall
exit $?