import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from router.model_router import ModelRouter
from infra.circuit_breaker import CircuitBreaker


def make_config(**overrides):
    defaults = dict(
        primary_endpoint="primary",
        backup_endpoint="backup",
        lite_endpoint="lite",
        enable_backup=True,
        blacklist_backup=set(),
        tenants_force_lite=set(),
        tenants_strict_sl=set(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_primary_success_routes_to_primary():
    config = make_config()
    router = ModelRouter(config)

    req = {"input": "ok"}
    primary_mock = Mock(return_value={"model": "primary", "request": req})
    backup_mock = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})

    router.primary.infer = primary_mock
    router.backup.infer = backup_mock
    router.lite.infer = lite_mock

    resp = router.infer(req, "tenant_success")

    assert resp == {"model": "primary", "request": req}
    primary_mock.assert_called_once_with(req)
    backup_mock.assert_not_called()
    lite_mock.assert_not_called()


def test_primary_timeout_uses_lite_when_backup_disabled():
    config = make_config(enable_backup=False)
    router = ModelRouter(config)

    def raise_timeout(request):
        raise TimeoutError()

    router.primary.infer = raise_timeout
    router.backup.infer = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.lite.infer = lite_mock

    resp = router.infer({"input": 123}, "tenant_timeout_no_backup")

    assert resp == {"model": "lite"}
    lite_mock.assert_called_once()
    router.backup.infer.assert_not_called()


def test_primary_timeout_blacklisted_uses_lite():
    config = make_config(enable_backup=True, blacklist_backup={"tenant_black"})
    router = ModelRouter(config)

    def raise_timeout(request):
        raise TimeoutError()

    router.primary.infer = raise_timeout
    backup_mock = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.backup.infer = backup_mock
    router.lite.infer = lite_mock

    resp = router.infer({"input": "x"}, "tenant_black")

    assert resp == {"model": "lite"}
    lite_mock.assert_called_once()
    backup_mock.assert_not_called()


def test_primary_exception_uses_backup_when_enabled():
    config = make_config(enable_backup=True)
    router = ModelRouter(config)

    def raise_exc(request):
        raise Exception("boom")

    router.primary.infer = raise_exc
    backup_mock = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.backup.infer = backup_mock
    router.lite.infer = lite_mock

    resp = router.infer({"input": "err"}, "tenant_err")

    assert resp == {"model": "backup"}
    backup_mock.assert_called_once()
    lite_mock.assert_not_called()


def test_circuit_breaker_open_uses_backup_for_non_strict_tenant():
    config = make_config(enable_backup=True, tenants_strict_sl=set())
    router = ModelRouter(config)

    # Open the circuit breaker by recording failures up to the threshold
    for _ in range(router.circuit_breaker.failure_threshold):
        router.circuit_breaker.record_failure()

    assert router.circuit_breaker.is_open() is True

    router.primary.infer = Mock(return_value={"model": "primary"})
    backup_mock = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.backup.infer = backup_mock
    router.lite.infer = lite_mock

    resp = router.infer({}, "tenant_non_strict")

    assert resp == {"model": "backup"}
    backup_mock.assert_called_once()
    router.primary.infer.assert_not_called()
    lite_mock.assert_not_called()


def test_blacklist_prevents_backup_on_exception():
    config = make_config(enable_backup=True, blacklist_backup={"tenantX"})
    router = ModelRouter(config)

    def raise_exc(request):
        raise Exception("boom")

    router.primary.infer = raise_exc
    router.backup.infer = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.lite.infer = lite_mock

    resp = router.infer({"input": "x"}, "tenantX")

    assert resp == {"model": "lite"}
    lite_mock.assert_called_once()
    router.backup.infer.assert_not_called()


def test_circuit_breaker_threshold_and_reset():
    cb = CircuitBreaker("test_cb", failure_threshold=3)
    assert cb.is_open() is False
    assert cb.failure_count == 0

    cb.record_failure()
    assert cb.is_open() is False
    assert cb.failure_count == 1

    cb.record_failure()
    assert cb.is_open() is False
    assert cb.failure_count == 2

    cb.record_failure()
    assert cb.is_open() is True
    assert cb.failure_count == 3

    cb.reset()
    assert cb.is_open() is False
    assert cb.failure_count == 0


def test_safety_net_degrades_to_lite_when_no_other_branch_taken():
    config = make_config()
    router = ModelRouter(config)

    # Force an unusual state: circuit breaker does not allow requests but also reports not open.
    # This will bypass all earlier returns and exercise the final safety-net.
    router.fallback_policy.force_lite = lambda tenant_id: False
    router.circuit_breaker.allow_request = lambda: False
    router.circuit_breaker.is_open = lambda: False

    router.primary.infer = Mock(return_value={"model": "primary"})
    router.backup.infer = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.lite.infer = lite_mock

    resp = router.infer({"input": "safety"}, "tenant_safety")

    assert resp == {"model": "lite"}
    lite_mock.assert_called_once()
    router.primary.infer.assert_not_called()
    router.backup.infer.assert_not_called()
