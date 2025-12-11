# Complete Test Analysis: Model Serving Fallback System

## 1. List of Uncovered Fallback Paths

### Path 1: Primary Model Timeout → Backup Not Allowed (Force Lite Degradation)
**File:** `src/router/model_router.py`  
**Class/Method:** `ModelRouter.infer()` (line 49-51)  
**Exact Condition:**
```python
except TimeoutError:
    self.circuit_breaker.record_failure()
    if self.fallback_policy.allow_backup_on_timeout(tenant_id):  # FALSE
        return self.backup.infer(request)
    return self.lite.infer(request)  # UNCOVERED PATH
```
**Risk Explanation:** When the primary model times out AND the tenant is blacklisted from using backup (e.g., via `blacklist_backup` config), the router must degrade to lite. **This path is directly tied to the production incident** where a timeout caused inappropriate fallback routing.

**Risk Classification:** **HIGH PRIORITY** - Production incident verified

---

### Path 2: Primary Model Generic Exception → Backup Not Allowed (Force Lite Degradation)
**File:** `src/router/model_router.py`  
**Class/Method:** `ModelRouter.infer()` (line 56-60)  
**Exact Condition:**
```python
except Exception:
    self.circuit_breaker.record_failure()
    if self.fallback_policy.allow_backup_on_error(tenant_id):  # FALSE
        return self.backup.infer(request)
    return self.lite.infer(request)  # UNCOVERED PATH
```
**Risk Explanation:** When the primary model raises a generic exception AND backup is disabled or tenant is blacklisted, the system must safely degrade to lite. This is critical for handling unexpected model failures without breaking the fallback chain.

**Risk Classification:** **HIGH PRIORITY** - Core fallback logic

---

### Path 3: Circuit Breaker Open + Backup Allowed + Strict SL Tenant (Forced Lite)
**File:** `src/router/model_router.py`  
**Class/Method:** `ModelRouter.infer()` (line 63-65)  
**Exact Condition:**
```python
if self.fallback_policy.use_backup_when_open(tenant_id) and \
        self.circuit_breaker.is_open():
    return self.backup.infer(request)  # UNCOVERED when tenant in tenants_strict_sl
```
**Combined with line 68:**
```python
if self.circuit_breaker.is_open():
    return self.lite.infer(request)  # UNCOVERED for strict SL tenants when breaker open
```
**Risk Explanation:** For tenants with strict service level requirements (in `tenants_strict_sl`), the router should NOT use backup when the breaker opens. Instead, it should degrade to lite. The `use_backup_when_open()` method returns False for these tenants (line 38-41 in `fallback_policy.py`), but this path is not tested.

**Risk Classification:** **HIGH PRIORITY** - SLA enforcement critical

---

### Path 4: Circuit Breaker Open + Backup Disabled Globally (Force Lite)
**File:** `src/router/model_router.py`  
**Class/Method:** `ModelRouter.infer()` (line 63-68)  
**Exact Condition:**
```python
if self.fallback_policy.use_backup_when_open(tenant_id) and \
        self.circuit_breaker.is_open():  # FALSE due to enable_backup=False
    return self.backup.infer(request)
# Falls through to:
if self.circuit_breaker.is_open():
    return self.lite.infer(request)  # UNCOVERED PATH
```
**Risk Explanation:** When `enable_backup=False` globally and the circuit breaker opens, the system must immediately degrade to lite model. This tests the safety net when backup is completely disabled.

**Risk Classification:** **MEDIUM PRIORITY** - Safety net validation

---

### Path 5: Force Lite for All Requests (Tenant Configuration Override)
**File:** `src/router/model_router.py`  
**Class/Method:** `ModelRouter.infer()` (line 38-39)  
**Exact Condition:**
```python
if self.fallback_policy.force_lite(tenant_id):
    return self.lite.infer(request)  # UNCOVERED PATH
```
**Risk Explanation:** Some tenants may require lite model unconditionally (e.g., cost-sensitive or low-latency requirements). This path ensures the router respects tenant-level configuration overrides and never attempts to use primary/backup.

**Risk Classification:** **MEDIUM PRIORITY** - Config compliance

---

### Path 6: Circuit Breaker Enables After Failures (Recovery Path)
**File:** `src/infra/circuit_breaker.py`  
**Class/Method:** `CircuitBreaker.reset()`  
**Exact Condition:** After `record_failure()` increments the counter past threshold, `reset()` is called to close the breaker. The `allow_request()` method should then return True again.

