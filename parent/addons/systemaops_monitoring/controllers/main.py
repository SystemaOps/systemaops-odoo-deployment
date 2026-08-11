import json
import threading

from odoo import http
from odoo.http import request

_requests_lock = threading.Lock()
_requests_total = 0

_DEFAULT_MONITORING_PORT = 3002


def _grafana_port() -> int:
    """Read the Grafana host port from monitoring.json (mounted by the
    deployment pipeline). On a SystemaOps-managed server every customer gets
    their own Grafana port, so it cannot be hardcoded."""
    try:
        with open("/etc/odoo/monitoring.json") as fh:
            return int(json.load(fh).get("grafana_port") or _DEFAULT_MONITORING_PORT)
    except (OSError, ValueError, TypeError):
        return _DEFAULT_MONITORING_PORT


class MonitoringController(http.Controller):
    """Exposes the embedded monitoring page and a small /metrics endpoint.

    The Grafana dashboard runs on the customer VM (host port from
    /etc/odoo/monitoring.json, default 3002) as part of the monitoring stack
    started during Phase 2. The /monitoring route renders an iframe pointing
    at it; the /metrics route is scraped by the local Prometheus
    (job "odoo", target localhost:8069).
    """

    @http.route("/monitoring", type="http", auth="user", csrf=False)
    def monitoring(self, **kwargs):
        monitoring_url = self._monitoring_url()
        return request.render(
            "systemaops_monitoring.monitoring_page",
            {"monitoring_url": monitoring_url},
        )

    @http.route("/metrics", type="http", auth="public", csrf=False)
    def metrics(self, **kwargs):
        global _requests_total
        with _requests_lock:
            _requests_total += 1

        body = "\n".join(
            [
                "# HELP systemaops_odoo_up Whether the Odoo app is serving metrics.",
                "# TYPE systemaops_odoo_up gauge",
                "systemaops_odoo_up 1",
                "# HELP systemaops_odoo_http_requests_total Requests served by the metrics endpoint.",
                "# TYPE systemaops_odoo_http_requests_total counter",
                f"systemaops_odoo_http_requests_total {_requests_total}",
                self._gauge("systemaops_odoo_users", "res.users", "Active Odoo users."),
                self._gauge("systemaops_odoo_contacts", "res.partner", "Partners/contacts."),
                self._gauge("systemaops_odoo_products", "product.template", "Product templates."),
            ]
        )
        return request.make_response(
            body + "\n",
            headers=[("Content-Type", "text/plain; version=0.0.4; charset=utf-8")],
        )

    def _gauge(self, name, model, help_text, query=None):
        try:
            count = request.env[model].search_count([]) if query is None else query()
        except Exception:
            count = -1
        return "\n".join(
            [
                f"# HELP {name} {help_text}",
                f"# TYPE {name} gauge",
                f"{name} {count}",
            ]
        )

    def _monitoring_url(self):
        host = request.httprequest.host or "localhost"
        hostname = host.rsplit(":", 1)[0].strip()
        if not hostname or hostname in ("localhost", "127.0.0.1"):
            hostname = "localhost"
        return f"http://{hostname}:{_grafana_port()}/"
