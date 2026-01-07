import os
import subprocess

from agent.client.cli import CLIControl
from agent.client.logger_config import DefaultLogger


class LVMStorageManager:
    """Менеджер для работы с LVM пулами"""

    def __init__(self, logger: DefaultLogger | None = None):
        self.logger = logger or DefaultLogger()
        self.cli = CLIControl()

    def check_lvm_support(self) -> bool:
        """Проверяет поддержку LVM в системе"""
        try:
            result = subprocess.run(["which", "lvm"], capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.error("LVM не установлен в системе")
                return False

            # Проверяем доступность lvm команд
            result = subprocess.run(["lvm", "version"], capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.debug(f"LVM доступен: {result.stdout.splitlines()[0]}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Ошибка проверки LVM: {e}")
            return False

    def list_volume_groups(self) -> list[str]:
        """Возвращает список доступных Volume Groups"""
        try:
            result = subprocess.run(
                ["vgs", "--noheadings", "-o", "vg_name"], capture_output=True, text=True
            )

            if result.returncode == 0:
                vgs = [
                    vg.strip()
                    for vg in result.stdout.strip().splitlines()
                    if vg.strip()
                ]
                self.logger.debug(f"Найдены VGs: {vgs}")
                return vgs
            return []
        except Exception as e:
            self.logger.error(f"Ошибка получения списка VGs: {e}")
            return []

    def get_vg_info(self, vg_name: str) -> dict[str, object]:
        """Получает информацию о Volume Group"""
        try:
            result = subprocess.run(
                [
                    "vgs",
                    vg_name,
                    "--units",
                    "b",
                    "--nosuffix",
                    "--noheadings",
                    "-o",
                    "vg_size,vg_free,vg_extent_size,vg_uuid",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return {}

            parts = result.stdout.strip().split()
            if len(parts) >= 4:
                return {
                    "size_bytes": int(float(parts[0])),
                    "free_bytes": int(float(parts[1])),
                    "extent_size": int(parts[2]),
                    "uuid": parts[3],
                }
            return {}
        except Exception as e:
            self.logger.error(f"Ошибка получения информации о VG {vg_name}: {e}")
            return {}

    def create_volume_group(self, vg_name: str, device_path: str) -> bool:
        """
        Создает новый Volume Group

        Args:
            vg_name: Имя Volume Group
            device_path: Путь к физическому устройству (например, /dev/sdb)

        Returns:
            bool: Успешность операции
        """
        try:
            # Проверяем существование устройства
            if not os.path.exists(device_path):
                self.logger.error(f"Устройство {device_path} не найдено")
                return False

            # Проверяем, занято ли устройство
            device = self.cli.execute([f"zramctl {device_path}"])
            if device_path in device and "SWAP" in device:
                raise ValueError(f"Устройство уже занято: {device}")
            # Создаем физический том

            pv_create = subprocess.run(
                ["pvcreate", device_path], capture_output=True, text=True
            )
            print(f"pvcreate {device_path}")
            if pv_create.returncode != 0:
                self.logger.error(
                    f"Ошибка создания физического тома: {pv_create.stderr}"
                )
                return False

            # Создаем Volume Group
            vg_create = subprocess.run(
                ["vgcreate", vg_name, device_path], capture_output=True, text=True
            )

            if vg_create.returncode == 0:
                self.logger.info(
                    f"Создан Volume Group {vg_name} на устройстве {device_path}"
                )
                return True
            else:
                self.logger.error(f"Ошибка создания Volume Group: {vg_create.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Ошибка создания VG {vg_name}: {e}")
            return False

    def remove_volume_group(self, vg_name: str) -> bool:
        """Удаляет Volume Group"""
        try:
            result = subprocess.run(
                ["vgremove", "-f", vg_name], capture_output=True, text=True
            )

            if result.returncode == 0:
                self.logger.info(f"Удален Volume Group {vg_name}")
                return True
            else:
                self.logger.error(f"Ошибка удаления VG {vg_name}: {result.stderr}")
                return False
        except Exception as e:
            self.logger.error(f"Ошибка удаления VG {vg_name}: {e}")
            return False

    def create_lvm_pool(self, vg_name: str, pool_name: str | None = None) -> bool:
        """
        Создает LVM пул в существующем Volume Group

        Args:
            vg_name: Имя Volume Group
            pool_name: Имя пула (опционально, по умолчанию совпадает с vg_name)

        Returns:
            bool: Успешность операции
        """
        try:
            if not pool_name:
                pool_name = vg_name

            # Проверяем существование VG
            vgs = self.list_volume_groups()
            if vg_name not in vgs:
                self.logger.error(f"Volume Group {vg_name} не найден")
                return False

            self.logger.info(
                f"Используется существующий Volume Group {vg_name} для пула {pool_name}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Ошибка создания LVM пула: {e}")
            return False

    def get_lvm_volumes(self, vg_name: str) -> list[dict[str, object]]:
        """Получает список логических томов в VG"""
        try:
            result = subprocess.run(
                [
                    "lvs",
                    vg_name,
                    "--noheadings",
                    "--units",
                    "b",
                    "--nosuffix",
                    "-o",
                    "lv_name,lv_size,lv_uuid",
                ],
                capture_output=True,
                text=True,
            )

            volumes = []
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        volumes.append(
                            {
                                "name": parts[0],
                                "size_bytes": int(float(parts[1])),
                                "uuid": parts[2],
                            }
                        )

            return volumes
        except Exception as e:
            self.logger.error(f"Ошибка получения списка LV в VG {vg_name}: {e}")
            return []
