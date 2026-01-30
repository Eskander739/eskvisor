#!/bin/bash
# /usr/local/bin/setup.sh
set -e

echo "=== Проверка поддержки cgroup v2 ядром ==="
if ! grep -q cgroup2 /proc/filesystems; then
    echo "ОШИБКА: CGroup V2 не поддерживается ядром системы" >&2
    exit 1
fi

echo "=== Установка CGroup V2 ==="
# Проверка, что cgroup2 еще не смонтирован
if mount | grep -q 'cgroup2 on'; then
    echo "CGroup V2 уже смонтирован"
else
    echo "=== Монтирование CGroup V2 ==="
    mount -t cgroup2 none /sys/fs/cgroup

    # Проверка успешности монтирования
    if [ $? -ne 0 ]; then
        echo "ОШИБКА: Не удалось смонтировать CGroup V2" >&2
        exit 1
    fi
fi

echo "=== Настройка контроллеров ==="
echo "+cpu +memory" > /sys/fs/cgroup/cgroup.subtree_control

if [ $? -ne 0 ]; then
    echo "ОШИБКА: Не удалось настроить контроллеры CGroup V2" >&2
    exit 1
fi

echo "=== CGroup V2 успешно настроен ==="

echo "=== Установка системы управления CGroup V2 ==="

# 1. Создаем директории
echo "Создание директорий..."
mkdir -p /cgroup/backups/cgroups
mkdir -p /usr/local/bin
mkdir -p /var/log

# 3. Копируем скрипты
echo "Копирование скриптов..."
cp /opt/eskvisor/agent/client/pycgroup/state/save.sh /usr/local/bin/
cp /opt/eskvisor/agent/client/pycgroup/state/restore.sh /usr/local/bin/
chmod 755 /usr/local/bin/*.sh

# 4. Копируем systemd сервисы
echo "Настройка systemd сервисов..."
cp cgroup-state.service /etc/systemd/system/
cp cgroup-state-timer.timer /etc/systemd/system/

echo "Состояние systemd cgroup-state сервисов: $(ls -d /etc/systemd/system/cgroup-state*)"
# 5. Включаем автозагрузку
echo "Включение автозагрузки..."
systemctl daemon-reload
systemctl enable cgroup-state.service
systemctl enable cgroup-state-timer.timer
systemctl start cgroup-state.service
systemctl start  cgroup-state-timer.timer

# 6. Проверяем
echo "Проверка установки..."
systemctl status cgroup-state.service --no-pager

echo "=== Установка завершена ==="
echo ""
echo "Команды управления:"
echo "  systemctl status cgroup-state.service  # статус сервиса"
echo "  systemctl start cgroup-state.service   # запуск сервиса"
echo "  systemctl stop cgroup-state.service    # остановка сервиса"
echo "  journalctl -u cgroup-state.service     # просмотр логов"
echo ""
echo "Ручное управление бэкапами:"
echo "  /usr/local/bin/save.sh        # сохранить сейчас"
echo "  /usr/local/bin/restore.sh     # восстановить все"
echo "  /usr/local/bin/restore.sh /cgroup/backups/cgroups/resource_pool  # восстановить конкретный"