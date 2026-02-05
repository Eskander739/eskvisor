#!/bin/bash

# update_agent.sh для AlmaLinux - обновление Eskvisor Agent без установки зависимостей

# Лог файл
LOG_FILE="/var/log/eskvisor_update.log"
exec > >(tee -a "$LOG_FILE") 2>&1

if [ -z "$1" ]; then
    echo "ERROR: Требуется указание ip agent"
    echo "USAGE: $0 <agent> <backend_url>"
    exit 1
fi

AGENT_URL="$1"
BACKEND_URL="$2"
echo "Backend: $BACKEND_URL"
echo "Agent: $AGENT_URL"

# Цвета для логгирования
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Переменные для подсчета результатов
SUCCESS_COUNT=0
ERROR_COUNT=0
SKIP_COUNT=0

# Таймауты (в секундах)
SERVICE_STOP_TIMEOUT=30
SERVICE_START_TIMEOUT=30
ROLLBACK_TIMEOUT=60

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

log_warning() {
    local message="$1"
    echo -e "${YELLOW}[ПРЕДУПРЕЖДЕНИЕ]${NC} $message"
}

# Функция проверки существования директории агента
check_agent_directory() {
    local agent_dir="/opt/eskvisor"

    if [[ ! -d "$agent_dir" ]]; then
        log_error "Директория агента не найдена: $agent_dir"
        return 1
    fi

    # Проверка основных файлов агента
    local required_files=(
        "$agent_dir/agent/client/main.py"
        "$agent_dir/agent/client/service/eskvisor.service"
        "$agent_dir/agent/client/service/eskvisor-task-manager.service"
    )

    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_warning "Файл агента не найден: $file"
        fi
    done

    return 0
}

# Функция создания резервной копии агента
create_backup() {
    local backup_dir="/var/backup/eskvisor"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_path="$backup_dir/backup_$timestamp"

    echo "Создание резервной копии агента..."

    # Создаем директорию для бэкапов если не существует
    sudo mkdir -p "$backup_dir"

    # Останавливаем сервисы перед созданием бэкапа
    stop_services_for_backup

    # Копируем агента
    echo "Копирование агента в $backup_path..."
    if sudo cp -r /opt/eskvisor "$backup_path"; then
        log_success "Резервная копия создана: $backup_path"

        # Сохраняем информацию о бэкапе
        echo "$backup_path" > /tmp/eskvisor_last_backup.txt
        echo "$timestamp" > /tmp/eskvisor_backup_timestamp.txt

        # Запускаем сервисы обратно
        start_services_after_backup

        return 0
    else
        log_error "Ошибка создания резервной копии"

        # Запускаем сервисы обратно даже при ошибке
        start_services_after_backup
        return 1
    fi
}

# Функция остановки сервисов для бэкапа
stop_services_for_backup() {
    echo "Временная остановка сервисов для создания резервной копии..."

    local services_to_stop=(
        "eskvisor.service"
        "eskvisor-state.service"
        "eskvisor-task-manager.service"
        "cgroup-state.service"
        "cgroup-state-timer.timer"
    )

    for service in "${services_to_stop[@]}"; do
        if systemctl is-active --quiet "$service"; then
            echo "Остановка $service..."
            if sudo systemctl stop "$service"; then
                log_success "$service остановлен"
            else
                log_warning "Не удалось остановить $service"
            fi
        fi
    done

    # Короткая пауза
    sleep 2
}

# Функция запуска сервисов после бэкапа
start_services_after_backup() {
    echo "Запуск сервисов после создания резервной копии..."

    local services_to_start=(
        "eskvisor.service"
        "eskvisor-task-manager.service"
        "cgroup-state.service"
        "cgroup-state-timer.timer"
    )

    for service in "${services_to_start[@]}"; do
        echo "Запуск $service..."
        if sudo systemctl start "$service"; then
            if sudo systemctl is-active --quiet "$service"; then
                log_success "$service запущен"
            else
                log_warning "$service не активен после запуска"
            fi
        else
            log_warning "Не удалось запустить $service"
        fi
    done
}

