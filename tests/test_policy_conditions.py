import pytest
from unittest.mock import Mock, MagicMock
from router.model_router import ModelRouter


class TestPolicyConditions:
    """Test suite for tenant policy conditions"""

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

    def test_force_lite_bypasses_all_models(self, mock_config):
        """
        Test Case D1: Force lite policy overrides all routing logic
        Expected: Lite model is called immediately regardless of primary status
        """
        tenant_id = "tenant_lite_forced"
        request_data = {"query": "test"}
        
        # Configure tenant to force lite
        mock_config.tenants_force_lite = {tenant_id}
        router = ModelRouter(mock_config)

        # Mock lite to return success
        lite_result = {"model": "lite", "forced": True}
        lite_mock = MagicMock(return_value=lite_result)
        router.lite.infer = lite_mock

        # Primary is healthy
        primary_mock = MagicMock(return_value={"model": "primary", "healthy": True})
        router.primary.infer = primary_mock

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify lite was called and primary was NOT called
        assert result == lite_result
        primary_mock.assert_not_called()
        lite_mock.assert_called_once_with(request_data)

    def test_normal_tenant_uses_primary_when_healthy(self, mock_config):
        """
        Test Case D2: Normal tenant (no special policies) uses primary when healthy
        Expected: Primary model called and returns successfully
        """
        tenant_id = "tenant_normal"
        request_data = {"query": "test"}
        
        router = ModelRouter(mock_config)

        # Mock primary to return success
        primary_result = {"model": "primary", "result": "success"}
        primary_mock = MagicMock(return_value=primary_result)
        router.primary.infer = primary_mock
        
        # Mock backup and lite
        backup_mock = MagicMock()
        router.backup.infer = backup_mock
        
        lite_mock = MagicMock()
        router.lite.infer = lite_mock

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify primary was called and backup/lite were NOT called
        assert result == primary_result
        primary_mock.assert_called_once_with(request_data)
        backup_mock.assert_not_called()
        lite_mock.assert_not_called()

    def test_backup_blacklist_enforcement(self, mock_config):
        """
        Test: Verify that blacklist logic correctly denies backup to blacklisted tenants
        Expected: allow_backup_on_timeout() returns False for blacklisted tenants
        """
        tenant_blacklisted = "tenant_blacklisted"
        tenant_normal = "tenant_normal"
        
        mock_config.blacklist_backup = {tenant_blacklisted}
        mock_config.enable_backup = True
        
        router = ModelRouter(mock_config)
        policy = router.fallback_policy

        # Blacklisted tenant should not be allowed backup
        assert not policy.allow_backup_on_timeout(tenant_blacklisted)
        assert not policy.allow_backup_on_error(tenant_blacklisted)
        
        # Normal tenant should be allowed backup
        assert policy.allow_backup_on_timeout(tenant_normal)
        assert policy.allow_backup_on_error(tenant_normal)

    def test_strict_sl_policy_prevents_backup_when_open(self, mock_config):
        """
        Test: Strict SL tenants should not use backup when circuit breaker opens
        Expected: use_backup_when_open() returns False for strict SL tenants
        """
        tenant_strict = "tenant_strict_sl"
        tenant_normal = "tenant_normal"
        
        mock_config.enable_backup = True
        mock_config.tenants_strict_sl = {tenant_strict}
        
        router = ModelRouter(mock_config)
        policy = router.fallback_policy

        # Strict SL tenant should not use backup when breaker opens
        assert not policy.use_backup_when_open(tenant_strict)
        
        # Normal tenant should use backup when breaker opens
        assert policy.use_backup_when_open(tenant_normal)
