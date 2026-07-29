import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(
    os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent.parent)
)

PARENT_DIR = PROJECT_ROOT / "parent"
DEPLOYMENTS_DIR = PROJECT_ROOT / "deployments"
ADDONS_DIR = PARENT_DIR / "addons"

CUSTOMER_DIR_PREFIX = "customer_"
ENV_FILE_NAME = ".deployment_env"

REQUIRED_WORKSPACE_FILES = [
    "docker-compose.yml",
    "Dockerfile",
    "config/odoo.conf",
    "nginx.conf",
]

DEPLOYMENT_ENV_PREFIX = "DEPLOYMENT_"


def get_customer_dir(deployment_id: str) -> Path:
    return DEPLOYMENTS_DIR / f"{CUSTOMER_DIR_PREFIX}{deployment_id}"


def save_deployment_env(deployment_id: str, env: Dict[str, Any]) -> None:
    path = DEPLOYMENTS_DIR / f".env_{deployment_id}"
    DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for key, val in env.items():
            f.write(f"{key}={val}\n")


def load_deployment_env(deployment_id: Optional[str] = None) -> Dict[str, str]:
    if deployment_id:
        path = DEPLOYMENTS_DIR / f".env_{deployment_id}"
        if path.exists():
            env = {}
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, val = line.split("=", 1)
                        env[key] = val
            return env
    env = {}
    for key, val in os.environ.items():
        if key.startswith(DEPLOYMENT_ENV_PREFIX) or key in (
            "DEPLOYMENT_ID",
            "CUSTOMER_DIR",
        ):
            env[key] = val
    return env