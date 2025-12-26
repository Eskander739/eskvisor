import os


class LibvirtConfig:


    @property
    def search_dirs(self) -> tuple:
        return (
            "/var/lib/libvirt/images",
            "/var/lib/libvirt/volumes",
            "/opt/vm_disks",
            os.path.expanduser("~/vm_disks")
            )

    @property
    def network_prefixes(self) -> tuple:
        return 'nfs://', 'smb://', 'cifs://', 'gluster://', 'rbd://'

    @property
    def disk_extensions(self) -> set:
        return {'.qcow2', '.raw', '.img', '.vmdk', '.vdi', '.vhd', '.vhdx'}
