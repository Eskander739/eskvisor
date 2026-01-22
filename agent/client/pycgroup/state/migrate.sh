#!/bin/bash
# /usr/local/bin/migrate.sh
# Миграция сохраненных конфигураций cgroup resource_pool* на удаленный хост

set -euo pipefail

# Конфигурация
BACKUP_ROOT="/cgroup/backups/cgroups"
LOG_FILE="/var/log/cgroup-migrate.log"
SSH_PORT=22
SSH_TIMEOUT=30

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции цветного вывода
color_echo() {
    local color="$1"
    local message="$2"
    echo -e "${color}${message}${NC}"
}

# Функции логирования
log() {
    local message="$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $message" | tee -a "$LOG_FILE"
}

log_error() {
    local message="$1"
    color_echo "$RED" "ОШИБКА: $message"
    log "ОШИБКА: $message"
}

log_success() {
    local message="$1"
    color_echo "$GREEN" "УСПЕХ: $message"
    log "УСПЕХ: $message"
}

log_info() {
    local message="$1"
    color_echo "$YELLOW" "INFO: $message"
    log "INFO: $message"
}

log_debug() {
    local message="$1"
    color_echo "$BLUE" "DEBUG: $message"
    log "DEBUG: $message"
}

# Показ справки
show_help() {
    echo "Использование: $0 [ОПЦИИ] <целевой_хост>"
    echo ""
    echo "Миграция сохраненных конфигураций cgroup resource_pool* на удаленный хост"
    echo ""
    echo "Опции:"
    echo "  -u, --user USER          Пользователь SSH (по умолчанию: текущий)"
    echo "  -p, --port PORT          Порт SSH (по умолчанию: 22)"
    echo "  -d, --dest PATH          Путь на целевом хосте (по умолчанию: $BACKUP_ROOT)"
    echo "  -b, --backup PATH        Локальный путь к бэкапам (по умолчанию: $BACKUP_ROOT)"
    echo "  -c, --config FILE        Файл конфигурации для миграции"
    echo "  -t, --test               Тестовый режим (проверка без передачи)"
    echo "  -f, --force              Принудительная перезапись на целевом хосте"
    echo "  -s, --sync               Синхронизация (удаление лишних файлов на целевом хосте)"
    echo "  -l, --list               Показать доступные для миграции пулы"
    echo "  --include PATTERN        Включить только пулы по шаблону (регулярное выражение)"
    echo "  --exclude PATTERN        Исключить пулы по шаблону (регулярное выражение)"
    echo "  -h, --help               Показать эту справку"
    echo ""
    echo "Примеры:"
    echo "  $0 user@remote-host                        # Базовая миграция"
    echo "  $0 -u admin -p 2222 remote-host            # С указанием пользователя и порта"
    echo "  $0 -d /backup/cgroups remote-host          # С указанием целевого пути"
    echo "  $0 -t remote-host                          # Тестовый режим"
    echo ""
    exit 0
}

# Проверка зависимостей
check_dependencies() {
    local missing_deps=()

    for cmd in rsync ssh scp ssh-keygen; do
        if ! command -v "$cmd" &>/dev/null; then
            missing_deps+=("$cmd")
        fi
    done

    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Отсутствуют необходимые команды: ${missing_deps[*]}"
        echo "Установите их с помощью:"
        echo "  apt-get install rsync openssh-client  # для Debian/Ubuntu"
        echo "  yum install rsync openssh-clients     # для CentOS/RHEL"
        exit 1
    fi
}

# Проверка SSH подключения
check_ssh_connection() {
    local host="$1"
    local user="$2"
    local port="$3"

    log_info "Проверка SSH подключения к ${user}@${host}:${port}"

    local ssh_command
    if [[ "$user" == "$(whoami)" ]]; then
        ssh_command="ssh -p $port -o ConnectTimeout=$SSH_TIMEOUT -o BatchMode=yes -o StrictHostKeyChecking=accept-new $host exit"
    else
        ssh_command="ssh -p $port -o ConnectTimeout=$SSH_TIMEOUT -o BatchMode=yes -o StrictHostKeyChecking=accept-new ${user}@${host} exit"
    fi

    if ! eval "$ssh_command" &>/dev/null; then
        log_error "Не удалось подключиться к ${user}@${host}:${port}"
        echo ""
        echo "Рекомендации:"
        echo "  1. Проверьте доступность хоста: ping $host"
        echo "  2. Проверьте порт SSH: nc -zv $host $port"
        echo "  3. Проверьте аутентификацию SSH:"
        echo "     - ssh-copy-id ${user}@${host} -p $port"
        echo "     - Или используйте ssh-agent"
        echo "  4. Проверьте настройки брандмауэра"
        return 1
    fi

    log_success "SSH подключение успешно"
    return 0
}

