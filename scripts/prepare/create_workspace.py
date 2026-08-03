#!/usr/bin/env python3
import os
import shutil
import sys
from pathlib import Path

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from scripts.utils.config import PARENT_DIR, REQUIRED_WORKSPACE_FILES, get_customer_dir
from scripts.utils.filesystem import copy_template, ensure_dir, verify_files
from scripts.utils.logger import error, info, warn


def flatten_bundle_addons(customer_dir: Path) -> int:
    addons_dir = customer_dir / "addons"
    if not addons_dir.exists():
        return 0

    moved = 0
    for entry in sorted(addons_dir.iterdir()):
        if not entry.is_dir() or (entry / "__manifest__.py").exists():
            continue

        for inner in sorted(entry.iterdir()):
            if inner.is_dir() and (inner / "__manifest__.py").exists():
                target = addons_dir / inner.name
                if target.exists():
                    warn(f"Addon name collision while flattening: {target}")
                    continue
                shutil.move(str(inner), str(target))
                moved += 1

        shutil.rmtree(entry)

    if moved:
        info(f"Flattened {moved} module(s) from bundle addon directories.")
    return moved


def main() -> None:
    deployment_id = os.environ.get("DEPLOYMENT_ID", "")
    if not deployment_id:
        error("DEPLOYMENT_ID environment variable is not set.")
        sys.exit(1)

    customer_dir = get_customer_dir(deployment_id)
    info(f"Creating workspace at: {customer_dir}")

    ensure_dir(customer_dir)
    copy_template(PARENT_DIR, customer_dir)
    info("Parent template copied to customer directory.")

    flatten_bundle_addons(customer_dir)

    missing = verify_files(customer_dir, REQUIRED_WORKSPACE_FILES)
    if missing:
        error(f"Required files missing after copy: {', '.join(missing)}")
        sys.exit(1)

    info(f"Workspace created successfully at {customer_dir}")
    print(f"CUSTOMER_DIR={customer_dir}")


if __name__ == "__main__":
    main()