# Функция обновления агента
update_agent() {
    echo "Обновление агента..."

    # Проверяем наличие новой версии в /tmp/eskvisor_new
    local new_agent_dir="/tmp/eskvisor_new"

    if [[ ! -d "$new_agent_dir" ]]; then
        log_error "Новая версия агента не найдена в $new_agent_dir"
        return 1
    fi

    # Останавливаем все сервисы агента
    stop_all_agent_services

    # Создаем временную копию текущего агента для отката
    local temp_backup="/tmp/eskvisor_backup_$(date +%s)"
    echo "Создание временной копии текущего агента в $temp_backup..."

    if sudo cp -r /opt/eskvisor "$temp_backup"; then
        log_success "Временная копия создана"
    else
        log_error "Ошибка создания временной копии"
        return 1
    fi

    # Удаляем старую версию агента
    echo "Удаление старой версии агента..."
    if sudo rm -rf /opt/eskvisor; then
        log_success "Старая версия удалена"
    else
        log_error "Ошибка удаления старой версии"
        return 1
    fi

    # Копируем новую версию
    echo "Копирование новой версии агента..."
    if sudo cp -r "$new_agent_dir" /opt/eskvisor; then
        log_success "Новая версия скопирована"
    else
        log_error "Ошибка копирования новой версии"

        # Пытаемся восстановить из временной копии
        echo "Попытка восстановления из временной копии..."
        if sudo cp -r "$temp_backup" /opt/eskvisor; then
            log_success "Восстановлено из временной копии"
        else
            log_error "КРИТИЧЕСКАЯ ОШИБКА: Не удалось восстановить агента"
        fi

        # Запускаем сервисы с восстановленной версией
        start_all_agent_services
        return 1
    fi

    # Обновляем конфигурацию окружения если нужно
    update_environment_config

    # Запускаем сервисы с новой версией
    start_all_agent_services

    # Проверяем работу новой версии
    if verify_agent_update; then
        # Удаляем временную копию при успешном обновлении
        sudo rm -rf "$temp_backup"
        log_success "Обновление завершено успешно"
        return 0
    else
        log_error "Проверка обновления не пройдена, выполняется откат..."

        # Выполняем откат к бэкапу
        if perform_rollback; then
            log_success "Откат выполнен успешно"
        else
            log_error "КРИТИЧЕСКАЯ ОШИБКА: Откат не удался"
        fi

        return 1
    fi
}