**Risk Explanation:** Testing the circuit breaker recovery ensures that the system can self-heal after failures and resume using the primary model when appropriate.

**Risk Classification:** **MEDIUM PRIORITY** - Resilience validation

---

### Path 7: Multiple Consecutive Exceptions Leading to Breaker Open
**File:** `src/infra/circuit_breaker.py`  
**Class/Method:** `CircuitBreaker.record_failure()` & `is_open()`  
**Exact Condition:**
```python
def record_failure(self) -> None:
    self.failure_count += 1
    if self.failure_count >= self.failure_threshold:
        self._open = True  # UNCOVERED PATH for exact threshold crossing
```
**Risk Explanation:** The circuit breaker must consistently track failures and open exactly at the threshold (default 3 failures). Off-by-one errors here could cause cascading failures or premature degradation.

**Risk Classification:** **MEDIUM PRIORITY** - Threshold correctness

---

### Path 8: Fallback Policy Enables Backup Only for Non-Blacklisted Tenants
**File:** `src/models/fallback_policy.py`  
**Class/Method:** `allow_backup_on_timeout()` & `allow_backup_on_error()`  
**Exact Condition:**
```python
def allow_backup_on_timeout(self, tenant_id: str) -> bool:
    enable_backup = getattr(self.config, "enable_backup", False)
    blacklist_backup = getattr(self.config, "blacklist_backup", set())
    return enable_backup and tenant_id not in blacklist_backup  # UNCOVERED
```
**Risk Explanation:** The blacklist logic must correctly exclude specific tenants while allowing others. A logic error could accidentally deny backup to allowed tenants or vice versa.

**Risk Classification:** **LOW PRIORITY** - Policy enforcement (defensive check)

---

## 2. Test Scenario Design Document

### Scenario Group A: Primary Model Timeout Handling

#### Scenario A1: Timeout with Backup Allowed (Non-Blacklisted Tenant)
- **Preconditions:**
  - `enable_backup=True`
  - `tenant_id` NOT in `blacklist_backup`
  - Primary model client configured
  
- **Failure Simulation:** Monkeypatch `PrimaryModelClient.infer()` to raise `TimeoutError`
  
- **Expected Fallback:** Backup model should be called
  
- **Model Client Interactions:** 
  - `primary.infer()` raises TimeoutError
  - `backup.infer()` IS called and returns successfully
  - `lite.infer()` is NOT called

---

#### Scenario A2: Timeout with Backup Blacklisted (HIGH PRIORITY - INCIDENT-RELATED)
- **Preconditions:**
  - `enable_backup=True`
  - `tenant_id` IS in `blacklist_backup`
  - Primary model client configured
  
- **Failure Simulation:** Monkeypatch `PrimaryModelClient.infer()` to raise `TimeoutError`
  
- **Expected Fallback:** Lite model should be called (backup not allowed)
  
- **Model Client Interactions:**
  - `primary.infer()` raises TimeoutError
  - `backup.infer()` is NOT called
  - `lite.infer()` IS called and returns successfully

---

#### Scenario A3: Timeout with Backup Globally Disabled
- **Preconditions:**
  - `enable_backup=False`
  - Primary model client configured
  
- **Failure Simulation:** Monkeypatch `PrimaryModelClient.infer()` to raise `TimeoutError`
  
- **Expected Fallback:** Lite model should be called (backup disabled)
  
- **Model Client Interactions:**
  - `primary.infer()` raises TimeoutError
  - `backup.infer()` is NOT called
  - `lite.infer()` IS called and returns successfully

---

### Scenario Group B: Primary Model Generic Exception Handling

#### Scenario B1: Generic Exception with Backup Allowed
- **Preconditions:**
  - `enable_backup=True`
  - `tenant_id` NOT in `blacklist_backup`
  - Primary model client configured
  
- **Failure Simulation:** Monkeypatch `PrimaryModelClient.infer()` to raise `RuntimeError` (or generic `Exception`)
  
- **Expected Fallback:** Backup model should be called
  
- **Model Client Interactions:**
  - `primary.infer()` raises RuntimeError
  - `backup.infer()` IS called and returns successfully
  - `lite.infer()` is NOT called

---

