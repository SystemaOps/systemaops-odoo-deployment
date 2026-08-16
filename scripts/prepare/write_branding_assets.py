#!/usr/bin/env python3
"""Decode customer branding images (company logo + owner photo) into the
workspace as files so they are packaged into the deployment artifact and
transferred to the VM for Phase 2 branding.

Inputs are base64 data URLs carried through DEPLOYMENT_COMPANY_LOGO and
DEPLOYMENT_OWNER_PHOTO (set by parse_config.py). No input means no branding.
"""
import base64
import os
import re
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from scripts.utils.config import get_customer_dir, load_deployment_env
from scripts.utils.filesystem import ensure_dir
from scripts.utils.logger import error, info


def _decode_data_url(data_url: str) -> bytes:
    """Strip a data URL prefix (data:image/png;base64,...) and decode."""
    match = re.match(r"^data:[^;]+;base64,(.*)$", data_url, re.DOTALL)
    payload = match.group(1) if match else data_url
    return base64.b64decode(payload)


def _write_branding_asset(customer_dir, env_key: str, filename: str, env: dict) -> None:
    raw = env.get(env_key, "")
    if not raw:
        return
    branding_dir = ensure_dir(customer_dir / "branding")
    data = _decode_data_url(raw)
    path = branding_dir / filename
    path.write_bytes(data)
    info(f"Wrote {path} ({len(data)} bytes)")


def main() -> None:
    deployment_id = os.environ.get("DEPLOYMENT_ID", "")
    if not deployment_id:
        error("DEPLOYMENT_ID environment variable is not set.")
        sys.exit(1)

    file_env = load_deployment_env(deployment_id)
    env = {**file_env, **os.environ}

    customer_dir = get_customer_dir(deployment_id)
    if not customer_dir.exists():
        error(f"Customer directory not found: {customer_dir}")
        sys.exit(1)

    _write_branding_asset(customer_dir, "DEPLOYMENT_COMPANY_LOGO", "company_logo.png", env)
    _write_branding_asset(customer_dir, "DEPLOYMENT_OWNER_PHOTO", "owner_photo.png", env)

    info(f"Branding assets processed for {deployment_id}")


if __name__ == "__main__":
    main()
