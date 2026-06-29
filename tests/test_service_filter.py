"""Service filtering: restrict a live topology to the app under study (e.g. ts-* only)."""


from slacheck.datadog.topology import filter_deps

_DEPS = {
    "ts-ui-dashboard": {"calls": ["ts-auth-service", "prometheus"]},
    "ts-auth-service": {"calls": ["ts-verification-code-service"]},
    "ts-verification-code-service": {"calls": []},
    "prometheus": {"calls": ["ts-ui-dashboard", "grafana"]},
    "grafana": {"calls": []},
    "ts-travel-service-with-jaeger": {"calls": ["ts-route-service-with-jaeger"]},
}


def test_include_prefix_keeps_only_matching_services():
    out = filter_deps(_DEPS, include_prefix="ts-")
    # all ts-* services kept (incl. the -with-jaeger ones, which match the prefix), the
    # callee ts-route-service-with-jaeger added as an isolated node; infra (prometheus,
    # grafana) dropped.
    assert set(out) == {
        "ts-ui-dashboard",
        "ts-auth-service",
        "ts-verification-code-service",
        "ts-travel-service-with-jaeger",
        "ts-route-service-with-jaeger",
    }
    # edges to non-matching services (prometheus) are pruned
    assert out["ts-ui-dashboard"]["calls"] == ["ts-auth-service"]


def test_exclude_pattern_drops_matching():
    out = filter_deps(_DEPS, include_prefix="ts-", exclude_contains="with-jaeger")
    assert "ts-travel-service-with-jaeger" not in out
    assert "ts-ui-dashboard" in out


def test_no_filter_returns_all():
    assert filter_deps(_DEPS) == _DEPS


def test_explicit_include_list():
    out = filter_deps(_DEPS, include=["ts-ui-dashboard", "ts-auth-service"])
    assert set(out) == {"ts-ui-dashboard", "ts-auth-service"}
    # ts-auth's edge to verification (not in the list) is pruned
    assert out["ts-auth-service"]["calls"] == []


def test_pruned_callees_still_appear_as_nodes_if_matching():
    # a callee that matches the filter but has no own entry is kept as an isolated node
    deps = {"ts-a": {"calls": ["ts-b"]}}
    out = filter_deps(deps, include_prefix="ts-")
    assert "ts-b" in out and out["ts-b"]["calls"] == []
