from pydantic import BaseModel


class HealthInfo(BaseModel):
    postgres_db: bool
    redis: bool