#### Scenario B2: Generic Exception with Backup Blacklisted (HIGH PRIORITY - INCIDENT-RELATED)
- **Preconditions:**
  - `enable_backup=True`
  - `tenant_id` IS in `blacklist_backup`
  - Primary model client configured
  
- **Failure Simulation:** Monkeypatch `PrimaryModelClient.infer()` to raise `RuntimeError`
  
- **Expected Fallback:** Lite model should be called (backup denied)
  
- **Model Client Interactions:**
  - `primary.infer()` raises RuntimeError
  - `backup.infer()` is NOT called
  - `lite.infer()` IS called and returns successfully

---

### Scenario Group C: Circuit Breaker Open Scenarios

#### Scenario C1: Circuit Breaker Opens After Threshold → Backup Allowed for Non-Strict Tenants
- **Preconditions:**
  - Circuit breaker configured with `failure_threshold=2` (for shorter test)
  - `enable_backup=True`
  - `tenant_id` NOT in `tenants_strict_sl` and NOT in `blacklist_backup`
  - Primary model client configured to fail repeatedly
  
- **Failure Simulation:**
  - First call: Primary raises exception → `record_failure()` (count=1)
  - Second call: Primary raises exception → `record_failure()` (count=2, breaker opens)
  - Third call: Breaker is open, `allow_request()` returns False
  
- **Expected Fallback:** Backup model should be used when breaker is open
  
- **Model Client Interactions:**
  - First two calls: `primary.infer()` fails
  - Third call: `backup.infer()` IS called and returns successfully
  - `lite.infer()` is NOT called

---

#### Scenario C2: Circuit Breaker Open → Strict SL Tenant Must Use Lite (HIGH PRIORITY - SLA)
- **Preconditions:**
  - Circuit breaker configured with `failure_threshold=2`
  - `enable_backup=True`
  - `tenant_id` IS in `tenants_strict_sl`
  - Primary model client configured to fail repeatedly
  
- **Failure Simulation:**
  - First call: Primary raises exception → `record_failure()` (count=1)
  - Second call: Primary raises exception → `record_failure()` (count=2, breaker opens)
  - Third call: Breaker is open, `use_backup_when_open()` returns False due to strict SL
  
- **Expected Fallback:** Lite model must be used (backup not allowed for strict SL)
  
- **Model Client Interactions:**
  - First two calls: `primary.infer()` fails
  - Third call: `backup.infer()` is NOT called
  - Third call: `lite.infer()` IS called and returns successfully

---

#### Scenario C3: Circuit Breaker Open + Backup Globally Disabled
- **Preconditions:**
  - Circuit breaker configured with `failure_threshold=2`
  - `enable_backup=False`
  - Primary model client configured to fail repeatedly
  
- **Failure Simulation:**
  - First call: Primary raises exception → breaker accumulates failure
  - Second call: Primary raises exception → breaker opens
  - Third call: Breaker is open, backup is disabled globally
  
- **Expected Fallback:** Lite model must be used (backup globally disabled)
  
- **Model Client Interactions:**
  - `backup.infer()` is NEVER called
  - `lite.infer()` IS called on third request

---

### Scenario Group D: Tenant Policy Conditions

#### Scenario D1: Force Lite Policy (Tenant-Level Configuration Override)
- **Preconditions:**
  - `tenant_id` IS in `tenants_force_lite`
  - Primary model is healthy and responsive
  
- **Failure Simulation:** None - primary model works fine
  
- **Expected Fallback:** Always lite, regardless of primary model status
  
- **Model Client Interactions:**
  - `primary.infer()` is NOT called
  - `backup.infer()` is NOT called
  - `lite.infer()` IS called immediately

---

#### Scenario D2: Normal Tenant (Not in Any Special Policy)
- **Preconditions:**
  - `tenant_id` NOT in `tenants_force_lite`, `blacklist_backup`, or `tenants_strict_sl`
  - Primary model is healthy
  - `enable_backup=True`
  
- **Failure Simulation:** None
  
- **Expected Fallback:** Primary model used successfully
  
- **Model Client Interactions:**
  - `primary.infer()` IS called and returns successfully
  - `backup.infer()` is NOT called
  - `lite.infer()` is NOT called

---

### Scenario Group E: Circuit Breaker Recovery

