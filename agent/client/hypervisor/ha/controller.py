import os
import re
import socket
from pathlib import Path

import orjson
from agent.client.cli import CLIControl
from agent.client.constants import DANGEROUS_PATTERNS
from agent.client.logger_config import DefaultLogger
from agent.client.models.general import NFSStorages, NFSStorageModel, LoadNFSStorages, NFSStorageForMount
from agent.client.stg.nfs import NFSStorageManager



class HAController:
    def __init__(self):
        self.logger = DefaultLogger("HAController")
        self.cli = CLIControl()
        self.nfs_storage_manager = NFSStorageManager()
        self.system_vm_configs_path = os.environ.get("SYSTEM_VM_CONFIGS_PATH")
        self.loaded_ha_nfs_storages_path = os.environ.get("LOADED_HA_NFS_STORAGES_PATH")
        self.nfs_vm_config_root = os.environ.get("NFS_VM_CONFIG_ROOT")
        if not self.cli.is_exists(self.loaded_ha_nfs_storages_path):
            nfs_storages_model = NFSStorages(nfs_storages=[]).model_dump_json()
            self.cli.create_file(self.loaded_ha_nfs_storages_path, f"{nfs_storages_model}")

    @staticmethod
    def validate_nfs_path_safety(path: str, enable_allow_prefixes: bool = False) -> bool:
        if not isinstance(path, str):
            return False

        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, path):
                return False

        if enable_allow_prefixes:
            allowed_prefixes = ["/eskvisor", "/mnt"]
            if not any(str(path).startswith(prefix) for prefix in allowed_prefixes):
                return False

        return True

    def system_vm_configs(self, path: str | None = None) -> tuple[list[str], list[str]]:
        """
        Возвращает локальные конфиги ВМ и конфиги ВМ в автозапуске
        """
        path = path if path else self.system_vm_configs_path

        if not self.validate_nfs_path_safety(path):
            self.logger.warning(f"Попытка инъекции в пути: '{path}'")
            raise ValueError(f"Попытка инъекции в пути: '{path}'")
        cmd_args = lambda local_path: f"ls {local_path} | grep '\.xml$'"
        vm_configs_list = []
        vm_autostart_configs_list = []
        vm_configs = self.cli.execute(cmd_args(path), shell=True, is_text=True).split("\n")
        if vm_configs:
            vm_configs_list = [vm_config for vm_config in vm_configs if vm_config]
        path = f"{path}/autostart"
        vm_autostart_configs = self.cli.execute(cmd_args(path), shell=True, is_text=True).split("\n")
        if vm_autostart_configs:
            vm_autostart_configs_list = [vm_config for vm_config in vm_autostart_configs if vm_config]

        return vm_configs_list, vm_autostart_configs_list

    @property
    def vm_configs_from_ha_storages(self) -> tuple[list[str], list[str]]:
        """
        Возвращает конфиги ВМ и конфиги ВМ в автозапуске из HA NFS хранилищ
        """
        storages = self.loaded_ha_nfs_storages
        vm_configs_list = []
        vm_autostart_configs_list = []

        for current_storage in storages.nfs_storages:
            path = f"{current_storage.mount}/{self.nfs_vm_config_root}"
            cmd_args = lambda local_path: f"ls {local_path} | grep '\.xml$'"
            vm_configs = self.cli.execute(cmd_args(path), shell=True, is_text=True).split("\n")
            if vm_configs:
                vm_configs_list = [vm_config for vm_config in vm_configs if vm_config]
            path = f"{path}/autostart"
            vm_autostart_configs = self.cli.execute(cmd_args(path), shell=True, is_text=True).split("\n")
            if vm_autostart_configs:
                vm_autostart_configs_list = [vm_config for vm_config in vm_autostart_configs if vm_config]

        return vm_configs_list, vm_autostart_configs_list

    @property
    def loaded_ha_nfs_storages(self) -> NFSStorages:
        """
        Возвращает список NFS хранилищ
        """

        nfs_storages = self.cli.execute(["cat", self.loaded_ha_nfs_storages_path])
        self.logger.info(f"Текущий конфиг HA NFS хранилищ: '{nfs_storages}'")
        nfs_storages_dict = orjson.loads(nfs_storages)
        nfs_storages_list = nfs_storages_dict.get("nfs_storages")
        nfs_storages_model = NFSStorages(nfs_storages=[])
        if not nfs_storages_list:
            return nfs_storages_model

        for storage in nfs_storages_list:
            nfs_storages_model.nfs_storages.append(NFSStorageModel(source=storage.get("source"), mount=storage.get("mount")))
        return nfs_storages_model

    def check_nfs_availability(self, source: str, ping_count: int = 2, timeout: int = 5) -> bool:
        """
        Проверяет доступность NFS сервера для монтирования
        """
        try:
            server = source.split(":")[0]
            self.logger.debug(f"Проверяем доступность сервера {server}")
            try:
                ping_cmd = ['ping', '-c', str(ping_count), '-W', '2', server]
                ping_result = self.cli.execute(ping_cmd, timeout=timeout)

                # Проверяем наличие ключевых фраз в выводе ping
                success_indicators = ['0% packet loss', 'time=', 'ttl=', 'bytes from']
                ping_successful = any(indicator in ping_result.lower()
                                      for indicator in success_indicators)

                if not ping_successful:
                    self.logger.warning(f"Сервер {server} недоступен по ping")
                    return False
            except Exception as e:
                self.logger.warning(f"Ошибка ping для {server}: {e}")
                return False
            self.logger.debug(f"Проверяем порт NFS (2049) на {server}")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((server, 2049))
                sock.close()

                if result != 0:
                    self.logger.warning(f"Порт 2049 (NFS) закрыт на сервере {server}")
                    return False
            except socket.error as e:
                self.logger.warning(f"Ошибка подключения к порту 2049: {e}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Ошибка при проверке доступности NFS: {e}")
            return False

    def load_and_mount_ha_nfs_storages(self, storages: LoadNFSStorages) -> bool:
        """
        Метод подключения NFS хранилищ, если они подгрузились со стороны бэкенда
        """

        if self.loaded_ha_nfs_storages.nfs_storages:
            self.logger.warning("Поддержка HA режима с множеством СХД планируются в будущих релизах")
            return False

        check_valid_list = [storage for storage in storages.nfs_storages_for_mount if storage]
        if check_valid_list:
            for storage in storages.nfs_storages_for_mount:
                source = storage.source  # ip NFS сервера
                current_nfs_name = storage.nfs_name  # имя NFS сервера
                read_current_config = self.cli.execute(["cat", self.loaded_ha_nfs_storages_path])
                current_config = NFSStorages.model_validate(orjson.loads(read_current_config))
                self.logger.info(f"Результат чтения конфига: '{read_current_config}'")

                if source in read_current_config:
                    continue

                if not self.check_nfs_availability(source):
                    raise ValueError("NFS сервер недоступен")

                mount_path = f"/mnt/{current_nfs_name}/"
                current_config.nfs_storages.append(NFSStorageModel(source=source, mount=mount_path))
                write_new_nfs_storage = self.cli.execute(
                    ["sh", "-c", f"echo '{current_config.model_dump_json()}' > {self.loaded_ha_nfs_storages_path}"], return_proc=True)
                if write_new_nfs_storage.returncode != 0:
                    self.logger.info(
                        f"Ошибка при обновлении конфигурации HA NFS хранилищ: '{write_new_nfs_storage.stderr}'")
                    return False
                self.logger.info(f"Результат записи нового NFS сервера: '{write_new_nfs_storage}'")
                read_updated_config = self.cli.execute(["cat", self.loaded_ha_nfs_storages_path])
                self.logger.info(f"Результат чтения конфига после записи: '{read_updated_config}'")
                if not self.cli.is_exists(mount_path):
                    self.cli.mkdir(mount_path)

                result_mount = self.nfs_storage_manager.mount(source, mount_path)
                if not result_mount:
                    return False
                return True
        return False

    def umount_ha_nfs_storages(self, storages: NFSStorages) -> bool:
        """
        Метод отмонтирования(удаления) NFS хранилищ
        """

        storages_for_umount = [storage for storage in storages.nfs_storages if storage]
        current_config = self.loaded_ha_nfs_storages
        updated_config = NFSStorages(nfs_storages=[])
        deleted_storage_mount_points = []
        if storages_for_umount:
            for umount_storage in storages_for_umount:
                for current_storage in current_config.nfs_storages:
                    if umount_storage.source != current_storage.source:
                        updated_config.nfs_storages.append(current_storage)
                    else:
                        umount_result = self.nfs_storage_manager.umount(current_storage.mount)
                        self.logger.info(f"Результат отмонтирования хранилища {current_storage.mount}: '{umount_result}'")
                        deleted_storage_mount_points.append(current_storage.mount)

        write_updated_nfs_storage = self.cli.execute(
            ["sh", "-c", f"echo '{updated_config.model_dump_json()}' > {self.loaded_ha_nfs_storages_path}"], return_proc=True)
        if write_updated_nfs_storage.returncode != 0:
            self.logger.info(f"Ошибка при обновлении конфигурации HA NFS хранилищ: '{write_updated_nfs_storage.stderr}'")
            return False
        self.logger.info(f"Отмонтированные хранилища: '{deleted_storage_mount_points}'")
        return True

    def delete_vm_from_nfs_config(self, vm_name: str):
        for nfs_storage in self.loaded_ha_nfs_storages.nfs_storages:
            config_path =str( Path(f'{nfs_storage.mount}/{self.nfs_vm_config_root}/{vm_name}.xml'))
            config_autostart_path = f'{nfs_storage.mount}/{self.nfs_vm_config_root}/autostart/{vm_name}.xml'
            self.delete_file_or_path(config_path)
            self.delete_file_or_path(config_autostart_path)

    def sync_nfs_vm_configs(self):
        """Синхронизирует только XML конфиги ВМ с удалением лишнего"""
        if not self.loaded_ha_nfs_storages_path:
            return

        for nfs_storage in self.loaded_ha_nfs_storages.nfs_storages:
            try:
                mounted_nfs_dir = str(Path(f'{nfs_storage.mount}{self.nfs_vm_config_root}'))
                if not self.is_directory(mounted_nfs_dir):
                    self.mkdir(mounted_nfs_dir)
                # Основные конфиги - ТОЛЬКО XML файлы
                rsync_cmd = [
                    'rsync', '-av',
                    '--include', '*.xml',  # Включаем только XML
                    '--exclude', '*',  # Исключаем всё остальное
                    '--prune-empty-dirs',  # Удаляем пустые директории
                    f'{self.system_vm_configs_path}',
                    f'{mounted_nfs_dir}'
                ]

                # Автозапуск - ТОЛЬКО XML файлы
                autostart_rsync_cmd = [
                    'rsync', '-av',
                    '--include', '*.xml',  # Включаем только XML
                    '--exclude', '*',  # Исключаем всё остальное
                    '--prune-empty-dirs',
                    f'{self.system_vm_configs_path}autostart/',
                    f'{mounted_nfs_dir}/autostart/'
                ]

                result_sync_vm_configs = self.cli.execute(rsync_cmd)
                self.logger.info(f"Результат синхронизации директории конфигов: '{result_sync_vm_configs}'")
                result_sync_vm_autostart_configs = self.cli.execute(autostart_rsync_cmd)
                self.logger.info(f"Результат синхронизации директории конфигов автозапуска: '{result_sync_vm_autostart_configs}'")
                self.logger.info(f"Синхронизировано XML с {nfs_storage}")

            except Exception as e:
                self.logger.error(f"Ошибка синхронизации {nfs_storage}: {e}")

    def is_directory(self, path: str):
        ru_err = "Это каталог"
        eng_err = "Is a directory"
        cmd_args = ["cat", path]
        result = self.cli.execute(cmd_args)
        if ru_err in result or eng_err in result:
            return True
        return False

    def mkdir(self, path: str):
        cmd_args = ["mkdir", "-p", path]
        result = self.cli.execute(cmd_args)
        return result


    def delete_file_or_path(self, path: str):
        cmd_args = ["rm", "-r", path]
        result = self.cli.execute(cmd_args)
        self.logger.info(f"Результат удаления файла/директории: '{result}'")
        return result


if __name__ == "__main__":
    cli = HAController()
    # print(cli.vm_configs())
    print(cli.load_and_mount_ha_nfs_storages(LoadNFSStorages(nfs_storages_for_mount=[NFSStorageForMount(source="127.0.0.1:/share_622825", nfs_name="ha_cluster")])))
    # print(cli.search_emulators())
    # print(cli.default_emulator)
