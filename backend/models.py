from pydantic import BaseModel
from typing import Optional


class StartServiceRequest(BaseModel):
    name: str
    repo: str
    port: int
    secrets_file: Optional[str] = None  # absolute path to a .properties file on the host
    env_vars: Optional[dict[str, str]] = None  # extra env vars injected into the container


class ServiceStatus(BaseModel):
    name: str
    container_id: Optional[str]
    status: str          # "running", "exited", "building", "not_found"
    port: Optional[int]
    healthy: bool
