import orjson

from agent.client.cli import CLIControl
from agent.client.hypervisor.libvirt.models.volume.group import VolumeGroup
from agent.client.logger_config import DefaultLogger


class VolumeGroupManager:
    """
    VG (Volume Group) - группа томов (объединяем физические тома (PV) в группу,
    создаём единый диск, который будем дальше разбивать так, как нам хочется)
    """

    def __init__(self):
        self.cli = CLIControl()
        self.logger = DefaultLogger("VolumeGroupManager")

    def delete_volume_group(self, volume_group_name: str, force: bool = True):
        cmd_args = ["vgremove"]
        if force:
            force_cmd_args = ["vgchange" " -an", volume_group_name]
            self.logger.info(
                f"Деактивация всех логических томов командой: {force_cmd_args}"
            )
            force_result = self.cli.execute(force_cmd_args)
            self.logger.info(f"Результат деактивации: {force_result}")
            cmd_args.append("--force")

        cmd_args.append(volume_group_name)
        self.logger.info(f"Удаление группы томов командой: {cmd_args}")
        result = self.cli.execute(cmd_args)
        self.logger.info(f"Результат удаления группы томов: {result}")
        return result

    def create_volume_group(self, pv_names: str | list[str], volume_group_name: str):
        if isinstance(pv_names, list):
            cmd_args = ["vgcreate", volume_group_name]
            for pv_name in pv_names:
                cmd_args.append(pv_name)
        elif isinstance(pv_names, str):
            cmd_args = ["vgcreate", volume_group_name, pv_names]
        else:
            raise ValueError(f"Некорректный тип данных: '{type(pv_names)}'")
        self.logger.info(f"Создание группы томов командой: {cmd_args}")
        result = self.cli.execute(cmd_args)
        self.logger.info(f"Результат создания группы томов: {result}")
        return result

    def delete_physical_volume_from_volume_group(
        self, pv_name: str, volume_group_name: str
    ):
        cmd_args = ["vgreduce", volume_group_name, pv_name]
        self.logger.info(
            f"Удаление физического тома {pv_name} из группы томов {volume_group_name} командой: {cmd_args}"
        )
        result = self.cli.execute(cmd_args)
        self.logger.info(f"Результат удаления группы томов: {result}")
        return result

    def add_physical_volume_from_volume_group(
        self, pv_name: str, volume_group_name: str
    ):
        cmd_args = ["vgextend", volume_group_name, pv_name]
        self.logger.info(
            f"Добавление физического тома {pv_name} в группу томов {volume_group_name} командой: {cmd_args}"
        )
        result = self.cli.execute(cmd_args)
        return result

    def edit_volume(self):
        raise NotImplementedError

    def get_volume_by_name(self, volume_group_name: str) -> VolumeGroup | None:
        self.logger.info(f"Получение группы томов: {volume_group_name}")
        cmd_args = [
            "vgs",
            volume_group_name,
            "--reportformat=json",
            "-o",
            "+vg_extent_size",
        ]
        result = self.cli.execute(cmd_args)
        if f'Volume group "{volume_group_name}" not found' in result or not result:
            self.logger.info(f"Группа томов не найдена: {volume_group_name}")
            return None
        self.logger.info(f"Группа томов найдена: {volume_group_name}")
        return self._parse_dict_to_models(orjson.loads(result)).pop()

    def get_volume_list(
        self,
        options: list[str] | None = None,
        noheadings: bool = False,
        separator: str | None = None,
        units: str | None = None,
        all: bool = True,
        unbuffered: bool = False,
        nosuffix: bool = False,
    ) -> list[VolumeGroup]:
        self.logger.info("Получение списка групп томов")
        cmd_args = ["vgs", "--reportformat=json", "-o", "+vg_extent_size"]

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
        vg_list = self._parse_dict_to_models(orjson.loads(result))
        if vg_list:
            self.logger.info("Получен список групп томов")
        else:
            self.logger.info("Получен пустой список групп томов")
        return vg_list

    @staticmethod
    def _parse_dict_to_models(output: dict) -> list[VolumeGroup]:
        result = output.get("report")[0].get("vg")
        physical_volumes_list = []

        for physical_volume in result:
            physical_volumes_list.append(
                VolumeGroup(
                    volume_name=physical_volume.get("vg_name"),
                    pv_count=physical_volume.get("pv_count"),
                    lv_count=physical_volume.get("lv_count"),
                    snap_count=physical_volume.get("snap_count"),
                    attributes=physical_volume.get("vg_attr"),
                    volume_size=physical_volume.get("vg_size"),
                    volume_free=physical_volume.get("vg_free"),
                    extent_size=physical_volume.get("vg_extent_size"),
                )
            )

        return physical_volumes_list


if __name__ == "__main__":
    manager = VolumeGroupManager()
    for pv in manager.get_volume_list():
        print("-" * 50)
        print("ИМЯ ГРУППЫ ТОМА: ", pv.volume_name)
        print("КОЛИЧЕСТВО ФИЗИЧЕСКИХ ТОМОВ: ", pv.pv_count)
        print("КОЛИЧЕСТВО ЛОГИЧЕСКИХ ТОМОВ: ", pv.lv_count)
        print("КОЛИЧЕСТВО СНАПШОТОВ: ", pv.snap_count)
        print("АТРИБУТЫ ГРУППЫ ТОМА: ", pv.attributes)
        print("РАЗМЕР ГРУППЫ ТОМА: ", pv.volume_size)
        print("СВОБОДНОЕ ПРОСТРАНСТВО ГРУППЫ ТОМА: ", pv.volume_free)
        print("РАЗМЕР БЛОКА ГРУППЫ ТОМА: ", pv.extent_size)
    # manager.add_physical_volume_from_volume_group("/dev/nvme0n1p5", "my_vg")
    # print(manager.delete_physical_volume_from_volume_group("/dev/nvme0n1p5", "eska_vg"))
