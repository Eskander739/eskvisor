import json
import os
import re

from agent.client.cli import CLIControl
from agent.client.hypervisor.libvirt.models.volume.logic_volume import (
    LogicalVolumeSizeType,
    LogicVolume,
)
from agent.client.logger_config import DefaultLogger


class LogicalVolumeManager:
    """
    LV (Logical Volume) - логические разделы, собственно раздел нашего нового «единого диска» ака Группы Томов,
    который мы потом форматируем и используем как обычный раздел, обычного жёсткого диска.
    """

    def __init__(self):
        self.cli = CLIControl()
        self.logger = DefaultLogger("LogicalVolumeManager")

    def create_volume(
        self,
        logic_volume_name: str,
        logic_volume_size: int | float,
        volume_group_name: str,
        logic_volume_size_type: LogicalVolumeSizeType = LogicalVolumeSizeType.GB,
        thin_pool: bool = True,  # для ресурса пулов(можно внутри такого logic volume создавать другие logic volume)
    ):

        logic_volume_path = f"/dev/{volume_group_name}/{logic_volume_name}"
        if os.path.exists(logic_volume_path):
            self.logger.info(f"Логический том уже существует: {logic_volume_path}")
            return f'Logical volume "{logic_volume_name}" created(logic volume exists)'
        cmd_args = [
            "lvcreate",
            "-y",
            "-n",
            logic_volume_name,  # Имя создаваемого LV
            "-L",
            f"{str(logic_volume_size)}{logic_volume_size_type.value}",  # Размер создаваемого LV и тип размера создаваемого LV
            volume_group_name,  # Имя группы томов, в которой создаем LV
        ]
        if thin_pool:
            cmd_args.append("--thin")
        self.logger.info(f"Создание логического тома командой: {cmd_args}")

        result = self.cli.execute(cmd_args)
        self.logger.info(f"Результат создания логического тома: {result}")
        return result

    def delete_logical_volume(
        self,
        logic_volume_name: str,
        volume_group_name: str,
        delete_used_logic_volume: bool = True,
    ):
        if not delete_used_logic_volume:
            """
            Удалить без подтверждения
            """
            self.logger.info(
                f"Удаление логического тома {volume_group_name}/{logic_volume_name} без подтверждения"
            )
            cmd_args = ["lvremove", "-y", f"{volume_group_name}/{logic_volume_name}"]
        else:
            """
            Принудительное удаление и без подтверждения (даже если используется)
            """
            self.logger.info(
                f"Удаление логического тома {volume_group_name}/{logic_volume_name} без подтверждения "
                "и даже при использовании"
            )
            cmd_args = [
                "lvremove",
                "-f",
                "-y",
                f"{volume_group_name}/{logic_volume_name}",
            ]
        result = self.cli.execute(cmd_args)
        self.logger.info(f"Результат удаления логического тома: {result}")
        return result

    def mass_delete_volume(
        self,
        logic_volume_names: list[str],
        volume_group_name: str,
        delete_used_logic_volume: bool = True,
    ):
        if not delete_used_logic_volume:
            """
            Удалить без подтверждения
            """
            self.logger.info(
                f"Массовое удаление логических томов {volume_group_name}/{logic_volume_names} без подтверждения"
            )
            cmd_args = ["lvremove", "-y"]
            for logic_volume_name in logic_volume_names:
                cmd_args.append(f" {volume_group_name}/{logic_volume_name}")
        else:
            """
            Принудительное удаление и без подтверждения (даже если используется)
            """
            self.logger.info(
                f"Массовое удаление логических томов {volume_group_name}/{logic_volume_names} без подтверждения "
                "и даже при использовании"
            )
            cmd_args = ["lvremove", "-f", "-y"]
            for logic_volume_name in logic_volume_names:
                cmd_args.append(f" {volume_group_name}/{logic_volume_name}")
        result = self.cli.execute(cmd_args)
        return result

    def delete_all_volume(self, volume_group_name: str):
        # Удалить все LV в VG (осторожно!)
        self.logger.info(
            f"Удаление всех логических томов {volume_group_name} без подтверждения и даже при использовании"
        )
        cmd_args = ["lvremove", "-f", "-y", volume_group_name]
        result = self.cli.execute(cmd_args)
        return result

    def edit_volume(
        self,
        logic_volume_name: str,
        volume_group_name: str,
        logic_volume_size: int | float,
        logic_volume_size_type: LogicalVolumeSizeType = LogicalVolumeSizeType.GB,
        thin_pool: bool = True,
    ):
        current_lv = self.get_volume_by_name(logic_volume_name, volume_group_name)
        if current_lv is None:
            return False
        self.logger.info(
            f"Расширение размера логического тома {logic_volume_name} на {logic_volume_size} {logic_volume_size_type.name}"
        )
        cmd_args = [
            "lvextend",
            "-L",
            f"+{str(logic_volume_size)}{logic_volume_size_type.value}",  # Размер создаваемого LV и тип размера создаваемого LV,
        ]
        if thin_pool:
            meta_size = max(logic_volume_size * 0.01, 512 * 1024 * 64)
            cmd_args.append("--poolmetadatasize")
            cmd_args.append(f"+{meta_size}B")
        cmd_args.append(f"{volume_group_name}/{logic_volume_name}")
        result = self.cli.execute(cmd_args)
        return result

    def get_volume_by_name(
        self, logic_volume_name: str, volume_group_name: str
    ) -> LogicVolume | None:
        self.logger.info(
            f"Получение логического тома {volume_group_name}/{logic_volume_name}"
        )
        cmd_args = [
            "lvs",
            f"{volume_group_name}/{logic_volume_name}",
            "--reportformat=json",
        ]

        result = self.cli.execute(cmd_args)
        if "Failed to find logical volume" in result:
            return None
        volume = self._parse_dict_to_models(json.loads(result))
        if volume:
            return volume.pop()
        return None

    def get_volume_list(
        self,
        options: list[str] | None = None,
        noheadings: bool = False,
        separator: str | None = None,
        units: str | None = None,
        all: bool = True,
        unbuffered: bool = False,
        nosuffix: bool = False,
    ) -> list[LogicVolume]:
        self.logger.info("Получение списка логических томов")
        cmd_args = ["lvs", "--reportformat=json"]

        if noheadings:
            cmd_args.append("--noheadings")

        if separator:
            cmd_args.extend(["--separator", separator])

        if units:
            cmd_args.extend(["--units", units])

        if all:
            cmd_args.append("--all")

        if unbuffered:
            cmd_args.append("--unbuffered")

        if nosuffix:
            cmd_args.append("--nosuffix")

        # Добавляем пользовательские опции
        if options:
            cmd_args.extend(options)
        result = self.cli.execute(cmd_args)
        return self._parse_dict_to_models(json.loads(result))

    def _parse_dict_to_models(self, output: dict) -> list[LogicVolume]:
        result = output.get("report")[0].get("lv")
        logic_volumes_list = []

        for logic_volume in result:
            volume_size = self.convert_storage_size_to_bytes(
                logic_volume.get("lv_size")
            )
            data_percent = logic_volume.get("data_percent")
            used_volume_size = (
                volume_size * float(data_percent.replace(",", ".")) / 100
                if data_percent
                else 0
            )
            logic_volumes_list.append(
                LogicVolume(
                    logic_volume_name=logic_volume.get("lv_name"),
                    volume_group_name=logic_volume.get("vg_name"),
                    attributes=logic_volume.get("lv_attr"),
                    volume_size=self.convert_storage_size_to_bytes(
                        logic_volume.get("lv_size")
                    ),
                    available_volume_size=volume_size - used_volume_size,
                    logic_volume_pool=logic_volume.get("pool_lv"),
                    is_snapshot=logic_volume.get("origin"),
                    data_percent=data_percent,
                    metadata_percent=logic_volume.get("metadata_percent"),
                    move_physical_volume=logic_volume.get("move_pv"),
                    mirror_logic=logic_volume.get("mirror_log"),
                    copy_percent=logic_volume.get("copy_percent"),
                    convert_logic_volume=logic_volume.get("convert_lv"),
                )
            )

        return logic_volumes_list

    def convert_storage_size_to_bytes(self, size_str: str) -> int:
        """
        Конвертирует строку с размером хранилища в байты

        Поддерживает форматы:
        - "1.5G" → 1610612736 байт
        - "1,00g" → 1073741824 байт
        - "500M" → 524288000 байт
        - "2T" → 2199023255552 байт
        - "1024K" → 1048576 байт
        - "512" → 512 байт (по умолчанию)

        Args:
            size_str: строка с размером (может содержать запятую или точку как разделитель)

        Returns:
            int: размер в байтах
        """
        # Приводим к нижнему регистру и убираем пробелы
        size_str = size_str.strip().lower()

        if not size_str:
            raise ValueError("Пустая строка размера")

        # Заменяем запятую на точку для корректного парсинга
        size_str = size_str.replace(",", ".")

        # Регулярное выражение для разбора
        pattern = r"^(\d+(?:\.\d+)?)\s*([tgmkb]?)b?$"
        match = re.match(pattern, size_str)

        if not match:
            raise ValueError(f"Некорректный формат размера: '{size_str}'")

        number_str, unit = match.groups()

        # Конвертируем число
        try:
            number = float(number_str)
        except ValueError:
            raise ValueError(f"Некорректное число: '{number_str}'")

        # Множители (в байтах)
        multipliers = {
            "t": 1024**4,  # терабайт
            "g": 1024**3,  # гигабайт
            "m": 1024**2,  # мегабайт
            "k": 1024**1,  # килобайт
            "": 1,  # байт (по умолчанию)
        }

        multiplier = multipliers.get(unit, 1)

        # Вычисляем размер в байтах
        bytes_size = int(number * multiplier)

        return bytes_size


