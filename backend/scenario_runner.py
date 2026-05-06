"""Core evaluation engine: loads YAML scenarios and executes them step by step."""

import json
import re
import time
from typing import Any, AsyncGenerator

import httpx
from jsonpath_ng import parse as jp_parse

import yaml_loader


# ---------------------------------------------------------------------------
# Variable interpolation
# ---------------------------------------------------------------------------

def _interpolate_str(text: str, context: dict) -> str:
    """Replace {{var}} placeholders with values from context."""
    return re.sub(
        r"\{\{(\w+)\}\}",
        lambda m: str(context[m.group(1)]) if m.group(1) in context else m.group(0),
        text,
    )


def _interpolate(value: Any, context: dict) -> Any:
    """Recursively interpolate dicts, lists, and strings."""
    if isinstance(value, str):
        return _interpolate_str(value, context)
    if isinstance(value, dict):
        return {k: _interpolate(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(item, context) for item in value]
    return value


# ---------------------------------------------------------------------------
# JSONPath extraction
# ---------------------------------------------------------------------------

def _extract(response_json: Any, spec: dict) -> dict:
    """Extract variables from a response using JSONPath expressions (e.g. $.id)."""
    extracted = {}
    for var_name, path_expr in spec.items():
        try:
            matches = jp_parse(path_expr).find(response_json)
            if matches:
                extracted[var_name] = matches[0].value
        except Exception:
            pass
    return extracted


# ---------------------------------------------------------------------------
# Single step execution
# ---------------------------------------------------------------------------

async def _execute_step(step: dict, service_map: dict, context: dict) -> dict:
    service_name = step["service"]
    if service_name not in service_map:
        return _step_error(step, f"Service '{service_name}' not found in group config")

    port = service_map[service_name]
    path = _interpolate(step["path"], context)
    method = step["method"].upper()
    body = _interpolate(step.get("body"), context) if step.get("body") else None
    headers = _interpolate(step.get("headers", {}), context)
    expected_status = step.get("expect_status", 200)
    extract_spec = step.get("extract", {})

    url = f"http://localhost:{port}{path}"
    t0 = time.monotonic()

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method=method,
                url=url,
                json=body,
                headers=headers,
                timeout=10.0,
            )
        duration_ms = int((time.monotonic() - t0) * 1000)

        # Try to parse response as JSON for extraction and display
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text

        extracted = _extract(resp_body, extract_spec) if extract_spec and isinstance(resp_body, dict) else {}

        passed = resp.status_code == expected_status
        return {
            "type": "step_result",
            "name": step["name"],
            "method": method,
            "url": url,
            "status": "pass" if passed else "fail",
            "http_status": resp.status_code,
            "expected_status": expected_status,
            "duration_ms": duration_ms,
            "extracted": extracted,
            "response_preview": _preview(resp_body),
            "error": None if passed else f"Expected {expected_status}, got {resp.status_code}",
        }

    except httpx.ConnectError:
        return _step_error(step, f"Connection refused at {url} — is the service running?", method, url)
    except httpx.TimeoutException:
        return _step_error(step, f"Request timed out after 10s", method, url)
    except Exception as e:
        return _step_error(step, str(e), method, url)


def _step_error(step: dict, error: str, method: str = "", url: str = "") -> dict:
    return {
        "type": "step_result",
        "name": step["name"],
        "method": method or step.get("method", ""),
        "url": url,
        "status": "fail",
        "http_status": None,
        "expected_status": step.get("expect_status", 200),
        "duration_ms": None,
        "extracted": {},
        "response_preview": None,
        "error": error,
    }


def _preview(body: Any) -> str:
    """Short preview of a response body for the log."""
    text = json.dumps(body) if not isinstance(body, str) else body
    return text[:200] + ("…" if len(text) > 200 else "")


# ---------------------------------------------------------------------------
# Full evaluation run (async generator → SSE-ready)
# ---------------------------------------------------------------------------

async def run_evaluation(group_name: str, level: str) -> AsyncGenerator[dict, None]:
    """
    Async generator that yields evaluation events for SSE streaming.

    Event types:
      eval_start, scenario_start, step_result, scenario_result, eval_result, eval_error
    """
    # Load configs
    try:
        group = yaml_loader.load_group(group_name)
        project = yaml_loader.load_project(group["project"])
    except FileNotFoundError as e:
        yield {"type": "eval_error", "message": str(e)}
        return

    if level not in project.get("scenarios", {}):
        yield {"type": "eval_error", "message": f"Level '{level}' not found in project '{group['project']}'"}
        return

    service_map = {s["name"]: s["port"] for s in group["services"]}
    scenarios = project["scenarios"][level]

    yield {
        "type": "eval_start",
        "group": group["group_name"],
        "project": project["project"],
        "level": level,
        "scenario_count": len(scenarios),
    }

    context: dict = {}   # persists across all scenarios in this run
    total_passed = total_failed = 0

    for scenario in scenarios:
        yield {"type": "scenario_start", "scenario": scenario["name"]}
        sc_passed = sc_failed = 0

        for step in scenario["steps"]:
            result = await _execute_step(step, service_map, context)

            if result["status"] == "pass":
                sc_passed += 1
                total_passed += 1
                # Merge extracted variables into shared context
                context.update(result["extracted"])
            else:
                sc_failed += 1
                total_failed += 1

            yield result

        yield {
            "type": "scenario_result",
            "scenario": scenario["name"],
            "passed": sc_passed,
            "failed": sc_failed,
        }

    yield {
        "type": "eval_result",
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_steps": total_passed + total_failed,
    }