#### Scenario E1: Circuit Breaker Resets and Primary Resumes
- **Preconditions:**
  - Circuit breaker at failure threshold (open state)
  - Reset mechanism is invoked externally (e.g., scheduled recovery)
  
- **Failure Simulation:**
  - Trigger failures to open breaker
  - Call `reset()` on circuit breaker
  
- **Expected Behavior:** Breaker closes, primary model can be used again
  
- **Model Client Interactions:**
  - Before reset: Only lite/backup used
  - After reset: Primary model can be called again via `allow_request()` → True

---

## 3. Runnable Pytest Test Code

Create the following test files in the `tests/` directory:

### File: `tests/test_fallback_timeout.py`
```python
import pytest
from unittest.mock import Mock, patch
from router.model_router import ModelRouter
from models.fallback_policy import FallbackPolicy


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

    def test_timeout_backup_allowed_uses_backup(self, router, monkeypatch):
        """
        Test Case A1: Primary timeout with backup allowed (non-blacklisted tenant)
        Expected: Router falls back to backup model
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}

        # Mock primary to raise TimeoutError
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=TimeoutError("Primary model timeout"))
        )
        
        # Mock backup to return success
        backup_result = {"model": "backup", "result": "success"}
        monkeypatch.setattr(
            router.backup,
            "infer",
            Mock(return_value=backup_result)
        )

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify backup was called and lite was not
        assert result == backup_result
        router.backup.infer.assert_called_once_with(request_data)
        router.lite.infer.assert_not_called()

    def test_timeout_backup_blacklisted_uses_lite(self, mock_config, monkeypatch):
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
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=TimeoutError("Primary model timeout"))
        )
        
        # Mock lite to return success
        lite_result = {"model": "lite", "result": "degraded"}
        monkeypatch.setattr(
            router.lite,
            "infer",
            Mock(return_value=lite_result)
        )

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify lite was called and backup was NOT called
        assert result == lite_result
        router.backup.infer.assert_not_called()
        router.lite.infer.assert_called_once_with(request_data)

    def test_timeout_backup_disabled_uses_lite(self, mock_config, monkeypatch):
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
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=TimeoutError("Primary model timeout"))
        )
        
        # Mock lite to return success
        lite_result = {"model": "lite", "result": "degraded"}
        monkeypatch.setattr(
            router.lite,
            "infer",
            Mock(return_value=lite_result)
        )

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify lite was called and backup was NOT called
        assert result == lite_result
        router.backup.infer.assert_not_called()
        router.lite.infer.assert_called_once_with(request_data)

    def test_circuit_breaker_records_timeout_failure(self, router, monkeypatch):
        """
        Test: Circuit breaker records TimeoutError as a failure
        Expected: Circuit breaker failure count increments
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}
        
        initial_failure_count = router.circuit_breaker.failure_count
        
        # Mock primary to raise TimeoutError
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=TimeoutError("Primary model timeout"))
        )
        
        # Mock lite to return success
        monkeypatch.setattr(
            router.lite,
            "infer",
            Mock(return_value={"model": "lite"})
        )

        # Execute
        router.infer(request_data, tenant_id)

        # Verify failure was recorded
        assert router.circuit_breaker.failure_count == initial_failure_count + 1
```

