import os
from pathlib import Path

from agent.client.hypervisor.libvirt.models.disk import DiskFormat
from agent.client.hypervisor.libvirt.models.resource_pool import (
    POOL_TYPE_DESCRIPTIONS,
    StoragePoolType,
)


class LibvirtConfig:

    @property
    def search_dirs(self) -> tuple:
        return (
            self.default_storage_dir,
            "/var/lib/libvirt/volumes",
            "/var/lib/libvirt/images",
            f"{str(Path.home())}/.local/share/libvirt/images",
            "/opt/vm_disks",
            os.path.expanduser("~/vm_disks"),
        )

    @property
    def network_prefixes(self) -> tuple:
        return "nfs://", "smb://", "cifs://", "gluster://", "rbd://"

    @property
    def disk_extensions(self) -> set:
        return {".qcow2", ".raw", ".img", ".vmdk", ".vdi", ".vhd", ".vhdx"}

    @property
    def default_session_storage(self):
        return f"{str(Path.home())}/.local/share/libvirt/images"

    @property
    def default_storage_dir(self):
        return "/var/lib/libvirt/images"

    @staticmethod
    def disk_format_by_path(disk_path: str) -> DiskFormat:
        if disk_path.endswith(".qcow2"):
            return DiskFormat.QCOW2
        elif disk_path.endswith(".raw") or disk_path.endswith(".img"):
            return DiskFormat.RAW
        elif disk_path.endswith(".vmdk"):
            return DiskFormat.VMDK
        elif disk_path.endswith(".vdi"):
            return DiskFormat.VDI
        elif disk_path.endswith(".vhd") or disk_path.endswith(".vhdx"):
            return DiskFormat.VHDX
        elif disk_path.endswith(".iso"):
            return DiskFormat.ISO
        elif disk_path.endswith(".img"):
            return DiskFormat.IMG
        return DiskFormat.UNKNOWN

    @staticmethod
    def get_pool_type_info(pool_type: StoragePoolType) -> dict:
        """
        Получение детальной информации о типе пула

        Args:
            pool_type: Тип пула

        Returns:
            Словарь с информацией о типе пула
        """
        info = {
            StoragePoolType.DIR: {
                "description": "Директория в локальной файловой системе",
                "requires": ["storage_path"],
                "recommended_for": "Локальные ВМ, разработка и тестирование",
                "performance": "Средняя",
                "scalability": "Ограничена размером диска",
                "redundancy": "Зависит от файловой системы",
            },
            StoragePoolType.FS: {
                "description": "Предварительно отформатированный раздел файловой системы",
                "requires": ["device_path"],
                "recommended_for": "Локальные ВМ с выделенным разделом",
                "performance": "Высокая",
                "scalability": "Ограничена размером раздела",
                "redundancy": "Нет",
            },
            StoragePoolType.LOGICAL: {
                "description": "Группа LVM логических томов",
                "requires": ["volume_group"],
                "recommended_for": "Локальные ВМ с динамическим выделением",
                "performance": "Высокая",
                "scalability": "Хорошая (через LVM)",
                "redundancy": "LVM зеркалирование",
            },
            StoragePoolType.RBD: {
                "description": "RADOS Block Device (Ceph)",
                "requires": ["monitor_host", "pool_name"],
                "recommended_for": "Кластерные среды, высокая доступность",
                "performance": "Высокая",
                "scalability": "Отличная",
                "redundancy": "Высокая (репликация Ceph)",
            },
            StoragePoolType.ISCSI: {
                "description": "iSCSI целевое устройство",
                "requires": ["target_host", "target_port"],
                "recommended_for": "SAN окружения, совместное хранилище",
                "performance": "Зависит от сети",
                "scalability": "Хорошая",
                "redundancy": "Зависит от SAN",
            },
            StoragePoolType.GLUSTER: {
                "description": "GlusterFS распределенный файловый том",
                "requires": ["volume_name", "hosts"],
                "recommended_for": "Распределенные системы, масштабирование",
                "performance": "Хорошая",
                "scalability": "Отличная",
                "redundancy": "Высокая (репликация Gluster)",
            },
            StoragePoolType.ZFS: {
                "description": "ZFS пул",
                "requires": ["pool_name", "devices"],
                "recommended_for": "Серверы с ZFS, snapshot и клонирование",
                "performance": "Отличная",
                "scalability": "Хорошая",
                "redundancy": "Высокая (ZFS RAID)",
            },
            StoragePoolType.NETFS: {
                "description": "Сетевая файловая система (NFS)",
                "requires": ["host", "path"],
                "recommended_for": "Общие хранилища, миграция ВМ",
                "performance": "Средняя",
                "scalability": "Хорошая",
                "redundancy": "Зависит от NFS сервера",
            },
        }

        return info.get(
            pool_type,
            {
                "description": POOL_TYPE_DESCRIPTIONS.get(
                    pool_type, "Неизвестный тип пула"
                ),
                "requires": ["Специфические параметры конфигурации"],
                "recommended_for": "Специализированные сценарии",
                "performance": "Зависит от конфигурации",
                "scalability": "Зависит от конфигурации",
                "redundancy": "Зависит от конфигурации",
            },
        )
