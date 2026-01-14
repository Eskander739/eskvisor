#!/bin/bash
# /usr/local/bin/cgroup-setup.sh
# Установка и настройка системы управления cgroup

set -e

echo "=== Установка системы управления cgroup для EskVisor ==="

# 1. Создаем директории
echo "Создание директорий..."
mkdir -p /eskvisor/backups/cgroups
mkdir -p /usr/local/bin
mkdir -p /var/log

# 2. Копируем конфигурационные файлы
echo "Копирование конфигурации..."
cp eskvisor-cgroup.conf /etc/
chmod 644 /etc/eskvisor-cgroup.conf

# 3. Копируем скрипты
echo "Копирование скриптов..."
cp save-cgroups.sh /usr/local/bin/
cp restore-cgroups.sh /usr/local/bin/
chmod 755 /usr/local/bin/*.sh

# 4. Копируем systemd сервисы
echo "Настройка systemd сервисов..."
cp eskvisor-cgroup.service /etc/systemd/system/
cp eskvisor-cgroup-timer.timer /etc/systemd/system/

echo "Состояние systemd eskvisor сервисов: $(ls -d /etc/systemd/system/eskvisor*)"
# 5. Включаем автозагрузку
echo "Включение автозагрузки..."
systemctl daemon-reload
systemctl enable eskvisor-cgroup.service
systemctl enable eskvisor-cgroup-timer.timer
systemctl start eskvisor-cgroup.service
systemctl start eskvisor-cgroup-timer.timer

# 6. Проверяем
echo "Проверка установки..."
systemctl status eskvisor-cgroup.service --no-pager

echo "=== Установка завершена ==="
echo ""
echo "Команды управления:"
echo "  systemctl status eskvisor-cgroup.service  # статус сервиса"
echo "  systemctl start eskvisor-cgroup.service   # запуск сервиса"
echo "  systemctl stop eskvisor-cgroup.service    # остановка сервиса"
echo "  journalctl -u eskvisor-cgroup.service     # просмотр логов"
echo ""
echo "Ручное управление бэкапами:"
echo "  /usr/local/bin/eskvisor-save-cgroups.sh        # сохранить сейчас"
echo "  /usr/local/bin/eskvisor-restore-cgroups.sh     # восстановить все"
echo "  /usr/local/bin/eskvisor-restore-cgroups.sh /eskvisor/backups/cgroups/resource_pool  # восстановить конкретный"