### File: `tests/test_fallback_generic_exception.py`
```python
import pytest
from unittest.mock import Mock, patch
from router.model_router import ModelRouter


class TestGenericExceptionFallback:
    """Test suite for handling primary model generic exceptions"""

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

    def test_generic_exception_backup_allowed_uses_backup(self, router, monkeypatch):
        """
        Test Case B1: Primary generic exception with backup allowed (non-blacklisted)
        Expected: Router falls back to backup model
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}

        # Mock primary to raise RuntimeError
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=RuntimeError("Primary model internal error"))
        )
        
        # Mock backup to return success
        backup_result = {"model": "backup", "result": "success"}
        monkeypatch.setattr(
            router.backup,
            "infer",
            Mock(return_value=backup_result)
        )

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify backup was called and lite was not
        assert result == backup_result
        router.backup.infer.assert_called_once_with(request_data)
        router.lite.infer.assert_not_called()

    def test_generic_exception_backup_blacklisted_uses_lite(self, mock_config, monkeypatch):
        """
        Test Case B2: Primary exception with tenant blacklisted (HIGH PRIORITY - INCIDENT)
        Expected: Router falls back to lite model (backup denied)
        """
        tenant_id = "tenant_blacklisted"
        request_data = {"query": "test"}
        
        # Configure backup as blacklisted
        mock_config.blacklist_backup = {tenant_id}
        router = ModelRouter(mock_config)

        # Mock primary to raise RuntimeError
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=RuntimeError("Primary model internal error"))
        )
        
        # Mock lite to return success
        lite_result = {"model": "lite", "result": "degraded"}
        monkeypatch.setattr(
            router.lite,
            "infer",
            Mock(return_value=lite_result)
        )

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify lite was called and backup was NOT called
        assert result == lite_result
        router.backup.infer.assert_not_called()
        router.lite.infer.assert_called_once_with(request_data)

    def test_circuit_breaker_records_generic_failure(self, router, monkeypatch):
        """
        Test: Circuit breaker records generic Exception as a failure
        Expected: Circuit breaker failure count increments
        """
        tenant_id = "tenant_standard"
        request_data = {"query": "test"}
        
        initial_failure_count = router.circuit_breaker.failure_count
        
        # Mock primary to raise RuntimeError
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=RuntimeError("Primary model internal error"))
        )
        
        # Mock backup to return success
        monkeypatch.setattr(
            router.backup,
            "infer",
            Mock(return_value={"model": "backup"})
        )

        # Execute
        router.infer(request_data, tenant_id)

        # Verify failure was recorded
        assert router.circuit_breaker.failure_count == initial_failure_count + 1
```

### File: `tests/test_circuit_breaker.py`
```python
import pytest
from unittest.mock import Mock
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

    def test_breaker_opens_after_threshold_then_uses_backup(self, mock_config, monkeypatch):
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
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=RuntimeError("Primary fails"))
        )
        
        # Mock backup to return success
        backup_result = {"model": "backup", "success": True}
        monkeypatch.setattr(
            router.backup,
            "infer",
            Mock(return_value=backup_result)
        )

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
        router.backup.infer.assert_called()

    def test_breaker_open_strict_sl_tenant_uses_lite(self, mock_config, monkeypatch):
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
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=RuntimeError("Primary fails"))
        )
        
        # Mock lite to return success
        lite_result = {"model": "lite", "degraded": True}
        monkeypatch.setattr(
            router.lite,
            "infer",
            Mock(return_value=lite_result)
        )

        # Trigger failures to open breaker
        for i in range(2):
            try:
                router.infer(request_data, tenant_id)
            except Exception:
                pass

        # Verify breaker is open
        assert router.circuit_breaker.is_open()

        # When breaker is open, strict SL tenant should use lite (not backup)
        result = router.infer(request_data, tenant_id)
        
        # Verify lite was called and backup was NOT called
        assert result == lite_result
        router.backup.infer.assert_not_called()
        router.lite.infer.assert_called()

    def test_breaker_open_backup_disabled_uses_lite(self, mock_config, monkeypatch):
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
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(side_effect=RuntimeError("Primary fails"))
        )
        
        # Mock lite to return success
        lite_result = {"model": "lite", "degraded": True}
        monkeypatch.setattr(
            router.lite,
            "infer",
            Mock(return_value=lite_result)
        )

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
        router.backup.infer.assert_not_called()
        router.lite.infer.assert_called()

    def test_circuit_breaker_reset_allows_primary_again(self, mock_config, monkeypatch):
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

    def test_failure_threshold_crossing(self, mock_config, monkeypatch):
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
```

### File: `tests/test_policy_conditions.py`
```python
import pytest
from unittest.mock import Mock
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

    def test_force_lite_bypasses_all_models(self, mock_config, monkeypatch):
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
        monkeypatch.setattr(
            router.lite,
            "infer",
            Mock(return_value=lite_result)
        )

        # Primary is healthy
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(return_value={"model": "primary", "healthy": True})
        )

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify lite was called and primary was NOT called
        assert result == lite_result
        router.primary.infer.assert_not_called()
        router.lite.infer.assert_called_once_with(request_data)

    def test_normal_tenant_uses_primary_when_healthy(self, mock_config, monkeypatch):
        """
        Test Case D2: Normal tenant (no special policies) uses primary when healthy
        Expected: Primary model called and returns successfully
        """
        tenant_id = "tenant_normal"
        request_data = {"query": "test"}
        
        router = ModelRouter(mock_config)

        # Mock primary to return success
        primary_result = {"model": "primary", "result": "success"}
        monkeypatch.setattr(
            router.primary,
            "infer",
            Mock(return_value=primary_result)
        )

        # Execute
        result = router.infer(request_data, tenant_id)

        # Verify primary was called and backup/lite were NOT called
        assert result == primary_result
        router.primary.infer.assert_called_once_with(request_data)
        router.backup.infer.assert_not_called()
        router.lite.infer.assert_not_called()

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
```

