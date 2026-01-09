import threading
import time
from pathlib import Path


class EnhancedVirtualResourcePoolManager(VirtualResourcePoolManager):

    def __init__(self):
        super().__init__()
        self.memory_manager = VMMemoryManager()
        self.enforcement_thread = None
        self._start_enforcement_daemon()

    def apply_real_memory_limits(self, vm_uuid: str, memory_limit: int):
        """Применение реальных лимитов памяти к ВМ"""
        # Получаем PID процесса ВМ
        pid = self._get_vm_pid(vm_uuid)
        if not pid:
            self.logger.error(f"Cannot find PID for VM {vm_uuid}")
            return False

        # Применяем лимиты
        try:
            return self.memory_manager.apply_memory_limits_to_vm(
                vm_uuid, pid, memory_limit, lock_memory=True
            )
        except Exception as e:
            self.logger.error(f"Failed to apply memory limits to VM {vm_uuid}: {e}")
            return False

    def _get_vm_pid(self, vm_uuid: str) -> int | None:
        """Получение PID процесса ВМ"""
        try:
            # Для QEMU/KVM ищем процесс по UUID
            import psutil

            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmdline = " ".join(proc.info["cmdline"] or [])
                    if vm_uuid in cmdline and (
                        "qemu" in proc.info["name"].lower()
                        or "kvm" in proc.info["name"].lower()
                    ):
                        return proc.info["pid"]
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            self.logger.warning("psutil not installed, using alternative method")

            # Альтернативный метод через /proc
            for proc_dir in Path("/proc").glob("[0-9]*"):
                try:
                    cmdline_file = proc_dir / "cmdline"
                    if cmdline_file.exists():
                        cmdline = cmdline_file.read_text()
                        if vm_uuid in cmdline:
                            return int(proc_dir.name)
                except Exception:
                    continue

        return None

    def _start_enforcement_daemon(self):
        """Запуск демона для принудительного соблюдения лимитов"""

        def enforcement_loop():
            while True:
                try:
                    # Проверяем все ВМ во всех пулах
                    for pool in self.get_virtual_resource_pool_list():
                        if pool.vm_uuid_list:
                            for vm_uuid in pool.vm_uuid_list:
                                self.memory_manager.enforce_memory_limits(vm_uuid)

                    time.sleep(5)  # Проверка каждые 5 секунд
                except Exception as e:
                    self.logger.error(f"Error in enforcement daemon: {e}")
                    time.sleep(10)

        self.enforcement_thread = threading.Thread(
            target=enforcement_loop, name="memory-enforcement-daemon", daemon=True
        )
        self.enforcement_thread.start()
