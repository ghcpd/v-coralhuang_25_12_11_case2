import pytest
from unittest.mock import Mock, MagicMock
from router.model_router import ModelRouter


class TestCircuitBreakerFallback:
    """Test suite for circuit breaker integration with fallback logic"""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration for model router"""
        config = Mock()
        config.primary_endpoint = "http://primary:8000"
        config.backup_endpoint = "http://backup:8000"
        config.lite_endpoint = "http://lite:8000"
        config.enable_backup = True
        config.blacklist_backup = set()
        config.tenants_force_lite = set()
        config.tenants_strict_sl = set()
        return config

    def test_breaker_opens_after_threshold_then_uses_backup(self, mock_config):
        """
        Test Case C1: Circuit breaker opens after failures, backup allowed
        Expected: After threshold failures, router uses backup when breaker is open
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}
        
        router = ModelRouter(mock_config)
        # Set lower threshold for faster test
        router.circuit_breaker.failure_threshold = 2

        # Mock primary to always raise
        primary_mock = MagicMock(side_effect=RuntimeError("Primary fails"))
        router.primary.infer = primary_mock
        
        # Mock backup to return success
        backup_result = {"model": "backup", "success": True}
        backup_mock = MagicMock(return_value=backup_result)
        router.backup.infer = backup_mock

        # First two calls: primary fails, triggers circuit breaker
        for i in range(2):
            try:
                router.infer(request_data, tenant_id)
            except Exception:
                pass

        # Verify breaker is now open
        assert router.circuit_breaker.is_open()

        # Third call: breaker is open, should use backup
        result = router.infer(request_data, tenant_id)
        
        # Verify backup was called
        assert result == backup_result
        backup_mock.assert_called()

    def test_breaker_open_strict_sl_tenant_uses_lite(self, mock_config):
        """
        Test Case C2: Circuit breaker open, strict SL tenant must use lite (HIGH PRIORITY)
        Expected: Even though backup is enabled, strict SL tenant uses lite when breaker opens
        """
        tenant_id = "tenant_strict"
        request_data = {"query": "test"}
        
        # Configure strict SL tenant
        mock_config.tenants_strict_sl = {tenant_id}
        router = ModelRouter(mock_config)
        router.circuit_breaker.failure_threshold = 2

        # Mock primary to always raise
        primary_mock = MagicMock(side_effect=RuntimeError("Primary fails"))
        router.primary.infer = primary_mock
        
        # Mock lite to return success
        lite_result = {"model": "lite", "degraded": True}
        lite_mock = MagicMock(return_value=lite_result)
        router.lite.infer = lite_mock

        # Trigger failures to open breaker (backup not called during these errors)
        for i in range(2):
            try:
                router.infer(request_data, tenant_id)
            except Exception:
                pass

        # Verify breaker is open
        assert router.circuit_breaker.is_open()

        # Now mock backup for the final call
        backup_mock = MagicMock()
        router.backup.infer = backup_mock

        # When breaker is open, strict SL tenant should use lite (not backup)
        result = router.infer(request_data, tenant_id)
        
        # Verify lite was called and backup was NOT called
        assert result == lite_result
        backup_mock.assert_not_called()
        lite_mock.assert_called()

    def test_breaker_open_backup_disabled_uses_lite(self, mock_config):
        """
        Test Case C3: Circuit breaker open with backup globally disabled
        Expected: Router uses lite when breaker opens and backup is disabled
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}
        
        # Disable backup globally
        mock_config.enable_backup = False
        router = ModelRouter(mock_config)
        router.circuit_breaker.failure_threshold = 2

        # Mock primary to always raise
        primary_mock = MagicMock(side_effect=RuntimeError("Primary fails"))
        router.primary.infer = primary_mock
        
        # Mock lite to return success
        lite_result = {"model": "lite", "degraded": True}
        lite_mock = MagicMock(return_value=lite_result)
        router.lite.infer = lite_mock
        
        # Mock backup
        backup_mock = MagicMock()
        router.backup.infer = backup_mock

        # Trigger failures to open breaker
        for i in range(2):
            try:
                router.infer(request_data, tenant_id)
            except Exception:
                pass

        # Verify breaker is open
        assert router.circuit_breaker.is_open()

        # When breaker is open and backup is disabled, use lite
        result = router.infer(request_data, tenant_id)
        
        # Verify lite was called and backup was NOT called
        assert result == lite_result
        backup_mock.assert_not_called()
        lite_mock.assert_called()

    def test_circuit_breaker_reset_allows_primary_again(self, mock_config):
        """
        Test Case E1: Circuit breaker resets and allows primary model again
        Expected: After reset, allow_request() returns True and primary can be used
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}
        
        router = ModelRouter(mock_config)
        
        # Manually open the breaker
        router.circuit_breaker._open = True
        router.circuit_breaker.failure_count = 3
        assert router.circuit_breaker.is_open()
        assert not router.circuit_breaker.allow_request()

        # Reset the breaker
        router.circuit_breaker.reset()
        
        # Verify breaker is now closed
        assert not router.circuit_breaker.is_open()
        assert router.circuit_breaker.allow_request()

    def test_failure_threshold_crossing(self, mock_config):
        """
        Test Case E2: Verify breaker opens at exact threshold
        Expected: Breaker opens when failure_count >= failure_threshold
        """
        router = ModelRouter(mock_config)
        router.circuit_breaker.failure_threshold = 3
        
        # Record failures and verify threshold crossing
        assert not router.circuit_breaker.is_open()
        
        router.circuit_breaker.record_failure()
        assert router.circuit_breaker.failure_count == 1
        assert not router.circuit_breaker.is_open()
        
        router.circuit_breaker.record_failure()
        assert router.circuit_breaker.failure_count == 2
        assert not router.circuit_breaker.is_open()
        
        router.circuit_breaker.record_failure()
        assert router.circuit_breaker.failure_count == 3
        assert router.circuit_breaker.is_open()
