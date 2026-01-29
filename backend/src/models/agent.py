from pydantic import BaseModel


class ConnectHostRequest(BaseModel):
    ip: str
    cluster: str
    name: str
    description: str | None = None
    admin: str
    password: str | None = None
    agent_file: str | None = None
