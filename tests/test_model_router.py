import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from router.model_router import ModelRouter


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


def test_primary_timeout_uses_backup_when_enabled():
    config = make_config(enable_backup=True, blacklist_backup=set())
    router = ModelRouter(config)

    def raise_timeout(req):
        raise TimeoutError()

    router.primary.infer = raise_timeout
    backup_mock = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.backup.infer = backup_mock
    router.lite.infer = lite_mock

    req = {"input": "x"}
    resp = router.infer(req, "tenantA")

    assert resp == {"model": "backup"}
    backup_mock.assert_called_once_with(req)
    lite_mock.assert_not_called()


def test_primary_exception_uses_lite_when_backup_disabled():
    config = make_config(enable_backup=False)
    router = ModelRouter(config)

    def raise_exc(req):
        raise Exception("boom")

    router.primary.infer = raise_exc
    router.backup.infer = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.lite.infer = lite_mock

    resp = router.infer({"input": "x"}, "tenantB")

    assert resp == {"model": "lite"}
    lite_mock.assert_called_once()
    router.backup.infer.assert_not_called()


def test_circuit_breaker_open_uses_lite_for_strict_tenant():
    config = make_config(enable_backup=True, tenants_strict_sl={"tenantC"})
    router = ModelRouter(config)

    # Open the circuit breaker by recording failures up to the threshold
    for _ in range(router.circuit_breaker.failure_threshold):
        router.circuit_breaker.record_failure()

    assert router.circuit_breaker.is_open() is True

    router.primary.infer = Mock(return_value={"model": "primary"})
    router.backup.infer = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.lite.infer = lite_mock

    resp = router.infer({}, "tenantC")

    assert resp == {"model": "lite"}
    router.primary.infer.assert_not_called()
    router.backup.infer.assert_not_called()
    lite_mock.assert_called_once()


def test_force_lite_tenant_always_uses_lite():
    config = make_config(tenants_force_lite={"tenantD"})
    router = ModelRouter(config)

    router.primary.infer = Mock(return_value={"model": "primary"})
    router.backup.infer = Mock(return_value={"model": "backup"})
    lite_mock = Mock(return_value={"model": "lite"})
    router.lite.infer = lite_mock

    resp = router.infer({"input": 1}, "tenantD")

    assert resp == {"model": "lite"}
    lite_mock.assert_called_once()
    router.primary.infer.assert_not_called()
    router.backup.infer.assert_not_called()
