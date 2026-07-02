"""Locust load generator for the train-ticket deployment (to populate live APM traces).

Purpose: drive a *sustained* load so Datadog APM aggregates a continuous p99 per service
(the 3-minute bursts we ran by hand only produced ~4 points/service). Run this for 20-40 min
against a port-forwarded ts-ui-dashboard so `trace.servlet.request` / `trace.spring.handler`
fill in, then re-`slacheck record` / `publish`.

Only exercises endpoints that actually respond on the shared cluster (login, stations, trains);
the heavy travel/booking endpoints return 504 there, so we skip them to keep RPS high.

Usage (from a machine with working gevent — e.g. your host, not the sandbox):
    kubectl port-forward -n tt-slacheck svc/ts-ui-dashboard 18080:8080 &
    # Web UI:
    locust -f scripts/loadgen/locustfile.py --host http://localhost:18080
    # or headless, 20 users, 5 min:
    locust -f scripts/loadgen/locustfile.py --host http://localhost:18080 \
        --headless -u 20 -r 5 -t 20m
"""

from __future__ import annotations

from locust import HttpUser, between, task

_USER = {"username": "fdse_microservice", "password": "111111"}


class TrainTicketUser(HttpUser):
    wait_time = between(0.1, 0.5)  # keep RPS high to feed APM sampling

    def on_start(self) -> None:
        """Log in once per simulated user; reuse the token for the session."""
        self.token = ""
        with self.client.post(
            "/api/v1/users/login", json=_USER, catch_response=True, name="login"
        ) as r:
            if r.status_code == 200:
                try:
                    self.token = r.json()["data"]["token"]
                except Exception:
                    r.failure("no token in login response")

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(3)
    def stations(self) -> None:
        self.client.get("/api/v1/stationservice/stations", headers=self._auth, name="stations")

    @task(3)
    def trains(self) -> None:
        self.client.get("/api/v1/trainservice/trains", headers=self._auth, name="trains")

    @task(1)
    def relogin(self) -> None:
        """Periodically re-login to also exercise ts-auth / ts-user / ts-verification."""
        with self.client.post(
            "/api/v1/users/login", json=_USER, catch_response=True, name="login"
        ) as r:
            if r.status_code == 200:
                try:
                    self.token = r.json()["data"]["token"]
                except Exception:
                    pass
