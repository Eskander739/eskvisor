#!/bin/bash
# /usr/local/bin/verify.sh
# Проверка состояния системы cgroup

echo "=== Проверка системы управления cgroup ==="
echo "Время: $(date)"
echo ""

# 1. Проверка сервисов
echo "1. Systemd сервисы:"
systemctl is-active cgroup-state.service >/dev/null 2>&1 && echo "  ✅ cgroup-state.service активен" || echo "  ❌ cgroup-state.service не активен"
systemctl is-active cgroup-state-timer.timer >/dev/null 2>&1 && echo "  ✅ cgroup-state-timer.timer активен" || echo "  ❌ cgroup-state-timer.timer не активен"

# 2. Проверка бэкапов
echo ""
echo "2. Бэкапы:"
if [[ -d "$latest_backup" ]]; then
    echo "  📊 Всего бэкапов: $(find /cgroup-state/backups/cgroups -maxdepth 1 -type d -name "2*" | wc -l)"
else
    echo "  ❌ Бэкапы не найдены"
fi

# 3. Проверка логов
echo ""
echo "3. Логи:"
if [[ -f "/var/log/cgroup-state-backup.log" ]]; then
    last_backup=$(tail -1 /var/log/cgroup-state-backup.log 2>/dev/null || echo "нет записей")
    echo "  📝 Последнее сохранение: $last_backup"
fi

if [[ -f "/var/log/cgroup-state.log" ]]; then
    last_restore=$(tail -1 /var/log/cgroup-state.log 2>/dev/null || echo "нет записей")
    echo "  📝 Последнее восстановление: $last_restore"
fi

# 4. Проверка пулов из конфига
echo ""
echo "4. Просмотр пулов из конфигурации:"
while IFS=':' read -r pool_name description; do
    [[ "$pool_name" =~ ^#.*$ ]] && continue
    [[ -z "$pool_name" ]] && continue

    pool_path="/sys/fs/cgroup/$pool_name"
    if [[ -d "$pool_path" ]]; then
        container_count=$(find "$pool_path" -type d -maxdepth 1 | tail -n +2 | wc -l)
        echo "  ✅ $pool_name: $description (контейнеров: $container_count)"
    else
        echo "  ⚠️  $pool_name: $description (не существует)"
    fi
done

echo ""
echo "=== Проверка завершена ==="