# Quick Reference: Fallback Logic Test Suite

## Run Tests Immediately

```powershell
cd 'C:\Bug_Bash\25_12_11\v-coralhuang_25_12_11_case2'
$env:PYTHONPATH='src'
python -m pytest tests/ -q
```

**Expected Output:** `16 passed in 0.08s`

---

## What Was Delivered

### 📋 Documentation
1. **TEST_ANALYSIS.md** - Complete analysis with 5 sections:
   - List of 8 uncovered fallback paths
   - Test scenario design document
   - Runnable pytest code (provided in-line)
   - README for test execution
   - Delivery plan with backlog items

2. **DELIVERY_SUMMARY.md** - Executive summary and validation

### 🧪 Test Files (16 Tests Total)

| File | Tests | Coverage |
|------|-------|----------|
| `test_fallback_timeout.py` | 4 | TimeoutError → backup/lite routing |
| `test_fallback_generic_exception.py` | 3 | Exception → backup/lite routing |
| `test_circuit_breaker.py` | 5 | Breaker open scenarios & recovery |
| `test_policy_conditions.py` | 4 | Tenant policy enforcement |

### 🔥 Production Incident Coverage

**3 Critical Tests Directly Address the Production Incident:**

1. `test_timeout_backup_blacklisted_uses_lite` 
   - **What:** Timeout with blacklisted tenant
   - **Why:** Core incident scenario

2. `test_generic_exception_backup_blacklisted_uses_lite`
   - **What:** Generic exception with blacklisted tenant  
   - **Why:** Prevents similar incidents with different errors

3. `test_breaker_open_strict_sl_tenant_uses_lite`
   - **What:** Breaker open, strict SL tenant must use lite
   - **Why:** Prevents SLA violations during degradation

---

## Uncovered Paths Tested

| Path ID | Condition | Test Name | Risk |
|---------|-----------|-----------|------|
| A1 | Timeout + Backup Allowed | `test_timeout_backup_allowed_uses_backup` | MEDIUM |
| **A2** | **Timeout + Backup Blacklisted** | **test_timeout_backup_blacklisted_uses_lite** | **HIGH** |
| A3 | Timeout + Backup Disabled | `test_timeout_backup_disabled_uses_lite` | MEDIUM |
| B1 | Exception + Backup Allowed | `test_generic_exception_backup_allowed_uses_backup` | MEDIUM |
| **B2** | **Exception + Backup Blacklisted** | **test_generic_exception_backup_blacklisted_uses_lite** | **HIGH** |
| **C2** | **Breaker Open + Strict SL Tenant** | **test_breaker_open_strict_sl_tenant_uses_lite** | **HIGH** |
| C3 | Breaker Open + Backup Disabled | `test_breaker_open_backup_disabled_uses_lite` | MEDIUM |
| D1 | Force Lite Policy | `test_force_lite_bypasses_all_models` | MEDIUM |

---

## Key Test Patterns

### Timeout Testing
```python
# Mock primary to raise TimeoutError
primary_mock = MagicMock(side_effect=TimeoutError("..."))
router.primary.infer = primary_mock

# Execute and verify fallback choice
result = router.infer(request_data, tenant_id)
assert result == expected_fallback_result
```

### Circuit Breaker Testing
```python
# Set low threshold for test
router.circuit_breaker.failure_threshold = 2

# Trigger failures
for i in range(2):
    try:
        router.infer(request_data, tenant_id)
    except:
        pass

# Verify breaker is open
assert router.circuit_breaker.is_open()

# Verify correct fallback when breaker is open
result = router.infer(request_data, tenant_id)
```

### Policy Testing
```python
# Configure policy
mock_config.tenants_strict_sl = {tenant_id}
router = ModelRouter(mock_config)

# Verify policy is enforced
policy = router.fallback_policy
assert not policy.use_backup_when_open(tenant_id)
```

---

## Installation

```bash
pip install pytest
```

## Run Variants

| Command | Output |
|---------|--------|
| `pytest tests/ -q` | Minimal (passed/failed summary) |
| `pytest tests/ -v` | Verbose (each test name) |
| `pytest tests/test_fallback_timeout.py` | Specific file |
| `pytest tests/ -k "timeout"` | Filter by keyword |
| `pytest --cov=src tests/` | Coverage report |

---

## File Structure

```
src/
├── router/
│   └── model_router.py          (Routes requests to models)
├── models/
│   ├── fallback_policy.py       (Tenant policy decisions)
│   ├── primary_model_client.py
│   ├── backup_model_client.py
│   └── lite_model_client.py
└── infra/
    └── circuit_breaker.py       (Failure tracking & open/close)

tests/
├── test_fallback_timeout.py         (Timeout scenarios)
├── test_fallback_generic_exception.py (Exception scenarios)
├── test_circuit_breaker.py          (Breaker logic)
└── test_policy_conditions.py        (Policy enforcement)
```

---

## Test Results Summary

```
============================= test session starts ==============================
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_breaker_opens_after_threshold_then_uses_backup PASSED [ 6%]
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_breaker_open_strict_sl_tenant_uses_lite PASSED [ 12%]
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_breaker_open_backup_disabled_uses_lite PASSED [ 18%]
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_circuit_breaker_reset_allows_primary_again PASSED [ 25%]
tests/test_circuit_breaker.py::TestCircuitBreakerFallback::test_failure_threshold_crossing PASSED [ 31%]
tests/test_fallback_generic_exception.py::TestGenericExceptionFallback::test_generic_exception_backup_allowed_uses_backup PASSED [ 37%]
tests/test_fallback_generic_exception.py::TestGenericExceptionFallback::test_generic_exception_backup_blacklisted_uses_lite PASSED [ 43%]
tests/test_fallback_generic_exception.py::TestGenericExceptionFallback::test_circuit_breaker_records_generic_failure PASSED [ 50%]
tests/test_fallback_timeout.py::TestTimeoutFallback::test_timeout_backup_allowed_uses_backup PASSED [ 56%]
tests/test_fallback_timeout.py::TestTimeoutFallback::test_timeout_backup_blacklisted_uses_lite PASSED [ 62%]
tests/test_fallback_timeout.py::TestTimeoutFallback::test_timeout_backup_disabled_uses_lite PASSED [ 68%]
tests/test_fallback_timeout.py::TestTimeoutFallback::test_circuit_breaker_records_timeout_failure PASSED [ 75%]
tests/test_policy_conditions.py::TestPolicyConditions::test_force_lite_bypasses_all_models PASSED [ 81%]
tests/test_policy_conditions.py::TestPolicyConditions::test_normal_tenant_uses_primary_when_healthy PASSED [ 87%]
tests/test_policy_conditions.py::TestPolicyConditions::test_backup_blacklist_enforcement PASSED [ 93%]
tests/test_policy_conditions.py::TestPolicyConditions::test_strict_sl_policy_prevents_backup_when_open PASSED [100%]

============================== 16 passed in 0.18s ==============================
```

---

## Contact & Support

- **Analysis Document:** TEST_ANALYSIS.md
- **Summary:** DELIVERY_SUMMARY.md
- **Test Files:** tests/ directory
- **Production Code:** src/ directory

All tests are fully documented with:
- Clear test names describing the scenario
- Detailed docstrings explaining purpose
- Inline comments on mock setup
- Explicit assertions for expected behavior
