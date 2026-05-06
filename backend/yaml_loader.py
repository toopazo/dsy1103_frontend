"""Load group and project YAML configs from the repo."""

from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).parent.parent.resolve()
GROUPS_DIR = REPO_ROOT / "groups"
PROJECTS_DIR = REPO_ROOT / "projects"


def load_group(name: str) -> dict:
    path = GROUPS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Group config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def load_project(name: str) -> dict:
    path = PROJECTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Project config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def list_groups() -> list[str]:
    return [p.stem for p in GROUPS_DIR.glob("*.yaml")]


def list_projects() -> list[str]:
    return [p.stem for p in PROJECTS_DIR.glob("*.yaml")]
