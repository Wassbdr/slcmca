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
    """Create or update the dashboard. Returns its public URL.

    ``dashboard`` is the plain dict from dashboard.builder; the SDK requires a typed
    ``Dashboard`` model, so we deserialize the dict through the client.
    """
    import json

    from datadog_api_client.v1.api.dashboards_api import DashboardsApi
    from datadog_api_client.v1.model.dashboard import Dashboard

    with _api_client(settings) as client:
        api = DashboardsApi(client)
        body: Dashboard = client.deserialize(json.dumps(dashboard), (Dashboard,), True)

        existing_id = None
        for d in getattr(api.list_dashboards(), "dashboards", []) or []:
            if getattr(d, "title", None) == dashboard["title"]:
                existing_id = getattr(d, "id", None)
                break

        if existing_id:
            resp = api.update_dashboard(dashboard_id=existing_id, body=body)
        else:
            resp = api.create_dashboard(body=body)

    dash_id = getattr(resp, "id", existing_id)
    return f"https://{settings.site}/dashboard/{dash_id}"