# Проверка зависимостей на целевом хосте
check_remote_dependencies() {
    local host="$1"
    local user="$2"
    local port="$3"

    log_info "Проверка зависимостей на целевом хосте"

    local ssh_cmd
    if [[ "$user" == "$(whoami)" ]]; then
        ssh_cmd="ssh -p $port $host"
    else
        ssh_cmd="ssh -p $port ${user}@${host}"
    fi

    # Проверяем наличие rsync
    if ! $ssh_cmd "command -v rsync" &>/dev/null; then
        log_error "На целевом хосте отсутствует rsync"
        echo "Установите rsync на целевом хосте:"
        echo "  apt-get install rsync  # для Debian/Ubuntu"
        echo "  yum install rsync      # для CentOS/RHEL"
        return 1
    fi

    # Проверяем наличие директории для бэкапов
    if ! $ssh_cmd "mkdir -p $REMOTE_BACKUP_ROOT" &>/dev/null; then
        log_error "Не удалось создать директорию на целевом хосте: $REMOTE_BACKUP_ROOT"
        return 1
    fi

    # Проверяем права на запись
    if ! $ssh_cmd "test -w $REMOTE_BACKUP_ROOT" &>/dev/null; then
        log_error "Нет прав на запись в директорию на целевом хосте: $REMOTE_BACKUP_ROOT"
        return 1
    fi

    log_success "Зависимости на целевом хосте проверены"
    return 0
}

