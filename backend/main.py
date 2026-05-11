"""DSY1103 Evaluador — FastAPI backend."""

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

import docker_manager as dm
import scenario_runner
import yaml_loader
from models import StartServiceRequest, ServiceStatus

app = FastAPI(title="DSY1103 Evaluador", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Docker image
# ---------------------------------------------------------------------------

@app.post("/api/image/build")
def build_image():
    if dm.runner_image_exists():
        return {"status": "already_exists", "image": dm.RUNNER_IMAGE}
    dm.build_runner_image()
    return {"status": "built", "image": dm.RUNNER_IMAGE}


@app.get("/api/image/status")
def image_status():
    return {"exists": dm.runner_image_exists(), "image": dm.RUNNER_IMAGE}


# ---------------------------------------------------------------------------
# Services (clone + run)
# ---------------------------------------------------------------------------

@app.post("/api/services")
def start_service(req: StartServiceRequest):
    try:
        source_dir = dm.clone_repo(req.name, req.repo)
        secrets = Path(req.secrets_file) if req.secrets_file else None
        container = dm.start_service(req.name, source_dir, req.port, secrets, req.env_vars)
        return {
            "status": "starting",
            "name": req.name,
            "container_id": container.short_id,
            "port": req.port,
            "logs_stream": f"/api/services/{req.name}/logs",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/services")
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


@app.delete("/api/services/{name}")
def stop_service(name: str):
    dm.stop_service(name)
    return {"status": "stopped", "name": name}


@app.delete("/api/services")
def stop_all():
    dm.stop_all_services()
    return {"status": "all_stopped"}


@app.get("/api/services/{name}/logs")
async def stream_logs(name: str, request: Request):
    async def generator():
        async for line in dm.async_log_stream(name):
            if await request.is_disconnected():
                break
            yield {"data": line}
    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# Config browser
# ---------------------------------------------------------------------------

@app.get("/api/groups")
def list_groups():
    return yaml_loader.list_groups()


@app.get("/api/groups/{name}")
def get_group(name: str):
    try:
        return yaml_loader.load_group(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/projects")
def list_projects():
    return yaml_loader.list_projects()


@app.get("/api/projects/{name}")
def get_project(name: str):
    try:
        return yaml_loader.load_project(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Evaluation (SSE streaming)
# ---------------------------------------------------------------------------

@app.get("/api/evaluate/{group_name}/{level}")
async def evaluate(group_name: str, level: str, request: Request):
    """
    Stream evaluation results as Server-Sent Events.

    level: easy | medium | hard
    """
    async def generator():
        async for event in scenario_runner.run_evaluation(group_name, level):
            if await request.is_disconnected():
                break
            yield {"data": json.dumps(event, ensure_ascii=False)}

    return EventSourceResponse(generator())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def api_health():
    return {"status": "ok"}
