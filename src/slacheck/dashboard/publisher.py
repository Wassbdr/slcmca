"""Push a dashboard dict to Datadog (Phase 4). Requires the ``datadog`` extra + dashboards_write.

Import-safe without the SDK: the datadog import is lazy. Idempotent: if a dashboard with the
same title exists, it is updated rather than duplicated.
"""

from __future__ import annotations

from slacheck.config import Settings


def _api_client(settings: Settings):
    from datadog_api_client import ApiClient, Configuration

    config = Configuration()
    config.api_key["apiKeyAuth"] = settings.api_key
    config.api_key["appKeyAuth"] = settings.app_key
    config.server_variables["site"] = settings.site
    return ApiClient(config)


def publish(dashboard: dict, settings: Settings) -> str:
    """Create or update the dashboard. Returns its public URL."""
    from datadog_api_client.v1.api.dashboards_api import DashboardsApi

    with _api_client(settings) as client:
        api = DashboardsApi(client)

        existing_id = None
        listed = api.list_dashboards()
        for d in listed.get("dashboards", []) or []:
            if d.get("title") == dashboard["title"]:
                existing_id = d.get("id")
                break

        if existing_id:
            resp = api.update_dashboard(dashboard_id=existing_id, body=dashboard)
        else:
            resp = api.create_dashboard(body=dashboard)

    dash_id = resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", existing_id)
    return f"https://{settings.site}/dashboard/{dash_id}"
