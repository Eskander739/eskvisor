#!/bin/bash
# /usr/local/bin/save-cgroups.sh
# Автоматическое сохранение конфигураций cgroup для resource_pool*

set -euo pipefail

# Конфигурация
BACKUP_ROOT="/eskvisor/backups/cgroups"
DATE=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/var/log/eskvisor-cgroup-backup.log"

# Логирование
exec >> "$LOG_FILE" 2>&1
echo "=== Начало сохранения cgroup конфигурации для resource_pool*: $(date) ==="

# Создаем директорию для бэкапа
mkdir -p "$BACKUP_ROOT"

# Функция для проверки, является ли файл конфигурируемым
is_configurable_file() {
    local file="$1"
    local filename=$(basename "$file")

    # Исключаем файлы, которые не нужно сохранять
    case "$filename" in
        cgroup.procs|cgroup.threads|cgroup.events|cgroup.stat|cgroup.controllers|cgroup.type)
            return 1
            ;;
        *.stat|*.events|*.current|*.peak|*.pressure|pids.current|pids.peak)
            return 1
            ;;
        *)
            # Сохраняем конфигурируемые файлы
            [[ -f "$file" ]] && [[ -w "$file" ]] && return 0
            return 1
            ;;
    esac
}

# Функция для сохранения одной cgroup
save_cgroup() {
    local cgroup_path="$1"
    local pool_name=$(basename "$cgroup_path")
    local backup_path="$BACKUP_ROOT/$pool_name"

    # Создаем директорию в бэкапе для этого пула
    mkdir -p "$backup_path"

    # Сохраняем все конфигурируемые файлы
    for file in "$cgroup_path"/*; do
        if is_configurable_file "$file"; then
            local filename=$(basename "$file")
            # Сохраняем значение файла
            cat "$file" > "$backup_path/$filename" 2>/dev/null || true
        fi
    done

    echo "Сохранен: $pool_name"
}

# Основной цикл сохранения - ищем все resource_pool* директории
echo "Поиск пулов resource_pool*..."

# Находим все директории resource_pool* в корне cgroup
find /sys/fs/cgroup -maxdepth 1 -type d -name 'resource_pool*' | while read -r pool_path; do
    pool_name=$(basename "$pool_path")

    if [[ -d "$pool_path" ]]; then
        echo "Сохранение пула: $pool_name"

        # Сохраняем сам пул
        save_cgroup "$pool_path"

        # Сохраняем все дочерние cgroups рекурсивно
        find "$pool_path" -type d | while read -r cgroup_dir; do
            if [[ "$cgroup_dir" != "$pool_path" ]]; then
                local sub_path="${cgroup_dir#$pool_path/}"
                local backup_sub_path="$BACKUP_ROOT/$pool_name/$sub_path"

                # Создаем директорию в бэкапе
                mkdir -p "$backup_sub_path"

                # Сохраняем все конфигурируемые файлы
                for file in "$cgroup_dir"/*; do
                    if is_configurable_file "$file"; then
                        local filename=$(basename "$file")
                        cat "$file" > "$backup_sub_path/$filename" 2>/dev/null || true
                    fi
                done

                echo "Сохранен: $pool_name/$sub_path"
            fi
        done
    else
        echo "Пропуск: $pool_path не существует"
    fi
done

# Проверяем, были ли сохранены какие-либо пулы
if [[ -z "$(find "$BACKUP_ROOT" -maxdepth 1 -type d -name 'resource_pool*')" ]]; then
    echo "ВНИМАНИЕ: Не найдено ни одного пула resource_pool* для сохранения"
    echo "Проверьте наличие директорий в /sys/fs/cgroup/resource_pool*"
fi

# Создаем файл с метаинформацией о бэкапе
cat > "$BACKUP_ROOT/backup_manifest_${DATE}.json" << EOF
{
    "backup_date": "$(date -Iseconds)",
    "backup_timestamp": "$(date +%s)",
    "hostname": "$(hostname)",
    "kernel_version": "$(uname -r)",
    "cgroup_version": "v2",
    "resource_pools_found": $(find /sys/fs/cgroup -maxdepth 1 -type d -name 'resource_pool*' | wc -l),
    "pools_saved": $(find "$BACKUP_ROOT" -maxdepth 1 -type d -name 'resource_pool*' | wc -l),
    "total_cgroups": $(find "$BACKUP_ROOT" -type d -name '*resource_pool*' | wc -l)
}
EOF

echo "=== Сохранение завершено: $(date) ==="
echo "Бэкап сохранен в: $BACKUP_ROOT"
echo "Найдено пулов: $(find /sys/fs/cgroup -maxdepth 1 -type d -name 'resource_pool*' | wc -l)"
echo "Сохранено пулов: $(find "$BACKUP_ROOT" -maxdepth 1 -type d -name 'resource_pool*' | wc -l)"
echo "Лог: $LOG_FILE"

exit 0