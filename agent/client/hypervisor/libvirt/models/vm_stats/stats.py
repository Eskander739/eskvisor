from pydantic import BaseModel


class CpuStat(BaseModel):
    avg: int | float
    min: int | float
    max: int | float
    current: int
    vcpu_avg: int | float


class MemoryStat(BaseModel):
    current_mb_avg: int | float
    current_mb_max: int | float
    rss_mb_avg: int | float
    usage_percent_avg: int
    current: int | float
    rss: int | float
    percent: int | float


class VMStats(BaseModel):
    cpu: CpuStat
    memory: MemoryStat
    samples: int


class MemoryUsageStat(BaseModel):
    current_mb: int | float
    maximum_mb: int | float
    rss_mb: int | float
    usage_percent: int | float
    rss_percent: int | float
    available_mb: int | float
    free_mb: int | float


class CpuAndRamUsage(BaseModel):
    memory: int | float
    cpu_core_count: int
    cpu_usage_percent: int | float
