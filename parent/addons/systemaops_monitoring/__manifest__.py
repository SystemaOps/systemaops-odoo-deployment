{
    "name": "Odoo Stack Monitoring",
    "summary": "Embedded monitoring dashboard and Prometheus /metrics endpoint for the deployed Odoo stack",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "views/menu.xml",
        "views/monitoring_templates.xml",
    ],
    "installable": True,
    "application": False,
}
