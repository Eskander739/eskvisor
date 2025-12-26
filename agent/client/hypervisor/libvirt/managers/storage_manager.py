import libvirt
import os
import re
from datetime import datetime

from agent.client.hypervisor.models.disk import (
    Disk, DiskCreate, DiskUpdate, DiskAttach, DiskDetach, DiskQuery,
    DiskFormat, DiskType, DiskStatus, BusType
)
from agent.client.hypervisor.libvirt.client import LibvirtClient


class StorageManager(LibvirtClient):
    """
    Управление хранилищами виртуальных дисков
    """

    def create_disk(self, disk_create: DiskCreate) -> Disk | None:
        """
        Создать новый виртуальный диск в указанном пуле хранилищ

        Args:
            disk_create: Модель для создания диска

        Returns:
            Disk: Созданный диск или None при ошибке
        """
        try:
            pool = self.conn.storagePoolLookupByName(disk_create.pool)

            # Получаем информацию о пуле
            pool_info = pool.info()
            if pool_info.state != libvirt.VIR_STORAGE_POOL_RUNNING:
                pool.create()

            # Создаем XML для диска
            size_bytes = int(disk_create.size_gb * 1024 * 1024 * 1024)

            xml_desc = f'''
            <volume>
                <name>{disk_create.name}</name>
                <capacity unit="bytes">{size_bytes}</capacity>
                <target>
                    <format type='{disk_create.format.value}'/>
                    <permissions>
                        <mode>0644</mode>
                    </permissions>
                </target>
                <backingStore/>
            </volume>
            '''

            # Создаем том
            vol = pool.createXML(xml_desc, 0)

            # Если не sparse и формат raw, заполняем диск нулями
            if not disk_create.sparse and disk_create.format == DiskFormat.RAW:
                stream = self.conn.newStream()
                vol.download(stream, 0, 0, 0)
                # Записываем нули
                zero_data = b'\0' * 1024 * 1024  # 1MB блоки
                for _ in range(int(disk_create.size_gb * 1024)):  # size_gb в MB
                    stream.send(zero_data)
                stream.finish()

            # Получаем информацию о созданном диске
            return self.get_disk_info(disk_create.pool, disk_create.name)

        except libvirt.libvirtError as e:
            print(f"Ошибка при создании диска: {e}")
            return None

    def delete_disk(self, pool_name: str, disk_name: str) -> bool:
        """
        Удалить виртуальный диск

        Args:
            pool_name: Имя пула хранилищ
            disk_name: Имя удаляемого диска

        Returns:
            bool: Успешность операции
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(disk_name)

            # Проверяем, не используется ли диск в активных ВМ
            # (это можно расширить при необходимости)

            # Удаляем диск
            vol.delete(0)
            return True

        except libvirt.libvirtError as e:
            print(f"Ошибка при удалении диска: {e}")
            return False

    def edit_disk(self, pool_name: str, disk_name: str, disk_update: DiskUpdate) -> Disk | None:
        """
        Изменить параметры виртуального диска

        Args:
            pool_name: Имя пула хранилищ
            disk_name: Имя изменяемого диска
            disk_update: Модель обновления диска

        Returns:
            Disk: Обновленный диск или None при ошибке
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(disk_name)

            changes = []

            # Изменение размера (только увеличение)
            if disk_update.new_size_gb is not None:
                vol_info = vol.info()
                current_size_gb = vol_info[1] / (1024 ** 3)

                if disk_update.new_size_gb > current_size_gb:
                    new_size_bytes = int(disk_update.new_size_gb * 1024 * 1024 * 1024)
                    vol.resize(new_size_bytes, 0)
                    changes.append(f"размер изменен на {disk_update.new_size_gb}GB")
                else:
                    print("Предупреждение: уменьшение размера диска не поддерживается напрямую")

            # Переименование
            if disk_update.name is not None and disk_update.name != disk_name:
                xml_desc = vol.XMLDesc()
                # Обновляем имя в XML
                new_xml = xml_desc.replace(f"<name>{disk_name}</name>", f"<name>{disk_update.name}</name>")

                # Создаем новый том с новым именем
                new_vol = pool.createXML(new_xml, 0)

                # Удаляем старый том
                vol.delete(0)

                changes.append(f"имя изменено на {disk_update.name}")
                disk_name = disk_update.name

            if changes:
                print(f"Диск изменен: {', '.join(changes)}")
                return self.get_disk_info(pool_name, disk_name)
            else:
                print("Не указано изменений")
                return self.get_disk_info(pool_name, disk_name)

        except libvirt.libvirtError as e:
            print(f"Ошибка при изменении диска: {e}")
            return None

    def attach_disk_to_vm(self, pool_name: str, disk_name: str, disk_attach: DiskAttach) -> Disk | None:
        """
        Добавить диск к виртуальной машине

        Args:
            pool_name: Имя пула хранилищ
            disk_name: Имя диска для добавления
            disk_attach: Модель для подключения диска

        Returns:
            Disk: Подключенный диск или None при ошибке
        """
        try:
            # Находим ВМ
            vm = self.conn.lookupByName(disk_attach.vm_name)

            # Находим диск в пуле
            pool = self.conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(disk_name)

            # Получаем информацию о диске
            disk_info = self.get_disk_info(pool_name, disk_name)
            if not disk_info:
                return None

            # Получаем путь к диску
            disk_path = vol.path()

            # Создаем XML для устройства диска
            disk_xml = f'''
            <disk type='file' device='disk'>
                <driver name='qemu' type='{disk_info.format.value}'/>
                <source file='{disk_path}'/>
                <target dev='{disk_attach.target_dev}' bus='{disk_attach.bus_type.value}'/>
                <address type='pci' domain='0x0000' bus='0x00' slot='0x0a' function='0x0'/>
            </disk>
            '''

            # Присоединяем диск к ВМ
            vm.attachDevice(disk_xml)

            print(f"Диск {disk_name} успешно добавлен к ВМ {disk_attach.vm_name} как {disk_attach.target_dev}")

            # Обновляем информацию о диске
            disk_info.vm_name = disk_attach.vm_name
            disk_info.status = DiskStatus.ATTACHED
            disk_info.target_dev = disk_attach.target_dev
            disk_info.bus_type = disk_attach.bus_type
            disk_info.cache_mode = disk_attach.cache_mode

            return disk_info

        except libvirt.libvirtError as e:
            print(f"Ошибка при добавлении диска к ВМ: {e}")
            return None

    def detach_disk_from_vm(self, disk_detach: DiskDetach) -> bool:
        """
        Отключить диск от виртуальной машины

        Args:
            disk_detach: Модель для отключения диска

        Returns:
            bool: Успешность операции
        """
        try:
            vm = self.conn.lookupByName(disk_detach.vm_name)

            # Получаем текущую конфигурацию ВМ
            xml_desc = vm.XMLDesc()

            # Находим XML блока диска для данного устройства
            lines = xml_desc.split('\n')
            disk_start = -1
            disk_end = -1

            for i, line in enumerate(lines):
                if f"<target dev='{disk_detach.target_dev}'" in line:
                    # Ищем начало блока диска
                    for j in range(i, -1, -1):
                        if '<disk ' in lines[j]:
                            disk_start = j
                            break
                    # Ищем конец блока диска
                    for j in range(i, len(lines)):
                        if '</disk>' in lines[j]:
                            disk_end = j
                            break
                    break

            if disk_start != -1 and disk_end != -1:
                # Извлекаем XML диска
                disk_xml = '\n'.join(lines[disk_start:disk_end + 1])

                # Отключаем диск
                vm.detachDevice(disk_xml)

                print(f"Диск {disk_detach.target_dev} успешно отключен от ВМ {disk_detach.vm_name}")
                return True
            else:
                print(f"Устройство {disk_detach.target_dev} не найдено в конфигурации ВМ")
                return False

        except libvirt.libvirtError as e:
            print(f"Ошибка при отключении диска от ВМ: {e}")
            return False

    def get_disk_info(self, pool_name: str, disk_name: str) -> Disk | None:
        """
        Получить информацию о диске

        Args:
            pool_name: Имя пула хранилищ
            disk_name: Имя диска

        Returns:
            Disk: Информация о диске или None при ошибке
        """
        try:
            pool = self.conn.storagePoolLookupByName(pool_name)
            vol = pool.storageVolLookupByName(disk_name)

            vol_info = vol.info()
            vol_xml = vol.XMLDesc()

            # Определяем формат диска
            disk_format = DiskFormat.UNKNOWN
            if 'type=\'qcow2\'' in vol_xml:
                disk_format = DiskFormat.QCOW2
            elif 'type=\'raw\'' in vol_xml:
                disk_format = DiskFormat.RAW

            # Парсим даты из XML
            created = None
            modified = None

            # Ищем timestamp в XML
            timestamp_match = re.search(r'<timestamp>(\d+)</timestamp>', vol_xml)
            if timestamp_match:
                timestamp = int(timestamp_match.group(1))
                created = datetime.fromtimestamp(timestamp)

            # Создаем объект Disk
            disk = Disk(
                name=disk_name,
                path=vol.path(),
                type=DiskType.POOL_DISK,
                format=disk_format,
                capacity_bytes=vol_info[1],
                allocation_bytes=vol_info[2],
                pool=pool_name,
                status=DiskStatus.DETACHED,
                created=created
            )

            return disk

        except libvirt.libvirtError as e:
            print(f"Ошибка при получении информации о диске: {e}")
            return None

    def list_disks(self, query: DiskQuery | None = None) -> list[Disk]:
        """
        Получить список всех дисков с фильтрацией

        Args:
            query: Параметры фильтрации

        Returns:
            list[Disk]: Список дисков
        """
        disks = []
        try:
            # Сначала соберем все диски из пулов хранилищ
            pool_disks = self._get_pool_disks(query)
            disks.extend(pool_disks)

            # Затем получим информацию о дисках, подключенных к ВМ
            attached_disks = self._get_attached_disks(query, pool_disks)
            disks.extend(attached_disks)

            # Применяем фильтр по подключенным дискам
            if query and query.attached_only is not None:
                if query.attached_only:
                    disks = [d for d in disks if d.status == DiskStatus.ATTACHED]
                else:
                    disks = [d for d in disks if d.status != DiskStatus.ATTACHED]

            return disks

        except libvirt.libvirtError as e:
            print(f"Ошибка при получении списка дисков: {e}")
            return []

    def _get_pool_disks(self, query: DiskQuery | None) -> list[Disk]:
        """Получить диски из пулов хранилищ"""
        disks = []

        if query and query.pool:
            # Конкретный пул
            try:
                pools = [self.conn.storagePoolLookupByName(query.pool)]
            except libvirt.libvirtError:
                pools = []
        else:
            # Все пулы
            pools = self.conn.listAllStoragePools()

        for pool in pools:
            try:
                pool_info = pool.info()
                if pool_info.state != libvirt.VIR_STORAGE_POOL_RUNNING:
                    try:
                        pool.create(0)
                    except:
                        continue

                pool_name = pool.name()

                volumes = pool.listAllVolumes()
                for vol in volumes:
                    try:
                        disk = self._volume_to_disk(vol, pool_name)
                        if disk and self._filter_disk(disk, query):
                            disks.append(disk)
                    except libvirt.libvirtError:
                        continue

            except libvirt.libvirtError:
                continue

        return disks

    def _get_attached_disks(self, query: DiskQuery | None, pool_disks: list[Disk]) -> list[Disk]:
        """Получить информацию о дисках, подключенных к ВМ"""
        attached_disks = []

        try:
            # Получаем все ВМ
            vm_ids = self.conn.listDomainsID()
            all_vms = []

            # Активные ВМ
            for vm_id in vm_ids:
                vm = self.conn.lookupByID(vm_id)
                all_vms.append(vm)

            # Неактивные ВМ
            for vm_name in self.conn.listDefinedDomains():
                vm = self.conn.lookupByName(vm_name)
                all_vms.append(vm)

            # Сопоставляем диски из ВМ с дисками из пулов
            for vm in all_vms:
                try:
                    vm_name = vm.name()

                    # Проверяем фильтр по ВМ
                    if query and query.vm_name and query.vm_name != vm_name:
                        continue

                    # Получаем XML конфигурации ВМ
                    xml_desc = vm.XMLDesc()

                    # Ищем все диски в XML ВМ
                    disk_blocks = self._extract_disk_blocks_from_vm_xml(xml_desc)

                    for disk_block in disk_blocks:
                        disk_path = disk_block.get('source_file')
                        target_dev = disk_block.get('target_dev')
                        bus_type_str = disk_block.get('bus_type')
                        driver_type = disk_block.get('driver_type')

                        if not disk_path:
                            continue

                        # Ищем диск в списке дисков из пулов
                        found_disk = None
                        for pool_disk in pool_disks:
                            if pool_disk.path == disk_path:
                                found_disk = pool_disk
                                break

                        if found_disk:
                            # Обновляем информацию о подключенном диске
                            found_disk.vm_name = vm_name
                            found_disk.status = DiskStatus.ATTACHED
                            found_disk.target_dev = target_dev

                            # Преобразуем строковый bus_type в enum
                            if bus_type_str:
                                try:
                                    found_disk.bus_type = BusType(bus_type_str)
                                except ValueError:
                                    found_disk.bus_type = None
                        else:
                            # Диск не найден в пулах, создаем новый объект
                            disk = self._create_disk_from_vm_attachment(
                                disk_path, vm_name, target_dev, bus_type_str, driver_type
                            )
                            if disk and self._filter_disk(disk, query):
                                attached_disks.append(disk)

                except libvirt.libvirtError:
                    continue

        except libvirt.libvirtError:
            pass

        return attached_disks

    def _extract_disk_blocks_from_vm_xml(self, xml_desc: str) -> list[dict]:
        """Извлечь информацию о дисках из XML ВМ"""
        disk_blocks = []

        # Парсим XML для поиска блоков дисков
        lines = xml_desc.split('\n')
        i = 0

        while i < len(lines):
            if '<disk ' in lines[i]:
                disk_block = {}
                j = i

                # Читаем до закрывающего тега </disk>
                while j < len(lines) and '</disk>' not in lines[j]:
                    line = lines[j]

                    # Извлекаем путь к файлу диска
                    if 'file=' in line:
                        match = re.search(r"file=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['source_file'] = match.group(1)

                    # Извлекаем целевое устройство
                    if 'target dev=' in line:
                        match = re.search(r"dev=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['target_dev'] = match.group(1)

                    # Извлекаем тип шины
                    if 'bus=' in line:
                        match = re.search(r"bus=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['bus_type'] = match.group(1)

                    # Извлекаем тип драйвера
                    if 'type=' in line and 'driver' in line:
                        match = re.search(r"type=['\"]([^'\"]+)['\"]", line)
                        if match:
                            disk_block['driver_type'] = match.group(1)

                    j += 1

                if disk_block:
                    disk_blocks.append(disk_block)

                i = j + 1
            else:
                i += 1

        return disk_blocks

    def _create_disk_from_vm_attachment(self, disk_path: str, vm_name: str,
                                        target_dev: str, bus_type_str: str,
                                        driver_type: str) -> Disk | None:
        """Создать объект Disk для диска, подключенного к ВМ, но не найденного в пулах"""
        try:
            # Определяем формат диска
            disk_format = DiskFormat.UNKNOWN
            if driver_type == 'qcow2':
                disk_format = DiskFormat.QCOW2
            elif driver_type == 'raw':
                disk_format = DiskFormat.RAW

            # Если не удалось определить по driver_type, пробуем по расширению
            if disk_format == DiskFormat.UNKNOWN:
                if disk_path.endswith('.qcow2'):
                    disk_format = DiskFormat.QCOW2
                elif disk_path.endswith('.raw') or disk_path.endswith('.img'):
                    disk_format = DiskFormat.RAW

            # Получаем размер файла
            size_bytes = 0
            if os.path.exists(disk_path):
                size_bytes = os.path.getsize(disk_path)

            # Преобразуем bus_type
            bus_type = None
            if bus_type_str:
                try:
                    bus_type = BusType(bus_type_str)
                except ValueError:
                    bus_type = None

            disk = Disk(
                name=os.path.basename(disk_path),
                path=disk_path,
                type=DiskType.VM_ATTACHED,
                format=disk_format,
                capacity_bytes=size_bytes,
                vm_name=vm_name,
                status=DiskStatus.ATTACHED,
                target_dev=target_dev,
                bus_type=bus_type
            )

            return disk
        except Exception as e:
            print(f"Ошибка при создании диска из подключения ВМ: {e}")
            return None

    def _volume_to_disk(self, vol, pool_name: str) -> Disk | None:
        """Преобразовать libvirt volume в объект Disk"""
        try:
            vol_info = vol.info()
            vol_xml = vol.XMLDesc()

            # Определяем формат диска
            disk_format = DiskFormat.UNKNOWN
            if 'type=\'qcow2\'' in vol_xml:
                disk_format = DiskFormat.QCOW2
            elif 'type=\'raw\'' in vol_xml:
                disk_format = DiskFormat.RAW

            disk = Disk(
                name=vol.name(),
                path=vol.path(),
                type=DiskType.POOL_DISK,
                format=disk_format,
                capacity_bytes=vol_info[1],
                allocation_bytes=vol_info[2],
                pool=pool_name,
                status=DiskStatus.DETACHED
            )

            return disk
        except libvirt.libvirtError:
            return None

    def _filter_disk(self, disk: Disk, query: DiskQuery | None) -> bool:
        """Применить фильтры к диску"""
        if not query:
            return True

        # Фильтр по формату
        if query.format and disk.format != query.format:
            return False

        # Фильтр по размеру
        size_gb = disk.get_effective_size_gb()
        if query.min_size_gb is not None and size_gb < query.min_size_gb:
            return False
        if query.max_size_gb is not None and size_gb > query.max_size_gb:
            return False

        # Фильтр по ВМ (для подключенных дисков)
        if query.vm_name and disk.vm_name != query.vm_name:
            return False

        # Фильтр по пулу (для дисков в пулах)
        if query.pool and disk.pool != query.pool:
            return False

        return True


if __name__ == "__main__":
    manager = StorageManager()

    # Пример использования новых методов

    # Создать диск
    # disk_create = DiskCreate(
    #     name="vm-disk.qcow2",
    #     pool="default-pool",
    #     size_gb=1,
    #     format=DiskFormat.QCOW2,
    #     sparse=True
    # )
    # created_disk = manager.create_disk(disk_create)
    # print(f"Создан диск: {created_disk.name if created_disk else 'Ошибка'}")

    # Получение списка дисков
    with StorageManager() as mng:
        # Без фильтров
        all_disks = mng.list_disks()
        print(f"Всего дисков: {len(all_disks)}")

        # Выводим информацию о каждом диске
        for disk in all_disks:
            print(f"Диск: {disk.name}, Тип: {disk.type}, "
                  f"Статус: {disk.status}, ВМ: {disk.vm_name}")

        # С фильтром
        query = DiskQuery(
            pool="default-pool",
            min_size_gb=1,
            format=DiskFormat.QCOW2
        )
        filtered_disks = mng.list_disks(query)
        print(f"\nОтфильтрованных дисков: {len(filtered_disks)}")

        # Только подключенные диски
        attached_query = DiskQuery(attached_only=True)
        attached_disks = mng.list_disks(attached_query)
        print(f"Подключенных дисков: {len(attached_disks)}")

    # # Подключить диск к ВМ
    # attach_cmd = DiskAttach(
    #     vm_name="my-vm",
    #     target_dev="vdb",
    #     bus_type=BusType.VIRTIO,
    #     cache_mode=CacheMode.WRITEBACK
    # )
    # attached_disk = manager.attach_disk_to_vm("default-pool", "vm-disk.qcow2", attach_cmd)

    # # Отключить диск от ВМ
    # detach_cmd = DiskDetach(
    #     vm_name="my-vm",
    #     target_dev="vdb"
    # )
    # manager.detach_disk_from_vm(detach_cmd)