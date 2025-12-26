from enum import Enum

from pydantic import BaseModel

from agent.client.xml_confugurator.models.general import StateYesNo


class ClockOffset(Enum):
    utc = "utc"
    timezone = "timezone"
    localtime = "localtime"
    variable = "variable"


class ClockTimezone(Enum):
    europe_moscow = "Europe/Moscow"

class TimerTickpolicy(Enum):
    catchup = "catchup"
    delay = "delay"

class Timer(BaseModel):
    name: str
    present: StateYesNo | None = None
    tickpolicy: TimerTickpolicy | None = None
    track: str | None = None

class XmlClock(BaseModel):
    """

    Пример:
    <clock offset='utc'>
      <!-- Таймеры для лучшей синхронизации -->
      <timer name='rtc' tickpolicy='catchup' track='wall'/>
      <timer name='pit' tickpolicy='delay'/>
      <timer name='hpet' present='no'/>  <!-- HPET может замедлять ВМ -->
      <timer name='kvmclock' present='yes'/>  <!-- Для Linux гостей -->
      <timer name='hypervclock' present='yes'/>  <!-- Для Windows гостей -->
    </clock>
    """

    offset: ClockOffset = ClockOffset.utc
    timezone: ClockTimezone | None = ClockTimezone.europe_moscow
    adjustment: int | None = None
    timer: list[Timer] | None = None