# Показать список доступных пулов для миграции
list_pools() {
    local backup_root="$1"

    if [[ ! -d "$backup_root" ]]; then
        log_error "Директория бэкапов не найдена: $backup_root"
        return 1
    fi

    local pools=($(find "$backup_root" -maxdepth 1 -type d -name 'resource_pool*' -exec basename {} \; | sort))

    if [[ ${#pools[@]} -eq 0 ]]; then
        echo "  (нет доступных пулов)"
        return 0
    fi

    echo "Доступные пулы для миграции:"
    for pool in "${pools[@]}"; do
        local pool_path="$backup_root/$pool"
        local size=$(du -sh "$pool_path" 2>/dev/null | cut -f1)
        local files_count=$(find "$pool_path" -type f | wc -l)
        local manifest=$(find "$pool_path" -name "MANIFEST.json" -o -name "backup_manifest_*.json" 2>/dev/null | head -1)

        echo "  • $pool"
        echo "      Размер: $size, Файлов: $files_count"

        if [[ -n "$manifest" ]]; then
            local backup_date=$(grep -o '"backup_date":"[^"]*"' "$manifest" 2>/dev/null | cut -d'"' -f4 | head -1)
            if [[ -n "$backup_date" ]]; then
                echo "      Дата бэкапа: $backup_date"
            fi
        fi
    done

    echo ""
    echo "Всего пулов: ${#pools[@]}"
    return 0
}

# Фильтрация пулов по шаблонам включения/исключения
filter_pools() {
    local backup_root="$1"
    local include_pattern="$2"
    local exclude_pattern="$3"

    local all_pools=($(find "$backup_root" -maxdepth 1 -type d -name 'resource_pool*' -exec basename {} \; | sort))
    local filtered_pools=()

    for pool in "${all_pools[@]}"; do
        local include=true

        # Применяем фильтр включения
        if [[ -n "$include_pattern" ]]; then
            if [[ ! "$pool" =~ $include_pattern ]]; then
                include=false
            fi
        fi

        # Применяем фильтр исключения
        if [[ -n "$exclude_pattern" ]]; then
            if [[ "$pool" =~ $exclude_pattern ]]; then
                include=false
            fi
        fi

        if [[ "$include" == "true" ]]; then
            filtered_pools+=("$pool")
        fi
    done

    echo "${filter_pools[@]}"
}

# Основная функция миграции
migrate_pools() {
    local local_path="$1"
    local remote_host="$2"
    local remote_user="$3"
    local remote_port="$4"
    local remote_path="$5"
    local test_mode="$6"
    local force_mode="$7"
    local sync_mode="$8"
    local pools=("${@:9}")

    log_info "Начало миграции ${#pools[@]} пулов"

    # Строим команду rsync
    local rsync_cmd="rsync -avz"

    # Настройка SSH
    rsync_cmd="$rsync_cmd -e 'ssh -p $remote_port -o StrictHostKeyChecking=accept-new'"

    # Добавляем опции в зависимости от режима
    if [[ "$test_mode" == "true" ]]; then
        rsync_cmd="$rsync_cmd --dry-run"
        log_info "ТЕСТОВЫЙ РЕЖИМ: файлы не будут переданы"
    fi

    if [[ "$force_mode" == "true" ]]; then
        rsync_cmd="$rsync_cmd --ignore-times"
    else
        rsync_cmd="$rsync_cmd --update"
    fi

    if [[ "$sync_mode" == "true" ]]; then
        rsync_cmd="$rsync_cmd --delete"
        log_info "Режим синхронизации: лишние файлы будут удалены на целевом хосте"
    fi

    # Добавляем прогресс и логирование
    rsync_cmd="$rsync_cmd --progress --stats"

    local migrated_count=0
    local failed_count=0
    local failed_pools=()

    # Мигрируем каждый пул
    for pool in "${pools[@]}"; do
        local pool_local_path="$local_path/$pool"
        local pool_remote_path="$remote_path/$pool"

        if [[ ! -d "$pool_local_path" ]]; then
            log_error "Пропуск: локальный путь не существует - $pool_local_path"
            failed_pools+=("$pool (не существует)")
            failed_count=$((failed_count + 1))
            continue
        fi

        log_info "Миграция пула: $pool"
        log_debug "  Локальный: $pool_local_path"
        log_debug "  Удаленный: ${remote_user}@${remote_host}:$pool_remote_path"

        # Создаем команду для этого пула
        local pool_rsync_cmd="$rsync_cmd '$pool_local_path/' '${remote_user}@${remote_host}:$pool_remote_path/'"

        # Выполняем миграцию
        log_debug "Выполнение: $pool_rsync_cmd"

        if eval "$pool_rsync_cmd" 2>&1 | tee -a "$LOG_FILE"; then
            log_success "Пул $pool успешно мигрирован"
            migrated_count=$((migrated_count + 1))

            # Создаем файл с метаинформацией о миграции
            local migration_manifest="$pool_local_path/MIGRATION_${DATE}.json"
            cat > "$migration_manifest" << EOF
{
    "pool_name": "$pool",
    "migration_date": "$(date -Iseconds)",
    "source_host": "$(hostname)",
    "destination_host": "$remote_host",
    "destination_user": "$remote_user",
    "destination_path": "$pool_remote_path",
    "migration_tool": "rsync/ssh",
    "files_count": $(find "$pool_local_path" -type f | wc -l),
    "total_size_bytes": $(du -sb "$pool_local_path" | cut -f1)
}
EOF

            # Копируем манифест на удаленный хост
            if [[ "$test_mode" != "true" ]]; then
                scp -P "$remote_port" -o StrictHostKeyChecking=accept-new \
                    "$migration_manifest" \
                    "${remote_user}@${remote_host}:$pool_remote_path/" 2>/dev/null || true
            fi
        else
            log_error "Ошибка при миграции пула: $pool"
            failed_pools+=("$pool")
            failed_count=$((failed_count + 1))
        fi

        echo ""
    done

    # Итоговый отчет
    echo "=== РЕЗУЛЬТАТЫ МИГРАЦИИ ==="
    echo ""

    if [[ $migrated_count -gt 0 ]]; then
        color_echo "$GREEN" "Успешно мигрировано: $migrated_count пулов"
    fi

    if [[ $failed_count -gt 0 ]]; then
        color_echo "$RED" "Не удалось мигрировать: $failed_count пулов"
        for failed in "${failed_pools[@]}"; do
            echo "  • $failed"
        done
    fi

    if [[ $test_mode == "true" ]]; then
        color_echo "$YELLOW" "ТЕСТОВЫЙ РЕЖИМ: Файлы не были переданы"
        echo ""
        echo "Для реальной миграции запустите команду без опции -t"
    fi

    return $failed_count
}

# Основная логика скрипта
main() {
    # Парсинг аргументов
    local SSH_USER=$(whoami)
    local REMOTE_BACKUP_ROOT="$BACKUP_ROOT"
    local LOCAL_BACKUP_ROOT="$BACKUP_ROOT"
    local CONFIG_FILE=""
    local TEST_MODE=false
    local FORCE_MODE=false
    local SYNC_MODE=false
    local LIST_MODE=false
    local INCLUDE_PATTERN=""
    local EXCLUDE_PATTERN=""

    # Парсим опции
    while [[ $# -gt 0 ]]; do
        case $1 in
            -u|--user)
                SSH_USER="$2"
                shift 2
                ;;
            -p|--port)
                SSH_PORT="$2"
                shift 2
                ;;
            -d|--dest)
                REMOTE_BACKUP_ROOT="$2"
                shift 2
                ;;
            -b|--backup)
                LOCAL_BACKUP_ROOT="$2"
                shift 2
                ;;
            -c|--config)
                CONFIG_FILE="$2"
                shift 2
                ;;
            -t|--test)
                TEST_MODE=true
                shift
                ;;
            -f|--force)
                FORCE_MODE=true
                shift
                ;;
            -s|--sync)
                SYNC_MODE=true
                shift
                ;;
            -l|--list)
                LIST_MODE=true
                shift
                ;;
            --include)
                INCLUDE_PATTERN="$2"
                shift 2
                ;;
            --exclude)
                EXCLUDE_PATTERN="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                ;;
            -*)
                log_error "Неизвестная опция: $1"
                show_help
                ;;
            *)
                REMOTE_HOST="$1"
                shift
                ;;
        esac
    done

    # Проверка обязательных параметров
    if [[ -z "$REMOTE_HOST" ]] && [[ "$LIST_MODE" != "true" ]]; then
        log_error "Не указан целевой хост"
        show_help
    fi

    # Проверка конфигурационного файла
    if [[ -n "$CONFIG_FILE" ]]; then
        if [[ ! -f "$CONFIG_FILE" ]]; then
            log_error "Конфигурационный файл не найден: $CONFIG_FILE"
            exit 1
        fi
        log_info "Загрузка конфигурации из: $CONFIG_FILE"
        source "$CONFIG_FILE"
    fi

    # Режим списка
    if [[ "$LIST_MODE" == "true" ]]; then
        log_info "Список доступных пулов в $LOCAL_BACKUP_ROOT"
        list_pools "$LOCAL_BACKUP_ROOT"
        exit 0
    fi

    # Начало миграции
    DATE=$(date +%Y%m%d_%H%M%S)
    log "=== Начало миграции cgroup конфигураций на $REMOTE_HOST ==="

    # Проверка зависимостей
    check_dependencies

    # Проверка локальной директории бэкапов
    if [[ ! -d "$LOCAL_BACKUP_ROOT" ]]; then
        log_error "Локальная директория бэкапов не найдена: $LOCAL_BACKUP_ROOT"
        exit 1
    fi

    # Получаем список пулов с учетом фильтров
    local POOLS_TO_MIGRATE=($(filter_pools "$LOCAL_BACKUP_ROOT" "$INCLUDE_PATTERN" "$EXCLUDE_PATTERN"))

    if [[ ${#POOLS_TO_MIGRATE[@]} -eq 0 ]]; then
        log_error "Нет пулов для миграции после применения фильтров"
        echo "Используйте опцию -l для просмотра доступных пулов"
        exit 1
    fi

    log_info "Найдено пулов для миграции: ${#POOLS_TO_MIGRATE[@]}"

    # Показываем список пулов для миграции
    echo "Планируется миграция следующих пулов:"
    for pool in "${POOLS_TO_MIGRATE[@]}"; do
        echo "  • $pool"
    done
    echo ""

    # Подтверждение (если не в тестовом режиме)
    if [[ "$TEST_MODE" != "true" ]] && [[ "$FORCE_MODE" != "true" ]]; then
        read -p "Продолжить миграцию? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Миграция отменена пользователем"
            exit 0
        fi
    fi

    # Проверка SSH подключения
    if ! check_ssh_connection "$REMOTE_HOST" "$SSH_USER" "$SSH_PORT"; then
        exit 1
    fi

    # Проверка зависимостей на целевом хосте
    if ! check_remote_dependencies "$REMOTE_HOST" "$SSH_USER" "$SSH_PORT"; then
        exit 1
    fi

    # Выполняем миграцию
    migrate_pools \
        "$LOCAL_BACKUP_ROOT" \
        "$REMOTE_HOST" \
        "$SSH_USER" \
        "$SSH_PORT" \
        "$REMOTE_BACKUP_ROOT" \
        "$TEST_MODE" \
        "$FORCE_MODE" \
        "$SYNC_MODE" \
        "${POOLS_TO_MIGRATE[@]}"

    local exit_code=$?

    log "=== Миграция завершена: $(date) ==="

    if [[ $exit_code -eq 0 ]]; then
        log_success "Миграция успешно завершена"
        echo ""
        echo "Для восстановления на целевом хосте выполните:"
        echo "  ssh ${SSH_USER}@${REMOTE_HOST} -p $SSH_PORT"
        echo "  /usr/local/bin/restore.sh $REMOTE_BACKUP_ROOT"
    else
        log_error "Миграция завершена с ошибками"
    fi

    exit $exit_code
}

# Запуск основной функции
main "$@"