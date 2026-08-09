#!/usr/bin/env python3
import json
import os
import secrets
import string
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from scripts.utils.config import get_customer_dir, load_deployment_env
from scripts.utils.filesystem import read_text, write_text
from scripts.utils.logger import error, info


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _load_env(source: dict = None, prefix: str = "DEPLOYMENT_") -> dict:
    env = {}
    src = source if source is not None else os.environ
    for key, val in src.items():
        if key.startswith(prefix):
            env[key[len(prefix) :].lower()] = val
    return env


def _update_docker_compose(
    path, company_slug: str, deployment_id: str, odoo_port: int, db_password: str, domain: str
) -> None:
    content = read_text(path)
    safe = company_slug

    content = content.replace("odoo:", f"odoo_{safe}:")
    content = content.replace("db:", f"db_{safe}:")
    content = content.replace("- db", f"- db_{safe}")
    content = content.replace("odoo-net", f"odoo_net_{safe}")
    content = content.replace("odoo-data", f"odoo_data_{safe}")
    content = content.replace("odoo-db-data", f"odoo_db_data_{safe}")
    content = content.replace('${ODOO_PORT:-8069}', str(odoo_port))
    content = content.replace("${DB_PASSWORD:-odoo}", db_password)
    content = content.replace("${DB_USER:-odoo}", f"odoo_{safe}")
    content = content.replace("${POSTGRES_DB:-postgres}", f"odoo_{safe}")
    content = content.replace("odoo:8069", f"odoo_{safe}:8069")
    content = content.replace("ODOO_PORT=", "# ODOO_PORT=")

    content = content.replace(
        "    image: postgres:15-alpine",
        f"    image: postgres:15-alpine\n    container_name: db_{safe}",
    )

    odoo_service_lines = f"  odoo_{safe}:\n    container_name: odoo_{safe}\n    build:"
    content = content.replace("  odoo:", odoo_service_lines)

    write_text(path, content)
    info(f"Updated docker-compose.yml for {company_slug}")


def _update_odoo_conf(
    path, db_password: str, db_user: str, db_host: str, admin_password: str
) -> None:
    content = read_text(path)
    content = content.replace("admin_passwd = admin", f"admin_passwd = {admin_password}")
    content = content.replace("db_host = db", f"db_host = {db_host}")
    content = content.replace("db_user = odoo", f"db_user = {db_user}")
    content = content.replace("db_password = odoo", f"db_password = {db_password}")
    write_text(path, content)
    info("Updated odoo.conf")


def _update_nginx_conf(path, domain: str, deployment_id: str) -> None:
    content = read_text(path)
    if domain:
        content = content.replace("server_name _;", f"server_name {domain};")
    else:
        content = content.replace(
            "server_name _;", f"server_name {deployment_id.lower()}.systemaops.local;"
        )
    write_text(path, content)
    info("Updated nginx.conf")


def main() -> None:
    env = _load_env()
    deployment_id = os.environ.get("DEPLOYMENT_ID") or env.get("DEPLOYMENT_ID", "")
    if not deployment_id:
        error("DEPLOYMENT_ID is not set.")
        sys.exit(1)

    file_env = load_deployment_env(deployment_id)
    env = {**_load_env(file_env), **_load_env()}

    company_name = env.get("company_name", "")
    safe_name = env.get("safe_company_name", "")
    if not safe_name and company_name:
        import re
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", company_name.lower())
        safe_name = re.sub(r"_+", "_", safe_name).strip("_")

    container_prefix = env.get("container_prefix", safe_name[:12] if safe_name else "customer")
    db_password = _random_password()
    admin_password = env.get("admin_password") or _random_password()
    try:
        odoo_port = int(env.get("odoo_port", 8069))
    except ValueError:
        odoo_port = 8069
    domain = env.get("domain", "")

    customer_dir = get_customer_dir(deployment_id)

    _update_docker_compose(
        customer_dir / "docker-compose.yml",
        container_prefix,
        deployment_id,
        odoo_port,
        db_password,
        domain,
    )

    _update_odoo_conf(
        customer_dir / "config/odoo.conf",
        db_password,
        f"odoo_{container_prefix}",
        f"db_{container_prefix}",
        admin_password,
    )

    _update_nginx_conf(customer_dir / "nginx.conf", domain, deployment_id)

    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"DEPLOYMENT_DB_PASSWORD={db_password}\n")
            f.write(f"DEPLOYMENT_ADMIN_PASSWORD={admin_password}\n")
            f.write(f"DEPLOYMENT_ODOO_PORT={odoo_port}\n")

    info("Configuration files updated successfully.")


if __name__ == "__main__":
    main()