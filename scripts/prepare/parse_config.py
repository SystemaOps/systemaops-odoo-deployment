#!/usr/bin/env python3
import json
import os
import re
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from scripts.utils.config import save_deployment_env
from scripts.utils.logger import error, info


REQUIRED_FIELDS = ["company_name", "database_name", "selected_modules"]
OPTIONAL_FIELDS = {
    "industry": "",
    "timezone": "UTC",
    "number_of_users": 10,
    "domain": "",
    "odoo_port": 8069,
    "grafana_port": 3002,
    "admin_name": "admin",
    "nginx_port": 80,
    # Phase 2 target VM
    "vm_provider": "",
    "vm_host": "",
    "vm_ssh_user": "",
    "vm_ssh_port": 22,
    "vm_domain": "",
    "ssh_key_secret": "",
    "offsite_target": "",
}


def parse_config(config_raw: str) -> dict:
    if not config_raw:
        error("DEPLOYMENT_CONFIG is empty.")
        sys.exit(1)

    try:
        config = json.loads(config_raw)
    except json.JSONDecodeError as exc:
        error(f"Invalid JSON: {exc}")
        sys.exit(1)

    missing = [f for f in REQUIRED_FIELDS if f not in config]
    if missing:
        error(f"Missing required fields: {', '.join(missing)}")
        sys.exit(1)

    if (
        not isinstance(config["selected_modules"], list)
        or len(config["selected_modules"]) == 0
    ):
        error("selected_modules must be a non-empty list.")
        sys.exit(1)

    return config


def _build_env(config: dict) -> dict:
    env = {}
    for key in REQUIRED_FIELDS:
        val = config[key]
        if isinstance(val, (list, dict)):
            val = json.dumps(val)
        env[f"DEPLOYMENT_{key.upper()}"] = val
    for key, default in OPTIONAL_FIELDS.items():
        val = config.get(key, default)
        if isinstance(val, (list, dict)):
            val = json.dumps(val)
        env[f"DEPLOYMENT_{key.upper()}"] = val
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", config["company_name"].lower())
    safe_name = re.sub(r"_+", "_", safe_name).strip("_")
    env["DEPLOYMENT_SAFE_COMPANY_NAME"] = safe_name
    container_safe = re.sub(r"[^a-zA-Z0-9]", "", config["company_name"].lower())[:12]
    env["DEPLOYMENT_CONTAINER_PREFIX"] = container_safe
    return env


def main() -> None:
    config_raw = os.environ.get("DEPLOYMENT_CONFIG", "")
    config = parse_config(config_raw)
    info(f"Parsed config for: {config['company_name']}")

    deployment_id = os.environ.get("DEPLOYMENT_ID", "unknown")
    env = _build_env(config)
    env["DEPLOYMENT_ID"] = deployment_id

    save_deployment_env(deployment_id, env)
    info("Configuration saved to shared env file.")

    env_file = os.environ.get("GITHUB_ENV", "")
    if env_file:
        with open(env_file, "a") as f:
            f.write("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
        info("Configuration exported to GITHUB_ENV.")


if __name__ == "__main__":
    main()