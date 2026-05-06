"""DSY1103 Evaluador — FastAPI backend."""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

import docker_manager as dm
from models import StartServiceRequest, ServiceStatus

app = FastAPI(title="DSY1103 Evaluador", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

@app.post("/api/image/build", summary="Build the spring-runner Docker image")
def build_image():
    if dm.runner_image_exists():
        return {"status": "already_exists", "image": dm.RUNNER_IMAGE}
    dm.build_runner_image()
    return {"status": "built", "image": dm.RUNNER_IMAGE}


@app.get("/api/image/status")
def image_status():
    return {"exists": dm.runner_image_exists(), "image": dm.RUNNER_IMAGE}


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

@app.post("/api/services", summary="Clone, build, and start a student service")
def start_service(req: StartServiceRequest):
    try:
        source_dir = dm.clone_repo(req.name, req.repo)
        secrets = Path(req.secrets_file) if req.secrets_file else None
        container = dm.start_service(req.name, source_dir, req.port, secrets)
        return {
            "status": "starting",
            "name": req.name,
            "container_id": container.short_id,
            "port": req.port,
            "logs_stream": f"/api/services/{req.name}/logs",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/services", summary="List all evaluator containers")
def list_services():
    return dm.list_services()


@app.get("/api/services/{name}/status", response_model=ServiceStatus)
def service_status(name: str, port: Optional[int] = None):
    info = dm.get_container_status(name)
    healthy = dm.check_health(port) if port else False
    return ServiceStatus(
        name=name,
        container_id=info.get("container_id"),
        status=info["status"],
        port=port,
        healthy=healthy,
    )


@app.delete("/api/services/{name}", summary="Stop and remove a service container")
def stop_service(name: str):
    dm.stop_service(name)
    return {"status": "stopped", "name": name}


@app.delete("/api/services", summary="Stop and remove ALL evaluator containers")
def stop_all():
    dm.stop_all_services()
    return {"status": "all_stopped"}


# ---------------------------------------------------------------------------
# Log streaming (SSE)
# ---------------------------------------------------------------------------

@app.get("/api/services/{name}/logs", summary="Stream container logs via SSE")
async def stream_logs(name: str, request: Request):
    async def generator():
        async for line in dm.async_log_stream(name):
            if await request.is_disconnected():
                break
            yield {"data": line}

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def api_health():
    return {"status": "ok"}
