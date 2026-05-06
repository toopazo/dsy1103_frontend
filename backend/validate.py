#!/usr/bin/env python3
"""
Validation script: clone → build → run → health check (one service).

Usage (from repo root):
    python3 backend/validate.py --repo https://github.com/toopazo/dsy1103_bibliotecaduoc --port 8081
    python3 backend/validate.py --repo https://github.com/toopazo/dsy1103_bibliotecaduoc --port 8081 --stop
"""

import argparse
import sys
import time
import threading
from pathlib import Path

# Run from repo root
sys.path.insert(0, str(Path(__file__).parent))
import docker_manager as dm


def _stream_logs(name: str):
    """Print container logs to stdout (runs in a background thread)."""
    import docker
    client = docker.from_env()
    try:
        container = client.containers.get(f"{dm.CONTAINER_PREFIX}{name}")
        for line in container.logs(stream=True, follow=True):
            print(f"  {line.decode('utf-8', errors='replace').rstrip()}")
    except Exception as e:
        print(f"  [log error] {e}")


def main():
    parser = argparse.ArgumentParser(description="Validate one Spring Boot service")
    parser.add_argument("--repo", required=True, help="GitHub repo URL")
    parser.add_argument("--name", default="test-service", help="Service name (used as container name)")
    parser.add_argument("--port", type=int, default=8081, help="Port to expose")
    parser.add_argument("--secrets", help="Path to application-secrets.properties (optional)")
    parser.add_argument("--stop", action="store_true", help="Stop the container after health check")
    parser.add_argument("--timeout", type=int, default=300, help="Health check timeout in seconds")
    args = parser.parse_args()

    # 1. Image
    print("\n[1/4] Checking spring-runner image...")
    if not dm.runner_image_exists():
        print("      Image not found. Building now (this takes a moment)...")
        dm.build_runner_image()
    else:
        print(f"      Image {dm.RUNNER_IMAGE} already exists. OK.")

    # 2. Clone
    print(f"\n[2/4] Cloning {args.repo} ...")
    source_dir = dm.clone_repo(args.name, args.repo)
    print(f"      Cloned to: {source_dir}")

    # 3. Start container
    print(f"\n[3/4] Starting container on port {args.port} ...")
    secrets_path = Path(args.secrets) if args.secrets else None
    container = dm.start_service(args.name, source_dir, args.port, secrets_path)
    print(f"      Container ID: {container.short_id}")
    print(f"      Streaming build log (Maven output):\n")

    log_thread = threading.Thread(target=_stream_logs, args=(args.name,), daemon=True)
    log_thread.start()

    # 4. Poll health check
    print(f"\n[4/4] Waiting for health check at localhost:{args.port}/actuator/health")
    print(f"      Timeout: {args.timeout}s\n")

    deadline = time.time() + args.timeout
    healthy = False
    while time.time() < deadline:
        if dm.check_health(args.port):
            healthy = True
            break
        # also check if container died
        info = dm.get_container_status(args.name)
        if info["status"] == "exited":
            print("\n[!] Container exited before becoming healthy.")
            break
        time.sleep(5)

    print("\n" + "=" * 50)
    if healthy:
        print(f"  RESULT: OK — service healthy at localhost:{args.port}")
        print(f"  Try: curl http://localhost:{args.port}/actuator/health")
    else:
        print("  RESULT: FAIL — service did not become healthy within timeout")
    print("=" * 50)

    if args.stop:
        print("\nStopping container...")
        dm.stop_service(args.name)
    else:
        print(f"\nContainer left running. To stop: docker stop {dm.CONTAINER_PREFIX}{args.name}")

    sys.exit(0 if healthy else 1)


if __name__ == "__main__":
    main()
