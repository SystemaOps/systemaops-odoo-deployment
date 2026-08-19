#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from scripts.utils.config import get_customer_dir, load_deployment_env
from scripts.utils.filesystem import write_text
from scripts.utils.logger import info


def _read_env(source: dict = None, prefix: str = "DEPLOYMENT_") -> dict:
    env = {}
    src = source if source is not None else os.environ
    for key, val in src.items():
        if key.startswith(prefix):
            name = key[len(prefix) :].lower()
            env[name] = val
    return env


def generate_summary(env: dict, deployment_id: str) -> dict:
    modules_raw = env.get("selected_modules", "[]")
    try:
        modules = json.loads(modules_raw)
    except (json.JSONDecodeError, TypeError):
        modules = []

    summary = {
        "deployment_id": deployment_id,
        "company_name": env.get("company_name", ""),
        "database_name": env.get("database_name", ""),
        "industry": env.get("industry", ""),
        "timezone": env.get("timezone", "UTC"),
        "number_of_users": int(env.get("number_of_users", 10)),
        "module_count": len(modules),
        "status": "package_prepared",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "odoo_port": int(env.get("odoo_port", 8069)),
        "grafana_port": int(env.get("grafana_port", 3002)),
        "admin_name": env.get("admin_name", "admin"),
        "domain": env.get("domain", ""),
        "container_prefix": env.get("container_prefix", ""),
        # Phase 2 target VM
        "vm_provider": env.get("vm_provider", ""),
        "vm_host": env.get("vm_host", ""),
        "vm_ssh_user": env.get("vm_ssh_user", ""),
        "vm_ssh_port": int(env.get("vm_ssh_port", 22) or 22),
        "vm_domain": env.get("vm_domain", ""),
        "ssh_key_secret": env.get("ssh_key_secret", ""),
        "offsite_target": env.get("offsite_target", ""),
    }
    return summary


# Module display name -> Odoo technical code mapping
MODULE_CODE_MAP = {
    'CRM': 'crm',
    'Sales': 'sale_management',
    'Purchase': 'purchase',
    'Inventory': 'stock',
    'Manufacturing': 'mrp',
    'Accounting': 'account',
    'HR': 'hr',
    'Payroll': 'hr_payroll',
    'POS': 'point_of_sale',
    'Website': 'website',
    'Project': 'project',
    'Helpdesk': 'helpdesk',
    'Quality': 'quality',
    'Maintenance': 'maintenance',
    'Rental': 'rental',
    'Knowledge': 'knowledge',
    'Marketing': 'marketing',
    'Planning': 'planning',
    'Field Service': 'fieldservice',
    'Contacts': 'contacts',
    'Discuss': 'discuss',
    'Studio': 'web_studio',
    'eCommerce': 'website_sale',
    'Blog': 'blog',
    'Forum': 'forum',
    'Live Chat': 'im_livechat',
    'eLearning': 'website_slides',
    'Point of Sale': 'point_of_sale',
    'Subscriptions': 'sale_subscription',
    'Invoicing': 'account_accountant',
    'Expenses': 'hr_expense',
    'Documents': 'documents',
    'Spreadsheets': 'spreadsheet',
    'Sign': 'sign',
    'ESG': 'esg',
    'PLM': 'mrp_plm',
    'Repair': 'repair',
    'Employees': 'hr',
    'Recruitment': 'hr_recruitment',
    'Time Off': 'hr_holidays',
    'Appraisals': 'hr_appraisal',
    'Referral': 'hr_referral',
    'Fleet': 'fleet',
    'Marketing Automation': 'marketing_automation',
    'Email Marketing': 'mass_mailing',
    'SMS Marketing': 'sms',
    'Social Marketing': 'social_marketing',
    'Events': 'event',
    'Survey': 'survey',
    'Timesheets': 'hr_timesheet',
    'Appointments': 'appointment',
    'Approvals': 'approval',
    'Internet of Things': 'iot',
    'VoIP': 'voip',
    'AI': 'ai',
    'WhatsApp': 'whatsapp',
}


def map_modules(display_names: list[str]) -> list[str]:
    """Convert display names to Odoo technical codes."""
    mapped = []
    for name in display_names:
        mapped.append(MODULE_CODE_MAP.get(name, name.lower().replace(' ', '_')))
    return mapped


def generate_install_modules(env: dict) -> dict:
    modules_raw = env.get("selected_modules", "[]")
    try:
        modules = json.loads(modules_raw)
    except (json.JSONDecodeError, TypeError):
        modules = []

    # Convert display names to Odoo technical codes
    modules = map_modules(modules)

    # The monitoring addon (menu + /monitoring + /metrics) ships with every
    # deployment, so it must always be in the init/install list.
    if "systemaops_monitoring" not in modules:
        modules.append("systemaops_monitoring")

    install = {
        "install_modules": modules,
        "phase_2_instructions": {
            "description": "Pass this module list to Odoo's module installation step in Phase 2.",
            "method": "odoo -i <module1,module2,...> or via Odoo UI Apps menu.",
        },
    }
    return install


def main() -> None:
    deployment_id = os.environ.get("DEPLOYMENT_ID", "")
    if not deployment_id:
        print("DEPLOYMENT_ID not set; using 'unknown'")
        deployment_id = "unknown"

    file_env = load_deployment_env(deployment_id)
    env = {**_read_env(file_env), **_read_env()}
    customer_dir = get_customer_dir(deployment_id)

    summary = generate_summary(env, deployment_id)
    summary_path = customer_dir / "deployment_summary.json"
    write_text(summary_path, json.dumps(summary, indent=2))
    info(f"Written: {summary_path}")

    install_modules = generate_install_modules(env)
    install_path = customer_dir / "install_modules.json"
    write_text(install_path, json.dumps(install_modules, indent=2))
    info(f"Written: {install_path}")

    print(f"Metadata generated for deployment {deployment_id}")


if __name__ == "__main__":
    main()