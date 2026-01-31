import sys
sys.path.insert(0, 'src')

import pytest
from unittest.mock import Mock, patch
from router.model_router import ModelRouter


class TestModelRouterFallback:

    @patch('models.lite_model_client.LiteModelClient.infer')
    @patch('models.backup_model_client.BackupModelClient.infer')
    @patch('models.primary_model_client.PrimaryModelClient.infer')
    def test_force_lite_policy(self, primary_mock, backup_mock, lite_mock):
        """Test that force_lite tenants always use lite model."""
        lite_mock.return_value = {'model': 'lite'}

        config = Mock()
        config.tenants_force_lite = {'tenant_force'}
        config.primary_endpoint = 'primary'
        config.backup_endpoint = 'backup'
        config.lite_endpoint = 'lite'
        config.enable_backup = True
        config.blacklist_backup = set()
        config.tenants_strict_sl = set()

        router = ModelRouter(config)
        result = router.infer('request', 'tenant_force')

        primary_mock.assert_not_called()
        backup_mock.assert_not_called()
        lite_mock.assert_called_once_with('request')
        assert result['model'] == 'lite'

    @patch('models.lite_model_client.LiteModelClient.infer')
    @patch('models.backup_model_client.BackupModelClient.infer')
    @patch('models.primary_model_client.PrimaryModelClient.infer')
    def test_primary_timeout_backup_allowed(self, primary_mock, backup_mock, lite_mock):
        """Test timeout with backup allowed."""
        primary_mock.side_effect = TimeoutError
        backup_mock.return_value = {'model': 'backup'}

        config = Mock()
        config.tenants_force_lite = set()
        config.primary_endpoint = 'primary'
        config.backup_endpoint = 'backup'
        config.lite_endpoint = 'lite'
        config.enable_backup = True
        config.blacklist_backup = set()
        config.tenants_strict_sl = set()

        router = ModelRouter(config)
        result = router.infer('request', 'tenant_normal')

        primary_mock.assert_called_once_with('request')
        backup_mock.assert_called_once_with('request')
        lite_mock.assert_not_called()
        assert result['model'] == 'backup'

    @patch('models.lite_model_client.LiteModelClient.infer')
    @patch('models.backup_model_client.BackupModelClient.infer')
    @patch('models.primary_model_client.PrimaryModelClient.infer')
    def test_primary_timeout_backup_blacklisted(self, primary_mock, backup_mock, lite_mock):
        """Test timeout with backup blacklisted."""
        primary_mock.side_effect = TimeoutError
        lite_mock.return_value = {'model': 'lite'}

        config = Mock()
        config.tenants_force_lite = set()
        config.primary_endpoint = 'primary'
        config.backup_endpoint = 'backup'
        config.lite_endpoint = 'lite'
        config.enable_backup = True
        config.blacklist_backup = {'tenant_black'}
        config.tenants_strict_sl = set()

        router = ModelRouter(config)
        result = router.infer('request', 'tenant_black')

        primary_mock.assert_called_once_with('request')
        backup_mock.assert_not_called()
        lite_mock.assert_called_once_with('request')
        assert result['model'] == 'lite'

    @patch('models.lite_model_client.LiteModelClient.infer')
    @patch('models.backup_model_client.BackupModelClient.infer')
    @patch('models.primary_model_client.PrimaryModelClient.infer')
    def test_primary_generic_exception_backup_allowed(self, primary_mock, backup_mock, lite_mock):
        """Test generic exception with backup allowed."""
        primary_mock.side_effect = Exception("generic error")
        backup_mock.return_value = {'model': 'backup'}

        config = Mock()
        config.tenants_force_lite = set()
        config.primary_endpoint = 'primary'
        config.backup_endpoint = 'backup'
        config.lite_endpoint = 'lite'
        config.enable_backup = True
        config.blacklist_backup = set()
        config.tenants_strict_sl = set()

        router = ModelRouter(config)
        result = router.infer('request', 'tenant_normal')

        primary_mock.assert_called_once_with('request')
        backup_mock.assert_called_once_with('request')
        lite_mock.assert_not_called()
        assert result['model'] == 'backup'

    @patch('models.lite_model_client.LiteModelClient.infer')
    @patch('models.backup_model_client.BackupModelClient.infer')
    @patch('models.primary_model_client.PrimaryModelClient.infer')
    def test_circuit_breaker_open_backup_allowed(self, primary_mock, backup_mock, lite_mock):
        """Test when circuit breaker is open and backup allowed."""
        backup_mock.return_value = {'model': 'backup'}

        config = Mock()
        config.tenants_force_lite = set()
        config.primary_endpoint = 'primary'
        config.backup_endpoint = 'backup'
        config.lite_endpoint = 'lite'
        config.enable_backup = True
        config.blacklist_backup = set()
        config.tenants_strict_sl = set()

        router = ModelRouter(config)
        # Open the breaker
        for _ in range(3):
            router.circuit_breaker.record_failure()

        result = router.infer('request', 'tenant_normal')

        primary_mock.assert_not_called()
        backup_mock.assert_called_once_with('request')
        lite_mock.assert_not_called()
        assert result['model'] == 'backup'

    @patch('models.lite_model_client.LiteModelClient.infer')
    @patch('models.backup_model_client.BackupModelClient.infer')
    @patch('models.primary_model_client.PrimaryModelClient.infer')
    def test_circuit_breaker_open_strict_sl(self, primary_mock, backup_mock, lite_mock):
        """Test when circuit breaker is open for strict SL tenant."""
        lite_mock.return_value = {'model': 'lite'}

        config = Mock()
        config.tenants_force_lite = set()
        config.primary_endpoint = 'primary'
        config.backup_endpoint = 'backup'
        config.lite_endpoint = 'lite'
        config.enable_backup = True
        config.blacklist_backup = set()
        config.tenants_strict_sl = {'tenant_strict'}

        router = ModelRouter(config)
        # Open the breaker
        for _ in range(3):
            router.circuit_breaker.record_failure()

        result = router.infer('request', 'tenant_strict')

        primary_mock.assert_not_called()
        backup_mock.assert_not_called()
        lite_mock.assert_called_once_with('request')
        assert result['model'] == 'lite'

    @patch('models.lite_model_client.LiteModelClient.infer')
    @patch('models.backup_model_client.BackupModelClient.infer')
    @patch('models.primary_model_client.PrimaryModelClient.infer')
    def test_primary_timeout_strict_sl_uses_backup_bug(self, primary_mock, backup_mock, lite_mock):
        """Test timeout for strict SL tenant - currently uses backup due to bug."""
        primary_mock.side_effect = TimeoutError
        backup_mock.return_value = {'model': 'backup'}

        config = Mock()
        config.tenants_force_lite = set()
        config.primary_endpoint = 'primary'
        config.backup_endpoint = 'backup'
        config.lite_endpoint = 'lite'
        config.enable_backup = True
        config.blacklist_backup = set()
        config.tenants_strict_sl = {'tenant_strict'}

        router = ModelRouter(config)
        result = router.infer('request', 'tenant_strict')

        primary_mock.assert_called_once_with('request')
        backup_mock.assert_called_once_with('request')
        lite_mock.assert_not_called()
        assert result['model'] == 'backup'  # This is the bug - should be lite for strict SL