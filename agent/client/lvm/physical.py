import orjson

from agent.client.cli import CLIControl
from agent.client.hypervisor.libvirt.models.volume.physical import PhysicalVolume
from agent.client.logger_config import DefaultLogger


class PhysicalVolumeManager:
    """
    PV (Physical Volume) - физические тома (это могут быть разделы или целые «неразбитые» диски)
    """

    def __init__(self):
        self.cli = CLIControl()
        self.logger = DefaultLogger("PhysicalVolumeManager")

    def create_volume(self, physical_volume_path: str):
        """
        Создание физического тома
        """

        cmd_args = ["pvcreate", physical_volume_path]
        # Выполняем команду
        self.logger.info(f"Создание физического тома командой: {cmd_args}")
        result = self.cli.execute(cmd_args)
        return result

    def valid_physical_volumes(self) -> list[str]:
        current_volumes = self.get_volume_list()
        valid_physical_volumes = []
        for current_volume in current_volumes:
            cmd_mountpoint_args = [
                "lsblk",
                current_volume.physical_name,
                "--output=MOUNTPOINTS",
            ]
            mountpoint = self.cli.execute(cmd_mountpoint_args)
            for protected_path in self.protected_volumes:
                if protected_path in mountpoint:
                    break
            else:
                valid_physical_volumes.append(current_volume.physical_name)

        return valid_physical_volumes

    @property
    def protected_volumes(self):
        return ["/boot/efi", "/home", "/", "/boot", "[SWAP]"]

    def delete_physical_volume(self, pv_name: str):
        cmd_mountpoint_args = ["lsblk", "/dev/nvme0n1p2", "--output=MOUNTPOINTS"]
        mountpoint = self.cli.execute(cmd_mountpoint_args)
        for protected_path in self.protected_volumes:
            if protected_path in mountpoint:
                raise ValueError(f"Запрещено удаление системных томов: '{pv_name}'")
        physical_volume = self.get_physical_volume_by_name(pv_name)
        if physical_volume.volume_name is not None and physical_volume.volume_name:
            raise ValueError("Требуется удаление тома из группы томов")

        cmd_args = ["pvremove", pv_name]
        self.logger.info(f"Удаление физического тома командой: {cmd_args}")
        result = self.cli.execute(cmd_args)
        self.logger.info(f"Результат удаления физического тома: {result}")
        return result

    def edit_volume(self):
        raise NotImplementedError

    def get_physical_volume_by_name(self, pv_name: str) -> PhysicalVolume:
        """
        Получение физического тома
        """
        self.logger.info(f"Получение физического тома: {pv_name}")
        cmd_args = ["pvs", pv_name, "--reportformat=json"]
        # Выполняем команду
        result = self.cli.execute(cmd_args)
        return self._parse_dict_to_models(orjson.loads(result)).pop()

    def get_volume_list(
        self,
        pv_name: str | None = None,
        vg_name: str | None = None,
        options: list[str] | None = None,
        verbose: bool = False,
        noheadings: bool = False,
        separator: str | None = None,
        units: str | None = None,
        aligned: bool = False,
        all: bool = False,
        unbuffered: bool = False,
        nosuffix: bool = False,
    ) -> list[PhysicalVolume]:
        """
        Получить список физических томов (PV) с фильтрами и опциями.

        Args:
            pv_name: Имя конкретного PV для фильтрации
            vg_name: Имя группы томов для фильтрации
            options: Дополнительные опции pvs в виде списка
            verbose: Подробный вывод (-v)
            noheadings: Не выводить заголовки (-o)
            separator: Разделитель полей (--separator)
            units: Единицы измерения (--units)
            aligned: Выровнять столбцы (--aligned)
            all: Показать все PV, включая внутренние (--all)
            unbuffered: Небуферизованный вывод (--unbuffered)
            nosuffix: Не показывать суффиксы единиц (--nosuffix)

        Returns:
            Вывод команды pvs
        """
        self.logger.info("Получение списка физических томов")
        # Базовые аргументы команды
        cmd_args = ["pvs", "--reportformat=json"]

        # Добавляем опции вывода
        if verbose:
            cmd_args.append("-v")

        if noheadings:
            cmd_args.append("--noheadings")

        if separator:
            cmd_args.extend(["--separator", separator])

        if units:
            cmd_args.extend(["--units", units])

        if aligned:
            cmd_args.append("--aligned")

        if all:
            cmd_args.append("--all")

        if unbuffered:
            cmd_args.append("--unbuffered")

        if nosuffix:
            cmd_args.append("--nosuffix")

        # Добавляем пользовательские опции
        if options:
            cmd_args.extend(options)

        # Добавляем фильтры
        if pv_name:
            cmd_args.append(pv_name)

        if vg_name:
            cmd_args.append(vg_name)

        # Выполняем команду
        result = self.cli.execute(cmd_args)
        return self._parse_dict_to_models(orjson.loads(result))

    @staticmethod
    def _parse_dict_to_models(output: dict) -> list[PhysicalVolume]:
        result = output.get("report")[0].get("pv")
        physical_volumes_list = []

        for physical_volume in result:
            physical_volumes_list.append(
                PhysicalVolume(
                    physical_name=physical_volume.get("pv_name"),
                    volume_name=physical_volume.get("volume_name"),
                    format=physical_volume.get("pv_fmt"),
                    attributes=physical_volume.get("pv_attr"),
                    physical_size=physical_volume.get("pv_size"),
                    physical_free=physical_volume.get("pv_free"),
                )
            )

        return physical_volumes_list


