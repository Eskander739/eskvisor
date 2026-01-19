from agent.client.cli import CLIControl
from agent.client.logger_config import DefaultLogger

# NFSv3 (оптимальные настройки)
RSIZE_V3 = 32768  # 32KB
WSIZE_V3 = 32768  # 32KB

# NFSv4.2 (как было)
RSIZE_V4 = 1048576  # 1MB
WSIZE_V4 = 1048576  # 1MB


class NFSStorageManager:
    """
    Работа с NFS хранилищами
    """

    def __init__(self):
        self.cli = CLIControl()
        self.logger = DefaultLogger("NFSStorage")

    def list_all_storages(self):
        cmd_args = ["mount", "-t", "nfs,nfs4"]
        result = self.cli.execute(cmd_args)
        mounts = []

        for line in result.strip().split("\n"):
            if line:
                parts = line.split()
                if len(parts) >= 3:
                    mounts.append(
                        {
                            "source": parts[0],
                            "mount_point": parts[2],
                            "options": parts[3][1:-1] if len(parts) > 3 else "",
                        }
                    )

        return mounts

    def mount(self, server_path: str, mount_point: str, nfs_version: str = "4.2"):
        # Определяем размеры блоков
        if nfs_version.startswith("4"):
            rsize = RSIZE_V4
            wsize = WSIZE_V4
        else:  # v3
            rsize = RSIZE_V3
            wsize = WSIZE_V3

        # Формируем опции
        options_parts = [
            f"vers={nfs_version}",
            "hard",
            "noatime",
            "async",
            f"rsize={rsize}",
            f"wsize={wsize}",
            "timeo=600",
            "retrans=3",
        ]

        # Добавляем lookupcache только для NFSv4+
        if nfs_version.startswith("4"):
            options_parts.append("lookupcache=all")

        cmd_args = [
            "mount",
            "-t",
            "nfs",
            "-o",
            ",".join(options_parts),
            server_path,
            mount_point,
        ]
        mount_result = self.cli.execute(cmd_args, return_proc=True)
        if mount_result.returncode != 0:
            self.logger.warning(f"Результат монтирования: '{mount_result.stderr}'")
            return False
        self.logger.warning(f"Результат монтирования: '{mount_result.stdout}'")
        return True

    def umount(self, mount_point: str):
        cmd_args = ["umount", mount_point]
        return self.cli.execute(cmd_args)

    def get_storage_info(self, mount_point: str):
        mounts = self.list_all_storages()

        for mount in mounts:
            if mount.get("mount_point") == mount_point:
                cmd_args = ["mount", "-v", "-t", "nfs"]
                detailed_info = self.cli.execute(cmd_args)

                for line in detailed_info.strip().split("\n"):
                    if mount_point in line and mount.get("source") in line:
                        mount["detailed"] = line
                        break

                return mount

        return None


if __name__ == "__main__":
    nfs_stg = NFSStorageManager()
    # nfs_load_model = NFSStorageForMount(
    #     source="127.0.0.1:/share_622825",
    #     nfs_name="cluster_HA_QC1")
    # print(nfs_load_model)
    # storage_model = LoadNFSStorages(nfs_storages_for_mount=[])
    # storage_model.nfs_storages_for_mount.append(nfs_load_model)
    # print(storage_model)
    # print(nfs_stg.load_and_mount_ha_nfs_storages(storage_model))

    # отмонтирование ha хранилищ
    # ha_model_umount = NFSStorages(nfs_storages=[])
    # ha_model_umount.nfs_storages.append(NFSStorageModel(source="127.0.0.1:/share_622825", mount="/mnt/cluster_HA_QC1"))
    # print(nfs_stg.umount_ha_nfs_storages(ha_model_umount))
    # cli = CLIControl()
    # nfs_path = f"/srv/nfs/share_{random.randint(100000, 999999)}"
    # nfs_mount_path = f"/mnt/nfs_{random.randint(100000, 999999)}"
    #
    # # Создать директории
    # nfs_share_mkdir = ["mkdir", "-p", nfs_path]
    # result_nfs_share_mkdir = cli.execute(nfs_share_mkdir)
    # print("result_nfs_share_mkdir: ", result_nfs_share_mkdir)
    # # nfs_share_mkdir = [
    # #     "chown",
    # #     # "nobody:nobody",
    # #     nfs_path
    # # ]
    # # result_nfs_share_mkdir = cli.execute(nfs_share_mkdir)
    # # print("result_nfs_share_mkdir: ", result_nfs_share_mkdir)
    # # Настроить экспорт
    # setting_export = [nfs_path, "127.0.0.1(rw,sync,no_subtree_check)"]
    # result_setting_export = cli.execute(setting_export)
    # print("setting_export: ", result_setting_export)
    # # Применить
    # apply_setting = ["exportfs", "-a"]
    # result_apply_setting = cli.execute(apply_setting)
    # print("result_apply_setting: ", result_apply_setting)
    # # Монтировать локально
    #
    # mkdir_local = ["mkdir", "-p", nfs_mount_path]
    # result_mkdir_local = cli.execute(mkdir_local)
    # print("result_mkdir_local: ", result_mkdir_local)
    # mount_local = ["mount", "-t", "nfs", f"127.0.0.1:{nfs_path}", nfs_mount_path]
    # result_mount_local = cli.execute(mount_local)
    # print("result_mount_local: ", result_mount_local)
    # time.sleep(10)
    #
    # # Отмонтировать принудительно
    # unmount_local = ["umount", "-f", nfs_mount_path]
    # result = cli.execute(unmount_local)
    #
    # # Удаление локальных директории хранилища
    # nfs_local_rmdir = ["rmdir", nfs_path]
    # cli.execute(nfs_local_rmdir)
    #
    # nfs_local_rmdir = ["rmdir", nfs_mount_path]
    # cli.execute(nfs_local_rmdir)
