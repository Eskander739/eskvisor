#!/bin/bash
# /usr/local/bin/eskvisor-cgroup-check.sh
# Проверка состояния системы cgroup

echo "=== Проверка системы управления cgroup ==="
echo "Время: $(date)"
echo ""

# 1. Проверка сервисов
echo "1. Systemd сервисы:"
systemctl is-active eskvisor-cgroup.service >/dev/null 2>&1 && echo "  ✅ eskvisor-cgroup.service активен" || echo "  ❌ eskvisor-cgroup.service не активен"
systemctl is-active eskvisor-cgroup-timer.timer >/dev/null 2>&1 && echo "  ✅ eskvisor-cgroup-timer.timer активен" || echo "  ❌ eskvisor-cgroup-timer.timer не активен"

# 2. Проверка бэкапов
echo ""
echo "2. Бэкапы:"
latest_backup=$(readlink -f /eskvisor/backups/cgroups/latest 2>/dev/null || echo "нет")
if [[ -d "$latest_backup" ]]; then
    echo "  ✅ Последний бэкап: $(basename "$latest_backup")"
    echo "  📊 Всего бэкапов: $(find /eskvisor/backups/cgroups -maxdepth 1 -type d -name "2*" | wc -l)"
else
    echo "  ❌ Бэкапы не найдены"
fi

# 3. Проверка логов
echo ""
echo "3. Логи:"
if [[ -f "/var/log/eskvisor-cgroup-backup.log" ]]; then
    last_backup=$(tail -1 /var/log/eskvisor-cgroup-backup.log 2>/dev/null || echo "нет записей")
    echo "  📝 Последнее сохранение: $last_backup"
fi

if [[ -f "/var/log/eskvisor-cgroup-restore.log" ]]; then
    last_restore=$(tail -1 /var/log/eskvisor-cgroup-restore.log 2>/dev/null || echo "нет записей")
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
done < /etc/eskvisor-cgroup.conf

echo ""
echo "=== Проверка завершена ==="