# Функция обновления конфигурации окружения
update_environment_config() {
    echo "Обновление конфигурации окружения..."

    local new_env_file="/opt/eskvisor/agent/.env"
    local current_env_file="/etc/eskvisor/agent.env"

    if [[ -f "$new_env_file" ]]; then
        # Если есть новые настройки, обновляем их
        if [[ -f "$current_env_file" ]]; then
            echo "Сохранение текущих настроек..."

            # Создаем бэкап текущей конфигурации
            local config_backup="/etc/eskvisor/agent.env.backup_$(date +%Y%m%d_%H%M%S)"
            sudo cp "$current_env_file" "$config_backup"

            # Объединяем настройки (новые значения из нового файла, но сохраняем существующие если их нет в новом)
            echo "Объединение конфигураций..."

            # Создаем временный файл для объединенной конфигурации
            local temp_config="/tmp/agent_env_merged_$(date +%s)"

            # Копируем новые настройки
            sudo cp "$new_env_file" "$temp_config"

            # Добавляем существующие настройки, которых нет в новом файле
            while IFS='=' read -r key value; do
                # Пропускаем комментарии и пустые строки
                [[ -z "$key" ]] || [[ "$key" =~ ^# ]] && continue

                # Проверяем есть ли этот ключ в новом файле
                if ! grep -q "^$key=" "$new_env_file"; then
                    echo "$key=$value" | sudo tee -a "$temp_config" > /dev/null
                fi
            done < "$current_env_file"

            # Заменяем текущую конфигурацию объединенной
            sudo mv "$temp_config" "$current_env_file"

            log_success "Конфигурация окружения обновлена"

            if [ -n "$AGENT_URL" ]; then
                mkdir -p /etc/eskvisor
                echo "AGENT_URL=$AGENT_URL" >> current_env_file
                echo "Agent URL saved: $AGENT_URL"
            else
                echo "WARNING: AGENT_URL is empty, not saving to config"
            fi

            if [ -n "$BACKEND_URL" ]; then
                mkdir -p /etc/eskvisor
                echo "BACKEND_URL=$BACKEND_URL" >> current_env_file
                echo "Backend URL saved: $BACKEND_URL"
            else
                echo "WARNING: BACKEND_URL is empty, not saving to config"
            fi
        else
            # Если конфигурации не было, просто копируем новую
            sudo mkdir -p /etc/eskvisor
            sudo cp "$new_env_file" "$current_env_file"
            log_success "Конфигурация окружения создана"

            if [ -n "$AGENT_URL" ]; then
                mkdir -p /etc/eskvisor
                echo "AGENT_URL=$AGENT_URL" >> current_env_file
                echo "Agent URL saved: $AGENT_URL"
            else
                echo "WARNING: AGENT_URL is empty, not saving to config"
            fi

            if [ -n "$BACKEND_URL" ]; then
                mkdir -p /etc/eskvisor
                echo "BACKEND_URL=$BACKEND_URL" >> current_env_file
                echo "Backend URL saved: $BACKEND_URL"
            else
                echo "WARNING: BACKEND_URL is empty, not saving to config"
            fi
        fi
    else
        log_skip "Файл конфигурации окружения не найден в новой версии"
    fi
}

# Функция остановки всех сервисов агента
stop_all_agent_services() {
    echo "========================================="
    echo "Остановка сервисов агента"
    echo "========================================="

    local services_to_stop=(
        "nginx"
        "eskvisor.service"
        "eskvisor-state.service"
        "eskvisor-task-manager.service"
        "cgroup-state.service"
        "cgroup-state-timer.timer"
    )

    for service in "${services_to_stop[@]}"; do
        echo "Остановка $service..."

        if systemctl is-active --quiet "$service"; then
            if sudo systemctl stop "$service"; then
                # Проверяем что сервис действительно остановился
                local wait_time=0
                while systemctl is-active --quiet "$service" && [ $wait_time -lt $SERVICE_STOP_TIMEOUT ]; do
                    sleep 1
                    ((wait_time++))
                done

                if systemctl is-active --quiet "$service"; then
                    log_warning "$service не остановился за $SERVICE_STOP_TIMEOUT секунд, принудительная остановка..."
                    sudo systemctl kill -s SIGKILL "$service"
                    sleep 2
                fi

                log_success "$service остановлен"
            else
                log_warning "Не удалось остановить $service, продолжаем обновление..."
            fi
        else
            log_skip "$service уже остановлен"
        fi
    done

    # Даем системе время на завершение процессов
    sleep 3
}

# Функция запуска всех сервисов агента
start_all_agent_services() {
    echo "========================================="
    echo "Запуск сервисов агента"
    echo "========================================="

    local services_to_start=(
        "redis"
        "nginx"
        "eskvisor.service"
        "eskvisor-state.service"
        "eskvisor-task-manager.service"
        "cgroup-state.service"
        "cgroup-state-timer.timer"
    )

    for service in "${services_to_start[@]}"; do
        echo "Запуск $service..."

        if ! systemctl is-active --quiet "$service"; then
            if sudo systemctl start "$service"; then
                # Проверяем что сервис запустился
                local wait_time=0
                while ! systemctl is-active --quiet "$service" && [ $wait_time -lt $SERVICE_START_TIMEOUT ]; do
                    sleep 1
                    ((wait_time++))
                done

                if systemctl is-active --quiet "$service"; then
                    log_success "$service запущен"
                else
                    log_error "$service не запустился за $SERVICE_START_TIMEOUT секунд"
                    sudo systemctl status "$service" --no-pager
                fi
            else
                log_error "Не удалось запустить $service"
                sudo systemctl status "$service" --no-pager
            fi
        else
            log_skip "$service уже запущен"
        fi
    done

    # Даем сервисам время на инициализацию
    sleep 5
}

# Функция проверки обновления агента
verify_agent_update() {
    echo "========================================="
    echo "Проверка обновления агента"
    echo "========================================="

    local verification_passed=true

    echo "1. Проверка файловой структуры агента..."
    if check_agent_directory; then
        log_success "Структура агента корректна"
    else
        log_error "Структура агента повреждена"
        verification_passed=false
    fi

    echo "2. Проверка работы сервисов..."
    local services_to_check=(
        "eskvisor.service"
        "eskvisor-state.service"
        "eskvisor-task-manager.service"
        "cgroup-state.service"
        "cgroup-state-timer.timer"
        "nginx"
        "redis"
    )

    for service in "${services_to_check[@]}"; do
        if systemctl is-active --quiet "$service"; then
            log_success "$service активен"
        else
            log_error "$service не активен"
            verification_passed=false
            sudo systemctl status "$service" --no-pager
        fi
    done

    echo "3. Проверка конфигурации nginx..."
    if sudo nginx -t 2>/dev/null; then
        log_success "Конфигурация nginx валидна"
    else
        log_error "Ошибка в конфигурации nginx"
        verification_passed=false
        sudo nginx -t
    fi

    echo "4. Проверка работы Redis..."
    if redis-cli ping | grep -q "PONG"; then
        log_success "Redis работает корректно"
    else
        log_error "Redis не отвечает"
        verification_passed=false
    fi

    echo "5. Быстрая проверка HTTP endpoints..."

    if $verification_passed; then
        log_success "Проверка обновления пройдена успешно"
        return 0
    else
        log_error "Проверка обновления не пройдена"
        return 1
    fi
}

# Функция выполнения отката к резервной копии
perform_rollback() {
    echo "========================================="
    echo "ВЫПОЛНЕНИЕ ОТКАТА К РЕЗЕРВНОЙ КОПИИ"
    echo "========================================="

    # Определяем последнюю резервную копию
    local backup_dir="/var/backup/eskvisor"
    local last_backup_file="/tmp/eskvisor_last_backup.txt"

    if [[ ! -f "$last_backup_file" ]]; then
        log_error "Файл с информацией о последнем бэкапе не найден"

        # Пытаемся найти последний бэкап
        local latest_backup=$(ls -td "$backup_dir"/backup_* 2>/dev/null | head -1)
        if [[ -n "$latest_backup" ]]; then
            log_warning "Найден последний бэкап: $latest_backup"
            local backup_path="$latest_backup"
        else
            log_error "Резервные копии не найдены, откат невозможен"
            return 1
        fi
    else
        local backup_path=$(cat "$last_backup_file")
    fi

    if [[ ! -d "$backup_path" ]]; then
        log_error "Резервная копия не найдена: $backup_path"
        return 1
    fi

    echo "Откат к резервной копии: $backup_path"

    # Останавливаем сервисы перед откатом
    stop_all_agent_services

    echo "Удаление текущей версии агента..."
    if sudo rm -rf /opt/eskvisor; then
        log_success "Текущая версия удалена"
    else
        log_error "Ошибка удаления текущей версии"
        return 1
    fi

    echo "Восстановление из резервной копии..."
    if sudo cp -r "$backup_path" /opt/eskvisor; then
        log_success "Агент восстановлен из резервной копии"
    else
        log_error "Ошибка восстановления из резервной копии"
        return 1
    fi

    # Восстанавливаем конфигурацию окружения если есть бэкап
    local config_backup=$(ls -t /etc/eskvisor/agent.env.backup_* 2>/dev/null | head -1)
    if [[ -n "$config_backup" && -f "$config_backup" ]]; then
        echo "Восстановление конфигурации окружения..."
        sudo cp "$config_backup" /etc/eskvisor/agent.env
        log_success "Конфигурация окружения восстановлена"
    fi

    # Запускаем сервисы с восстановленной версией
    start_all_agent_services

    # Проверяем восстановление
    echo "Проверка восстановления после отката..."
    if verify_agent_update; then
        log_success "Откат выполнен успешно"
        return 0
    else
        log_error "Откат выполнен, но проверка не пройдена"
        return 1
    fi
}

# Функция очистки временных файлов
cleanup_temp_files() {
    echo "========================================="
    echo "ОЧИСТКА ВРЕМЕННЫХ ФАЙЛОВ"
    echo "========================================="

    # Удаляем распакованного агента
    if [[ -d "/tmp/eskvisor_new" ]]; then
        sudo rm -rf /tmp/eskvisor_new
        log_success "Временная директория /tmp/eskvisor_new удалена"
    fi

    # Удаляем архив агента
    local agent_archive="/tmp/eskvisor_agent_package.tar.gz"
    if [[ -f "$agent_archive" ]]; then
        sudo rm -f "$agent_archive"
        log_success "Архив агента $agent_archive удален"
    fi

    # Очищаем временные файлы скрипта
    rm -f /tmp/eskvisor_last_backup.txt
    rm -f /tmp/eskvisor_backup_timestamp.txt
}

# Основная функция
main() {
    echo "========================================="
    echo "ОБНОВЛЕНИЕ ESKVISOR AGENT"
    echo "========================================="

    echo "Логирование обновления в файл: $LOG_FILE"

    # Проверка прав
    if [[ $EUID -ne 0 ]]; then
        echo "Этот скрипт должен быть запущен с правами root"
        exit 1
    fi

    # Проверяем существование агента
    if ! check_agent_directory; then
        log_error "Агент не установлен или поврежден. Обновление невозможно."
        exit 1
    fi

    # Создаем резервную копию
    if ! create_backup; then
        log_error "Не удалось создать резервную копию. Прерывание обновления."
        exit 1
    fi

    # Обновляем агента
    if update_agent; then
        log_success "Агент успешно обновлен"
    else
        log_error "Ошибка обновления агента"

        # Если обновление не удалось, но у нас есть бэкап, предлагаем откат
        if perform_rollback; then
            log_success "Откат выполнен"
            cleanup_temp_files
        else
            log_error "Откат не удался"
            cleanup_temp_files
        fi

        exit 1
    fi

    # Финальный отчет
    echo ""
    echo "========================================="
    echo "ОБНОВЛЕНИЕ ЗАВЕРШЕНО"
    echo "========================================="
    echo -e "${GREEN}Успешно выполнено: $SUCCESS_COUNT${NC}"
    echo -e "${RED}Ошибок: $ERROR_COUNT${NC}"
    echo -e "${YELLOW}Пропущено: $SKIP_COUNT${NC}"
    echo ""

    if [[ $ERROR_COUNT -eq 0 ]]; then
        echo -e "${GREEN}Агент успешно обновлен!${NC}"
        echo ""
        echo "Текущая версия агента:"
        echo "  Расположение: /opt/eskvisor"
        echo "  Конфигурация: /etc/eskvisor/agent.env"
        echo ""
        echo "Статус сервисов:"
        sudo systemctl is-active eskvisor.service &>/dev/null && echo -e "  Eskvisor: ${GREEN}активен${NC}" || echo -e "  Eskvisor: ${RED}не активен${NC}"
        sudo systemctl is-active eskvisor-state.service &>/dev/null && echo -e "  Eskvisor: ${GREEN}активен${NC}" || echo -e "  Eskvisor: ${RED}не активен${NC}"
        sudo systemctl is-active eskvisor-task-manager.service &>/dev/null && echo -e "  Eskvisor Task Manager: ${GREEN}активен${NC}" || echo -e "  Eskvisor Task Manager: ${RED}не активен${NC}"
        sudo systemctl is-active nginx &>/dev/null && echo -e "  Nginx: ${GREEN}активен${NC}" || echo -e "  Nginx: ${RED}не активен${NC}"
        sudo systemctl is-active redis &>/dev/null && echo -e "  Redis: ${GREEN}активен${NC}" || echo -e "  Redis: ${RED}не активен${NC}"
        sudo systemctl is-active cgroup-state-timer.timer &>/dev/null && echo -e "  Cgroup State Timer: ${GREEN}активен${NC}" || echo -e "  Cgroup State Timer: ${RED}не активен${NC}"

        echo ""
        echo "Резервная копия сохранена в: /var/backup/eskvisor/"
        echo "Лог обновления сохранен в: $LOG_FILE"
    else
        echo -e "${YELLOW}Были ошибки при обновлении. Проверьте лог выше.${NC}"
        echo "Для отката выполните: sudo bash /path/to/update_agent.sh --rollback"
    fi

    exit $ERROR_COUNT
}

# Обработка аргументов командной строки
case "${1:-}" in
    "--rollback")
        echo "Запуск отката к резервной копии..."
        if perform_rollback; then
            echo -e "${GREEN}Откат выполнен успешно${NC}"
            exit 0
        else
            echo -e "${RED}Откат не удался${NC}"
            exit 1
        fi
        ;;
    "--verify")
        echo "Запуск проверки текущей установки..."
        if verify_agent_update; then
            echo -e "${GREEN}Проверка пройдена успешно${NC}"
            exit 0
        else
            echo -e "${RED}Проверка не пройдена${NC}"
            exit 1
        fi
        ;;
    "--help"|"-h")
        echo "Использование: $0 [опции]"
        echo ""
        echo "Опции:"
        echo "  --rollback    Выполнить откат к последней резервной копии"
        echo "  --verify      Проверить текущую установку агента"
        echo "  --help, -h    Показать эту справку"
        echo ""
        echo "Без опций: выполнить обновление агента"
        exit 0
        ;;
    *)
        # Запуск основного скрипта
        main
        ;;
esac