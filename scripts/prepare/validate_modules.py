#!/usr/bin/env python3
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from scripts.utils.config import ADDONS_DIR, get_customer_dir, load_deployment_env
from scripts.utils.logger import error, info, warn


def _get_available_addons() -> set:
    if not ADDONS_DIR.exists():
        warn(f"Addons directory not found: {ADDONS_DIR}")
        return set()
    return {p.name for p in ADDONS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")}


def validate_modules(
    requested: list, customer_dir
) -> dict:
    available = _get_available_addons()
    report = {
        "requested_modules": requested,
        "available_modules": sorted(available),
        "valid": [],
        "invalid": [],
        "not_found": [],
    }

    for mod in requested:
        if mod in available:
            report["valid"].append(mod)
            info(f"Module found: {mod}")
        else:
            report["invalid"].append(mod)
            warn(f"Module not in addons directory: {mod}")

    report["all_valid"] = len(report["invalid"]) == 0

    report_path = customer_dir / "config" / "module_validation.json"
    os.makedirs(report_path.parent, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    info(f"Validation report written to {report_path}")

    return report


def main() -> None:
    deployment_id = os.environ.get("DEPLOYMENT_ID", "")
    file_env = load_deployment_env(deployment_id) if deployment_id else {}

    modules_raw = (
        os.environ.get("DEPLOYMENT_SELECTED_MODULES")
        or file_env.get("DEPLOYMENT_SELECTED_MODULES", "[]")
    )
    deployment_id = deployment_id or file_env.get("DEPLOYMENT_ID", "")

    try:
        requested = json.loads(modules_raw)
    except json.JSONDecodeError as exc:
        error(f"Invalid SELECTED_MODULES JSON: {exc}")
        sys.exit(1)

    if not isinstance(requested, list):
        error("SELECTED_MODULES must be a JSON array.")
        sys.exit(1)

    customer_dir = get_customer_dir(deployment_id) if deployment_id else None
    report = validate_modules(requested, customer_dir)

    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"MODULE_VALIDATION_STATUS={'passed' if report['all_valid'] else 'failed'}\n")
            f.write(f"VALID_MODULE_COUNT={len(report['valid'])}\n")
            f.write(f"INVALID_MODULE_COUNT={len(report['invalid'])}\n")

    if not report["all_valid"]:
        warn(f"Some modules are missing: {report['invalid']}")
        sys.exit(1)


if __name__ == "__main__":
    main()