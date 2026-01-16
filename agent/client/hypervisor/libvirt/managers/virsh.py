import queue
import sys
import threading
import time

import pexpect

from agent.client.logger_config import logger


class VirshConsoleController:
    def __init__(self, vm_name):
        """
        Контроллер для управления ВМ через virsh console с активацией Ctrl+D

        Args:
            vm_name: имя виртуальной машины
        """
        self.vm_name = vm_name
        self.child = None
        self.connected = False
        self.command_queue = queue.Queue()
        self.response_queue = queue.Queue()
        self.reader_thread = None
        self.writer_thread = None
        self.running = False
        self.echo_enabled = True  # Флаг для управления выводом

    def connect(self, timeout=30):
        """
        Подключение к консоли ВМ с активацией через Ctrl+D

        Returns:
            bool: True если подключение успешно, False в противном случае
        """
        logger.info(f"Подключаюсь к ВМ: {self.vm_name}")

        try:
            # Запускаем virsh console
            self.child = pexpect.spawn(
                f"virsh --connect qemu:///system console {self.vm_name}",
                timeout=timeout,
            )
            # self.child.logfile = sys.stdout.buffer

            # Ждем приветственного сообщения
            try:
                self.child.expect(
                    ["Escape character", "connected to domain"], timeout=10
                )
                logger.info("Соединение с консолью установлено")
            except pexpect.TIMEOUT:
                logger.warning("Таймаут ожидания приветствия, продолжаем...")

            # Активируем консоль через Ctrl+D
            logger.info("Активирую консоль (Ctrl+D)...")
            self.child.send("\x04")  # Ctrl+D
            time.sleep(1)

            # Нажимаем Enter для гарантии
            self.child.sendline("")
            time.sleep(0.5)

            # Проверяем активацию
            try:
                self.child.expect(
                    ["login:", "Login:", "$", "#", ":", "~#", "~$"], timeout=3
                )
                logger.info("Консоль активирована")
                self.connected = True

                # Запускаем потоки для чтения/записи
                self.running = True
                self._start_io_threads()

                return True

            except pexpect.TIMEOUT:
                logger.warning("Консоль не ответила, пробую еще раз...")
                # Вторая попытка
                self.child.send("\x04")
                time.sleep(1)
                self.child.sendline("\n\n")
                time.sleep(1)

                try:
                    self.child.expect([":", "$", "#"], timeout=2)
                    logger.info("Консоль активирована на второй попытке")
                    self.connected = True
                    self._start_io_threads()
                    return True
                except BaseException:
                    logger.error("Не удалось активировать консоль")
                    return False

        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
            return False

    def _start_io_threads(self):
        """Запуск потоков для чтения и записи"""
        # Поток для чтения вывода
        self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self.reader_thread.start()

        # Поток для отправки команд
        self.writer_thread = threading.Thread(target=self._write_commands, daemon=True)
        self.writer_thread.start()

    def _read_output(self):
        """Поток для чтения вывода из консоли"""
        while self.running and self.child:
            try:
                # Читаем доступные данные
                if self.child.isalive():
                    try:
                        # Пробуем прочитать данные
                        index = self.child.expect(
                            ["\n", "\r", pexpect.TIMEOUT], timeout=0.1
                        )

                        if index != 2:  # Не таймаут
                            # Получаем вывод до совпадения
                            before = self.child.before.decode("utf-8", errors="ignore")
                            after = self.child.after.decode("utf-8", errors="ignore")

                            # Объединяем данные
                            data = before + after

                            if data:
                                # Очищаем данные от возможных эхо-копий команд
                                cleaned_data = self._clean_output(data)

                                if cleaned_data:
                                    # Помещаем в очередь для обработки
                                    self.response_queue.put(("output", cleaned_data))

                                    # Выводим только если включен вывод
                                    if self.echo_enabled:
                                        sys.stdout.write(cleaned_data)
                                        sys.stdout.flush()
                    except pexpect.TIMEOUT:
                        pass
                    except pexpect.EOF:
                        logger.error("Конец потока (EOF)")
                        self.running = False
                        break
                else:
                    logger.error("Процесс virsh завершился")
                    self.running = False
                    break

            except Exception as e:
                logger.warning(f"Ошибка чтения: {e}")
                time.sleep(0.1)

    def _clean_output(self, data):
        """Очистка вывода от эхо-копий команд и управляющих символов"""
        # Удаляем управляющие последовательности ANSI
        import re

        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        data = ansi_escape.sub("", data)

        # Удаляем возврат каретки
        data = data.replace("\r", "")

        return data

    def _write_commands(self):
        """Поток для отправки команд в консоль"""
        while self.running:
            try:
                # Ждем команды из очереди
                cmd_type, data = self.command_queue.get(timeout=0.1)

                if cmd_type == "command" and self.child and self.child.isalive():
                    # Временно отключаем вывод перед отправкой команды
                    old_echo = self.echo_enabled
                    self.echo_enabled = False

                    # Отправляем команду
                    self.child.sendline(data)

                    # Включаем вывод обратно
                    self.echo_enabled = old_echo

                    # Ждем небольшое время для выполнения
                    time.sleep(0.5)

                elif cmd_type == "special":
                    # Отправка специальных символов
                    if data == "ctrl_d":
                        self.child.send("\x04")
                    elif data == "enter":
                        self.child.send("\n")
                    elif data == "ctrl_c":
                        self.child.send("\x03")

                self.command_queue.task_done()

            except queue.Empty:
                # Очередь пуста, продолжаем
                continue
            except Exception as e:
                logger.warning(f"Ошибка отправки: {e}")

    def send_command(self, command, wait_for_response=True, timeout=5):
        """
        Отправка команды в консоль ВМ

        Args:
            command: команда для выполнения
            wait_for_response: ждать ли ответа
            timeout: время ожидания ответа (секунды)

        Returns:
            str: вывод команды или None
        """
        if not self.connected:
            logger.error("Не подключено к консоли")
            return None

        # Очищаем очередь ответов
        while not self.response_queue.empty():
            self.response_queue.get()

        # Выводим приглашение команды (но не саму команду)
        if self.echo_enabled:
            sys.stdout.write("\n[>] ")
            sys.stdout.flush()

        # Отправляем команду
        self.command_queue.put(("command", command))
        if wait_for_response:
            output = ""
            start_time = time.time()
            response_started = False

            while time.time() - start_time < timeout:
                try:
                    # Пытаемся получить ответ
                    resp_type, data = self.response_queue.get(timeout=0.1)
                    if resp_type == "output":
                        # Игнорируем эхо команды (если есть)
                        if not response_started and command in data:
                            data = data.replace(command, "", 1)

                        if data.strip():
                            # response_started = True
                            output += data

                except queue.Empty:
                    continue
            return output
        else:
            return "Команда отправлена"

    def activate_console(self):
        """Повторная активация консоли через Ctrl+D"""
        if self.connected and self.child:
            if self.echo_enabled:
                logger.info("Повторная активация консоли (Ctrl+D)...")
            self.command_queue.put(("special", "ctrl_d"))
            time.sleep(1)
            self.command_queue.put(("special", "enter"))
            return True
        return False

    def press_enter(self):
        """Нажатие Enter"""
        if self.connected and self.child:
            self.command_queue.put(("special", "enter"))
            return True
        return False

    def send_ctrl_c(self):
        """Отправка Ctrl+C"""
        if self.connected and self.child:
            self.command_queue.put(("special", "ctrl_c"))
            return True
        return False

    def interactive_control(self):
        """
        Интерактивное управление ВМ без выхода из консоли
        Показывает только вывод от ВМ, скрывая ввод пользователя
        """
        if not self.connected:
            logger.error("Сначала подключитесь к консоли")
            return

        try:
            while self.running:
                # Читаем ввод пользователя (не показываем его)
                try:
                    user_input = input("").strip()

                    if not user_input:
                        continue

                    # Обработка специальных команд
                    if user_input.startswith(":"):
                        cmd = user_input[1:].lower()

                        if cmd == "exit":
                            logger.info("Выход из интерактивного режима")
                            logger.info("Консоль остается подключенной")
                            break

                        elif cmd == "activate":
                            self.activate_console()

                        elif cmd == "enter":
                            self.press_enter()

                        elif cmd == "ctrl+c":
                            self.send_ctrl_c()

                        else:
                            logger.warning(f"Неизвестная команда: {cmd}")

                    else:
                        # Обычная команда для ВМ
                        self.send_command(
                            user_input, wait_for_response=True, timeout=10
                        )

                except EOFError:
                    logger.warning("Конец ввода (EOF)")
                    break
                except KeyboardInterrupt:
                    logger.warning("Прервано пользователем, отправляю Ctrl+C...")
                    self.send_ctrl_c()

        except Exception as e:
            logger.error(f"Ошибка: {e}")

    def execute_commands(self, commands):
        """
        Выполнение списка команд

        Args:
            commands: список команд для выполнения

        Returns:
            dict: результаты выполнения команд
        """
        all_results = []

        for cmd in commands:
            if self.echo_enabled:
                logger.info(f"Выполняю: {cmd}")
            command_result = self.send_command(cmd, wait_for_response=True, timeout=10)
            all_results.append(command_result)

            # Не выводим результат повторно, так как он уже показан
            if not command_result:
                if self.echo_enabled:
                    logger.warning("Нет ответа")

            # Пауза между командами
            time.sleep(1)

        return all_results

    def monitor_console(self, duration=60):
        """
        Мониторинг вывода консоли в течение указанного времени

        Args:
            duration: длительность мониторинга в секундах
        """
        if not self.connected:
            logger.error("Не подключено")
            return

        logger.info(f"Начинаю мониторинг на {duration} секунд...")
        logger.info("Нажмите Ctrl+C для остановки")

        start_time = time.time()
        output_buffer = ""

        try:
            while time.time() - start_time < duration and self.running:
                # Проверяем наличие новых данных
                try:
                    resp_type, data = self.response_queue.get(timeout=0.5)
                    if resp_type == "output":
                        output_buffer += data
                        # Выводим в реальном времени
                        if self.echo_enabled:
                            sys.stdout.write(data)
                            sys.stdout.flush()
                except queue.Empty:
                    continue

        except KeyboardInterrupt:
            logger.info("Мониторинг остановлен пользователем")

        logger.info("Мониторинг завершен")
        logger.info(f"Всего получено данных: {len(output_buffer)} символов")

        return output_buffer

    def disconnect(self):
        """
        Корректное отключение от консоли
        """
        logger.info("Отключаюсь от консоли...")

        self.running = False

        # Останавливаем потоки
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=2)

        if self.writer_thread and self.writer_thread.is_alive():
            self.writer_thread.join(timeout=2)

        # Закрываем соединение
        if self.child:
            try:
                # Отправляем Ctrl+] для выхода из virsh console
                self.child.send("\x1d")
                time.sleep(0.5)
                self.child.close()
            except BaseException:
                pass
            self.child = None

        self.connected = False
        logger.info("Отключено")


# Пример использования
if __name__ == "__main__":
    # Создание контроллера
    virsh_console = VirshConsoleController("VM-TEST-31353")

    virsh_console.connect()
    results = virsh_console.execute_commands(
        ["root", "cd /", "mkdir hello_eskvisor", "ls"]
    )
    for result in results:
        print(result)
