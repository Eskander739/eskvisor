from pydantic import BaseModel


class VolumeGroup(BaseModel):
    volume_name: str  # Имя группы томов, к которой принадлежит PV
    pv_count: int  # Количество физических томов в группе
    lv_count: int  # Количество логических томов в группе
    snap_count: int  # Количество снапшотов в группе
    attributes: str  # Атрибуты группы
    volume_size: str  # Общий размер группы томов
    volume_free: str  # Свободное место в группе томов
