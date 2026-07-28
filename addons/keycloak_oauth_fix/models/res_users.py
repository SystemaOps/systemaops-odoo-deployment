from odoo import api, models
import requests

class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _auth_oauth_validate(self, provider, access_token):
        """
        Keycloak /userinfo rejects access_token in query string (401).
        Odoo's generic OAuth validator may use that pattern.
        Force Bearer Authorization header when validation_endpoint is Keycloak userinfo.
        """
        endpoint = (provider or {}).get("validation_endpoint") or ""
        if endpoint.endswith("/protocol/openid-connect/userinfo"):
            try:
                resp = requests.get(
                    endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10,
                )
            except Exception:
                return {"error": "invalid_request"}

            if resp.status_code != 200:
                # Return Keycloak error json if present
                try:
                    data = resp.json()
                    if isinstance(data, dict) and "error" in data:
                        return data
                except Exception:
                    pass
                return {"error": "invalid_request"}

            return resp.json()

        return super()._auth_oauth_validate(provider, access_token)
