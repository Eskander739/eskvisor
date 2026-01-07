from enum import Enum

from pydantic import BaseModel


class LogicVolume(BaseModel):
    logic_volume_name: str
    volume_group_name: str
    attributes: str  # Атрибуты логического тома
    volume_size: int  # Общий размер логического тома в байтах
    logic_volume_pool: str  # Имя thin pool (для тонких LV), если пусто - обычный LV (не thin-provisioned)
    is_snapshot: str  # origin Исходный LV (для снапшотов), если пусто - не снапшот
    data_percent: str  # Процент использования данных
    metadata_percent: str  # Процент использования метаданных
    move_physical_volume: str  #  Physical Volume для перемещения данных, если пусто - данные не перемещаются
    mirror_logic: str  # Логическое устройство для зеркалирования, если пусто - не зеркалированный LV
    copy_percent: (
        str  # Процент копирования(для зеркал, RAID), если пусто - не копируется
    )
    convert_logic_volume: str  # Тип конвертации, если пусто = не конвертируется


class LogicalVolumeSizeType(Enum):
    TB = "T"
    GB = "G"
    MB = "M"
    KB = "K"
