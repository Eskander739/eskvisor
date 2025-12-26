from agent.client.hypervisor.libvirt.client import LibvirtClient
from agent.client.hypervisor.models.general import VMState
from agent.client.hypervisor.models.vm import VirtualMachine


class VmManager(LibvirtClient):
    """
    Управление виртуальными машинами
    """

    libvirtError = None

    def __init__(self, connection_uri: str = "qemu:///system"):
        super().__init__(connection_uri)

    def list_vms(self, only_active: bool = False) -> list[VirtualMachine]:
        """
        Получение списка виртуальных машин

        Args:
            only_active: только активные ВМ

        Returns:
            Список информации о ВМ
        """
        if not self.conn:
            raise ConnectionError("Сначала подключитесь к гипервизору")

        vms = []
        try:
            # Получаем все домены (виртуальные машины)
            if only_active:
                domain_ids = self.conn.listDomainsID()
                for domain_id in domain_ids:
                    domain = self.conn.lookupByID(domain_id)
                    vms.append(self._get_vm_info(domain))
            else:
                domains = self.conn.listAllDomains(0)
                for domain in domains:
                    vms.append(self._get_vm_info(domain))

        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения списка ВМ: {e}")

        return vms

    def _get_vm_info(self, domain) -> VirtualMachine:
        """Получение информации о виртуальной машине"""
        try:
            info = domain.info()
            state = VMState(info[0])

            return VirtualMachine(
                name=domain.name(),
                state=state,
                id=domain.ID() if domain.ID() != -1 else -1,
                uuid=domain.UUIDString(),
                vcpus=info[3],
                memory=info[1],
                max_memory=info[2],
                cpu_time=info[4]
            )
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения информации о ВМ: {e}")
            raise

    def get_vm_by_name(self, name: str) -> VirtualMachine | None:
        """Получение ВМ по имени"""
        try:
            virtual_machine = self.conn.lookupByName(name)
            return self._get_vm_info(virtual_machine)
        except self.libvirtError:
            return None

    def start_vm(self, name: str) -> bool:
        """Запуск виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.create() == 0:
                self.logger.info(f"ВМ {name} запущена")
                return True
            return False
        except self.libvirtError as e:
            self.logger.error(f"Ошибка запуска ВМ {name}: {e}")
            return False

    def shutdown_vm(self, name: str, force: bool = False) -> bool:
        """
        Выключение виртуальной машины

        Args:
            name: имя ВМ
            force: принудительное выключение
        """
        try:
            domain = self.conn.lookupByName(name)

            if force:
                # Принудительное выключение
                result = domain.destroy()
            else:
                # Корректное выключение (требует поддержки в гостевой ОС)
                result = domain.shutdown()

            if result == 0:
                action = "принудительно выключена" if force else "выключена"
                self.logger.info(f"ВМ {name} {action}")
                return True
            return False

        except self.libvirtError as e:
            self.logger.error(f"Ошибка выключения ВМ {name}: {e}")
            return False

    def reboot_vm(self, name: str) -> bool:
        """Перезагрузка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.reboot(0) == 0:
                self.logger.info(f"ВМ {name} перезагружается")
                return True
            return False
        except self.libvirtError as e:
            self.logger.error(f"Ошибка перезагрузки ВМ {name}: {e}")
            return False

    def suspend_vm(self, name: str) -> bool:
        """Приостановка виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.suspend() == 0:
                self.logger.info(f"ВМ {name} приостановлена")
                return True
            return False
        except self.libvirtError as e:
            self.logger.error(f"Ошибка приостановки ВМ {name}: {e}")
            return False

    def resume_vm(self, name: str) -> bool:
        """Возобновление работы виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)
            if domain.resume() == 0:
                self.logger.info(f"ВМ {name} возобновлена")
                return True
            return False
        except self.libvirtError as e:
            self.logger.error(f"Ошибка возобновления ВМ {name}: {e}")
            return False

    def create_vm_from_xml(self, xml_config: str, autostart: bool = False) -> bool:
        """
        Создание ВМ из XML конфигурации

        Args:
            xml_config: XML конфигурация ВМ
            autostart: автостарт при загрузке хоста
        """

        # TODO: Добавить механизм создания дисков если они отсутствуют

        try:
            domain = self.conn.defineXML(xml_config)
            if domain is None:
                self.logger.error("Не удалось создать ВМ из XML")
                return False

            if autostart:
                domain.setAutostart(1)

            self.logger.info(f"ВМ {domain.name()} создана")
            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка создания ВМ: {e}")
            return False

    def delete_vm(self, name: str) -> bool:
        """Удаление виртуальной машины"""
        try:
            domain = self.conn.lookupByName(name)

            # Если ВМ запущена, выключаем её
            if domain.isActive():
                domain.destroy()

            # Удаляем конфигурацию
            domain.undefine()

            self.logger.info(f"ВМ {name} удалена")
            return True

        except self.libvirtError as e:
            self.logger.error(f"Ошибка удаления ВМ {name}: {e}")
            return False

    def get_vm_xml(self, name: str) -> str | None:
        """Получение XML конфигурации ВМ"""
        try:
            domain = self.conn.lookupByName(name)
            return domain.XMLDesc(0)
        except self.libvirtError as e:
            self.logger.error(f"Ошибка получения XML для ВМ {name}: {e}")
            return None


if __name__ == "__main__":
    with VmManager() as vms:
        # print(vms.shutdown_vm("test-vm-01", force=True))
        # print(vms.start_vm(name="test-vm-01"))
        print(vms.shutdown_vm(name="test-vm-01"))
        print(vms.list_vms())