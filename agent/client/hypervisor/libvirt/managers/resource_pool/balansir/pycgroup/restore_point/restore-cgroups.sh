#!/bin/bash
# /usr/local/bin/restore-cgroups.sh
# Автоматическое восстановление конфигураций cgroup для resource_pool*

set -euo pipefail

# Конфигурация
BACKUP_ROOT="/eskvisor/backups/cgroups"
BACKUP_DIR="${1:-$BACKUP_ROOT}"
LOG_FILE="/var/log/eskvisor-cgroup-restore.log"

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
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

# Начало работы
log "=== Начало восстановления cgroup конфигурации для resource_pool* ==="

# Проверяем наличие бэкапа
if [[ ! -d "$BACKUP_DIR" ]]; then
    log_error "Директория бэкапа $BACKUP_DIR не найдена"
    echo "Доступные бэкапы:"
    find "$BACKUP_ROOT" -maxdepth 1 -type d -name "resource_pool*" | sort -r
    exit 1
fi

log_info "Восстановление из: $BACKUP_DIR"

# Функция для создания cgroup
create_cgroup() {
    local cgroup_path="$1"
    local parent_dir

    # Проверяем, существует ли уже cgroup
    if [[ -d "$cgroup_path" ]]; then
        log_info "Cgroup уже существует: $cgroup_path"
        return 0
    fi

    parent_dir=$(dirname "$cgroup_path")

    # Проверяем существование родительской директории
    if [[ ! -d "$parent_dir" ]]; then
        log_error "Родительская директория не существует: $parent_dir"
        return 1
    fi

    # Проверяем права на запись в родительскую директорию
    if [[ ! -w "$parent_dir" ]]; then
        log_error "Нет прав на запись в родительскую директорию: $parent_dir"
        return 1
    fi

    # Создаем cgroup
    if mkdir -p "$cgroup_path" 2>/dev/null; then
        log_info "Создана cgroup: $cgroup_path"

        # Для resource_pool включаем контроллеры
        if [[ "$cgroup_path" =~ /sys/fs/cgroup/resource_pool ]]; then
            log_info "Включение контроллеров для: $cgroup_path"
            # Включаем контроллеры только если файл существует и доступен для записи
            if [[ -f "$cgroup_path/cgroup.subtree_control" ]] && [[ -w "$cgroup_path/cgroup.subtree_control" ]]; then
                echo "+cpu +memory +io +pids" > "$cgroup_path/cgroup.subtree_control" 2>/dev/null || {
                    log_info "Не удалось включить контроллеры для $cgroup_path (возможно уже включены)"
                }
            else
                log_info "Файл cgroup.subtree_control недоступен для записи: $cgroup_path/cgroup.subtree_control"
            fi
        fi

        return 0
    else
        log_error "Не удалось создать cgroup: $cgroup_path"
        return 1
    fi
}

