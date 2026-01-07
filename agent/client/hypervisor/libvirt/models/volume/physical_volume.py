from pydantic import BaseModel


class PhysicalVolume(BaseModel):
    physical_name: str  # Путь к физическому тому (диск/раздел)
    volume_name: str | None = None  # Имя группы томов, к которой принадлежит PV
    format: str  # Формат тома (обычно lvm2)
    attributes: str  # Атрибуты тома
    physical_size: str  # Общий размер физического тома
    physical_free: str  # Свободное место на физическом томе
