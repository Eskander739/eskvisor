import libvirt

from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.models.snapshots import SnapshotWithParent, Snapshot


class SnapshotManager(LibvirtClient):
    """
    Управление снапшотами
    """
    libvirtError = libvirt.libvirtError

    def __init__(self, connection_uri: str = "qemu:///system"):
        super().__init__(connection_uri)

    def snapshots_by_vm_name(self, name: str) -> list[SnapshotWithParent]:
        """
        Получить все снапшоты виртуальной машины по имени
        """
        try:
            virtual_machine = self.conn.lookupByName(name)
            snapshots = virtual_machine.listAllSnapshots(flags=0)
            self.logger.info(f"Количество снапшотов: {len(snapshots)}")
            snapshots_list = []

            for snapshot in snapshots:
                snapshot_data = SnapshotWithParent(
                    name=snapshot.getName(),
                    description=snapshot.getDescription(),
                    created=snapshot.getCreationTime(),
                    state=snapshot.getState()
                )

                # Получение информации о родительском снапшоте
                try:
                    parent_snapshot = snapshot.getParent()
                    snapshot_data.parent = Snapshot(
                        name=parent_snapshot.getName(),
                        description=parent_snapshot.getDescription(),
                        created=parent_snapshot.getCreationTime(),
                        state=parent_snapshot.getState()
                    )
                except self.libvirtError:
                    snapshot_data.parent = None

                snapshots_list.append(snapshot_data)

            return snapshots_list
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения списка снапшотов: {e}")
            return []

    def snapshot_by_name(self, vm_name: str, snapshot_name: str) -> SnapshotWithParent | None:
        """
        Получить снапшот по имени виртуальной машины и имени снапшота
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotLookupByName(snapshot_name, flags=0)

            snapshot_data = SnapshotWithParent(
                name=snapshot.getName(),
                description=snapshot.getDescription(),
                created=snapshot.getCreationTime(),
                state=snapshot.getState()
            )

            # Информация о родительском снапшоте
            try:
                parent_snapshot = snapshot.getParent()
                snapshot_data.parent = Snapshot(
                    name=parent_snapshot.getName(),
                    description=parent_snapshot.getDescription(),
                    created=parent_snapshot.getCreationTime(),
                    state=parent_snapshot.getState()
                )
            except self.libvirtError:
                snapshot_data.parent = None

            return snapshot_data

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения снапшота: {e}")
            return None

    def create_snapshot(self, vm_name: str, snapshot_name: str, description: str = "",
                        disk_only: bool = False, quiesce: bool = False) -> bool:
        """
        Создать снапшот виртуальной машины
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)

            # Подготовка XML для снапшота
            snapshot_xml = f"""
            <domainsnapshot>
                <name>{snapshot_name}</name>
                <description>{description}</description>
            </domainsnapshot>
            """

            # Настройка флагов
            flags = 0
            if disk_only:
                flags |= libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY
            if quiesce:
                flags |= libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_QUIESCE

            # Создание снапшота
            snapshot = virtual_machine.snapshotCreateXML(snapshot_xml, flags)

            if snapshot:
                self.logger.info(f"Снапшот '{snapshot_name}' успешно создан для VM '{vm_name}'")
                return True
            return False

        except self.libvirtError as e:
            self.logger.error(f"Ошибка создания снапшота: {e}")
            return False

    def delete_snapshot(self, vm_name: str, snapshot_name: str,
                        remove_children: bool = False) -> bool:
        """
        Удалить снапшот виртуальной машины
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotLookupByName(snapshot_name, flags=0)

            # Настройка флагов
            flags = 0
            if remove_children:
                flags |= libvirt.VIR_DOMAIN_SNAPSHOT_DELETE_CHILDREN
            flags |= libvirt.VIR_DOMAIN_SNAPSHOT_DELETE_METADATA_ONLY

            # Удаление снапшота
            snapshot.delete(flags)

            self.logger.info(f"Снапшот '{snapshot_name}' успешно удален для VM '{vm_name}'")
            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления снапшота: {e}")
            return False

    def revert_to_snapshot(self, vm_name: str, snapshot_name: str) -> bool:
        """
        Восстановить виртуальную машину до состояния снапшота
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotLookupByName(snapshot_name, flags=0)

            # Восстановление до снапшота
            virtual_machine.revertToSnapshot(snapshot, flags=0)

            self.logger.info(f"VM '{vm_name}' восстановлена до снапшота '{snapshot_name}'")
            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка восстановления до снапшота: {e}")
            return False

    def update_snapshot_description(self, vm_name: str, snapshot_name: str,
                                    new_description: str) -> bool:
        """
        Обновить описание снапшота
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotLookupByName(snapshot_name, flags=0)

            # Получение текущего XML снапшота
            snapshot_xml = snapshot.getXMLDesc(flags=0)

            # Обновление описания в XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(snapshot_xml)

            # Поиск и обновление элемента description
            description_elem = root.find('description')
            if description_elem is not None:
                description_elem.text = new_description
            else:
                # Если элемента description нет, создаем его
                desc_elem = ET.SubElement(root, 'description')
                desc_elem.text = new_description

            # Преобразование обратно в XML строку
            updated_xml = ET.tostring(root, encoding='unicode')

            # Создание нового снапшота с обновленным описанием и удаление старого
            new_snapshot = virtual_machine.snapshotCreateXML(updated_xml,
                                                             flags=libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_REPLACE)

            if new_snapshot:
                self.logger.info(f"Описание снапшота '{snapshot_name}' успешно обновлено")
                return True
            return False

        except self.libvirtError as e:
            self.logger.error(f"Ошибка обновления описания снапшота: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка обработки XML: {e}")
            return False

    def get_current_snapshot(self, vm_name: str) -> SnapshotWithParent | None:
        """
        Получить текущий активный снапшот виртуальной машины
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotCurrent(flags=0)

            if snapshot:
                snapshot_data = SnapshotWithParent(
                    name=snapshot.getName(),
                    description=snapshot.getDescription(),
                    created=snapshot.getCreationTime(),
                    state=snapshot.getState()
                )

                # Информация о родительском снапшоте
                try:
                    parent_snapshot = snapshot.getParent()
                    snapshot_data.parent = Snapshot(
                        name=parent_snapshot.getName(),
                        description=parent_snapshot.getDescription(),
                        created=parent_snapshot.getCreationTime(),
                        state=parent_snapshot.getState()
                    )
                except self.libvirtError:
                    snapshot_data.parent = None

                return snapshot_data
            return None

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения текущего снапшота: {e}")
            return None