# Tests README

How to run tests
-----------------

Install pytest (use venv if needed):

```bash
python -m pip install pytest
```

Run tests from the project root:

```bash
pytest -q
```

Repo layout
-----------

The repository is expected to have the following layout (root relative):

- src/ (production Python code)
- tests/ (pytest test files)

The test runner adds `src` to PYTHONPATH so imports like `from router.model_router import ModelRouter` work.

Notes on fallback validation
---------------------------
- Tests simulate primary model failures (TimeoutError and generic Exception) by monkeypatching the `PrimaryModelClient.infer` method.
- Tests verify which model client handled the request by monkeypatching `infer` on the backup and lite clients and recording calls.
- Circuit breaker open state can be induced by setting `router.circuit_breaker._open = True` in tests or by simulating repeated failures.

Mocking strategies used
----------------------
- Use `monkeypatch.setattr` to modify `PrimaryModelClient.infer`, `BackupModelClient.infer`, and `LiteModelClient.infer`.
- Avoid modifying production code; tests only change behavior at runtime through monkeypatching.

Test coverage should include:
- Force-lite routing
- Primary success path
- Primary timeout -> backup vs lite based on blacklist
- Primary generic exception -> backup vs lite based on blacklist
- Circuit breaker open state -> backup vs lite
- Replacement behavior for strict SL tenants (tenant_strict) where strict SL currently only affects the open breaker path.
