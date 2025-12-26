import os


class LibvirtConfig:


    @property
    def local_prefixes(self) -> tuple:
        return (
                '/var/lib/libvirt',
                '/opt/vm_disks',
                os.path.expanduser('~'),
                '/mnt/',
                '/media/'
            )

    @property
    def network_prefixes(self) -> tuple:
        return 'nfs://', 'smb://', 'cifs://', 'gluster://', 'rbd://'