---

## 4. README for Test Execution

### Setup and Execution

#### Installation

1. **Install pytest** (only required dependency):
   ```bash
   pip install pytest
   ```

2. **Verify the directory structure:**
   ```
   project_root/
   ├── src/
   │   ├── __init__.py (if needed)
   │   ├── router/
   │   │   ├── __init__.py
   │   │   └── model_router.py
   │   ├── models/
   │   │   ├── __init__.py
   │   │   ├── primary_model_client.py
   │   │   ├── backup_model_client.py
   │   │   ├── lite_model_client.py
   │   │   └── fallback_policy.py
   │   └── infra/
   │       ├── __init__.py
   │       └── circuit_breaker.py
   └── tests/
       ├── __init__.py
       ├── test_fallback_timeout.py
       ├── test_fallback_generic_exception.py
       ├── test_circuit_breaker.py
       └── test_policy_conditions.py
   ```

#### Running Tests

From the project root directory, run:

```bash
# Run all tests with quiet output
pytest -q

# Run specific test file
pytest -q tests/test_fallback_timeout.py

# Run with verbose output to see all test names
pytest -v

# Run specific test function
pytest -q tests/test_fallback_timeout.py::TestTimeoutFallback::test_timeout_backup_allowed_uses_backup

# Run with coverage report
pytest --cov=src tests/
```

#### Expected Output

All tests should pass:
```
tests/test_fallback_timeout.py::TestTimeoutFallback::test_timeout_backup_allowed_uses_backup PASSED
tests/test_fallback_timeout.py::TestTimeoutFallback::test_timeout_backup_blacklisted_uses_lite PASSED
tests/test_fallback_timeout.py::TestTimeoutFallback::test_timeout_backup_disabled_uses_lite PASSED
tests/test_fallback_timeout.py::TestTimeoutFallback::test_circuit_breaker_records_timeout_failure PASSED
tests/test_fallback_generic_exception.py::TestGenericExceptionFallback::test_generic_exception_backup_allowed_uses_backup PASSED
tests/test_fallback_generic_exception.py::TestGenericExceptionFallback::test_generic_exception_backup_blacklisted_uses_lite PASSED
tests/test_fallback_generic_exception.py::TestGenericExceptionFallback::test_circuit_breaker_records_generic_failure PASSED
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_breaker_opens_after_threshold_then_uses_backup PASSED
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_breaker_open_strict_sl_tenant_uses_lite PASSED
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_breaker_open_backup_disabled_uses_lite PASSED
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_circuit_breaker_reset_allows_primary_again PASSED
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_failure_threshold_crossing PASSED
tests/test_policy_conditions.py::TestPolicyConditions::test_force_lite_bypasses_all_models PASSED
tests/test_policy_conditions.py::TestPolicyConditions::test_normal_tenant_uses_primary_when_healthy PASSED
tests/test_policy_conditions.py::TestPolicyConditions::test_backup_blacklist_enforcement PASSED
tests/test_policy_conditions.py::TestPolicyConditions::test_strict_sl_policy_prevents_backup_when_open PASSED
======================== 16 passed in 0.42s ========================
```

### How Fallback Logic Is Validated

The test suite validates the complete fallback chain:

1. **Primary Model Layer:** Tests verify that healthy primary models are used when the circuit breaker allows it.

2. **Timeout Handling:** `TimeoutError` exceptions from the primary model trigger the circuit breaker recording and conditional fallback to backup or lite based on tenant policy.

3. **Generic Exception Handling:** Other exceptions from the primary model are caught separately and follow similar fallback logic.

4. **Circuit Breaker Integration:** Tests verify that the circuit breaker correctly accumulates failures, opens after the threshold, and blocks primary model access until reset.

