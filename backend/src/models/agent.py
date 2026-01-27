from pydantic import BaseModel


class ConnectHostRequest(BaseModel):
    ip: str
    cluster: str
    name: str
    description: str | None = None
    admin: str
    password: str | None = None


# print(ConnectHostRequest(ip="0.0.0.0", cluster="34", name="esk_agent", description="Гипервизор для ИИ", admin="root", password="root").model_dump_json())
