import pytest
from unittest.mock import Mock, MagicMock
from router.model_router import ModelRouter


class TestTimeoutFallback:
    """Test suite for handling primary model timeouts"""

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

    @pytest.fixture
    def router(self, mock_config):
        """Instantiate the model router with mock config"""
        return ModelRouter(mock_config)

    def test_timeout_backup_allowed_uses_backup(self, router):
        """
        Test Case A1: Primary timeout with backup allowed (non-blacklisted tenant)
        Expected: Router falls back to backup model
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}

        # Mock primary to raise TimeoutError
        primary_mock = MagicMock(side_effect=TimeoutError("Primary model timeout"))
        router.primary.infer = primary_mock
        
        # Mock backup to return success
        backup_result = {"model": "backup", "result": "success"}
        backup_mock = MagicMock(return_value=backup_result)
        router.backup.infer = backup_mock
        
        # Mock lite
        lite_mock = MagicMock()
        router.lite.infer = lite_mock

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify backup was called and lite was not
        assert result == backup_result
        backup_mock.assert_called_once_with(request_data)
        lite_mock.assert_not_called()

    def test_timeout_backup_blacklisted_uses_lite(self, mock_config):
        """
        Test Case A2: Primary timeout with tenant blacklisted (HIGH PRIORITY - INCIDENT)
        Expected: Router falls back to lite model (backup denied)
        """
        tenant_id = "tenant_blacklisted"
        request_data = {"query": "test"}
        
        # Configure backup as blacklisted
        mock_config.blacklist_backup = {tenant_id}
        router = ModelRouter(mock_config)

        # Mock primary to raise TimeoutError
        primary_mock = MagicMock(side_effect=TimeoutError("Primary model timeout"))
        router.primary.infer = primary_mock
        
        # Mock lite to return success
        lite_result = {"model": "lite", "result": "degraded"}
        lite_mock = MagicMock(return_value=lite_result)
        router.lite.infer = lite_mock
        
        # Mock backup
        backup_mock = MagicMock()
        router.backup.infer = backup_mock

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify lite was called and backup was NOT called
        assert result == lite_result
        backup_mock.assert_not_called()
        lite_mock.assert_called_once_with(request_data)

    def test_timeout_backup_disabled_uses_lite(self, mock_config):
        """
        Test Case A3: Primary timeout with backup globally disabled
        Expected: Router falls back to lite model (backup disabled)
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}
        
        # Disable backup globally
        mock_config.enable_backup = False
        router = ModelRouter(mock_config)

        # Mock primary to raise TimeoutError
        primary_mock = MagicMock(side_effect=TimeoutError("Primary model timeout"))
        router.primary.infer = primary_mock
        
        # Mock lite to return success
        lite_result = {"model": "lite", "result": "degraded"}
        lite_mock = MagicMock(return_value=lite_result)
        router.lite.infer = lite_mock
        
        # Mock backup
        backup_mock = MagicMock()
        router.backup.infer = backup_mock

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify lite was called and backup was NOT called
        assert result == lite_result
        backup_mock.assert_not_called()
        lite_mock.assert_called_once_with(request_data)

    def test_circuit_breaker_records_timeout_failure(self, router):
        """
        Test: Circuit breaker records TimeoutError as a failure
        Expected: Circuit breaker failure count increments
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}
        
        initial_failure_count = router.circuit_breaker.failure_count
        
        # Mock primary to raise TimeoutError
        primary_mock = MagicMock(side_effect=TimeoutError("Primary model timeout"))
        router.primary.infer = primary_mock
        
        # Mock lite to return success
        lite_mock = MagicMock(return_value={"model": "lite"})
        router.lite.infer = lite_mock

        # Execute
        router.infer(request_data, tenant_id)

        # Verify failure was recorded
        assert router.circuit_breaker.failure_count == initial_failure_count + 1
