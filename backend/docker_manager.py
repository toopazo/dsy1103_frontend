"""Manages cloning, building, and running student Spring Boot services via Docker."""

import asyncio
import subprocess
import shutil
from pathlib import Path
from typing import Optional, AsyncGenerator

import docker
import httpx

# Paths are relative to repo root (where the backend is launched from)
REPO_ROOT = Path(__file__).parent.parent.resolve()
CLONES_DIR = REPO_ROOT / "clones"
RUNNER_IMAGE = "dsy1103-spring-runner:latest"
CONTAINER_PREFIX = "dsy1103-"
MAVEN_CACHE = Path.home() / ".m2"


def _docker_client():
    return docker.from_env()


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

def build_runner_image() -> None:
    """Build the spring-runner Docker image from the repo root."""
    print(f"[docker] Building {RUNNER_IMAGE} ...")
    client = _docker_client()
    client.images.build(
        path=str(REPO_ROOT),
        dockerfile="Dockerfile.spring-runner",
        tag=RUNNER_IMAGE,
        rm=True,
    )
    print(f"[docker] Image {RUNNER_IMAGE} ready.")


def runner_image_exists() -> bool:
    try:
        _docker_client().images.get(RUNNER_IMAGE)
        return True
    except docker.errors.ImageNotFound:
        return False


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------

def clone_repo(name: str, repo_url: str) -> Path:
    """Clone a GitHub repo into clones/<name>/. Re-clones if already present."""
    target = CLONES_DIR / name
    if target.exists():
        shutil.rmtree(target)
    CLONES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[git] Cloning {repo_url} → {target}")
    subprocess.run(["git", "clone", repo_url, str(target)], check=True)
    return target


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def start_service(
    name: str,
    source_dir: Path,
    port: int,
    secrets_file: Optional[Path] = None,
) -> "docker.models.containers.Container":
    """Start a spring-runner container for the given cloned repo."""
    client = _docker_client()
    container_name = f"{CONTAINER_PREFIX}{name}"

    # Stop and remove any existing container with the same name
    try:
        old = client.containers.get(container_name)
        print(f"[docker] Removing existing container {container_name}")
        old.stop(timeout=5)
        old.remove()
    except docker.errors.NotFound:
        pass

    volumes = {
        str(source_dir.resolve()): {"bind": "/app", "mode": "rw"},
        str(MAVEN_CACHE): {"bind": "/root/.m2", "mode": "rw"},
    }

    if secrets_file and secrets_file.exists():
        volumes[str(secrets_file.resolve())] = {
            "bind": "/secrets/app-secrets.properties",
            "mode": "ro",
        }
        print(f"[docker] Mounting secrets: {secrets_file.name}")

    # Ensure Maven cache dir exists on host so Docker doesn't create it as root
    MAVEN_CACHE.mkdir(parents=True, exist_ok=True)

    print(f"[docker] Starting {container_name} on port {port} ...")
    container = client.containers.run(
        image=RUNNER_IMAGE,
        name=container_name,
        volumes=volumes,
        environment={"PORT": str(port)},
        ports={f"{port}/tcp": port},
        detach=True,
    )
    return container


def stop_service(name: str) -> None:
    client = _docker_client()
    container_name = f"{CONTAINER_PREFIX}{name}"
    try:
        c = client.containers.get(container_name)
        c.stop(timeout=5)
        c.remove()
        print(f"[docker] Stopped and removed {container_name}")
    except docker.errors.NotFound:
        print(f"[docker] Container {container_name} not found, nothing to stop")


def stop_all_services() -> None:
    client = _docker_client()
    for c in client.containers.list(all=True):
        if c.name.startswith(CONTAINER_PREFIX):
            c.stop(timeout=5)
            c.remove()
            print(f"[docker] Stopped {c.name}")


# ---------------------------------------------------------------------------
# Status & health
# ---------------------------------------------------------------------------

def get_container_status(name: str) -> dict:
    client = _docker_client()
    try:
        c = client.containers.get(f"{CONTAINER_PREFIX}{name}")
        return {"status": c.status, "container_id": c.short_id}
    except docker.errors.NotFound:
        return {"status": "not_found", "container_id": None}


def list_services() -> list[dict]:
    client = _docker_client()
    result = []
    for c in client.containers.list(all=True):
        if c.name.startswith(CONTAINER_PREFIX):
            result.append({
                "name": c.name.removeprefix(CONTAINER_PREFIX),
                "container_id": c.short_id,
                "status": c.status,
            })
    return result


def check_health(port: int) -> bool:
    """Single health check attempt against /actuator/health."""
    try:
        resp = httpx.get(f"http://localhost:{port}/actuator/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Log streaming (async, for SSE)
# ---------------------------------------------------------------------------

async def async_log_stream(name: str) -> AsyncGenerator[str, None]:
    """Async generator that yields container log lines (for SSE)."""
    client = _docker_client()
    container_name = f"{CONTAINER_PREFIX}{name}"
    loop = asyncio.get_event_loop()

    try:
        container = client.containers.get(container_name)
    except docker.errors.NotFound:
        yield f"ERROR: container {container_name} not found"
        return

    log_gen = container.logs(stream=True, follow=True)

    while True:
        line = await loop.run_in_executor(None, lambda: next(log_gen, None))
        if line is None:
            break
        yield line.decode("utf-8", errors="replace").rstrip()