if __name__ == "__main__":
    cli = CLIControl()
    disk_name = "disk-test-60780"
    cmd_arg = f"df --output=source,target | grep {disk_name} | awk " + "'{print $2}'"
    result = cli.execute(cmd_arg, shell=True, is_text=True).split("\n")[0]
    print("result: ", result)
    # nfs_stg = NFSStorage()
    # nfs_path = f"/srv/nfs/share_{random.randint(100000, 999999)}/"
    # nfs_mount_path = f"/mnt/nfs_{random.randint(100000, 999999)}/"
    #
    # # Создать директории
    # nfs_share_mkdir = ["mkdir", "-p", nfs_path]
    # cli.execute(nfs_share_mkdir)
    #
    # # Настроить экспорт
    # setting_export = [nfs_path, "127.0.0.1(rw,sync,no_subtree_check)"]
    # cli.execute(setting_export)
    #
    # # Применить
    # apply_setting = ["exportfs", "-a"]
    # cli.execute(apply_setting)
    #
    # # Монтировать локально
    # mkdir_local = ["mkdir", "-p", nfs_mount_path]
    # cli.execute(mkdir_local)
    # time.sleep(1)
    # result = nfs_stg.mount(f"127.0.0.1:{nfs_path}", nfs_mount_path)
    # print(result)
    # yield nfs_mount_path

    # Отмонтировать принудительно
    # nfs_stg.unmount(nfs_mount_path)
    #
    # # Удаление локальных директории хранилища
    # nfs_local_rmdir = ["rmdir", nfs_path]
    # cli.execute(nfs_local_rmdir)
    #
    # nfs_local_rmdir = ["rmdir", nfs_mount_path]
    # cli.execute(nfs_local_rmdir)
    # manager = PhysicalVolumeManager()
    # for pv in manager.get_volume_list():
    #     print("-" * 50)
    #     print("ИМЯ ФИЗИЧЕСКОГО ТОМА: ", pv.physical_name)
    #     print("ИМЯ VOLUME ГРУППЫ: ", pv.volume_name)
    #     print("АТРИБУТЫ ФИЗИЧЕСКОГО ТОМА: ", pv.attributes)
    #     print("ФОРМАТ ФИЗИЧЕСКОГО ТОМА: ", pv.format)
    #     print("РАЗМЕР ФИЗИЧЕСКОГО ТОМА: ", pv.physical_size)
    #     print("СВОБОДНОЕ ПРОСТРАНСТВО ФИЗИЧЕСКОГО ТОМА: ", pv.physical_free)
    # data = manager.get_physical_volume_by_name("/dev/nvme0n1p5")
    # print("-" * 50)
    # print("ИМЯ ФИЗИЧЕСКОГО ТОМА: ", data.physical_name)
    # print("ИМЯ VOLUME ГРУППЫ: ", data.volume_name)
    # print("ФОРМАТ ФИЗИЧЕСКОГО ТОМА: ", data.format)
    # print("РАЗМЕР ФИЗИЧЕСКОГО ТОМА: ", data.physical_size)
    # print("СВОБОДНОЕ ПРОСТРАНСТВО ФИЗИЧЕСКОГО ТОМА: ", data.physical_free)
