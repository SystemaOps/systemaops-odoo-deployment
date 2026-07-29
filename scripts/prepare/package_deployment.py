#!/usr/bin/env python3
import json
import os
import tarfile
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from scripts.utils.config import DEPLOYMENTS_DIR, REQUIRED_WORKSPACE_FILES, get_customer_dir, load_deployment_env
from scripts.utils.filesystem import verify_files
from scripts.utils.logger import error, info


REQUIRED_METADATA = ["deployment_summary.json", "install_modules.json"]


def verify_structure(customer_dir) -> list:
    missing = verify_files(customer_dir, REQUIRED_WORKSPACE_FILES)
    missing.extend(verify_files(customer_dir, REQUIRED_METADATA))
    return missing


def create_archive(customer_dir, deployment_id: str) -> str:
    archive_name = f"deployment_{deployment_id}.tar.gz"
    archive_path = DEPLOYMENTS_DIR / archive_name
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(customer_dir, arcname=customer_dir.name)
    info(f"Created archive: {archive_path}")
    return str(archive_path)


def write_manifest(customer_dir, archive_path: str) -> None:
    manifest = {
        "deployment_package": archive_path,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready_for_deployment",
        "message": "Package validated and archived. Ready for Phase 2 VM deployment.",
    }
    manifest_path = customer_dir / "deployment_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    info(f"Written: {manifest_path}")


def main() -> None:
    deployment_id = os.environ.get("DEPLOYMENT_ID", "")
    if not deployment_id:
        error("DEPLOYMENT_ID is not set.")
        sys.exit(1)

    file_env = load_deployment_env(deployment_id)
    deployment_id = deployment_id or file_env.get("DEPLOYMENT_ID", "")

    customer_dir = get_customer_dir(deployment_id)
    if not customer_dir.exists():
        error(f"Customer directory not found: {customer_dir}")
        sys.exit(1)

    info(f"Packaging deployment {deployment_id} from {customer_dir}")

    missing = verify_structure(customer_dir)
    if missing:
        error(f"Missing required files: {', '.join(missing)}")
        sys.exit(1)

    archive_path = create_archive(customer_dir, deployment_id)

    write_manifest(customer_dir, archive_path)

    info(f"Deployment package ready: {archive_path}")

    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"DEPLOYMENT_ARCHIVE={archive_path}\n")

    print(f"PACKAGE_PATH={archive_path}")


if __name__ == "__main__":
    main()