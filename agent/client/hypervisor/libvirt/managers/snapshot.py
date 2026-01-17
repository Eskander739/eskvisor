import os
import shutil
import uuid
import xml.etree.ElementTree as ET

import libvirt

from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.libvirt.models.volume.disk import (
    Disk,
    DiskType,
    SnapshotDiskInfo,
)
from agent.client.hypervisor.libvirt.models.general import VMState
from agent.client.hypervisor.libvirt.models.msg import (
    CommandMessagesEnum,
    SnapshotMessage,
)
from agent.client.hypervisor.libvirt.models.snapshots import (
    ClonedSnapshot,
    CreateMultipleSnapshots,
    CreateMultipleSnapshotsError,
    CreateSnapshotChainError,
    CreateSnapshotChainSuccess,
    DeleteSnapshotInfo,
    MultipleSnapshotsRequest,
    Snapshot,
    SnapshotCloneRequest,
    SnapshotCreateRequest,
    SnapshotList,
    SnapshotRevertSuccess,
    SnapshotsChain,
    SnapshotWithParent,
)
from agent.client.hypervisor.libvirt.models.vm import VirtualMachine
from agent.client.logger_config import DefaultLogger


class SnapshotManager(LibvirtClient):
    """
    Управление снапшотами с возвратом SnapshotMessage
    """

    libvirtError = libvirt.libvirtError

    def __init__(self):
        super().__init__()
        self.logger = DefaultLogger("SnapshotManager")

    def snapshots_by_vm_name(
        self, vm_name: str
    ) -> SnapshotMessage:
        """
        Получить все снапшоты виртуальной машины по имени

        Returns:
            SnapshotMessage с информацией о снапшотах в rp_info
        """

        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshots = virtual_machine.listAllSnapshots(flags=0)
            self.logger.info(f"Количество снапшотов для ВМ {vm_name}: {len(snapshots)}")

            snapshots_list = []
            snapshots_info = []

            for snapshot in snapshots:
                # Получение информации о родительском снапшоте
                try:
                    parent_snapshot = snapshot.getParent()
                    parent_snapshot_xml = snapshot.getXMLDesc(flags=0)
                    parent_snapshot_info_dict = self._parse_snapshot_xml(
                        parent_snapshot_xml
                    )
                    parent_size = self._get_snapshot_size(snapshot)
                    parent_vm_config = VirtualMachine(
                        name=parent_snapshot_info_dict.get("vm_name"),
                        uuid=parent_snapshot_info_dict.get("uuid"),
                        max_memory=parent_snapshot_info_dict.get("memory"),
                        memory=parent_snapshot_info_dict.get("current_memory"),
                        vcpus=parent_snapshot_info_dict.get("vcpu"),
                        state=parent_snapshot_info_dict.get("state"),
                    )
                    parent_snapshot = Snapshot(
                        name=parent_snapshot.getName(),
                        vm_name=snapshot.getName(),
                        description=parent_snapshot_info_dict.get("description"),
                        created=parent_snapshot_info_dict.get("creation_time"),
                        state=parent_snapshot_info_dict.get("state"),
                        is_current=parent_snapshot_info_dict.get("current"),
                        size_bytes=parent_size,
                        disks=self._parse_snapshot_disks_xml(parent_snapshot_xml),
                        vm_config=parent_vm_config,
                    )
                except self.libvirtError:
                    parent_snapshot = None

                # Получение размера снапшота
                try:
                    size = self._get_snapshot_size(snapshot)
                    snapshot_xml = snapshot.getXMLDesc(flags=0)
                    snapshot_info_dict = self._parse_snapshot_xml(snapshot_xml)
                    vm_config = VirtualMachine(
                        name=snapshot_info_dict.get("vm_name"),
                        uuid=snapshot_info_dict.get("uuid"),
                        max_memory=snapshot_info_dict.get("memory"),
                        memory=snapshot_info_dict.get("current_memory"),
                        vcpus=snapshot_info_dict.get("vcpu"),
                        state=snapshot_info_dict.get("state"),
                    )
                    snapshot_info = SnapshotWithParent(
                        name=snapshot.getName(),
                        description=snapshot_info_dict.get("description"),
                        created=snapshot_info_dict.get("creation_time"),
                        state=snapshot_info_dict.get("state"),
                        parent=parent_snapshot if parent_snapshot else None,
                        size_bytes=size,
                        vm_name=vm_name,
                        is_current=snapshot_info_dict.get("current"),
                        disks=self._parse_snapshot_disks_xml(snapshot_xml),
                        vm_config=vm_config,
                    )
                    snapshots_info.append(snapshot_info)
                except Exception as e:
                    self.logger.warning(
                        f"Не удалось получить размер снапшота {snapshot.getName()}: {e}"
                    )
                    snapshot_xml = snapshot.getXMLDesc(flags=0)
                    snapshot_info_dict = self._parse_snapshot_xml(snapshot_xml)
                    vm_config = VirtualMachine(
                        name=snapshot_info_dict.get("vm_name"),
                        uuid=snapshot_info_dict.get("uuid"),
                        max_memory=snapshot_info_dict.get("memory"),
                        memory=snapshot_info_dict.get("current_memory"),
                        vcpus=snapshot_info_dict.get("vcpu"),
                        state=snapshot_info_dict.get("state"),
                    )
                    snapshot_info = SnapshotWithParent(
                        name=snapshot.getName(),
                        description=snapshot_info_dict.get("description"),
                        created=snapshot_info_dict.get("creation_time"),
                        state=snapshot_info_dict.get("state"),
                        parent=parent_snapshot if parent_snapshot else None,
                        size_bytes=None,
                        vm_name=vm_name,
                        is_current=snapshot_info_dict.get("current"),
                        disks=self._parse_snapshot_disks_xml(snapshot_xml),
                        vm_config=vm_config,
                    )
                    snapshots_info.append(snapshot_info)

                snapshots_list.append(snapshot_info)

            if snapshots_list:
                return SnapshotMessage(
                    success=True,
                    message=CommandMessagesEnum.snapshot_list_found.value,
                    code=CommandMessagesEnum.snapshot_list_found.name,
                    snapshot_info=SnapshotList(
                        vm_name=vm_name,
                        snapshots=snapshots_info,
                        count=len(snapshots_list),
                        chain_depth=self._calculate_chain_depth(snapshots_list),
                    ),
                )
            else:
                return SnapshotMessage(
                    success=False,
                    message=CommandMessagesEnum.snapshot_list_error.value,
                    code=CommandMessagesEnum.snapshot_list_error.name,
                    snapshot_info=SnapshotList(
                        vm_name=vm_name, snapshots=[], count=0, chain_depth=0
                    ),
                )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения списка снапшотов: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_list_error.value,
                code=CommandMessagesEnum.snapshot_list_error.name,
                note=str(e),
            )

    def snapshot_by_name(
        self, vm_name: str, snapshot_name: str
    ) -> SnapshotMessage:
        """
        Получить снапшот по имени виртуальной машины и имени снапшота

        Returns:
            SnapshotMessage с информацией о снапшоте в rp_info
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotLookupByName(snapshot_name, flags=0)

            # Информация о родительском снапшоте
            try:
                parent_snapshot = snapshot.getParent()
                parent_snapshot_xml = snapshot.getXMLDesc(flags=0)
                parent_snapshot_info_dict = self._parse_snapshot_xml(
                    parent_snapshot_xml
                )
                parent_size = self._get_snapshot_size(snapshot)
                vm_config = VirtualMachine(
                    name=parent_snapshot_info_dict.get("vm_name"),
                    uuid=parent_snapshot_info_dict.get("uuid"),
                    max_memory=parent_snapshot_info_dict.get("memory"),
                    memory=parent_snapshot_info_dict.get("current_memory"),
                    vcpus=parent_snapshot_info_dict.get("vcpu"),
                    state=parent_snapshot_info_dict.get("state"),
                )
                parent_snapshot = Snapshot(
                    name=parent_snapshot.getName(),
                    vm_name=snapshot.getName(),
                    description=parent_snapshot_info_dict.get("description"),
                    created=parent_snapshot_info_dict.get("creation_time"),
                    state=parent_snapshot_info_dict.get("state"),
                    is_current=parent_snapshot_info_dict.get("current"),
                    size_bytes=parent_size,
                    disks=self._parse_snapshot_disks_xml(parent_snapshot_xml),
                    vm_config=vm_config,
                )
            except self.libvirtError:
                parent_snapshot = None

            # Получение размера снапшота
            size = self._get_snapshot_size(snapshot)
            snapshot_xml = snapshot.getXMLDesc(flags=0)
            snapshot_info_dict = self._parse_snapshot_xml(snapshot_xml)
            vm_config = VirtualMachine(
                name=snapshot_info_dict.get("vm_name"),
                uuid=snapshot_info_dict.get("uuid"),
                max_memory=snapshot_info_dict.get("memory"),
                memory=snapshot_info_dict.get("current_memory"),
                vcpus=snapshot_info_dict.get("vcpu"),
                state=snapshot_info_dict.get("state"),
            )
            snapshot_info = SnapshotWithParent(
                name=snapshot.getName(),
                description=snapshot_info_dict.get("description"),
                created=snapshot_info_dict.get("creation_time"),
                state=snapshot_info_dict.get("state"),
                parent=parent_snapshot if parent_snapshot else None,
                size_bytes=size,
                vm_name=vm_name,
                is_current=snapshot_info_dict.get("current"),
                disks=self._parse_snapshot_disks_xml(snapshot_xml),
                vm_config=vm_config,
            )
            return SnapshotMessage(
                success=True,
                message=CommandMessagesEnum.vm_successfully_found.value,
                code=CommandMessagesEnum.snapshot_found.name,
                snapshot_info=snapshot_info,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения снапшота: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_not_found.value,
                code=CommandMessagesEnum.snapshot_not_found.name,
                note=str(e),
            )

    def create_snapshot(
        self, request: SnapshotCreateRequest
    ) -> SnapshotMessage:
        """
        Создать снапшот виртуальной машины

        Returns:
            SnapshotMessage с результатом операции
        """
        try:
            # Проверяем наличие свободного места
            if not self._check_disk_space(request.vm_name):
                return SnapshotMessage(
                    success=False,
                    message=CommandMessagesEnum.snapshot_insufficient_space.value,
                    code=CommandMessagesEnum.snapshot_insufficient_space.name,
                    note="Check available space in storage",
                )

            virtual_machine = self.conn.lookupByName(request.vm_name)

            # Проверяем состояние ВМ
            state, _ = virtual_machine.state()
            is_running = state == libvirt.VIR_DOMAIN_RUNNING

            if not is_running and request.quiesce:
                self.logger.warning(
                    "Параметр quiesce игнорируется для остановленной ВМ"
                )

            # Подготовка XML для снапшота
            snapshot_xml = f"""
            <domainsnapshot>
                <name>{request.snapshot_name}</name>
                <description>{request.description}</description>
            </domainsnapshot>
            """

            # Настройка флагов
            flags = 0
            if request.disk_only:
                flags |= libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY
            if request.quiesce and is_running:
                flags |= libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_QUIESCE

            # Создание снапшота
            snapshot = virtual_machine.snapshotCreateXML(snapshot_xml, flags)

            if snapshot:
                self.logger.info(
                    f"Снапшот '{request.snapshot_name}' успешно создан для VM '{request.vm_name}'"
                )
                current_shanpshot = self.get_current_snapshot(
                    request.vm_name
                )
                current_shanpshot.message = (
                    CommandMessagesEnum.snapshot_successfully_created.value
                )
                current_shanpshot.code = (
                    CommandMessagesEnum.snapshot_successfully_created.name
                )
                return current_shanpshot

            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_create_error.value,
                code=CommandMessagesEnum.snapshot_create_error.name,
            )

        except self.libvirtError as e:
            error_msg = str(e)
            if "No space left" in error_msg or "disk full" in error_msg.lower():
                return SnapshotMessage(
                    success=False,
                    message=CommandMessagesEnum.snapshot_insufficient_space.value,
                    code=CommandMessagesEnum.snapshot_insufficient_space.name,
                    note=error_msg,
                )

            self.logger.error(f"Ошибка создания снапшота: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_create_error.value,
                code=CommandMessagesEnum.snapshot_create_error.name,
                note=error_msg,
            )

    def delete_snapshot(
        self,
        vm_name: str,
        snapshot_name: str,
        remove_children: bool = False,
    ) -> SnapshotMessage:
        """
        Удалить снапшот виртуальной машины

        Returns:
            SnapshotMessage с результатом операции
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

            self.logger.info(
                f"Снапшот '{snapshot_name}' успешно удален для VM '{vm_name}'"
            )
            return SnapshotMessage(
                success=True,
                message=CommandMessagesEnum.snapshot_successfully_deleted.value,
                code=CommandMessagesEnum.snapshot_successfully_deleted.name,
                snapshot_info=DeleteSnapshotInfo(
                    vm_name=vm_name,
                    snapshot_name=snapshot_name,
                    remove_children=remove_children,
                ),
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления снапшота: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_delete_error.value,
                code=CommandMessagesEnum.snapshot_delete_error.name,
                note=str(e),
            )

    def delete_all_snapshots_by_vm_name(
        self,
        vm_name: str,
    ) -> SnapshotMessage:
        """
        Удалить снапшотов виртуальной машины

        Returns:
            SnapshotMessage с результатом операции
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshots = virtual_machine.listAllSnapshots(flags=0)
            for current_snapshot in snapshots:
                current_snapshot.delete(libvirt.VIR_DOMAIN_SNAPSHOT_DELETE_CHILDREN)
                self.logger.info(
                    f"Снапшот '{current_snapshot.getName()}' успешно удален для VM '{vm_name}'"
                )
            return SnapshotMessage(
                success=True,
                message=CommandMessagesEnum.snapshots_successfully_deleted.value,
                code=CommandMessagesEnum.snapshots_successfully_deleted.name,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления снапшота: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_delete_error.value,
                code=CommandMessagesEnum.snapshot_delete_error.name,
                note=str(e),
            )

    def revert_to_snapshot(
        self, vm_name: str, snapshot_name: str
    ) -> SnapshotMessage:
        """
        Восстановить виртуальную машину до состояния снапшота

        Returns:
            SnapshotMessage с результатом операции
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotLookupByName(snapshot_name, flags=0)
            # Восстановление до снапшота
            virtual_machine.revertToSnapshot(snapshot, flags=0)

            self.logger.info(
                f"VM '{vm_name}' восстановлена до снапшота '{snapshot_name}'"
            )

            return SnapshotMessage(
                success=True,
                message=CommandMessagesEnum.snapshot_revert_success.value,
                code=CommandMessagesEnum.snapshot_revert_success.name,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка восстановления до снапшота: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_revert_error.value,
                code=CommandMessagesEnum.snapshot_revert_error.name,
                note=str(e),
            )

    def update_snapshot_description(
        self, vm_name: str, snapshot_name: str, new_description: str
    ) -> SnapshotMessage:
        """
        Обновить описание снапшота

        Returns:
            SnapshotMessage с результатом операции
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotLookupByName(snapshot_name, flags=0)

            # Получение текущего XML снапшота
            snapshot_xml = snapshot.getXMLDesc(flags=0)

            # Обновление описания в XML
            root = ET.fromstring(snapshot_xml)

            # Поиск и обновление элемента description
            description_elem = root.find("description")
            if description_elem is not None:
                description_elem.text = new_description
            else:
                # Если элемента description нет, создаем его
                desc_elem = ET.SubElement(root, "description")
                desc_elem.text = new_description

            # Преобразование обратно в XML строку
            updated_xml = ET.tostring(root, encoding="unicode")

            # Создание нового снапшота с обновленным описанием и удаление старого
            new_snapshot = virtual_machine.snapshotCreateXML(
                updated_xml, flags=libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_CURRENT
            )

            if new_snapshot:
                self.logger.info(
                    f"Описание снапшота '{snapshot_name}' успешно обновлено"
                )
                current_snapshot = self.snapshot_by_name(
                    vm_name, snapshot_name
                )
                current_snapshot.message = (
                    CommandMessagesEnum.snapshot_update_success.value
                )
                current_snapshot.code = CommandMessagesEnum.snapshot_update_success.name
                return current_snapshot

            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_update_error.value,
                code=CommandMessagesEnum.snapshot_update_error.name,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка обновления описания снапшота: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_update_error.value,
                code=CommandMessagesEnum.snapshot_update_error.name,
                note=str(e),
            )
        except Exception as e:
            self.logger.error(f"Ошибка обработки XML: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_update_error.value,
                code=CommandMessagesEnum.snapshot_update_error.name,
                note=str(e),
            )

    def _get_snapshot_description(self, snapshot) -> str | None:
        """
        Извлечь описание снапшота из его XML-конфигурации

        Args:
            snapshot: Объект virDomainSnapshot

        Returns:
            Описание снапшота или пустую строку если описание отсутствует
        """
        try:
            xml_desc = snapshot.getXMLDesc(flags=0)
            root = ET.fromstring(xml_desc)

            # Ищем элемент description
            description_elem = root.find("description")

            if description_elem is not None and description_elem.text:
                return description_elem.text.strip()
            else:
                return None

        except Exception as e:
            self.logger.debug(f"Не удалось извлечь описание снапшота: {e}")
            return None

    def get_current_snapshot(self, vm_name: str) -> SnapshotMessage:
        """
        Получить текущий активный снапшот виртуальной машины

        Returns:
            SnapshotMessage с информацией о текущем снапшоте в rp_info
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotCurrent(flags=0)

            if snapshot:
                # Получаем XML снапшота для извлечения полной информации
                snapshot_xml = snapshot.getXMLDesc(flags=0)

                # Извлекаем информацию из XML
                snapshot_info_dict = self._parse_snapshot_xml(snapshot_xml)
                # Информация о родительском снапшоте
                try:
                    parent_snapshot = snapshot.getParent()
                    if parent_snapshot:
                        parent_xml = parent_snapshot.getXMLDesc(flags=0)
                        parent_info_dict = self._parse_snapshot_xml(parent_xml)
                        parent_size = self._get_snapshot_size(parent_snapshot)
                        vm_config_parent = VirtualMachine(
                            name=snapshot_info_dict.get("vm_name"),
                            uuid=parent_info_dict.get("uuid"),
                            max_memory=parent_info_dict.get("memory"),
                            memory=parent_info_dict.get("current_memory"),
                            vcpus=parent_info_dict.get("vcpu"),
                            state=parent_info_dict.get("state"),
                        )
                        parent_snapshot = Snapshot(
                            name=parent_snapshot.getName(),
                            vm_name=snapshot.getName(),
                            description=parent_info_dict.get("description"),
                            created=parent_info_dict.get("creation_time"),
                            state=parent_info_dict.get("state"),
                            is_current=parent_info_dict.get("current"),
                            size_bytes=parent_size,
                            disks=self._parse_snapshot_disks_xml(parent_xml),
                            vm_config=vm_config_parent,
                        )
                    else:
                        parent_snapshot = None
                except self.libvirtError:
                    parent_snapshot = None

                # Получение размера снапшота
                size = self._get_snapshot_size(snapshot)
                vm_config = VirtualMachine(
                    name=snapshot_info_dict.get("vm_name"),
                    uuid=snapshot_info_dict.get("uuid"),
                    max_memory=snapshot_info_dict.get("memory"),
                    memory=snapshot_info_dict.get("current_memory"),
                    vcpus=snapshot_info_dict.get("vcpu"),
                    state=snapshot_info_dict.get("state"),
                )
                snapshot_info = SnapshotWithParent(
                    name=snapshot.getName(),
                    description=snapshot_info_dict.get("description"),
                    created=snapshot_info_dict.get("creation_time"),
                    state=snapshot_info_dict.get("state"),
                    parent=parent_snapshot if parent_snapshot else None,
                    size_bytes=size,
                    vm_name=vm_name,
                    is_current=snapshot_info_dict.get("current"),
                    disks=self._parse_snapshot_disks_xml(snapshot_xml),
                    vm_config=vm_config,
                )
                return SnapshotMessage(
                    success=True,
                    message=CommandMessagesEnum.snapshot_found.value,
                    code=CommandMessagesEnum.snapshot_found.name,
                    snapshot_info=snapshot_info,
                )

            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_not_found.value,
                code=CommandMessagesEnum.snapshot_not_found.name,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения текущего снапшота: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_not_found.value,
                code=CommandMessagesEnum.snapshot_not_found.name,
                note=str(e),
            )

    def _parse_snapshot_disks_xml(self, xml_desc: str) -> list[Disk]:
        """
        Парсинг XML снапшота для извлечения информации

        Args:
            xml_desc: XML описание снапшота

        Returns:
            Словарь с извлеченной информацией
        """
        try:

            root = ET.fromstring(xml_desc)
            devices = root.find("domain").find("devices")
            disk_list = []
            disk_list_from_secion_disks = []
            for current_disk in root.find("disks").findall("disk"):
                disk_list_from_secion_disks.append(
                    SnapshotDiskInfo(
                        name=current_disk.get("name"),
                        snapshot=current_disk.get("snapshot"),
                    )
                )

            # Извлекаем memory
            disks = devices.findall("disk")
            for current_disk in disks:
                disk_path = current_disk.find("source").get("file")
                disk_name = os.path.basename(disk_path)
                disk_list.append(
                    Disk(
                        name=disk_name,
                        path=disk_path,
                        type=DiskType.SNAPSHOT,
                        format=current_disk.find("driver").get("type"),
                        bus_type=current_disk.find("target").get("bus"),
                        target_dev=current_disk.find("target").get("dev"),
                        file_path_exists=False,
                    )
                )
            target_dev_from_disk_list = tuple(
                sorted([current_disk.target_dev for current_disk in disk_list])
            )
            target_dev_from_disk_section_list = tuple(
                sorted(
                    [current_disk.name for current_disk in disk_list_from_secion_disks]
                )
            )
            if target_dev_from_disk_list != target_dev_from_disk_section_list:
                raise ValueError("Некорректное состояние дисков снапшота")

            return disk_list

        except Exception as e:
            self.logger.warning(f"Ошибка парсинга XML снапшота: {e}")
            return []

    def _parse_snapshot_xml(self, xml_desc: str) -> dict:
        """
        Парсинг XML снапшота для извлечения информации

        Args:
            xml_desc: XML описание снапшота

        Returns:
            Словарь с извлеченной информацией
        """
        try:

            root = ET.fromstring(xml_desc)
            result = {}

            # Извлекаем имя ВМ из снапшота
            name_elem = root.find("name")
            if name_elem is not None and name_elem.text:
                result["name"] = name_elem.text.strip()
            else:
                result["name"] = None

            # Извлекаем описание
            description_elem = root.find("description")
            if description_elem is not None and description_elem.text:
                result["description"] = description_elem.text.strip()
            else:
                result["description"] = None

            # Извлекаем имя ВМ
            vm_name_elem = root.find("domain").find("name")
            if vm_name_elem is not None and vm_name_elem.text:
                result["vm_name"] = vm_name_elem.text.strip()
            else:
                result["vm_name"] = None

            # Извлекаем memory
            memory_elem = root.find("domain").find("memory")
            if memory_elem is not None and memory_elem.text:
                result["memory"] = memory_elem.text.strip()
            else:
                result["memory"] = None

            # Извлекаем currentMemory
            current_memory_elem = root.find("domain").find("currentMemory")
            if current_memory_elem is not None and current_memory_elem.text:
                result["current_memory"] = current_memory_elem.text.strip()
            else:
                result["current_memory"] = None

            # Извлекаем vcpu
            vcpu_elem = root.find("domain").find("vcpu")
            if vcpu_elem is not None and vcpu_elem.text:
                result["vcpu"] = vcpu_elem.get("current")
                result["max_vcpus"] = vcpu_elem.text.strip()
            else:
                result["vcpu"] = None
                result["max_vcpus"] = None

            # Извлекаем время создания
            creation_time_elem = root.find("creationTime")
            if creation_time_elem is not None and creation_time_elem.text:
                try:
                    result["creation_time"] = int(creation_time_elem.text)
                except ValueError:
                    result["creation_time"] = None
            else:
                result["creation_time"] = None

            # Извлекаем состояние
            state_elem = root.find("state")
            if state_elem is not None and state_elem.text:
                result["state"] = VMState.__dict__.get(state_elem.text.upper()).value
            else:
                result["state"] = None

            # Дополнительно: родительский снапшот (для цепочки)
            parent_elem = root.find("parent")
            if parent_elem is not None:
                # У родителя может быть атрибут name
                parent_name = parent_elem.get("name")
                if parent_name:
                    result["parent_name"] = parent_name

                # Или текст внутри элемента
                elif parent_elem.text:
                    result["parent_name"] = parent_elem.text.strip()
                else:
                    result["parent_name"] = None
            else:
                result["parent_name"] = None

            uuid_elem = root.find("domain").find("uuid")
            if uuid_elem is not None and uuid_elem.text:
                result["uuid"] = uuid_elem.text.strip()
            else:
                result["uuid"] = None

            # 2. Дочерние снапшоты (если есть)
            children_elem = root.find("children")
            if children_elem is not None:
                children = []
                for child in children_elem.findall("snapshot"):
                    child_name = child.find("name")
                    if child_name is not None and child_name.text:
                        children.append(child_name.text.strip())
                result["children"] = children
            else:
                result["children"] = []

            # 3. Флаги активности
            result["active"] = (
                root.get("active") == "1" if root.get("active") else False
            )
            result["current"] = (
                root.get("current") == "1" if root.get("current") else False
            )

            return result

        except Exception as e:
            self.logger.warning(f"Ошибка парсинга XML снапшота: {e}")
            return {
                "name": None,
                "description": None,
                "creation_time": None,
                "state": None,
                "parent_name": None,
            }

    def clone_vm_from_snapshot(
        self, request: SnapshotCloneRequest
    ) -> SnapshotMessage:
        """
        Клонировать ВМ из снапшота

        Returns:
            SnapshotMessage с результатом операции
        """
        try:

            # Получаем исходную ВМ
            source_vm = self.conn.lookupByName(request.source_vm_name)
            new_uuid = str(uuid.uuid4())

            # Получаем снапшот
            snapshot = source_vm.snapshotLookupByName(
                request.source_snapshot_name, flags=0
            )

            # Получаем XML конфигурации ВМ из снапшота
            snapshot_xml = snapshot.getXMLDesc(flags=libvirt.VIR_DOMAIN_XML_SECURE)

            # Парсим XML
            root = ET.fromstring(snapshot_xml)

            # Обновляем имя ВМ
            name_elem = root.find("domain").find("name")
            if name_elem is not None:
                name_elem.text = request.new_vm_name

            # Генерируем новый UUID если нужно
            if request.generate_new_uuid:
                uuid_elem = root.find("domain").find("uuid")
                if uuid_elem is not None:
                    uuid_elem.text = new_uuid

            # Обновляем пути к дискам для новой ВМ
            for disk_elem in root.findall(".//disk"):
                source_elem = disk_elem.find("source")
                if source_elem is not None and "file" in source_elem.attrib:
                    old_path = source_elem.get("file")
                    if old_path:
                        # Создаем новый путь для диска
                        dir_name = os.path.dirname(old_path)
                        base_name = os.path.basename(old_path)
                        new_path = os.path.join(
                            dir_name, f"{request.new_vm_name}_{base_name}"
                        )

                        # Копируем диск
                        try:
                            shutil.copy2(old_path, new_path)
                            source_elem.set("file", new_path)
                        except Exception as e:
                            self.logger.error(
                                f"Ошибка копирования диска {old_path}: {e}"
                            )
                            return SnapshotMessage(
                                success=False,
                                message=CommandMessagesEnum.snapshot_clone_error.value,
                                code=CommandMessagesEnum.snapshot_clone_error.name,
                                note=str(e),
                            )

            # Преобразуем XML обратно в строку
            new_xml = ET.tostring(root.find("domain"), encoding="unicode")

            # Создаем новую ВМ
            new_domain = self.conn.defineXML(new_xml)

            if new_domain:
                self.logger.info(
                    f"ВМ '{request.new_vm_name}' успешно клонирована из снапшота '{request.source_snapshot_name}'"
                )

                # Запускаем ВМ если исходная была запущена
                source_state, _ = source_vm.state()
                # if source_state == libvirt.VIR_DOMAIN_RUNNING:
                #     new_domain.create()
                return SnapshotMessage(
                    success=True,
                    message=CommandMessagesEnum.snapshot_clone_success.value,
                    code=CommandMessagesEnum.snapshot_clone_success.name,
                    snapshot_info=ClonedSnapshot(
                        source_vm_name=request.source_vm_name,
                        source_snapshot_name=request.source_snapshot_name,
                        new_vm_name=request.new_vm_name,
                        new_uuid=new_uuid,
                        vm_started=source_state == libvirt.VIR_DOMAIN_RUNNING,
                    ),
                )

            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_clone_error.value,
                code=CommandMessagesEnum.snapshot_clone_error.name,
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка клонирования ВМ из снапшота: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_clone_error.value,
                code=CommandMessagesEnum.snapshot_clone_error.name,
                note=str(e),
            )
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при клонировании ВМ: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_clone_error.value,
                code=CommandMessagesEnum.snapshot_clone_error.name,
                note=str(e),
            )

    def create_snapshot_chain(
        self,
        vm_name: str,
        snapshot_names: list[str],
        descriptions: list[str] = None,
    ) -> SnapshotMessage:
        """
        Создать цепочку снапшотов

        Returns:
            SnapshotMessage с результатом операции
        """

        if descriptions is None:
            descriptions = [""] * len(snapshot_names)

        if len(snapshot_names) != len(descriptions):
            return SnapshotMessage(
                success=False,
                message="Number of snapshot names and descriptions does not match",
                code="SNAPSHOT_CHAIN_INVALID_PARAMS",
            )

        created_snapshots = []
        errors = []

        try:
            virtual_machine = self.conn.lookupByName(vm_name)

            for i, (snapshot_name, description) in enumerate(
                zip(snapshot_names, descriptions)
            ):
                try:
                    # Подготовка XML для снапшота
                    snapshot_xml = f"""
                    <domainsnapshot>
                        <name>{snapshot_name}</name>
                        <description>{description}</description>
                    </domainsnapshot>
                    """

                    # Создание снапшота
                    snapshot = virtual_machine.snapshotCreateXML(snapshot_xml, flags=0)

                    if snapshot:
                        created_snapshot = self.snapshot_by_name(
                            vm_name, snapshot_name
                        )
                        created_snapshots.append(created_snapshot.snapshot_info)
                        self.logger.info(
                            f"Снапшот {i + 1}/{len(snapshot_names)} создан: {snapshot_name}"
                        )
                    else:
                        errors.append(f"Failed to create snapshot {snapshot_name}")

                except self.libvirtError as e:
                    errors.append(f"Error creating snapshot {snapshot_name}: {str(e)}")
                    # Прерываем цепочку при ошибке
                    break

            if errors:
                return SnapshotMessage(
                    success=False,
                    message=CommandMessagesEnum.snapshot_create_error.value,
                    code=CommandMessagesEnum.snapshot_create_error.name,
                    snapshot_info=CreateSnapshotChainError(
                        vm_name=vm_name,
                        created_snapshots=created_snapshots,
                        errors=errors,
                        total_requested=len(created_snapshots),
                        successfully_created=len(created_snapshots),
                    ),
                    note="; ".join(errors),
                )

            return SnapshotMessage(
                success=True,
                message=CommandMessagesEnum.snapshot_successfully_created.value,
                code=CommandMessagesEnum.snapshot_successfully_created.name,
                snapshot_info=CreateSnapshotChainSuccess(
                    vm_name=vm_name,
                    created_snapshots=created_snapshots,
                    total_created=len(created_snapshots),
                    chain_depth=len(created_snapshots),
                ),
            )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка создания цепочки снапшотов: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_create_error.value,
                code=CommandMessagesEnum.snapshot_create_error.name,
                note=str(e),
            )

    def create_multiple_vm_snapshots(
        self, request: MultipleSnapshotsRequest
    ) -> SnapshotMessage:
        """
        Создать снапшоты для нескольких ВМ одновременно

        Returns:
            SnapshotMessage с результатами операций
        """
        results = []
        errors = []
        successful = 0

        for snapshot_request in request.snapshots:
            try:
                result = self.create_snapshot(snapshot_request)
                results.append(result)

                if not result.success:
                    errors.append(f"{snapshot_request.vm_name}: {result.message}")
                else:
                    successful += 1

            except Exception as e:
                errors.append(f"{snapshot_request.vm_name}: {str(e)}")

        if errors:
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_create_error.value,
                code=CommandMessagesEnum.snapshot_create_error.name,
                snapshot_info=CreateMultipleSnapshotsError(
                    results=results,
                    total_requested=len(results),
                    successful=successful,
                    failed=len(errors),
                ),
                note="; ".join(errors),
            )

        return SnapshotMessage(
            success=True,
            message=CommandMessagesEnum.snapshot_successfully_created.value,
            code=CommandMessagesEnum.snapshot_successfully_created.name,
            snapshot_info=CreateMultipleSnapshots(
                results=results, total_created=len(results), successful=len(results)
            ),
        )

    def revert_to_parent_snapshot(
        self, vm_name: str, snapshot_name: str
    ) -> SnapshotMessage:
        """
        Восстановить ВМ до родительского снапшота (откат к более раннему состоянию)

        Returns:
            SnapshotMessage с результатом операции
        """
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            snapshot = virtual_machine.snapshotLookupByName(snapshot_name, flags=0)

            # Получаем родительский снапшот
            try:
                parent_snapshot = snapshot.getParent()
                if parent_snapshot:
                    parent_name = parent_snapshot.getName()

                    # Восстанавливаем до родительского снапшота
                    virtual_machine.revertToSnapshot(parent_snapshot, flags=0)

                    # Получаем список снапшотов после родительского (включая текущий)
                    snapshots_after = self._get_snapshots_after(vm_name, parent_name)

                    self.logger.info(
                        f"VM '{vm_name}' восстановлена до родительского снапшота '{parent_name}'"
                    )

                    return SnapshotMessage(
                        success=True,
                        message=CommandMessagesEnum.snapshot_revert_success.value,
                        code=CommandMessagesEnum.snapshot_revert_success.name,
                        snapshot_info=SnapshotRevertSuccess(
                            vm_name=vm_name,
                            current_snapshot=snapshot_name,
                            parent_snapshot=parent_name,
                            snapshots_made_inactive=[s.name for s in snapshots_after],
                            note="Snapshots created after parent have become inactive",
                        ),
                    )
                else:
                    return SnapshotMessage(
                        success=False,
                        message=CommandMessagesEnum.snapshot_not_found.value,
                        code=CommandMessagesEnum.snapshot_not_found.name,
                        note="Cannot revert to parent snapshot: no parent found",
                    )

            except self.libvirtError as e:
                return SnapshotMessage(
                    success=False,
                    message=CommandMessagesEnum.snapshot_revert_error.value,
                    code=CommandMessagesEnum.snapshot_revert_error.name,
                    note=str(e),
                )

        except self.libvirtError as e:
            self.logger.error(f"Ошибка восстановления до родительского снапшота: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_revert_error.value,
                code=CommandMessagesEnum.snapshot_revert_error.name,
                note=str(e),
            )

    def get_snapshot_chain(self, vm_name: str) -> SnapshotMessage:
        """
        Получить цепочку снапшотов ВМ с детальной информацией

        Returns:
            SnapshotMessage с информацией о цепочке снапшотов
        """
        try:
            # Получаем все снапшоты ВМ
            snapshots_msg = self.snapshots_by_vm_name(vm_name)

            if snapshots_msg.message == CommandMessagesEnum.snapshot_list_error.value:
                return snapshots_msg

            snapshots_info = snapshots_msg.snapshot_info.snapshots

            # Строим дерево снапшотов
            snapshot_tree = self._build_snapshot_tree(snapshots_info)

            # Находим корневые снапшоты (без родителей)
            root_snapshots = [s for s in snapshots_info if not s.parent]

            # Строим цепочки
            chains = []
            for root in root_snapshots:
                chain = self._build_chain_from_root(root.name, snapshots_info)
                chains.append(chain)

            return SnapshotMessage(
                success=True,
                message=CommandMessagesEnum.snapshot_found.value,
                code=CommandMessagesEnum.snapshot_found.name,
                snapshot_info=SnapshotsChain(
                    vm_name=vm_name,
                    snapshots=snapshots_info,
                    snapshot_tree=snapshot_tree,
                    chains=chains,
                    root_snapshots=[s.name for s in root_snapshots],
                    chain_depth=max([len(c) for c in chains]) if chains else 0,
                ),
            )

        except Exception as e:
            self.logger.error(f"Ошибка получения цепочки снапшотов: {e}")
            return SnapshotMessage(
                success=False,
                message=CommandMessagesEnum.snapshot_not_found.value,
                code=CommandMessagesEnum.snapshot_not_found.name,
                note=str(e),
            )

    # Вспомогательные методы

    def _get_snapshot_size(self, snapshot) -> int:
        """Получить размер снапшота в байтах"""
        try:
            xml_desc = snapshot.getXMLDesc(flags=0)
            root = ET.fromstring(xml_desc)

            total_size = 0

            # Ищем диски в снапшоте
            for disk in root.findall(".//disk"):
                # Получаем источник диска
                source = disk.find("source")
                if source is not None:
                    # Проверяем атрибуты файла или устройства
                    file_path = source.get("file")
                    if file_path and os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)

                    # Для других типов источников можно добавить дополнительную логику

            return total_size

        except Exception as e:
            self.logger.warning(f"Не удалось определить размер снапшота: {e}")
            return 0

    def _check_disk_space(self, vm_name: str, required_gb: int = 1) -> bool:
        """Проверить наличие свободного места в хранилище"""
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            xml_desc = virtual_machine.XMLDesc(flags=0)
            root = ET.fromstring(xml_desc)

            # Ищем пути к дискам
            disk_paths = []
            for disk in root.findall(".//disk"):
                source = disk.find("source")
                if source is not None:
                    file_path = source.get("file")
                    if file_path:
                        disk_paths.append(file_path)

            # Проверяем свободное место для первого диска (упрощенная проверка)
            if disk_paths:
                disk_path = disk_paths[0]
                disk_dir = os.path.dirname(disk_path)

                # Получаем статистику использования диска
                stat = os.statvfs(disk_dir)
                free_space_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)

                # Требуется хотя бы 1GB свободного места
                return free_space_gb >= required_gb

            return True

        except Exception as e:
            self.logger.warning(f"Не удалось проверить свободное место: {e}")
            return True  # В случае ошибки разрешаем создание снапшота

    def _get_snapshots_after(self, vm_name: str, snapshot_name: str) -> list:
        """Получить снапшоты, созданные после указанного снапшота"""
        try:
            virtual_machine = self.conn.lookupByName(vm_name)
            all_snapshots = virtual_machine.listAllSnapshots(flags=0)

            # Находим целевой снапшот
            target_snapshot = None
            for snapshot in all_snapshots:
                if snapshot.getName() == snapshot_name:
                    target_snapshot = snapshot
                    break

            if not target_snapshot:
                return []

            # Получаем все потомки целевого снапшота
            descendants = []

            def get_descendants(current_snapshot: libvirt.virDomainSnapshot):
                try:
                    children = current_snapshot.listAllChildren(flags=0)
                    for child in children:
                        descendants.append(child)
                        get_descendants(child)
                except self.libvirtError:
                    pass

            get_descendants(target_snapshot)

            return descendants

        except self.libvirtError:
            return []

    @staticmethod
    def _calculate_chain_depth(snapshots: list[SnapshotWithParent]) -> int:
        """Рассчитать глубину цепочки снапшотов"""
        if not snapshots:
            return 0

        # Находим максимальную длину цепочки
        max_depth = 0

        def get_depth(snapshot_name, snapshots_dict, current_depth):
            nonlocal max_depth
            max_depth = max(max_depth, current_depth)

            # Ищем детей этого снапшота
            for snapshot in snapshots_dict.values():
                if snapshot.parent and snapshot.parent.name == snapshot_name:
                    get_depth(snapshot.name, snapshots_dict, current_depth + 1)

        # Создаем словарь для быстрого поиска
        snapshots_dict = {s.name: s for s in snapshots}

        # Находим корневые снапшоты (без родителей)
        root_snapshots = [s for s in snapshots if not s.parent]

        for root in root_snapshots:
            get_depth(root.name, snapshots_dict, 1)

        return max_depth

    @staticmethod
    def _build_snapshot_tree(snapshots_info: list[SnapshotWithParent]) -> dict:
        """Построить дерево снапшотов"""
        tree = {}

        # Создаем узлы для всех снапшотов
        for snapshot in snapshots_info:
            tree[snapshot.name] = {"info": snapshot, "children": []}

        # Строим связи родитель-ребенок
        for snapshot in snapshots_info:
            if snapshot.parent:
                parent_name = snapshot.parent.name
                if parent_name and parent_name in tree:
                    tree[parent_name]["children"].append(snapshot.name)

        # Находим корневые узлы
        root_nodes = [name for name, node in tree.items() if not node["info"].parent]

        return {"nodes": tree, "roots": root_nodes}

    @staticmethod
    def _build_chain_from_root(
        root_name: str, snapshots_info: list[SnapshotWithParent]
    ) -> list[SnapshotWithParent]:
        """Построить цепочку начиная с корневого снапшота"""
        chain = []

        # Создаем словарь для быстрого поиска
        snapshots_dict = {s.name: s for s in snapshots_info}

        current_name = root_name
        while current_name in snapshots_dict:
            current_snapshot = snapshots_dict[current_name]
            chain.append(current_snapshot)

            # Ищем следующего ребенка
            next_snapshot = None
            for snapshot in snapshots_info:
                if snapshot.parent and snapshot.parent.name == current_name:
                    next_snapshot = snapshot.name
                    break

            if next_snapshot:
                current_name = next_snapshot
            else:
                break

        return chain
