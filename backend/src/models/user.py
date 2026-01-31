from datetime import datetime

from pydantic import BaseModel

from src.rbac.roles_and_users import UserRole


class UserLogin(BaseModel):
    email: str
    password: str
    remember_me: bool | None = None


class EmailForRestPassword(BaseModel):
    email: str


class UserAuth(BaseModel):
    email: str
    password: str


class UserAddInDb(BaseModel):
    role: UserRole
    name: str
    description: str | None = None
    pass_hash: str
    email: str
    created: datetime
    deleted: datetime | None = None
    created_by: int | None = None


class UserInDB(BaseModel):
    id: int
    role: UserRole
    name: str
    description: str | None = None
    pass_hash: str
    email: str
    created: datetime
    deleted: datetime | None = None
    blocked: bool = False
    created_by: int | None = None

    class Config:
        orm_mode = True


class UserLow(BaseModel):
    id: int
    role: UserRole
    name: str
    description: str | None = None
    img_external_id: str | None = None
    blocked: bool = False
    created_by: int | None = None

class UserMedium(BaseModel):
    id: int
    role: UserRole
    name: str
    description: str | None = None
    email: str
    created: datetime
    deleted: datetime | None = None
    blocked: bool = False
    created_by: int | None = None


class UserLite(BaseModel):
    id: int
    name: str
    description: str | None = None
    created: datetime
    deleted: datetime | None = None
    blocked: bool = False
    created_by: int | None = None


class UsersListLite(BaseModel):
    total: int
    page: int
    limit: int
    items: list[UserLite]

class UsersList(BaseModel):
    total: int
    page: int
    limit: int
    items: list[UserInDB]

class HelpUser(BaseModel):
    email: str
    theme: str
    message: str