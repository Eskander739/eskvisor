from ipaddress import IPv4Address

from pydantic import BaseModel, model_validator


class ConnectHostRequest(BaseModel):
    ip: str
    backend_ip: str | None = None
    cluster: str
    name: str
    description: str | None = None
    admin: str
    password: str | None = None
    agent_file: str | None = None

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        if self.backend_ip is not None:
            IPv4Address(self.backend_ip)

        return self


class UpdateAgentRequest(BaseModel):
    ip: str
    backend_ip: str | None = None
    admin: str
    agent_file: str | None = None

    @model_validator(mode="after")
    def validate_disk_type_constraints(self):
        if self.backend_ip is not None:
            IPv4Address(self.backend_ip)

        return self