if __name__ == "__main__":
    manager = LogicalVolumeManager()
    # manager.create_volume("ESKA", 1.5, "vg_eskvisor_01")
    manager.delete_all_volume("vg_eskvisor_01")
    for pv in manager.get_volume_list():
        print("-" * 50)
        print("ИМЯ ЛОГИЧЕСКОГО ТОМА: ", pv.logic_volume_name)
        print("ИМЯ ГРУППЫ ТОМА: ", pv.volume_group_name)
        print("АТРИБУТЫ ТОМА: ", pv.attributes)
        print("РАЗМЕР ЛОГИЧЕСКОГО ТОМА В БАЙТАХ: ", pv.volume_size)
        print("РАЗМЕР ЛОГИЧЕСКОГО ТОМА В ГБ: ", pv.volume_size_gb)
        print(
            "ДОСТУПНОЕ ПРОСТРАНСТВО ЛОГИЧЕСКОГО ТОМА В БАЙТАХ: ",
            pv.available_volume_size,
        )
        print(
            "ДОСТУПНОЕ ПРОСТРАНСТВО ЛОГИЧЕСКОГО ТОМА В ГБ: ",
            pv.available_volume_size_gb,
        )
        print("ЯВЛЯЕТСЯ ЛИ ТОМ СНАПШОТОМ: ", bool(pv.is_snapshot))
        print("ПРОЦЕНТ ИСПОЛЬЗОВАНИЯ ДАННЫХ: ", pv.data_percent)
        print("ПРОЦЕНТ ИСПОЛЬЗОВАНИЯ МЕТАДАННЫХ: ", pv.metadata_percent)
