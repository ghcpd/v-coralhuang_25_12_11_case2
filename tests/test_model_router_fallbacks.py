import types
import pytest

from router.model_router import ModelRouter
from models.primary_model_client import PrimaryModelClient
from models.backup_model_client import BackupModelClient
from models.lite_model_client import LiteModelClient


class DummyConfig:
    def __init__(self, **kwargs):
        # default endpoints used by tests
        self.primary_endpoint = kwargs.get("primary_endpoint", "primary://localhost")
        self.backup_endpoint = kwargs.get("backup_endpoint", "backup://localhost")
        self.lite_endpoint = kwargs.get("lite_endpoint", "lite://localhost")
        self.enable_backup = kwargs.get("enable_backup", True)
        self.blacklist_backup = kwargs.get("blacklist_backup", set())
        self.tenants_force_lite = kwargs.get("tenants_force_lite", set())
        self.tenants_strict_sl = kwargs.get("tenants_strict_sl", set())


def test_primary_timeout_allows_backup(monkeypatch):
    """Primary times out and backup is allowed -> backup.infer called."""
    tenant_id = "tenant-A"
    config = DummyConfig(enable_backup=True, blacklist_backup=set())
    router = ModelRouter(config)

    # Flag holders
    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_timeout(self, request):
        called["primary"] += 1
        raise TimeoutError("Primary timeout simulated")

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_timeout)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    assert resp["model"] == "backup"
    assert called["primary"] == 1
    assert called["backup"] == 1
    assert called["lite"] == 0


def test_primary_timeout_blacklist_falls_to_lite(monkeypatch):
    """Primary times out but tenant is blacklisted -> should go to lite."""
    tenant_id = "tenant-B"
    config = DummyConfig(enable_backup=True, blacklist_backup={tenant_id})
    router = ModelRouter(config)

    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_timeout(self, request):
        called["primary"] += 1
        raise TimeoutError("Primary timeout simulated")

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_timeout)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    assert resp["model"] == "lite"
    assert called["primary"] == 1
    assert called["backup"] == 0
    assert called["lite"] == 1


def test_circuit_breaker_open_uses_backup_and_not_primary(monkeypatch):
    """When circuit breaker is open and backup allowed, router uses backup."""
    tenant_id = "tenant-C"
    config = DummyConfig(enable_backup=True)
    router = ModelRouter(config)

    # Open circuit breaker by setting its internal flag; this is easier than
    # simulating many consecutive failures in tests.
    router.circuit_breaker._open = True

    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_infer(self, request):
        called["primary"] += 1
        return {"model": "primary"}

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_infer)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    assert resp["model"] == "backup"
    assert called["primary"] == 0
    assert called["backup"] == 1
    assert called["lite"] == 0


def test_strict_tenant_timeout_allows_backup_current_behavior(monkeypatch):
    """A tenant listed in `tenants_strict_sl` should NOT use backup when breaker open;
    however, on a timeout during a single primary request, the current code does
    not check strict SL for timeout/error fallback, which can lead to a problematic
    fallback choice. This test asserts the current behavior: on timeout, backup
    may be used even for strict tenants."""
    tenant_id = "tenant-strict"
    config = DummyConfig(enable_backup=True, tenants_strict_sl={tenant_id})
    router = ModelRouter(config)

    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_timeout(self, request):
        called["primary"] += 1
        raise TimeoutError("Primary timeout simulated")

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_timeout)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    # Current code allows backup on timeout; this is a potential incident.
    assert resp["model"] == "backup"
    assert called["primary"] == 1
    assert called["backup"] == 1
    assert called["lite"] == 0


def test_primary_success_routes_to_primary(monkeypatch):
    """Primary succeeds -> primary.infer called and others not called."""
    tenant_id = "tenant-ok"
    config = DummyConfig(enable_backup=True)
    router = ModelRouter(config)

    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_infer(self, request):
        called["primary"] += 1
        return {"model": "primary"}

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_infer)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    assert resp["model"] == "primary"
    assert called["primary"] == 1
    assert called["backup"] == 0
    assert called["lite"] == 0


def test_generic_exception_allows_backup(monkeypatch):
    """Primary raises generic Exception -> backup used when allowed."""
    tenant_id = "tenant-ex"
    config = DummyConfig(enable_backup=True)
    router = ModelRouter(config)

    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_error(self, request):
        called["primary"] += 1
        raise Exception("boom")

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_error)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    assert resp["model"] == "backup"
    assert called["primary"] == 1
    assert called["backup"] == 1
    assert called["lite"] == 0


def test_generic_exception_blacklist_falls_to_lite(monkeypatch):
    """Primary raises Exception but tenant blacklisted -> lite used."""
    tenant_id = "tenant-ex-b"
    config = DummyConfig(enable_backup=True, blacklist_backup={tenant_id})
    router = ModelRouter(config)

    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_error(self, request):
        called["primary"] += 1
        raise Exception("boom")

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_error)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    assert resp["model"] == "lite"
    assert called["primary"] == 1
    assert called["backup"] == 0
    assert called["lite"] == 1


def test_force_lite_routes_to_lite(monkeypatch):
    """Tenant in `tenants_force_lite` always goes to lite model."""
    tenant_id = "tenant-force"
    config = DummyConfig(tenants_force_lite={tenant_id})
    router = ModelRouter(config)

    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_infer(self, request):
        called["primary"] += 1
        return {"model": "primary"}

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_infer)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    assert resp["model"] == "lite"
    assert called["primary"] == 0
    assert called["backup"] == 0
    assert called["lite"] == 1


def test_breaker_open_strict_sl_routes_to_lite(monkeypatch):
    """Breaker open and tenant in strict SL -> lite used (backup disallowed)."""
    tenant_id = "tenant-strict-open"
    config = DummyConfig(enable_backup=True, tenants_strict_sl={tenant_id})
    router = ModelRouter(config)

    router.circuit_breaker._open = True

    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_infer(self, request):
        called["primary"] += 1
        return {"model": "primary"}

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_infer)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    assert resp["model"] == "lite"
    assert called["primary"] == 0
    assert called["backup"] == 0
    assert called["lite"] == 1


def test_enable_backup_false_fallbacks_to_lite_on_timeout(monkeypatch):
    """When `enable_backup` is False, a timeout should fallback to lite."""
    tenant_id = "tenant-no-backup"
    config = DummyConfig(enable_backup=False)
    router = ModelRouter(config)

    called = {"primary": 0, "backup": 0, "lite": 0}

    def primary_timeout(self, request):
        called["primary"] += 1
        raise TimeoutError("Primary timeout simulated")

    def backup_infer(self, request):
        called["backup"] += 1
        return {"model": "backup"}

    def lite_infer(self, request):
        called["lite"] += 1
        return {"model": "lite"}

    monkeypatch.setattr(PrimaryModelClient, "infer", primary_timeout)
    monkeypatch.setattr(BackupModelClient, "infer", backup_infer)
    monkeypatch.setattr(LiteModelClient, "infer", lite_infer)

    resp = router.infer({"input": "x"}, tenant_id)
    assert resp["model"] == "lite"
    assert called["primary"] == 1
    assert called["backup"] == 0
    assert called["lite"] == 1