# Функция для восстановления конфигурационных файлов
restore_configs() {
    local backup_path="$1"
    local cgroup_path="$2"
    local restored_count=0
    local total_files=0

    # Проверяем, существует ли backup_path
    if [[ ! -d "$backup_path" ]]; then
        log_error "Директория бэкапа не существует: $backup_path"
        return 1
    fi

    # Проверяем, существует ли cgroup_path
    if [[ ! -d "$cgroup_path" ]]; then
        log_error "Целевая cgroup не существует: $cgroup_path"
        return 1
    fi

    log_info "Восстановление конфигов из $backup_path в $cgroup_path"

    # Перебираем файлы в директории бэкапа
    for config_file in "$backup_path"/*; do
        if [[ -f "$config_file" ]] && [[ ! "$config_file" =~ MANIFEST\.json$ ]]; then
            total_files=$((total_files + 1))
            local filename=$(basename "$config_file")
            local target_file="$cgroup_path/$filename"

            # Пропускаем системные файлы, которые нельзя изменять напрямую
            case "$filename" in
                cgroup.procs|cgroup.threads|cgroup.events|cgroup.type|cgroup.controllers)
                    continue
                    ;;
            esac

            # Проверяем, существует ли файл в cgroup (опционально, можно создавать)
            if [[ ! -f "$target_file" ]]; then
                log_info "  Файл не существует в cgroup, пропускаем: $filename"
                continue
            fi

            # Проверяем доступность для записи
            if [[ ! -w "$target_file" ]]; then
                log_info "  Файл недоступен для записи: $target_file"
                continue
            fi

            # Читаем значение из бэкапа
            local backup_value
            backup_value=$(cat "$config_file" 2>/dev/null || echo "")

            # Только если значение не пустое
            if [[ -n "$backup_value" ]]; then
                log_info "  Запись $filename = '$backup_value'"
                if echo "$backup_value" > "$target_file" 2>/dev/null; then
                    restored_count=$((restored_count + 1))
                    log_info "  ✓ Восстановлен: $filename"
                else
                    log_info "  ✗ Не удалось записать: $filename"
                fi
            else
                log_info "  ∅ Пропущен (пустое значение): $filename"
            fi
        fi
    done

    log_info "  Восстановлено файлов: $restored_count из $total_files"
    return 0
}

# Создаем временные файлы для хранения результатов
TEMP_RESTORED="/tmp/restored_pools.$$"
TEMP_FAILED="/tmp/failed_pools.$$"

touch "$TEMP_RESTORED" "$TEMP_FAILED"

# Основной цикл восстановления
log_info "Поиск пулов для восстановления в $BACKUP_DIR"

# Находим все директории resource_pool* в BACKUP_DIR
backup_pool_dirs=($(find "$BACKUP_DIR" -maxdepth 1 -type d -name 'resource_pool*'))

log_info "Найдено пулов для восстановления: ${#backup_pool_dirs[@]}"

for backup_pool_dir in "${backup_pool_dirs[@]}"; do
    pool_name=$(basename "$backup_pool_dir")
    log_info "--- Восстановление пула: $pool_name ---"

    # Целевой путь в cgroup
    target_pool_path="/sys/fs/cgroup/$pool_name"

    # Шаг 1: Создаем директорию cgroup
    if create_cgroup "$target_pool_path"; then
        # Шаг 2: Восстанавливаем конфигурационные файлы
        if restore_configs "$backup_pool_dir" "$target_pool_path"; then
            echo "$target_pool_path" >> "$TEMP_RESTORED"
            log_info "Пул $pool_name успешно создан и настроен"
        else
            echo "$pool_name" >> "$TEMP_FAILED"
            log_error "Не удалось восстановить конфиги для пула: $pool_name"
        fi
    else
        echo "$pool_name" >> "$TEMP_FAILED"
        log_error "Не удалось создать пул: $pool_name"
    fi

    # Восстанавливаем вложенные cgroup (если есть)
    log_info "Поиск вложенных cgroup в $pool_name..."
    find "$backup_pool_dir" -type d | while read -r backup_sub_dir; do
        [[ "$backup_sub_dir" == "$backup_pool_dir" ]] && continue

        sub_path="${backup_sub_dir#$backup_pool_dir/}"
        target_sub_path="$target_pool_path/$sub_path"

        log_info "  Восстановление вложенной: $sub_path"

        # Создаем вложенную cgroup
        if create_cgroup "$target_sub_path"; then
            restore_configs "$backup_sub_dir" "$target_sub_path"
        fi
    done

    echo ""
done

# Читаем результаты из временных файлов
restored_pools=()
if [[ -s "$TEMP_RESTORED" ]]; then
    mapfile -t restored_pools < "$TEMP_RESTORED"
fi

failed_pools=()
if [[ -s "$TEMP_FAILED" ]]; then
    mapfile -t failed_pools < "$TEMP_FAILED"
fi

# Удаляем временные файлы
rm -f "$TEMP_RESTORED" "$TEMP_FAILED"

# Проверяем результаты восстановления
echo "=== РЕЗУЛЬТАТЫ ВОССТАНОВЛЕНИЯ ==="
echo ""

all_success=true

for pool_path in "${restored_pools[@]}"; do
    pool_name=$(basename "$pool_path")

    # Проверяем, существует ли директория в /sys/fs/cgroup/
    if [[ -d "$pool_path" ]]; then
        color_echo "$GREEN" "✓ УСПЕХ: Конфигурация восстановлена"
        echo "  Путь: $pool_path"

        # Проверяем наличие основных файлов конфигурации
        echo "  Проверка конфигурационных файлов:"

        # Проверяем различные возможные файлы конфигурации
        config_found=false

        for config_file in "cpu.max" "cpu.weight" "memory.max" "memory.high" "io.max" "pids.max"; do
            if [[ -f "$pool_path/$config_file" ]]; then
                value_data=$(cat "$pool_path/$config_file" 2>/dev/null || echo "не удалось прочитать")
                echo "    • $config_file: $value_data"
                config_found=true
            fi
        done

        if [[ "$config_found" == "false" ]]; then
            echo "    • (нет конфигурационных файлов или они нечитаемы)"
        fi

        echo ""
    else
        color_echo "$RED" "✗ ОШИБКА: Конфигурация НЕ восстановлена"
        echo "  Пул: $pool_name не найден в /sys/fs/cgroup/"
        echo ""
        all_success=false
    fi
done

# Отчет о неудачных попытках
if [[ ${#failed_pools[@]} -gt 0 ]]; then
    echo "=== НЕ УДАЛОСЬ ВОССТАНОВИТЬ ==="
    for failed_pool in "${failed_pools[@]}"; do
        color_echo "$RED" "✗ $failed_pool"
    done
    echo ""
    all_success=false
fi

# Итоговый статус
if $all_success && [[ ${#restored_pools[@]} -gt 0 ]]; then
    color_echo "$GREEN" "========================================="
    color_echo "$GREEN" "ВСЕ КОНФИГУРАЦИИ УСПЕШНО ВОССТАНОВЛЕНЫ!"
    color_echo "$GREEN" "========================================="
    echo ""
    echo "Восстановленные пути:"
    for pool_path in "${restored_pools[@]}"; do
        color_echo "$GREEN" "  • $pool_path"
    done
    echo ""
    echo "Проверка:"
    echo "  ls /sys/fs/cgroup/resource_pool*"
    ls -la /sys/fs/cgroup/resource_pool* 2>/dev/null || echo "  Нет восстановленных пулов"
    exit 0
else
    color_echo "$RED" "======================================"
    color_echo "$RED" "ВОССТАНОВЛЕНИЕ ЗАВЕРШИЛОСЬ С ОШИБКАМИ"
    color_echo "$RED" "======================================"
    echo ""
    echo "Успешно восстановлено: ${#restored_pools[@]} пулов"
    echo "Не удалось восстановить: ${#failed_pools[@]} пулов"

    if [[ ${#restored_pools[@]} -eq 0 ]]; then
        log_error "Не удалось восстановить ни одного resource_pool"
        echo ""
        echo "Возможные причины:"
        echo "1. Нет прав на запись в /sys/fs/cgroup/"
        echo "2. Не включены контроллеры cgroup в системе"
        echo "3. Бэкап не содержит resource_pool директорий"
        echo "4. Cgroup v2 не поддерживается системой"

        # Проверяем доступность cgroup
        if [[ ! -d "/sys/fs/cgroup" ]]; then
            echo "   • Директория /sys/fs/cgroup не существует"
        elif [[ ! -w "/sys/fs/cgroup" ]]; then
            echo "   • Нет прав на запись в /sys/fs/cgroup/"
            echo "   • Текущий пользователь: $(whoami)"
            echo "   • Права: $(ls -ld /sys/fs/cgroup)"
        fi

        # Проверяем контроллеры
        if [[ -f "/sys/fs/cgroup/cgroup.controllers" ]]; then
            echo "   • Доступные контроллеры: $(cat /sys/fs/cgroup/cgroup.controllers 2>/dev/null)"
        fi

        # Проверяем, есть ли файлы в бэкапе
        echo ""
        echo "Содержимое бэкапа:"
        find "$BACKUP_DIR" -type f -name "*.max" -o -name "*.weight" -o -name "*.high" | head -10
    fi

    exit 1
fi