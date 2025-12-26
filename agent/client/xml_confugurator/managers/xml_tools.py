import re

from lxml import etree


class XmlTools:

    @staticmethod
    def validate_cpuset(cpuset_str: str) -> bool:
        """
        Проверяет валидность строки cpuset для libvirt.
        Формат: цифры, диапазоны (1-4), исключения (^3), разделители запятые.
        Примеры валидных: "0", "0-3", "0,2", "0-3,^2", "0-3,^1-2".
        """
        if not cpuset_str or not isinstance(cpuset_str, str):
            return False

        # Паттерн для проверки каждого элемента
        # 1) ^\d+$ — отдельная цифра (например, "0")
        # 2) ^\d+-\d+$ — диапазон (например, "1-4")
        # 3) ^\^\d+$ — исключение цифры (например, "^2")
        # 4) ^\^\d+-\d+$ — исключение диапазона (например, "^1-3")
        element_pattern = r'^(\^?\d+)(-\d+)?$'

        elements = cpuset_str.split(',')

        for elem in elements:
            elem = elem.strip()
            if not elem:
                return False  # Пустой элемент

            if not re.match(element_pattern, elem):
                return False  # Не соответствует формату

            # Проверка диапазона (если есть)
            if '-' in elem:
                # Убираем символ исключения для проверки чисел
                clean_elem = elem.lstrip('^')
                start, end = map(int, clean_elem.split('-'))
                if start >= end:
                    return False  # Неверный диапазон

        return True

    @staticmethod
    def _count_cores_in_cpuset(cpuset_str: str) -> int:
        """
        Подсчитывает количество физических ядер, доступных в cpuset.
        Игнорирует исключения (элементы с ^).
        """
        if not cpuset_str:
            return 0

        total_cores = 0
        elements = cpuset_str.split(',')

        for elem in elements:
            elem = elem.strip()
            if not elem or elem.startswith('^'):
                continue  # Пропускаем исключения

            if '-' in elem:
                # Диапазон
                start, end = map(int, elem.split('-'))
                total_cores += (end - start + 1)
            else:
                # Отдельное ядро
                total_cores += 1

        return total_cores



def serialize_xml(func):

    def _serialize_xml(*args, **kwargs):
        xml = func(*args, **kwargs)
        xml = xml.replace(" >", ">")
        xml = xml.replace(" />", "/>")
        # parser = etree.XMLParser(recover=True)  # recover=True попытается исправить ошибки
        # tree = etree.fromstring(xml, parser)
        #
        # Красивое форматирование
        # pretty_xml = etree.tostring(tree, pretty_print=True, encoding='unicode')

        return xml

    return _serialize_xml

# def serialize_xml(func):
#     """Декоратор для сериализации и форматирования XML"""
#
#     def _serialize_xml(*args, **kwargs):
#         xml = func(*args, **kwargs)
#
#         parser = etree.XMLParser(
#             recover=True,  # пытаться исправлять ошибки
#             remove_blank_text=True  # удалять пустой текст
#         )
#
#         try:
#             tree = etree.fromstring(xml, parser)
#
#             # Логируем ошибки, если они были
#             if parser.error_log:
#                 print(f"Внимание: XML был восстановлен после {len(parser.error_log)} ошибок")
#                 for error in parser.error_log:
#                     print(f"  - {error.message} (строка {error.line})")
#
#             # Возвращаем красиво отформатированный XML
#             return etree.tostring(
#                 tree,
#                 pretty_print=True,
#                 encoding='unicode',
#                 method='xml'
#             )
#
#         except Exception as e:
#             print(f"Критическая ошибка при обработке XML: {e}")
#             # Возвращаем исходный XML как fallback
#             return xml
#
#     return _serialize_xml