#!/usr/bin/env python3
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from scripts.utils.config import PARENT_DIR, REQUIRED_WORKSPACE_FILES, get_customer_dir
from scripts.utils.filesystem import copy_template, ensure_dir, verify_files
from scripts.utils.logger import error, info


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

    missing = verify_files(customer_dir, REQUIRED_WORKSPACE_FILES)
    if missing:
        error(f"Required files missing after copy: {', '.join(missing)}")
        sys.exit(1)

    info(f"Workspace created successfully at {customer_dir}")
    print(f"CUSTOMER_DIR={customer_dir}")


if __name__ == "__main__":
    main()