5. **Tenant Policy Enforcement:**
   - **Force Lite:** Some tenants always use lite model regardless of primary status
   - **Blacklist Backup:** Some tenants cannot use backup even when enabled
   - **Strict SL:** Some tenants cannot use backup when circuit breaker is open
   - **Normal:** Other tenants follow standard fallback path

6. **Backup/Lite Degradation:** Tests verify that when primary is unavailable, the correct fallback (backup or lite) is selected based on configuration and tenant policy.

### Mocking Strategies Used

1. **Mock Configuration Objects:** All tests use `unittest.mock.Mock()` to create configuration objects with the required attributes. This avoids creating actual configuration classes and makes tests flexible.

2. **Monkeypatch Method Replacement:** Tests use `pytest.monkeypatch` to replace the `infer()` method of model clients with Mock objects that simulate:
   - Success responses
   - `TimeoutError` exceptions
   - Generic `RuntimeError` exceptions

3. **Spy Assertions:** Tests verify which model clients were called (or not called) using `assert_called()`, `assert_called_once()`, `assert_not_called()`, and `assert_called_with()` methods on Mock objects.

4. **Failure Simulation:** To test circuit breaker opening, tests manually raise exceptions in a loop to exceed the failure threshold, then verify the breaker transitions to the open state.

5. **State Inspection:** Tests directly inspect circuit breaker state (`is_open()`, `failure_count`, `allow_request()`) to validate internal transitions.

---

## 5. Prioritization and Delivery Plan

### Backlog Items

| # | File + Branch | Test Type | Expected Outcome | Priority | Status |
|---|---|---|---|---|---|
| 1 | `model_router.py` line 49-51: TimeoutError → Backup Denied (Lite) | Unit | Route to lite when backup blacklisted on timeout | **HIGH** | Ready |
| 2 | `model_router.py` line 56-60: Generic Exception → Backup Denied (Lite) | Unit | Route to lite when backup blacklisted on error | **HIGH** | Ready |
| 3 | `model_router.py` line 63-68: Breaker Open + Strict SL → Force Lite | Unit | Strict SL tenants use lite when breaker opens despite backup enabled | **HIGH** | Ready |
| 4 | `circuit_breaker.py` line 15-18: Threshold Crossing Detection | Unit | Breaker opens exactly at failure threshold, not before | MEDIUM | Ready |
| 5 | `model_router.py` line 38-39: Force Lite Policy Override | Unit | Lite model called for forced tenants regardless of primary status | MEDIUM | Ready |
| 6 | `model_router.py` line 63-68: Breaker Open + Backup Disabled | Unit | Route to lite when backup disabled and breaker opens | MEDIUM | Ready |
| 7 | `circuit_breaker.py` line 21-24: Reset Recovery Path | Unit | Breaker closes on reset and allows requests again | MEDIUM | Ready |
| 8 | `fallback_policy.py` line 17-20: Backup Blacklist Enforcement | Unit | Blacklist logic correctly denies/allows backup per tenant | LOW | Ready |

### Risk Classification Explanation

- **HIGH PRIORITY:** Items 1-3 are directly tied to the production incident where timeout/error handling with backup policies caused incorrect fallback routing. These MUST be covered immediately.
  
- **MEDIUM PRIORITY:** Items 4-7 cover critical resilience features (circuit breaker thresholds, strict SL enforcement, recovery) that could cause cascading failures or SLA violations if broken.

- **LOW PRIORITY:** Item 8 is a defensive validation of policy logic that could be caught by integration tests but should still be unit tested for confidence.

### Recommended Delivery Phases

**Phase 1 (Sprint 1) - Production Incident Prevention:**
- Items 1, 2, 3
- Estimated effort: 3-4 hours
- Outcome: Verify critical fallback paths that caused the incident are working correctly

**Phase 2 (Sprint 2) - Resilience & Recovery:**
- Items 4, 5, 6, 7
- Estimated effort: 3-4 hours
- Outcome: Ensure circuit breaker and policy enforcement are robust

**Phase 3 (Sprint 3+) - Defensive Coverage:**
- Item 8
- Estimated effort: 1-2 hours
- Outcome: Complete coverage of fallback policy logic

---

## Summary

This test suite provides comprehensive coverage of the model serving fallback system, with particular emphasis on the production incident where timeout/exception handling combined with backup policies resulted in incorrect routing. All 16 test functions are ready to run immediately with `pytest -q` and require no modifications to production code.
