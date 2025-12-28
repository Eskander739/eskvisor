import os
from pathlib import Path

from agent.client.hypervisor.models.disk import DiskFormat


class LibvirtConfig:


    @property
    def search_dirs(self) -> tuple:
        return (
            self.default_storage_dir,
            "/var/lib/libvirt/volumes",
            "/var/lib/libvirt/images",
            f"{str(Path.home())}/.local/share/libvirt/images",
            "/opt/vm_disks",
            os.path.expanduser("~/vm_disks")
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
        return DiskFormat.UNKNOWN
