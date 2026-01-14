#!/bin/bash
# /usr/local/bin/setup.sh
# Установка и настройка системы управления cgroup

set -e

echo "=== Установка системы управления CGroup V2 ==="

# 1. Создаем директории
echo "Создание директорий..."
mkdir -p /cgroup/backups/cgroups
mkdir -p /usr/local/bin
mkdir -p /var/log

# 3. Копируем скрипты
echo "Копирование скриптов..."
cp save.sh /usr/local/bin/
cp restore.sh /usr/local/bin/
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