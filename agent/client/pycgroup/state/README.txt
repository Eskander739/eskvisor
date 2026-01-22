Примеры использования migrate.sh:

# 1. Базовая миграция
./migrate.sh user@remote-host

# 2. Миграция с указанием пользователя и порта
./migrate.sh -u admin -p 2222 remote-host

# 3. Тестовая миграция (без реальной передачи)
./migrate.sh -t remote-host

# 4. Синхронизация (удаление лишних файлов на целевом хосте)
./migrate.sh -s remote-host

# 5. Использование конфигурационного файла
./migrate.sh -c migrate.conf remote-host

# 6. Показать список доступных пулов
./migrate.sh -l